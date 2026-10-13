"""Shared plumbing for every Profiles builder.

What lives here, and why it is shared rather than copied into each builder:

  * Where the data lake is (GDA_DATA_ROOT, via GDA's own gda_paths helper).
  * The "profiles last updated" date: the newest instant a builder reads,
    taken from GDA's standard data-currency rule and floored to UTC midnight so
    two runs on the same day give the same bytes. Every row carries it as
    last_updated_utc.
  * The field spec (<Family>/fields.json): the definition of every column a
    family's parquet may hold. Loading it checks the spec itself is well formed.
  * The spec gate: before ANY parquet is written, the frame is checked against
    its spec. Any mismatch raises and nothing is written (fail loud).
  * Atomic parquet writes (temp file, then replace), so a crash never leaves a
    half-written profile file behind.
  * FIELDS.md: a human-readable table rendered from fields.json.

Rules that apply to every builder (see the repo README):
  * Nothing is invented. A field with no source stays null and its spec says so.
  * Plain ASCII, EN-GB spelling, no em or en dashes, no smart quotes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# --------------------------------------------------------------------------- #
# Locations
# --------------------------------------------------------------------------- #

# The Profiles repository root (this file is <root>/tools/profiles_common.py).
PROFILES_ROOT = Path(__file__).resolve().parent.parent

# GDA's Scripts folder holds horizon.py and gda_paths.py. By default it is the
# GDA repo sitting next to this one in the Code folder; PROFILES_GDA_SCRIPTS
# overrides that. We import GDA's helpers rather than copying them, so the
# data-currency rule can never drift between the two projects.
GDA_SCRIPTS_ENV = "PROFILES_GDA_SCRIPTS"
DEFAULT_GDA_SCRIPTS = PROFILES_ROOT.parent / "GDA" / "v1" / "Scripts"


class ProfilesError(RuntimeError):
    """Any condition a builder must not continue past. Always fail loud."""


class SpecError(ProfilesError):
    """A fields.json file is malformed."""


class GateError(ProfilesError):
    """A frame does not match its field spec, so it must not be written."""


def _import_gda_helpers():
    """Import GDA's horizon and gda_paths modules, or stop with a clear message."""
    scripts = Path(os.environ.get(GDA_SCRIPTS_ENV, "").strip() or DEFAULT_GDA_SCRIPTS)
    if not (scripts / "horizon.py").is_file() or not (scripts / "gda_paths.py").is_file():
        raise ProfilesError(
            f"GDA helper scripts not found in {scripts}. Expected horizon.py and gda_paths.py there. "
            f"Clone the GDA repo next to Profiles, or set {GDA_SCRIPTS_ENV} to its v1/Scripts folder.")
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import gda_paths  # noqa: E402  (imported from GDA on purpose)
    import horizon  # noqa: E402
    return horizon, gda_paths


def check_versions() -> None:
    """Refuse to build with library versions other than those pinned in
    tools/requirements.txt: the Parquet bytes, and float handling, must not drift
    between builds."""
    import numpy
    pins = {}
    for line in (Path(__file__).parent / "requirements.txt").read_text(encoding="ascii").splitlines():
        if "==" in line:
            name, ver = line.split("==", 1)
            pins[name.strip()] = ver.strip()
    have = {"pandas": pd.__version__, "pyarrow": pa.__version__, "numpy": numpy.__version__}
    wrong = {k: (have.get(k), v) for k, v in pins.items() if have.get(k) != v}
    if wrong:
        raise ProfilesError(f"library versions differ from tools/requirements.txt (installed, pinned): {wrong}. "
                            f"Run pip install -r tools/requirements.txt")


def lake_root() -> Path:
    """The lake's DataSources folder. GDA_DATA_ROOT must be set: on a development
    box the fallback inside the GDA repo is a partial copy, and reading a partial
    lake without noticing is exactly the mistake gda_paths was written to stop."""
    check_versions()
    _, gda_paths = _import_gda_helpers()
    if not os.environ.get(gda_paths.DATA_ROOT_ENV, "").strip():
        raise ProfilesError(
            f"{gda_paths.DATA_ROOT_ENV} is not set. Point it at the full lake's DataSources folder, "
            f"for example W:\\gda\\DataSources.")
    return gda_paths.data_root(Path("unused-because-the-variable-is-set"))


def resolve_cutoff(as_of: str | None = None, now: datetime | None = None) -> datetime:
    """The profiles last-updated instant, as a tz-aware UTC datetime.

    With as_of ("YYYY-MM-DD"): that date at 00:00 UTC, which GDA's currency rule
    must accept. Without it: the latest date GDA allows, floored to 00:00 UTC.
    Flooring makes every run on the same day read the same window."""
    horizon, _ = _import_gda_helpers()
    if as_of:
        try:
            day = datetime.strptime(as_of, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise ProfilesError(f"--as-of must be YYYY-MM-DD, got {as_of!r}") from exc
        horizon.assert_historical(day, now)
        return day
    c = horizon.cutoff(now)
    return c.replace(hour=0, minute=0, second=0, microsecond=0)


# --------------------------------------------------------------------------- #
# Field specs
# --------------------------------------------------------------------------- #

# GridSim's closed unit vocabulary (GridSim schemas/schemaNotes.md section 3,
# rule 2). A spec unit must be one of these, or one of the EXTRA units below.
GRIDSIM_UNITS = frozenset({
    "1", "pu@system", "pu@machine", "pu@transformer", "s", "Hz", "Hz/s", "MW", "MVA",
    "Mvar", "kV", "km", "ohm/km", "uS/km", "%", "MWh", "MW/min", "MW/Hz/MW", "degC",
    "deg", "MW.s/Hz", "MW/Hz", "MW/s/MW", "V", "min",
})

# Units the profiles need that GridSim does not have yet. Each is a proposal for
# GridSim's vocabulary when the schema work resumes; until then a field using one
# is flagged in FIELDS.md so nobody mistakes it for a GridSim-ready value.
EXTRA_UNITS = frozenset({
    "ohm",      # absolute series impedance of a whole circuit
    "uS",       # absolute shunt susceptance of a whole circuit
    "h",        # hours (for example hours above 80% loading)
    "rpm",      # shaft speed
    "kN.m",     # shaft torque
    "tCO2/MWh", # emission intensity
    "s.MVA",    # stored kinetic energy (inertia constant times rating)
    "m",        # metres (OSGB easting and northing, EPSG:27700)
})

# No unit at all: identifiers, names, flags and free text.
NO_UNIT = None

ALLOWED_TYPES = frozenset({"float64", "int64", "string", "bool", "timestamp"})

# GridSim provenance tags (schemaNotes.md section 3, rule 4), case-sensitive.
PROVENANCE_TAGS = frozenset({
    "Recorded", "DerivedFromRecorded", "CuratedPlaceholder", "Synthetic",
    "Counterfactual", "Interpolated", "UnvalidatedAtScale",
})

# A table either describes assets (reference data, like library data) or holds
# statistics of time-stamped operational readings (observed). GridSim treats the
# two differently: observed tables have to pass its time guard.
TABLE_KINDS = frozenset({"reference", "observed"})

# Every table starts with these, in this order. profile_rev and content_sha256 are
# filled by write_profile (see assign_revisions), not by the builders.
IDENTITY_FIELDS = ("profile_id", "profile_rev", "content_sha256")
# Left out of the content hash: they describe the build, not the profile.
NOT_HASHED = frozenset({"profile_rev", "content_sha256", "last_updated_utc"})

REQUIRED_FIELD_KEYS = ("name", "type", "unit", "description", "source", "provenance", "nullable", "sensitive")
# unit_from names the string field in the same table that holds the unit of an
# as-published value whose unit varies by row (for example reported_r1 with
# reported_impedance_base). Every numeric field without a fixed unit must have one.
OPTIONAL_FIELD_KEYS = ("unit_from",)


@dataclass(frozen=True)
class Field:
    name: str
    type: str
    unit: str | None
    description: str
    source: str
    provenance: str
    nullable: bool
    sensitive: bool
    unit_from: str | None = None


@dataclass(frozen=True)
class Spec:
    family: str
    table: str
    kind: str            # "reference" (describes assets) or "observed" (statistics of time-stamped readings)
    description: str
    fields: tuple[Field, ...]
    sha256: str          # hash of the spec file bytes, recorded in the manifest

    @property
    def names(self) -> list[str]:
        return [f.name for f in self.fields]

    def field(self, name: str) -> Field:
        for f in self.fields:
            if f.name == name:
                return f
        raise SpecError(f"{self.family}/{self.table}: no field named {name!r}")


def is_plain_ascii(text: str) -> bool:
    """True when text is printable ASCII (tabs and newlines allowed). Catches the
    em and en dashes and smart quotes the house style forbids."""
    return all(c in "\t\n\r" or 32 <= ord(c) < 127 for c in text)


def load_spec(path: Path, table: str) -> Spec:
    """Load one table's spec from a family fields.json, checking the spec itself.

    A fields.json holds {"family": ..., "tables": {<table>: {"description": ...,
    "fields": [...]}}}. Every problem found is reported at once, not one at a time."""
    raw_bytes = Path(path).read_bytes()
    try:
        raw = json.loads(raw_bytes.decode("ascii"))
    except UnicodeDecodeError as exc:
        raise SpecError(f"{path}: spec must be plain ASCII ({exc})") from exc
    problems: list[str] = []
    family = raw.get("family")
    tables = raw.get("tables")
    if not isinstance(family, str) or not family:
        problems.append("missing 'family'")
    if not isinstance(tables, dict) or table not in tables:
        raise SpecError(f"{path}: no table {table!r} under 'tables'")
    t = tables[table]
    if t.get("kind") not in TABLE_KINDS:
        problems.append(f"table kind must be one of {sorted(TABLE_KINDS)}, got {t.get('kind')!r}")
    seen: set[str] = set()
    fields: list[Field] = []
    for i, f in enumerate(t.get("fields", [])):
        where = f"field #{i} ({f.get('name', '?')})"
        missing = [k for k in REQUIRED_FIELD_KEYS if k not in f]
        extra = sorted(set(f) - set(REQUIRED_FIELD_KEYS) - set(OPTIONAL_FIELD_KEYS))
        if missing:
            problems.append(f"{where}: missing keys {missing}")
            continue
        if extra:
            problems.append(f"{where}: unknown keys {extra}")
        if f["name"] in seen:
            problems.append(f"{where}: duplicate name")
        seen.add(f["name"])
        if f["type"] not in ALLOWED_TYPES:
            problems.append(f"{where}: type {f['type']!r} not in {sorted(ALLOWED_TYPES)}")
        if f["unit"] is not None and f["unit"] not in GRIDSIM_UNITS | EXTRA_UNITS:
            problems.append(f"{where}: unit {f['unit']!r} is not in the unit vocabulary")
        if f["unit"] is not None and f["type"] not in ("float64", "int64"):
            problems.append(f"{where}: only numeric fields may carry a unit")
        if f["provenance"] not in PROVENANCE_TAGS:
            problems.append(f"{where}: provenance {f['provenance']!r} is not a GridSim tag")
        if f["provenance"] == "CuratedPlaceholder" and "[VERIFY]" not in f["description"]:
            problems.append(f"{where}: a CuratedPlaceholder description must contain [VERIFY]")
        if f["source"] == "none" and not f["nullable"]:
            problems.append(f"{where}: a field with no source must be nullable")
        if not isinstance(f["nullable"], bool) or not isinstance(f["sensitive"], bool):
            problems.append(f"{where}: nullable and sensitive must be true or false")
        for key in ("name", "description", "source"):
            if not isinstance(f[key], str) or not f[key].strip():
                problems.append(f"{where}: {key} must be a non-blank string")
        if f["type"] in ("float64", "int64") and f["unit"] is None and not f.get("unit_from"):
            problems.append(f"{where}: a numeric field needs a unit, or unit_from naming the field that holds it")
        if f.get("unit_from") is not None and f["unit"] is not None:
            problems.append(f"{where}: give unit or unit_from, not both")
        fields.append(Field(**{k: f[k] for k in REQUIRED_FIELD_KEYS}, unit_from=f.get("unit_from")))
    if not fields:
        problems.append("no fields")
    names = [f.name for f in fields]
    if names[:len(IDENTITY_FIELDS)] != list(IDENTITY_FIELDS):
        problems.append(f"every table must start with {list(IDENTITY_FIELDS)}, got {names[:len(IDENTITY_FIELDS)]}")
    by_name = {f.name: f for f in fields}
    for f in fields:
        if f.unit_from is not None and (f.unit_from not in by_name or by_name[f.unit_from].type != "string"):
            problems.append(f"{f.name}: unit_from {f.unit_from!r} must name a string field in this table")
    if problems:
        raise SpecError(f"{path} [{table}]:\n  " + "\n  ".join(problems))
    return Spec(family=family, table=table, kind=t["kind"], description=t.get("description", ""),
                fields=tuple(fields), sha256=hashlib.sha256(raw_bytes).hexdigest())


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #

def _type_ok(series: pd.Series, ftype: str) -> bool:
    """Does the column's dtype match the spec type? All-null columns must still
    carry the right dtype, so a builder cannot hand over an untyped null column."""
    dt = series.dtype
    if ftype == "float64":
        return dt == "float64"
    if ftype == "int64":
        return str(dt) in ("int64", "Int64")
    if ftype == "bool":
        return str(dt) in ("bool", "boolean")
    if ftype == "string":
        return str(dt) in ("string", "string[python]", "str") or (
            dt == object and series.dropna().map(lambda v: isinstance(v, str)).all())
    if ftype == "timestamp":
        return isinstance(dt, pd.DatetimeTZDtype) and str(dt.tz) == "UTC"
    return False


def gate(df: pd.DataFrame, spec: Spec) -> None:
    """Check a frame against its spec. Raises GateError listing every problem."""
    problems: list[str] = []
    cols = list(df.columns)
    unknown = [c for c in cols if c not in spec.names]
    missing = [n for n in spec.names if n not in cols]
    if unknown:
        problems.append(f"columns not in spec: {unknown}")
    if missing:
        problems.append(f"spec fields missing from frame: {missing}")
    if not unknown and not missing and cols != spec.names:
        problems.append("column order differs from the spec order")
    for f in spec.fields:
        if f.name not in df.columns:
            continue
        s = df[f.name]
        if not _type_ok(s, f.type):
            problems.append(f"{f.name}: dtype {s.dtype} does not match spec type {f.type}")
        if not f.nullable and s.isna().any():
            problems.append(f"{f.name}: {int(s.isna().sum())} nulls in a non-nullable field")
        if f.source == "none" and s.notna().any():
            problems.append(f"{f.name}: spec says no source, but {int(s.notna().sum())} values are set")
        if f.type == "string":
            bad = s.dropna().map(lambda v: not is_plain_ascii(str(v)))
            if bad.any():
                problems.append(f"{f.name}: {int(bad.sum())} values are not plain ASCII")
        if f.type == "float64" and s.dtype == "float64":
            inf = s.map(lambda v: v in (float("inf"), float("-inf")))
            if inf.any():
                problems.append(f"{f.name}: {int(inf.sum())} infinite values")
    if df.index.has_duplicates or not isinstance(df.index, pd.RangeIndex):
        problems.append("index must be a clean RangeIndex (reset_index(drop=True) before writing)")
    if problems:
        raise GateError(f"{spec.family}/{spec.table}: refused to write:\n  " + "\n  ".join(problems))


# --------------------------------------------------------------------------- #
# Hand-kept names (every family, every table)
# --------------------------------------------------------------------------- #

# Each family may keep <Family>/names.csv: one line per profile Mark has named
# (operator, site, address) from his own knowledge. Every table carries the same
# four named_* columns; write_profile fills them from the file. The file is
# checked hard: a name for a profile the family does not produce stops the build,
# so a typo in a profile_id cannot silently fail to match.
NAME_FILE = "names.csv"
NAME_COLUMNS = ["profile_id", "operator", "site_name", "address", "named_by", "notes"]
NAMED_FIELDS = {"named_operator": "operator", "named_site": "site_name",
                "named_address": "address", "named_by": "named_by"}
_names_cache: dict[str, pd.DataFrame] = {}
_names_used: dict[str, set] = {}


def load_names(family: str, root: Path | None = None) -> pd.DataFrame:
    """Read <Family>/names.csv (validated), indexed by profile_id. A family with
    no file has no names. Cached per family for one build."""
    import csv
    key = f"{root or PROFILES_ROOT}|{family}"
    if key in _names_cache:
        return _names_cache[key]
    path = Path(root or PROFILES_ROOT) / family / NAME_FILE
    if not path.exists():
        df = pd.DataFrame(columns=NAME_COLUMNS).set_index("profile_id")
        _names_cache[key] = df
        return df
    text = path.read_bytes().decode("utf-8-sig")
    if not is_plain_ascii(text):
        raise ProfilesError(f"{path} must be plain ASCII (check for accents, curly quotes or dashes)")
    lines = text.splitlines()
    header = next(csv.reader(lines), [])
    if header != NAME_COLUMNS:
        raise ProfilesError(f"{path} header must be {NAME_COLUMNS}, got {header}")
    df = pd.DataFrame(list(csv.DictReader(lines)), columns=NAME_COLUMNS).fillna("")
    df = df.apply(lambda c: c.astype(str).str.strip())
    problems = []
    for i, r in df.iterrows():
        where = f"{path.name} line {i + 2}"
        if not r["profile_id"]:
            problems.append(f"{where}: profile_id is blank")
        if not (r["operator"] or r["site_name"] or r["address"]):
            problems.append(f"{where}: names nothing (operator, site_name and address are all blank)")
    dup = df["profile_id"][df["profile_id"].duplicated()]
    if len(dup):
        problems.append(f"{path.name}: profile_id repeated: {sorted(set(dup))}")
    if problems:
        raise ProfilesError("names file refused:\n  " + "\n  ".join(problems))
    df = df.replace({"": None}).set_index("profile_id")
    _names_cache[key] = df
    return df


def apply_names(df: pd.DataFrame, spec: Spec, root: Path | None = None) -> pd.DataFrame:
    """Fill the named_* columns from the family's names.csv and record which
    names were used (see verify_names_used)."""
    if not all(n in spec.names for n in NAMED_FIELDS):
        return df
    names = load_names(spec.family, root)
    out = df.copy()
    hit = out["profile_id"].isin(names.index)
    for field, col in NAMED_FIELDS.items():
        values = [names.at[pid, col] if h else None for pid, h in zip(out["profile_id"], hit)]
        out[field] = pd.Series(values, index=out.index, dtype=object)
    _names_used.setdefault(f"{root or PROFILES_ROOT}|{spec.family}", set()).update(out.loc[hit, "profile_id"])
    return out


def verify_names_used(family: str, root: Path | None = None) -> int:
    """After a family is written: every name in its names.csv must have matched a
    profile. Returns how many profiles were named. Resets the per-build state."""
    key = f"{root or PROFILES_ROOT}|{family}"
    names = load_names(family, root)
    used = _names_used.pop(key, set())
    _names_cache.pop(key, None)
    unmatched = sorted(set(names.index) - used)
    if unmatched:
        raise ProfilesError(f"{family}/{NAME_FILE} names profiles this family does not produce: {unmatched}")
    return len(used)


# --------------------------------------------------------------------------- #
# Writing
# --------------------------------------------------------------------------- #

def _canon(value) -> str:
    """Exact, type-tagged text for one value, for hashing. Floats use their hex
    form, so two values hash the same only when every bit is the same."""
    if value is None or value is pd.NA or value is pd.NaT:
        return "n:"
    if isinstance(value, float) or isinstance(value, np.floating):
        return "n:" if value != value else "f:" + float(value).hex()
    if isinstance(value, (bool, np.bool_)):
        return "b:" + ("1" if value else "0")
    if isinstance(value, (int, np.integer)):
        return "i:" + str(int(value))
    if isinstance(value, pd.Timestamp):
        return "t:" + value.isoformat()
    return "s:" + str(value)


def content_hashes(df: pd.DataFrame, spec: Spec) -> pd.Series:
    """SHA-256 of each row's content: every spec field except NOT_HASHED, in spec
    order, each value in its exact canonical form. Null values are left out, so
    adding a column that is null for a row does not change that row's hash (and
    so does not raise its revision); setting a value does."""
    # Only columns present: a missing one is reported by the gate, not here.
    cols = [f.name for f in spec.fields if f.name not in NOT_HASHED and f.name in df.columns]
    out = []
    for row in df[cols].itertuples(index=False, name=None):
        text = "\x1f".join(f"{c}={_canon(v)}" for c, v in zip(cols, row) if _canon(v) != "n:")
        out.append(hashlib.sha256(text.encode("utf-8")).hexdigest())
    return pd.Series(out, index=df.index, dtype=object)


def assign_revisions(df: pd.DataFrame, spec: Spec, previous: Path | None) -> pd.DataFrame:
    """Fill profile_rev and content_sha256.

    A profile keeps its revision while its content is unchanged. When its content
    changes it gets the previous revision plus one; a new profile starts at 1. The
    previous revisions are read from the file this table is about to replace, so a
    published id@rev never silently changes meaning."""
    out = df.drop(columns=[c for c in ("profile_rev", "content_sha256") if c in df.columns]).copy()
    shas = content_hashes(out.assign(profile_rev=0, content_sha256=""), spec)
    prev: dict[str, tuple[int, str]] = {}
    if previous is not None and Path(previous).exists():
        old = pd.read_parquet(previous)
        if {"profile_id", "profile_rev", "content_sha256"} <= set(old.columns):
            prev = {pid: (int(r), str(h)) for pid, r, h in
                    zip(old["profile_id"], old["profile_rev"], old["content_sha256"])}
    revs = []
    for pid, sha in zip(out["profile_id"], shas):
        if pid not in prev:
            revs.append(1)
        else:
            rev, old_sha = prev[pid]
            revs.append(rev if old_sha == sha else rev + 1)
    out.insert(1, "profile_rev", pd.Series(revs, index=out.index, dtype="int64"))
    out.insert(2, "content_sha256", shas)
    return out


def _root_of(path: Path, family: str) -> Path | None:
    """The folder holding the family folder a file is written into: None for the
    Profiles repo itself, otherwise (tests) the parent of the nearest folder
    named after the family."""
    p = Path(path).resolve()
    if p.is_relative_to(PROFILES_ROOT.resolve()):
        return None
    for parent in p.parents:
        if parent.name == family:
            return parent.parent
    raise ProfilesError(f"{p} is not inside a {family} folder")


def check(df: pd.DataFrame, spec: Spec, previous: Path | None = None) -> pd.DataFrame:
    """What write_profile does before writing: add revisions, then gate. Returns
    the frame exactly as it would be written."""
    out = assign_revisions(df, spec, previous)
    gate(out, spec)
    return out


def write_profile(df: pd.DataFrame, spec: Spec, path: Path) -> dict:
    """Add revisions, gate the frame, then write it atomically. Returns a manifest
    entry.

    Values are written exactly as computed (float64, no rounding). Parquet is
    written with pinned library versions (check_versions), no pandas index
    metadata and a fixed compression, so identical frames give identical bytes."""
    if all(n in spec.names for n in NAMED_FIELDS):
        df = apply_names(df, spec, _root_of(path, spec.family))
    df = check(df, spec, path)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    table = table.replace_schema_metadata(None)   # drop pandas metadata (holds library versions)
    fd, tmp = tempfile.mkstemp(suffix=".parquet.tmp", dir=str(path.parent))
    os.close(fd)
    try:
        pq.write_table(table, tmp, compression="zstd", write_statistics=True)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return {
        "path": path.relative_to(PROFILES_ROOT).as_posix() if path.is_relative_to(PROFILES_ROOT) else str(path),
        "rows": int(len(df)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "spec": f"{spec.family}/{spec.table}",
        "spec_sha256": spec.sha256,
    }


def render_fields_md(fields_json: Path) -> str:
    """Render a family's fields.json as a Markdown table (FIELDS.md)."""
    raw = json.loads(Path(fields_json).read_text(encoding="ascii"))
    out = [f"# {raw['family']} fields",
           "",
           "Generated from `fields.json` by `tools/profiles_common.py`. Do not edit by hand.",
           "",
           "Units marked * are not yet in GridSim's unit vocabulary (proposed additions).",
           ""]
    for tname, t in raw["tables"].items():
        out += [f"## {tname} ({t.get('kind', '?')})", "", t.get("description", ""), "",
                "| Field | Type | Unit | Provenance | Null | Sensitive | Source | Description |",
                "|---|---|---|---|---|---|---|---|"]
        for f in t["fields"]:
            unit = f["unit"] or (f"per `{f['unit_from']}`" if f.get("unit_from") else "")
            if unit in EXTRA_UNITS:
                unit += " *"
            out.append(f"| `{f['name']}` | {f['type']} | {unit} | {f['provenance']} | "
                       f"{'yes' if f['nullable'] else 'no'} | {'yes' if f['sensitive'] else 'no'} | "
                       f"{f['source']} | {f['description']} |")
        out.append("")
    return "\n".join(out)


def write_fields_md(fields_json: Path) -> None:
    """Write FIELDS.md next to fields.json (only if the content changed)."""
    target = Path(fields_json).with_name("FIELDS.md")
    text = render_fields_md(fields_json)
    if not target.exists() or target.read_text(encoding="ascii") != text:
        target.write_text(text, encoding="ascii", newline="\n")


# --------------------------------------------------------------------------- #
# Small helpers builders share
# --------------------------------------------------------------------------- #

# GB voltage classes that have a Profiles folder.
VOLTAGE_CLASSES = {6.6: "6.6kv", 11.0: "11kv", 33.0: "33kv", 66.0: "66kv",
                   132.0: "132kv", 275.0: "275kv", 400.0: "400kv"}

# Operators publish some equipment at its operating voltage (for example a 33kV
# class transformer at 33.2kV or 31.5kV). A voltage within this fraction of a
# class is filed under that class; the published voltage is kept in its own
# column. 5% keeps distinct classes apart (20kV and 22kV still have no folder).
VOLTAGE_CLASS_TOLERANCE = 0.05


def voltage_folder(kv: float) -> str | None:
    """Map a voltage to its Profiles folder name, or None when it is not within
    VOLTAGE_CLASS_TOLERANCE of a GB class (for example 22kV or 3.3kV)."""
    if kv is None or pd.isna(kv) or float(kv) <= 0:
        return None
    for nominal, folder in VOLTAGE_CLASSES.items():
        if abs(float(kv) - nominal) <= VOLTAGE_CLASS_TOLERANCE * nominal:
            return folder
    return None


def last_updated_column(n: int, cutoff: datetime) -> pd.Series:
    """A last_updated_utc column of length n with the right dtype."""
    return pd.Series([cutoff] * n, dtype="datetime64[us, UTC]") if n else pd.Series([], dtype="datetime64[us, UTC]")


def window_start(cutoff: datetime, days: int) -> datetime:
    """Start of a fixed look-back window ending at the cutoff."""
    return cutoff - timedelta(days=days)


# Published text is held as plain ASCII (house rule; GridSim reads ASCII). Common
# punctuation is mapped explicitly; accented letters lose their accent through
# Unicode decomposition. A character with no mapping stops the build.
_ASCII_MAP = {
    "\u00a0": " ", "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u00d8": "O", "\u00f8": "o", "\u00c6": "AE", "\u00e6": "ae",
    "\u00df": "ss", "\u0141": "L", "\u0142": "l", "\u00a2": "c", "\u2026": "...",
}


def to_ascii(text: str) -> str:
    """Plain-ASCII form of published text (see _ASCII_MAP). Fails loud on a
    character it cannot map, rather than dropping it silently."""
    import unicodedata
    if is_plain_ascii(text):
        return text
    mapped = "".join(_ASCII_MAP.get(ch, ch) for ch in text)
    folded = "".join(ch for ch in unicodedata.normalize("NFKD", mapped) if not unicodedata.combining(ch))
    if not is_plain_ascii(folded):
        bad = sorted({hex(ord(c)) for c in folded if not is_plain_ascii(c)})
        raise ProfilesError(f"no ASCII form for characters {bad} in {text!r}")
    return folded


def str_or_none(s: pd.Series) -> pd.Series:
    """Strings stay strings (trimmed, plain ASCII via to_ascii); NaN, None and
    blanks become None, so every string column has one consistent null."""
    def one(v):
        if v is None or v is pd.NA:
            return None
        if isinstance(v, float) and v != v:      # NaN
            return None
        text = to_ascii(str(v)).strip()
        return text or None
    return s.map(one).astype(object)


def slug(text) -> str:
    """Lower-case letters and digits joined by '-', for readable ids."""
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return s or "unknown"


def sha_id(prefix: str, key: str) -> str:
    """Stable short id: prefix plus the first 16 hex characters of SHA-256(key)."""
    return f"{prefix}-" + hashlib.sha256(key.encode("ascii")).hexdigest()[:16]


def empty_frame(spec: Spec) -> pd.DataFrame:
    """A zero-row frame with the spec's columns and dtypes (passes the gate)."""
    dtypes = {"float64": "float64", "int64": "int64", "string": object, "bool": "bool",
              "timestamp": "datetime64[us, UTC]"}
    return pd.DataFrame({f.name: pd.Series([], dtype=dtypes[f.type]) for f in spec.fields})


def spec_order(df: pd.DataFrame, spec: Spec) -> pd.DataFrame:
    """Columns in spec order, without profile_rev and content_sha256 (write_profile
    adds those). Fails loud on a spec field the builder did not produce."""
    want = [n for n in spec.names if n not in ("profile_rev", "content_sha256")]
    df = df.copy()
    for n in NAMED_FIELDS:               # filled from names.csv at write time
        if n in want and n not in df.columns:
            df[n] = pd.Series([None] * len(df), index=df.index, dtype=object)
    missing = [n for n in want if n not in df.columns]
    if missing:
        raise GateError(f"{spec.family}/{spec.table}: builder did not produce {missing}")
    return df[want]


def utc_timestamps(df: pd.DataFrame, spec: Spec) -> pd.DataFrame:
    """Give every spec timestamp column the datetime64[us, UTC] dtype. An empty
    frame built from arrays otherwise ends up with object columns, which the
    gate (rightly) refuses. Values are not changed, only their dtype."""
    out = df.copy()
    for f in spec.fields:
        if f.type == "timestamp" and f.name in out.columns:
            out[f.name] = pd.to_datetime(out[f.name], utc=True).astype("datetime64[us, UTC]")
    return out


def to_num(s: pd.Series) -> pd.Series:
    """Coerce published text or numbers to float64. Placeholders such as '-',
    '', 'N/A', 'NOT KNOWN' and 'TBC' become NaN; thousands commas, percent signs
    and spaces are stripped. Same rules as GDA's NetworkModel normalisers."""
    if s.dtype.kind == "f":
        return s.astype("float64")
    t = s.astype("string").str.strip().str.replace(r"[,%]| ", "", regex=True)
    return pd.to_numeric(t, errors="coerce").astype("float64")


# Published status words -> energised / out / planned / unknown. Same rules as
# GDA's NetworkModel/sources/common.norm_status (DeadStatuses mirror GridSim.Gda).
_OUT = re.compile(r"out of service|decommiss|removed|abandon|disconnect", re.I)
_PLANNED = re.compile(r"future|planned|proposed|accepted|under construction|scheme", re.I)
_ENERGISED = re.compile(r"unchanged|updated|existing|new|connected|energi[sz]ed|commissioned|in service|operational",
                        re.I)


def norm_status(value) -> str:
    if value is None or value is pd.NA or (isinstance(value, float) and value != value):
        return "unknown"
    s = str(value).strip()
    if not s or s == "-":
        return "unknown"
    if _OUT.search(s):
        return "out"
    if _PLANNED.search(s):
        return "planned"
    if _ENERGISED.search(s):
        return "energised"
    return "unknown"


def latest_snapshot(folder: Path, pattern: str, key: str, last_updated: datetime) -> Path:
    """The snapshot file with the newest date on or before the last-updated date.
    key is the partition name (snapshot_date or edition_year; an edition year
    counts from 1 January of that year)."""
    best = None
    for p in folder.glob(pattern):
        value = p.parent.name.split("=", 1)[1]
        stamp = (pd.Timestamp(value, tz="UTC") if key == "snapshot_date"
                 else pd.Timestamp(f"{value}-01-01", tz="UTC"))
        if stamp <= last_updated and (best is None or stamp > best[0]):
            best = (stamp, p)
    if best is None:
        raise ProfilesError(f"no {folder.name} snapshot on or before {last_updated.date()}")
    return best[1]


def single_parquet(folder: Path) -> pd.DataFrame:
    """Read the one data parquet in a lake dataset folder. GDA stores geometry in
    a '<name>__geometry.parquet' side table next to the data; those are skipped.
    Anything else that is not exactly one file stops the build."""
    folder = Path(folder)
    files = sorted(p for p in folder.glob("*.parquet") if not p.stem.endswith("__geometry"))
    if len(files) != 1:
        raise ProfilesError(f"expected one data parquet file in {folder}, found {[p.name for p in files]}")
    return pd.read_parquet(files[0])


def ensure_unique(series: pd.Series, what: str) -> None:
    """Fail loud when an identifier column has duplicates."""
    dup = series[series.duplicated()]
    if len(dup):
        raise ProfilesError(f"{what}: {len(dup)} duplicate values, for example {dup.head(5).tolist()}")
