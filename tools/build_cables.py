"""Build the Cables profiles from the GDA cable lake.

Input : <lake>/Derived/cable_lake/cable_lake.parquet  (one file, about 148k rows)
Output: Cables/<voltage_class>/circuits.parquet   one row per published circuit
        Cables/<voltage_class>/types.parquet      archetypes (per-km impedance, rating, length spread)
        Cables/<voltage_class>/spans.parquet      GIS overhead span summaries (length and conductor)
        Cables/FIELDS.md                          rendered from Cables/fields.json

The cable lake holds three kinds of row (its element_class column):
  * circuit      - LTDS published circuits with impedance and ratings (6.6kV to 132kV)
  * gis_circuit  - SSEN transmission GIS circuits: route and length, no impedance
                   (this is the only 275kV and 400kV evidence in the lake)
  * gis_span     - GIS line spans keyed only by voltage: length and conductor

Nothing is invented. Where the source carries the 9999 "no value" sentinel the
harmonised value is nulled and the row's quality_flags says so; the value as
reported is still kept in the reported_* columns, untouched.

Run:  python tools/build_cables.py [--as-of YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import hashlib
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import profiles_common as pc

FAMILY = "Cables"
SOURCE_DATASET = "Derived/cable_lake/cable_lake.parquet"
FIELDS_JSON = pc.PROFILES_ROOT / FAMILY / "fields.json"

# The value some operators publish to mean "not known". Anything equal to it is
# treated as missing, never as a real 9999 ohm or 9999 MVA.
SENTINEL = 9999.0

# Archetypes and span summaries are per voltage CLASS (an 11.5kV circuit sits in
# the 11kv class); their voltage_kv is the class's nominal voltage.
CLASS_NOMINAL_KV = {folder: kv for kv, folder in pc.VOLTAGE_CLASSES.items()}

# Columns read from the lake (nothing else is loaded, to keep reads small).
LAKE_COLUMNS = [
    "cable_id", "operator", "licence", "voltage_kv", "circuit_name", "circuit_code",
    "from_node", "to_node", "length_km_published", "geom_length_km",
    "r_ohm", "x_ohm", "r_pct_100mva", "x_pct_100mva", "b_pct_100mva",
    "r1_raw", "x1_raw", "b1_raw", "r0_raw", "x0_raw", "impedance_base",
    "winter_rating_mva", "summer_rating_mva", "rating_mva", "conductor_type",
    "ohl_or_underground", "geometry_wkt", "status", "element_class", "evidence_source",
]


# --------------------------------------------------------------------------- #
# Pure transforms (no I/O, so the tests can drive them with small frames)
# --------------------------------------------------------------------------- #

def _is_sentinel(s: pd.Series) -> pd.Series:
    return s.eq(SENTINEL)


def _construction(s: pd.Series) -> pd.Series:
    """overhead / underground / unknown (anything else in the source is unknown)."""
    s = s.fillna("unknown").astype(str).str.strip().str.lower()
    return s.where(s.isin(["overhead", "underground"]), "unknown").astype(object)


def prepare_circuits(lake: pd.DataFrame, last_updated: datetime) -> pd.DataFrame:
    """Turn cable lake circuit rows (circuit and gis_circuit) into circuits-table
    rows, columns in spec order. Rows whose voltage has no Profiles folder are
    dropped here; the caller counts them for the report."""
    df = lake[lake["element_class"].isin(["circuit", "gis_circuit"])].copy()
    df["voltage_class"] = df["voltage_kv"].map(pc.voltage_folder)
    df = df[df["voltage_class"].notna()].copy()

    flags: list[list[str]] = [[] for _ in range(len(df))]

    def flag(mask: pd.Series, name: str) -> None:
        for i in np.flatnonzero(mask.to_numpy()):
            flags[i].append(name)

    # --- impedance: null the sentinel in every harmonised column ---------------
    imp_sentinel = (_is_sentinel(df["r_ohm"]) | _is_sentinel(df["x_ohm"])
                    | _is_sentinel(df["r1_raw"]) | _is_sentinel(df["x1_raw"]))
    flag(imp_sentinel, "sentinel_9999_impedance")
    for col in ("r_ohm", "x_ohm", "r_pct_100mva", "x_pct_100mva"):
        df[col] = df[col].mask(imp_sentinel)
    b_sentinel = _is_sentinel(df["b1_raw"])
    flag(b_sentinel, "sentinel_9999_susceptance")
    df["b_pct_100mva"] = df["b_pct_100mva"].mask(b_sentinel)

    zero_imp = df["r_ohm"].eq(0) & df["x_ohm"].eq(0)
    flag(zero_imp, "zero_impedance")

    # --- ratings ---------------------------------------------------------------
    for col, name in (("winter_rating_mva", "winter"), ("summer_rating_mva", "summer"), ("rating_mva", "main")):
        bad = _is_sentinel(df[col])
        flag(bad, f"sentinel_9999_rating_{name}")
        df[col] = df[col].mask(bad)
        zero = df[col].eq(0)
        flag(zero, f"zero_rating_{name}")
        df[col] = df[col].mask(zero)

    # --- length: LTDS published length first, else the computed route length ---
    is_ltds = df["element_class"].eq("circuit")

    # --- source keys ----------------------------------------------------------
    # LTDS cable_ids are unique (checked below, fail loud). SSEN transmission GIS
    # features are not: one feeder drawn as several segments shares an id, and
    # some features have no id at all ("...:gis:nan"). Those get a stable
    # "#segNN" suffix ordered by route length then geometry hash, and a flag.
    key = df["cable_id"].astype(str)
    no_id = ~is_ltds & key.str.endswith(":nan")
    flag(no_id, "gis_feature_without_id")
    geo_hash = df["geometry_wkt"].fillna("").map(lambda w: hashlib.sha256(w.encode("utf-8")).hexdigest())
    order = pd.DataFrame({"key": key, "len": df["geom_length_km"].fillna(-1.0), "h": geo_hash})
    order = order.sort_values(["key", "len", "h"], kind="mergesort")
    order["n"] = order.groupby("key").cumcount()
    order["size"] = order.groupby("key")["key"].transform("size")
    seg = order["n"].reindex(df.index)
    shared = (~is_ltds) & order["size"].reindex(df.index).gt(1)
    flag(shared & ~no_id, "gis_segment_of_shared_id")
    suffix = seg.map(lambda n: f"#seg{int(n):02d}").astype(str)   # astype: an empty frame stays a str column
    key = key.where(~shared, key + suffix)
    df["cable_id"] = key

    length = df["length_km_published"].where(is_ltds, df["geom_length_km"])
    no_length = length.isna() | length.le(0)
    flag(no_length, "no_length")
    length = length.mask(length.le(0))

    # --- derived electrical values -------------------------------------------
    # Shunt susceptance in siemens is (b% / 100) x S_base / V^2 with S in MVA and
    # V in kV (MVA / kV^2 is siemens); x 1e6 gives microsiemens.
    b_us = (df["b_pct_100mva"] / 100.0) * 100.0 / (df["voltage_kv"] ** 2) * 1e6

    # Zero sequence to ohms by the rule that reproduces the cable lake's own r_ohm
    # from r1_raw for every base (checked 2026-10-05 on all 16,131 circuits):
    # percent on 100 MVA x kV^2/100/100, per unit on 100 MVA x kV^2/100, ohmic as is.
    z_base = df["voltage_kv"] ** 2 / 100.0
    to_ohm = df["impedance_base"].map({"percent_on_100mva": 0.01, "pu_on_100mva": 1.0}) * z_base
    to_ohm = to_ohm.where(df["impedance_base"].ne("ohmic_referred"), 1.0)
    unknown_base = sorted(set(df["impedance_base"].dropna()) - {"percent_on_100mva", "pu_on_100mva", "ohmic_referred"})
    if unknown_base:
        raise pc.ProfilesError(f"cable impedance base(s) with no conversion rule: {unknown_base}")
    zero_sentinel = _is_sentinel(df["r0_raw"]) | _is_sentinel(df["x0_raw"])
    flag(zero_sentinel, "sentinel_9999_zero_sequence")
    r0_ohm = (df["r0_raw"] * to_ohm).mask(zero_sentinel)
    x0_ohm = (df["x0_raw"] * to_ohm).mask(zero_sentinel)
    usable = length.notna() & ~zero_imp
    r_km = (df["r_ohm"] / length).where(usable)
    x_km = (df["x_ohm"] / length).where(usable)
    b_km = (b_us / length).where(length.notna())
    x_over_r = (df["x_ohm"] / df["r_ohm"]).where(df["r_ohm"].gt(0))

    out = pd.DataFrame({
        "profile_id": df["cable_id"].map(lambda k: pc.sha_id("cable", k)).astype(object),
        "source_dataset": SOURCE_DATASET,
        "source_key": df["cable_id"].astype(str).astype(object),
        "evidence_source": pc.str_or_none(df["evidence_source"]),
        "last_updated_utc": pc.last_updated_column(len(df), last_updated).to_numpy(),
        "operator": df["operator"].astype(str).astype(object),
        "licence": pc.str_or_none(df["licence"]),
        "voltage_kv": df["voltage_kv"].astype("float64"),
        "voltage_class": df["voltage_class"].astype(object),
        "row_kind": np.where(is_ltds, "ltds_circuit", "gis_circuit").astype(object),
        "circuit_name": pc.str_or_none(df["circuit_name"]),
        "circuit_code": pc.str_or_none(df["circuit_code"]),
        "from_node": pc.str_or_none(df["from_node"]),
        "to_node": pc.str_or_none(df["to_node"]),
        "status": pc.str_or_none(df["status"]),
        "construction": _construction(df["ohl_or_underground"]),
        "conductor_type": pc.str_or_none(df["conductor_type"]),
        "length_km": length.astype("float64"),
        "length_km_published": df["length_km_published"].astype("float64"),
        "length_km_route": df["geom_length_km"].astype("float64"),
        "r_ohm": df["r_ohm"].astype("float64"),
        "x_ohm": df["x_ohm"].astype("float64"),
        "b_us": b_us.astype("float64"),
        "r0_ohm": r0_ohm.astype("float64"),
        "x0_ohm": x0_ohm.astype("float64"),
        "r_pct_100mva": df["r_pct_100mva"].astype("float64"),
        "x_pct_100mva": df["x_pct_100mva"].astype("float64"),
        "b_pct_100mva": df["b_pct_100mva"].astype("float64"),
        "r_ohm_per_km": r_km.astype("float64"),
        "x_ohm_per_km": x_km.astype("float64"),
        "b_us_per_km": b_km.astype("float64"),
        "x_over_r": x_over_r.astype("float64"),
        "reported_impedance_base": pc.str_or_none(df["impedance_base"]),
        "reported_r1": df["r1_raw"].astype("float64"),
        "reported_x1": df["x1_raw"].astype("float64"),
        "reported_b1": df["b1_raw"].astype("float64"),
        "reported_r0": df["r0_raw"].astype("float64"),
        "reported_x0": df["x0_raw"].astype("float64"),
        "rating_winter_mva": df["winter_rating_mva"].astype("float64"),
        "rating_summer_mva": df["summer_rating_mva"].astype("float64"),
        "rating_mva": df["rating_mva"].astype("float64"),
        "rate_a_mva": df["winter_rating_mva"].astype("float64"),
        "rate_a_basis": pd.Series(np.where(df["winter_rating_mva"].notna(), "winter continuous", None),
                                  index=df.index, dtype=object),
        "rate_b_mva": np.full(len(df), np.nan),
        "rate_b_basis": pd.Series([None] * len(df), index=df.index, dtype=object),
        "rate_c_mva": np.full(len(df), np.nan),
        "rate_c_basis": pd.Series([None] * len(df), index=df.index, dtype=object),
        "geometry_wkt": pc.str_or_none(df["geometry_wkt"]),
        "quality_flags": [";".join(f) for f in flags],
    })
    out["quality_flags"] = out["quality_flags"].astype(object)
    if out["source_key"].duplicated().any():
        dups = out.loc[out["source_key"].duplicated(), "source_key"].head(5).tolist()
        raise pc.ProfilesError(f"cable lake has duplicate cable_id values, for example {dups}")
    if out["profile_id"].duplicated().any():
        raise pc.ProfilesError("profile_id hash collision in circuits (should never happen)")
    spec = pc.load_spec(FIELDS_JSON, "circuits")
    out = pc.spec_order(pc.utc_timestamps(out, spec), spec)
    return out.sort_values(["voltage_kv", "source_key"], kind="mergesort").reset_index(drop=True)


def _pct(s: pd.Series, q: float) -> float:
    """Percentile with a fixed method, or NaN for an empty sample."""
    s = s.dropna()
    return float(np.quantile(s.to_numpy(), q, method="linear")) if len(s) else float("nan")


def build_types(circuits: pd.DataFrame, last_updated: datetime) -> pd.DataFrame:
    """Archetypes per voltage x construction x conductor type, from clean LTDS
    circuits only (row_kind ltds_circuit and no quality flags at all)."""
    clean = circuits[circuits["row_kind"].eq("ltds_circuit") & circuits["quality_flags"].eq("")].copy()
    clean["conductor_type"] = clean["conductor_type"].fillna("unknown")
    rows = []
    for (vclass, cons, cond), g in clean.groupby(
            ["voltage_class", "construction", "conductor_type"], sort=True):
        kv = CLASS_NOMINAL_KV[vclass]
        rows.append({
            "profile_id": f"cabletype-{vclass}-{pc.slug(cons)}-{pc.slug(cond)}",
            "source_dataset": SOURCE_DATASET,
            "voltage_kv": float(kv), "voltage_class": vclass,
            "construction": cons, "conductor_type": cond,
            "n_circuits": int(len(g)),
            "n_with_per_km": int(g["r_ohm_per_km"].notna().sum()),
            "r_ohm_per_km_p10": _pct(g["r_ohm_per_km"], 0.10),
            "r_ohm_per_km_p50": _pct(g["r_ohm_per_km"], 0.50),
            "r_ohm_per_km_p90": _pct(g["r_ohm_per_km"], 0.90),
            "x_ohm_per_km_p10": _pct(g["x_ohm_per_km"], 0.10),
            "x_ohm_per_km_p50": _pct(g["x_ohm_per_km"], 0.50),
            "x_ohm_per_km_p90": _pct(g["x_ohm_per_km"], 0.90),
            "b_us_per_km_p50": _pct(g["b_us_per_km"], 0.50),
            "rating_mva_p10": _pct(g["rating_mva"], 0.10),
            "rating_mva_p50": _pct(g["rating_mva"], 0.50),
            "rating_mva_p90": _pct(g["rating_mva"], 0.90),
            "length_km_p10": _pct(g["length_km"], 0.10),
            "length_km_p50": _pct(g["length_km"], 0.50),
            "length_km_p90": _pct(g["length_km"], 0.90),
        })
    return _finish_summary(rows, "types", last_updated)


def build_spans(lake: pd.DataFrame, last_updated: datetime) -> pd.DataFrame:
    """Summaries of GIS spans per voltage x operator x construction x conductor."""
    df = lake[lake["element_class"].eq("gis_span")].copy()
    df["voltage_class"] = df["voltage_kv"].map(pc.voltage_folder)
    df = df[df["voltage_class"].notna() & df["geom_length_km"].gt(0)].copy()
    df["construction"] = _construction(df["ohl_or_underground"])
    df["conductor_type"] = pc.str_or_none(df["conductor_type"]).fillna("unknown")
    rows = []
    for (vclass, op, cons, cond), g in df.groupby(
            ["voltage_class", "operator", "construction", "conductor_type"], sort=True):
        kv = CLASS_NOMINAL_KV[vclass]
        rows.append({
            "profile_id": f"cablespan-{vclass}-{pc.slug(op)}-{pc.slug(cons)}-{pc.slug(cond)}",
            "source_dataset": SOURCE_DATASET,
            "voltage_kv": float(kv), "voltage_class": vclass, "operator": str(op),
            "construction": cons, "conductor_type": cond,
            "n_spans": int(len(g)),
            "total_route_km": float(g["geom_length_km"].sum()),
            "span_km_p10": _pct(g["geom_length_km"], 0.10),
            "span_km_p50": _pct(g["geom_length_km"], 0.50),
            "span_km_p90": _pct(g["geom_length_km"], 0.90),
        })
    return _finish_summary(rows, "spans", last_updated)


def _finish_summary(rows: list[dict], table: str, last_updated: datetime) -> pd.DataFrame:
    """Put summary rows into spec column order with the right dtypes. Fails loud
    if two groups slugged to the same profile_id."""
    spec = pc.load_spec(FIELDS_JSON, table)
    if not rows:
        return pc.spec_order(pc.empty_frame(spec), spec)
    out = pd.DataFrame(rows)
    out["last_updated_utc"] = pc.last_updated_column(len(out), last_updated).to_numpy()
    if out["profile_id"].duplicated().any():
        raise pc.ProfilesError(f"{table}: two groups map to the same profile_id: "
                               f"{out.loc[out['profile_id'].duplicated(), 'profile_id'].tolist()[:5]}")
    for f in spec.fields:
        if f.type == "string" and f.name in out.columns:
            out[f.name] = out[f.name].astype(object)
    return pc.spec_order(out, spec).sort_values("profile_id", kind="mergesort").reset_index(drop=True)


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #

def build(lake_dir: Path, last_updated: datetime, out_root: Path = pc.PROFILES_ROOT) -> dict:
    """Read the cable lake, write every voltage folder, return a report."""
    src = lake_dir / "Derived" / "cable_lake" / "cable_lake.parquet"
    if not src.is_file():
        raise pc.ProfilesError(f"cable lake not found: {src}")
    lake = pd.read_parquet(src, columns=LAKE_COLUMNS)

    circuits = prepare_circuits(lake, last_updated)
    types = build_types(circuits, last_updated)
    spans = build_spans(lake, last_updated)

    specs = {t: pc.load_spec(FIELDS_JSON, t) for t in ("circuits", "types", "spans")}
    frames = {"circuits": circuits, "types": types, "spans": spans}
    written = []
    for vclass in sorted(set(pc.voltage_folder(v) for v in (6.6, 11, 33, 66, 132, 275, 400))):
        for table, frame in frames.items():
            part = frame[frame["voltage_class"].eq(vclass)].reset_index(drop=True)
            path = out_root / FAMILY / vclass / f"{table}.parquet"
            if len(part):
                written.append(pc.write_profile(part, specs[table], path))
            elif path.exists():
                path.unlink()   # no rows now: do not leave a stale file from an older build

    circ_rows = lake[lake["element_class"].isin(["circuit", "gis_circuit"])]
    skipped = circ_rows[circ_rows["voltage_kv"].map(pc.voltage_folder).isna()]
    named = pc.verify_names_used(FAMILY)
    pc.write_fields_md(FIELDS_JSON)
    return {
        "family": FAMILY,
        "inputs": [SOURCE_DATASET],
        "files": written,
        "notes": {"profiles_named": named, 
            "circuits_skipped_no_voltage_folder": {str(k): int(v) for k, v in
                                                   skipped.groupby("voltage_kv").size().items()},
            "circuits_with_quality_flags": int(circuits["quality_flags"].ne("").sum()),
            # GIS spans the source publishes without a voltage (chiefly NPG HV
            # feeders). They are left out rather than given a guessed class.
            "spans_skipped_no_voltage": int((lake["element_class"].eq("gis_span")
                                             & lake["voltage_kv"].isna()).sum()),
            "spans_skipped_no_voltage_folder": int((lake["element_class"].eq("gis_span")
                                                    & lake["voltage_kv"].notna()
                                                    & lake["voltage_kv"].map(pc.voltage_folder).isna()).sum()),
        },
    }


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--as-of", help="profiles last-updated date, YYYY-MM-DD (default: latest available)")
    args = ap.parse_args(argv)
    report = build(pc.lake_root(), pc.resolve_cutoff(args.as_of))
    for f in report["files"]:
        print(f"  {f['path']}: {f['rows']} rows")
    print(f"  notes: {report['notes']}")
    return report


if __name__ == "__main__":
    main()
