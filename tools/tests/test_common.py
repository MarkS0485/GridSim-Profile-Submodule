"""Tests for profiles_common: spec loading, the gate, writing and dates.

The gate is the one thing standing between a builder bug and a bad profile file,
so every refusal path is tested on its own."""

import json
from datetime import datetime, timezone

import pandas as pd
import pytest

import profiles_common as pc

UTC = timezone.utc


def _field(name, type_="float64", unit="MW", **kw):
    f = {"name": name, "type": type_, "unit": unit, "description": f"{name} test field.",
         "source": "test", "provenance": "Recorded", "nullable": False, "sensitive": False}
    f.update(kw)
    return f


IDENT = [_field("profile_id", "string", None), _field("profile_rev", "int64", "1"),
         _field("content_sha256", "string", None)]


def _spec_file(tmp_path, fields, table="t", kind="reference", ident=True):
    """A one-table spec. The identity fields every table must start with are
    added unless ident=False."""
    p = tmp_path / "fields.json"
    body = {"kind": kind, "description": "d", "fields": (IDENT if ident else []) + fields}
    if kind is None:
        del body["kind"]
    p.write_text(json.dumps({"family": "Test", "tables": {table: body}}), encoding="ascii")
    return p


def _good_spec(tmp_path):
    return pc.load_spec(_spec_file(tmp_path, [
        _field("p_mw"),
        _field("n", "int64", "1"),
        _field("ok", "bool", None),
        _field("when", "timestamp", None),
        _field("note", "string", None, nullable=True),
    ]), "t")


def _good_frame():
    return pd.DataFrame({
        "profile_id": pd.Series(["a", "b"], dtype=object),
        "p_mw": [1.0, 2.5],
        "n": pd.Series([1, 2], dtype="int64"),
        "ok": [True, False],
        "when": pd.Series([datetime(2026, 1, 1, tzinfo=UTC)] * 2, dtype="datetime64[us, UTC]"),
        "note": pd.Series([None, "x"], dtype=object),
    })


# --------------------------------------------------------------------------- #
# Spec loading
# --------------------------------------------------------------------------- #

def test_good_spec_loads(tmp_path):
    spec = _good_spec(tmp_path)
    assert spec.names == ["profile_id", "profile_rev", "content_sha256", "p_mw", "n", "ok", "when", "note"]
    assert spec.kind == "reference"
    assert len(spec.sha256) == 64


@pytest.mark.parametrize("bad, message", [
    (_field("x", unit="furlongs"), "unit vocabulary"),
    (_field("x", type_="decimal"), "type"),
    (_field("x", provenance="recorded"), "not a GridSim tag"),
    (_field("x", provenance="CuratedPlaceholder"), "[VERIFY]"),
    (_field("x", source="none"), "no source must be nullable"),
    (_field("x", type_="string", unit="MW"), "only numeric"),
    (_field("x", description="  "), "non-blank"),
    ({**_field("x"), "colour": "red"}, "unknown keys"),
])
def test_bad_field_is_refused(tmp_path, bad, message):
    with pytest.raises(pc.SpecError, match=message.replace("[", r"\[").replace("]", r"\]")):
        pc.load_spec(_spec_file(tmp_path, [bad]), "t")


def test_missing_key_and_duplicate_reported_together(tmp_path):
    f = _field("x")
    del f["unit"]
    with pytest.raises(pc.SpecError) as e:
        pc.load_spec(_spec_file(tmp_path, [f, _field("y"), _field("y")]), "t")
    assert "missing keys" in str(e.value) and "duplicate name" in str(e.value)


def test_non_ascii_spec_refused(tmp_path):
    p = tmp_path / "fields.json"
    p.write_bytes(json.dumps({"family": "T", "tables": {"t": {"kind": "reference", "fields": [
        _field("x", description="smart \u2018quote\u2019")]}}}, ensure_ascii=False).encode("utf-8"))
    with pytest.raises(pc.SpecError, match="ASCII"):
        pc.load_spec(p, "t")


def test_unknown_table_refused(tmp_path):
    with pytest.raises(pc.SpecError, match="no table"):
        pc.load_spec(_spec_file(tmp_path, [_field("x")]), "other")


def test_extra_units_allowed_and_flagged_in_fields_md(tmp_path):
    p = _spec_file(tmp_path, [_field("r", unit="ohm")])
    pc.load_spec(p, "t")
    assert "ohm *" in pc.render_fields_md(p)


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #

def test_good_frame_passes(tmp_path):
    out = pc.check(_good_frame(), _good_spec(tmp_path))
    assert out["profile_rev"].tolist() == [1, 1] and out["content_sha256"].str.len().eq(64).all()


@pytest.mark.parametrize("mutate, message", [
    (lambda df: df.assign(extra=1.0), "not in spec"),
    (lambda df: df.drop(columns=["p_mw"]), "missing from frame"),
    (lambda df: df[["p_mw", "profile_id", "n", "ok", "when", "note"]], "order"),
    (lambda df: df.assign(p_mw=["1", "2"]), "dtype"),
    (lambda df: df.assign(n=[1.0, 2.0]), "dtype"),
    (lambda df: df.assign(p_mw=[1.0, None]), "non-nullable"),
    (lambda df: df.assign(profile_id=["a", "caf\xe9"]), "ASCII"),
    (lambda df: df.assign(profile_id=["a", "en\u2013dash"]), "ASCII"),
    (lambda df: df.assign(p_mw=[1.0, float("inf")]), "infinite"),
    (lambda df: df.assign(when=pd.Series([datetime(2026, 1, 1)] * 2)), "dtype"),
    (lambda df: df.set_axis([5, 6]), "RangeIndex"),
])
def test_gate_refuses(tmp_path, mutate, message):
    with pytest.raises(pc.GateError, match=message):
        pc.check(mutate(_good_frame()), _good_spec(tmp_path))


def test_gate_refuses_values_in_a_no_source_field(tmp_path):
    spec = pc.load_spec(_spec_file(tmp_path, [_field("poles", "int64", "1", source="none", nullable=True)]), "t")
    ids = pd.Series(["a", "b"], dtype=object)
    pc.check(pd.DataFrame({"profile_id": ids, "poles": pd.Series([None, None], dtype="Int64")}), spec)
    with pytest.raises(pc.GateError, match="no source"):
        pc.check(pd.DataFrame({"profile_id": ids, "poles": pd.Series([2, None], dtype="Int64")}), spec)


def test_gate_failure_writes_nothing(tmp_path):
    out = tmp_path / "x" / "t.parquet"
    with pytest.raises(pc.GateError):
        pc.write_profile(_good_frame().assign(extra=1.0), _good_spec(tmp_path), out)
    assert not out.exists() and not list(tmp_path.rglob("*.tmp"))


# --------------------------------------------------------------------------- #
# Writing
# --------------------------------------------------------------------------- #

def test_write_is_deterministic_and_round_trips(tmp_path):
    spec = _good_spec(tmp_path)
    a, b = tmp_path / "a.parquet", tmp_path / "b.parquet"
    ea = pc.write_profile(_good_frame(), spec, a)
    eb = pc.write_profile(_good_frame(), spec, b)
    assert a.read_bytes() == b.read_bytes()
    assert ea["sha256"] == eb["sha256"] and ea["rows"] == 2
    back = pd.read_parquet(a)
    assert list(back.columns) == spec.names
    assert back["p_mw"].tolist() == [1.0, 2.5]


# --------------------------------------------------------------------------- #
# Dates and helpers
# --------------------------------------------------------------------------- #

def test_default_last_updated_is_floored_to_midnight():
    now = datetime(2026, 10, 5, 15, 30, tzinfo=UTC)
    c = pc.resolve_cutoff(None, now)
    assert c == datetime(2026, 9, 28, 0, 0, tzinfo=UTC)   # 7 d 1 h earlier is 2026-09-28 14:30


def test_as_of_in_range_is_accepted_and_too_recent_refused():
    now = datetime(2026, 10, 5, 15, 30, tzinfo=UTC)
    assert pc.resolve_cutoff("2026-09-01", now) == datetime(2026, 9, 1, tzinfo=UTC)
    with pytest.raises(Exception):
        pc.resolve_cutoff("2026-10-04", now)
    with pytest.raises(pc.ProfilesError, match="YYYY-MM-DD"):
        pc.resolve_cutoff("05/10/2026", now)


@pytest.mark.parametrize("kv, folder", [
    (6.6, "6.6kv"), (11.0, "11kv"), (33, "33kv"), (66.0, "66kv"), (132.0, "132kv"),
    (275.0, "275kv"), (400.0, "400kv"), (22.0, None), (20.0, None), (3.3, None), (None, None),
    (float("nan"), None), (0.0, None), (-33.0, None),
    # operating voltages within 5% of a class file under that class
    (11.5, "11kv"), (33.2, "33kv"), (31.5, "33kv"), (32.8, "33kv"), (6.3, "6.6kv"),
    (31.0, None), (12.0, None),
])
def test_voltage_folder(kv, folder):
    assert pc.voltage_folder(kv) == folder


def test_plain_ascii():
    assert pc.is_plain_ascii("Colleges, 33kV\tline\n")
    assert not pc.is_plain_ascii("em\u2014dash")
    assert not pc.is_plain_ascii("bell\x07")


def test_lake_root_requires_variable(monkeypatch):
    monkeypatch.delenv("GDA_DATA_ROOT", raising=False)
    with pytest.raises(pc.ProfilesError, match="GDA_DATA_ROOT"):
        pc.lake_root()


def test_missing_gda_scripts_fails_loud(monkeypatch, tmp_path):
    monkeypatch.setenv(pc.GDA_SCRIPTS_ENV, str(tmp_path))
    with pytest.raises(pc.ProfilesError, match="GDA helper scripts not found"):
        pc.resolve_cutoff(None)


# --------------------------------------------------------------------------- #
# Table kinds, identity fields, revisions, versions
# --------------------------------------------------------------------------- #

def test_table_kind_required(tmp_path):
    with pytest.raises(pc.SpecError, match="kind"):
        pc.load_spec(_spec_file(tmp_path, [_field("x")], kind=None), "t")
    with pytest.raises(pc.SpecError, match="kind"):
        pc.load_spec(_spec_file(tmp_path, [_field("x")], kind="live"), "t")
    assert pc.load_spec(_spec_file(tmp_path, [_field("x")], kind="observed"), "t").kind == "observed"


def test_identity_fields_required_first(tmp_path):
    with pytest.raises(pc.SpecError, match="must start with"):
        pc.load_spec(_spec_file(tmp_path, [_field("profile_id", "string", None), _field("x")], ident=False), "t")


def test_revision_unchanged_bumped_and_new(tmp_path):
    spec = _good_spec(tmp_path)
    path = tmp_path / "t.parquet"
    pc.write_profile(_good_frame(), spec, path)
    pc.write_profile(_good_frame(), spec, path)                # same content: same revision
    assert pd.read_parquet(path)["profile_rev"].tolist() == [1, 1]
    changed = _good_frame()
    changed.loc[1, "p_mw"] = 2.5000000000000004                # the next float after 2.5
    changed = pd.concat([changed, _good_frame().iloc[[0]].assign(profile_id="c")], ignore_index=True)
    pc.write_profile(changed, spec, path)
    back = pd.read_parquet(path).set_index("profile_id")["profile_rev"].to_dict()
    assert back == {"a": 1, "b": 2, "c": 1}
    pc.write_profile(changed, spec, path)                      # stable on a repeat build
    assert pd.read_parquet(path).set_index("profile_id")["profile_rev"].to_dict() == back


def test_content_hash_uses_exact_bits_and_ignores_last_updated(tmp_path):
    spec = pc.load_spec(_spec_file(tmp_path, [_field("v"), _field("last_updated_utc", "timestamp", None)]), "t")
    ts = lambda d: pd.Series([d], dtype="datetime64[us, UTC]")
    base = pd.DataFrame({"profile_id": ["a"], "profile_rev": [0], "content_sha256": [""], "v": [0.1 + 0.2],
                         "last_updated_utc": ts(datetime(2026, 1, 1, tzinfo=UTC))})
    h = pc.content_hashes(base, spec)[0]
    assert pc.content_hashes(base.assign(last_updated_utc=ts(datetime(2026, 2, 1, tzinfo=UTC))), spec)[0] == h
    assert pc.content_hashes(base.assign(v=[0.3]), spec)[0] != h    # 0.1 + 0.2 != 0.3 in float64


def test_check_versions_matches_pins():
    pc.check_versions()


def test_check_versions_refuses_drift(monkeypatch):
    monkeypatch.setattr(pc.pd, "__version__", "0.0.1")
    with pytest.raises(pc.ProfilesError, match="library versions"):
        pc.check_versions()


def test_numeric_field_needs_unit_or_unit_from(tmp_path):
    with pytest.raises(pc.SpecError, match="needs a unit, or unit_from"):
        pc.load_spec(_spec_file(tmp_path, [_field("x", unit=None)]), "t")
    ok = pc.load_spec(_spec_file(tmp_path, [_field("x", unit=None, unit_from="x_unit"),
                                            _field("x_unit", "string", None)]), "t")
    assert ok.field("x").unit_from == "x_unit"


@pytest.mark.parametrize("fields, message", [
    ([_field("x", unit=None, unit_from="nope")], "must name a string field"),
    ([_field("x", unit=None, unit_from="y"), _field("y")], "must name a string field"),
    ([_field("x", unit_from="u"), _field("u", "string", None)], "not both"),
])
def test_bad_unit_from_refused(tmp_path, fields, message):
    with pytest.raises(pc.SpecError, match=message):
        pc.load_spec(_spec_file(tmp_path, fields), "t")


def test_unit_from_shown_in_fields_md(tmp_path):
    p = _spec_file(tmp_path, [_field("x", unit=None, unit_from="x_unit"), _field("x_unit", "string", None)])
    assert "per `x_unit`" in pc.render_fields_md(p)


@pytest.mark.parametrize("raw, ascii_", [
    ("Glyn Rh\xf4nwy", "Glyn Rhonwy"), ("St\xf8rmark\xa0Ltd", "Stormark Ltd"),
    ("Smith\u2019s \u2013 site", "Smith's - site"), ("10 m\xb2", "10 m2"), ("plain", "plain"),
])
def test_to_ascii(raw, ascii_):
    assert pc.to_ascii(raw) == ascii_


def test_to_ascii_fails_loud_on_unmappable():
    with pytest.raises(pc.ProfilesError, match="no ASCII form"):
        pc.to_ascii("\u4e2d\u6587")


def test_str_or_none_transliterates_and_nulls():
    out = pc.str_or_none(pd.Series(["  Caf\xe9 ", "", None, float("nan")]))
    assert out.iloc[0] == "Cafe" and out.iloc[1:].isna().all()



# --------------------------------------------------------------------------- #
# Hand-kept names
# --------------------------------------------------------------------------- #

NAMES_HEADER = "profile_id,operator,site_name,address,named_by,notes\n"


def _named_spec(tmp_path):
    named = [_field(n, "string", None, nullable=True) for n in pc.NAMED_FIELDS]
    p = tmp_path / "Test"
    p.mkdir(exist_ok=True)
    return pc.load_spec(_spec_file(p, [_field("p_mw")] + named), "t")


def _write_names(tmp_path, body: bytes):
    (tmp_path / "Test").mkdir(exist_ok=True)
    (tmp_path / "Test" / "names.csv").write_bytes(NAMES_HEADER.encode("ascii") + body)


def _frame_ab():
    return pd.DataFrame({"profile_id": pd.Series(["a", "b"], dtype=object), "p_mw": [1.0, 2.0]})


def test_names_applied_at_write_and_bump_revision(tmp_path):
    spec = _named_spec(tmp_path)
    out = tmp_path / "Test" / "t.parquet"
    pc.write_profile(_frame_ab(), spec, out)
    assert pc.verify_names_used("Test", tmp_path) == 0
    _write_names(tmp_path, b'a,Ark Data Centres,Tottenham Hale,"Ardra Road, Tottenham",Mark,\n')
    pc._names_cache.clear()
    pc._names_used.clear()
    pc.write_profile(_frame_ab(), spec, out)
    back = pd.read_parquet(out).set_index("profile_id")
    assert back.loc["a", "named_site"] == "Tottenham Hale" and back.loc["a", "named_address"] == "Ardra Road, Tottenham"
    assert pd.isna(back.loc["b", "named_site"])
    assert back.loc["a", "profile_rev"] == 2 and back.loc["b", "profile_rev"] == 1   # naming is a content change


def test_names_for_unknown_profile_fail_loud(tmp_path):
    spec = _named_spec(tmp_path)
    _write_names(tmp_path, b"zz,Ark,Site,,Mark,\n")
    pc._names_cache.clear()
    pc._names_used.clear()
    pc.write_profile(_frame_ab(), spec, tmp_path / "Test" / "t.parquet")
    with pytest.raises(pc.ProfilesError, match="does not produce"):
        pc.verify_names_used("Test", tmp_path)


@pytest.mark.parametrize("body, message", [
    (b",Ark,Site,,Mark,\n", "blank"),
    (b"a,,,,Mark,\n", "names nothing"),
    (b"a,Ark,A,,M,\na,Ark,B,,M,\n", "repeated"),
    ("a,Ark,Totten\u2013ham,,M,\n".encode("utf-8"), "ASCII"),
])
def test_names_file_refused(tmp_path, body, message):
    _write_names(tmp_path, body)
    pc._names_cache.clear()
    with pytest.raises(pc.ProfilesError, match=message):
        pc.load_names("Test", tmp_path)


def test_names_file_header_checked(tmp_path):
    (tmp_path / "Test").mkdir()
    (tmp_path / "Test" / "names.csv").write_text("id,name\na,b\n", encoding="ascii")
    pc._names_cache.clear()
    with pytest.raises(pc.ProfilesError, match="header"):
        pc.load_names("Test", tmp_path)


def test_every_real_table_carries_the_named_fields():
    import json
    for fam in ["Cables", "Transformers", "Generator", "Demands", "Interconnects"]:
        path = pc.PROFILES_ROOT / fam / "fields.json"
        for t in json.loads(path.read_text(encoding="ascii"))["tables"]:
            assert all(n in pc.load_spec(path, t).names for n in pc.NAMED_FIELDS), (fam, t)



def test_adding_a_null_column_does_not_change_the_hash(tmp_path):
    base = pc.load_spec(_spec_file(tmp_path, [_field("v")]), "t")
    (tmp_path / "w").mkdir()
    wider = pc.load_spec(_spec_file(tmp_path / "w", [_field("v"), _field("extra", "string", None, nullable=True)]), "t")
    row = pd.DataFrame({"profile_id": ["a"], "profile_rev": [0], "content_sha256": [""], "v": [1.5]})
    h1 = pc.content_hashes(row, base)[0]
    assert pc.content_hashes(row.assign(extra=[None]), wider)[0] == h1
    assert pc.content_hashes(row.assign(extra=["x"]), wider)[0] != h1
