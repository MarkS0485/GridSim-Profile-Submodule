"""Tests for build_cables, driven by small synthetic cable-lake frames."""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

import build_cables as bc
import profiles_common as pc

WHEN = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _row(cable_id, kv=33.0, element_class="circuit", **kw):
    base = {c: np.nan for c in bc.LAKE_COLUMNS}
    base.update({
        "cable_id": cable_id, "operator": "ukpn", "licence": "EPN", "voltage_kv": kv,
        "circuit_name": "Test", "circuit_code": "T1", "from_node": "A", "to_node": "B",
        "length_km_published": 2.0, "r_ohm": 0.4, "x_ohm": 0.8,
        "r_pct_100mva": 3.67, "x_pct_100mva": 7.35, "b_pct_100mva": 0.1,
        "r1_raw": 3.67, "x1_raw": 7.35, "b1_raw": 0.1, "impedance_base": "percent_on_100mva",
        "winter_rating_mva": 30.0, "summer_rating_mva": 27.0, "rating_mva": 30.0,
        "ohl_or_underground": "unknown", "status": "energised",
        "element_class": element_class, "evidence_source": "ltds.csv",
    })
    base.update(kw)
    return base


def _lake(*rows):
    return pd.DataFrame(list(rows), columns=bc.LAKE_COLUMNS)


def _spec(table):
    return pc.load_spec(bc.FIELDS_JSON, table)


def test_clean_circuit_values_and_gate():
    out = bc.prepare_circuits(_lake(_row("c1")), WHEN)
    pc.check(out, _spec("circuits"))
    r = out.iloc[0]
    assert r.r_ohm_per_km == pytest.approx(0.2)
    assert r.x_ohm_per_km == pytest.approx(0.4)
    assert r.x_over_r == pytest.approx(2.0)
    # 0.1 % on 100 MVA at 33 kV: 0.001 x 100 / 33^2 S = 91.827 uS
    assert r.b_us == pytest.approx(0.001 * 100 / 33.0 ** 2 * 1e6)
    assert r.b_us_per_km == pytest.approx(r.b_us / 2.0)
    assert r.quality_flags == "" and r.voltage_class == "33kv" and r.row_kind == "ltds_circuit"
    assert r.profile_id.startswith("cable-") and len(r.profile_id) == 22


def test_sentinel_impedance_nulled_but_reported_value_kept():
    out = bc.prepare_circuits(_lake(_row("c1", r_ohm=9999.0, r1_raw=9999.0)), WHEN)
    r = out.iloc[0]
    assert np.isnan(r.r_ohm) and np.isnan(r.x_ohm) and np.isnan(r.r_ohm_per_km)
    assert r.reported_r1 == 9999.0
    assert "sentinel_9999_impedance" in r.quality_flags


def test_sentinel_and_zero_ratings_nulled_and_flagged():
    out = bc.prepare_circuits(_lake(_row("c1", winter_rating_mva=9999.0, rating_mva=9999.0),
                                    _row("c2", summer_rating_mva=0.0)), WHEN)
    a, b = out.iloc[0], out.iloc[1]
    assert np.isnan(a.rating_winter_mva) and np.isnan(a.rating_mva) and a.rating_summer_mva == 27.0
    assert "sentinel_9999_rating_winter" in a.quality_flags
    assert np.isnan(b.rating_summer_mva) and "zero_rating_summer" in b.quality_flags


def test_zero_impedance_gives_no_per_km():
    r = bc.prepare_circuits(_lake(_row("c1", r_ohm=0.0, x_ohm=0.0)), WHEN).iloc[0]
    assert r.r_ohm == 0.0 and np.isnan(r.r_ohm_per_km) and np.isnan(r.x_over_r)
    assert "zero_impedance" in r.quality_flags


@pytest.mark.parametrize("length", [0.0, np.nan])
def test_no_length_flagged(length):
    r = bc.prepare_circuits(_lake(_row("c1", length_km_published=length)), WHEN).iloc[0]
    assert np.isnan(r.length_km) and np.isnan(r.r_ohm_per_km) and "no_length" in r.quality_flags


def test_unclassed_voltages_dropped():
    out = bc.prepare_circuits(_lake(_row("a", kv=22.0), _row("b", kv=11.5), _row("c", kv=11.0)), WHEN)
    assert out["source_key"].tolist() == ["c", "b"]        # sorted by voltage, 22kV dropped
    assert out["voltage_class"].tolist() == ["11kv", "11kv"] and out["voltage_kv"].tolist() == [11.0, 11.5]


def test_gis_circuit_uses_route_length_and_has_no_impedance():
    r = bc.prepare_circuits(_lake(_row("g1", kv=400.0, element_class="gis_circuit", length_km_published=np.nan,
                                       geom_length_km=12.5, r_ohm=np.nan, x_ohm=np.nan, r1_raw=np.nan,
                                       x1_raw=np.nan, b1_raw=np.nan, b_pct_100mva=np.nan)), WHEN).iloc[0]
    assert r.row_kind == "gis_circuit" and r.length_km == 12.5 and np.isnan(r.r_ohm_per_km)
    assert r.voltage_class == "400kv"


def test_shared_gis_ids_get_stable_segment_suffixes():
    rows = [_row("ssen:gis:X", kv=275.0, element_class="gis_circuit", geom_length_km=L, geometry_wkt=w)
            for L, w in ((5.0, "LINESTRING(1 1,2 2)"), (1.0, "LINESTRING(3 3,4 4)"))]
    rows.append(_row("ssen:gis:nan", kv=275.0, element_class="gis_circuit", geom_length_km=2.0))
    a = bc.prepare_circuits(_lake(*rows), WHEN)
    b = bc.prepare_circuits(_lake(*reversed(rows)), WHEN)     # input order must not matter
    assert a["source_key"].tolist() == b["source_key"].tolist()
    keys = set(a["source_key"])
    assert {"ssen:gis:X#seg00", "ssen:gis:X#seg01", "ssen:gis:nan"} == keys
    short = a[a.source_key == "ssen:gis:X#seg00"].iloc[0]
    assert short.length_km == 1.0 and "gis_segment_of_shared_id" in short.quality_flags
    assert "gis_feature_without_id" in a[a.source_key == "ssen:gis:nan"].iloc[0].quality_flags


def test_duplicate_ltds_ids_fail_loud():
    with pytest.raises(pc.ProfilesError, match="duplicate cable_id"):
        bc.prepare_circuits(_lake(_row("dup"), _row("dup")), WHEN)


def test_types_use_only_clean_ltds_rows_and_pass_gate():
    circuits = bc.prepare_circuits(_lake(
        _row("a", r_ohm=0.2), _row("b", r_ohm=0.4), _row("c", r_ohm=0.6),
        _row("bad", r_ohm=0.0, x_ohm=0.0),                     # flagged: excluded
        _row("ug", ohl_or_underground="underground", conductor_type="300mm XLPE")), WHEN)
    types = bc.build_types(circuits, WHEN)
    pc.check(types, _spec("types"))
    u = types[types.construction == "unknown"].iloc[0]
    assert u.n_circuits == 3 and u.r_ohm_per_km_p50 == pytest.approx(0.2)
    assert u.r_ohm_per_km_p10 == pytest.approx(0.12) and u.r_ohm_per_km_p90 == pytest.approx(0.28)
    assert "cabletype-33kv-underground-300mm-xlpe" in set(types.profile_id)


def test_spans_summary_and_gate():
    lake = _lake(*[_row(f"s{i}", kv=11.0, element_class="gis_span", geom_length_km=L,
                        ohl_or_underground="overhead") for i, L in enumerate([0.1, 0.2, 0.3])],
                 _row("nov", kv=np.nan, element_class="gis_span", geom_length_km=1.0))
    spans = bc.build_spans(lake, WHEN)
    pc.check(spans, _spec("spans"))
    assert len(spans) == 1
    s = spans.iloc[0]
    assert s.n_spans == 3 and s.total_route_km == pytest.approx(0.6) and s.span_km_p50 == pytest.approx(0.2)


def test_empty_summaries_have_spec_dtypes():
    pc.check(bc.build_types(bc.prepare_circuits(_lake(_row("x", kv=22.0)), WHEN), WHEN), _spec("types"))


def test_circuits_are_deterministic(tmp_path):
    lake = _lake(_row("b"), _row("a", kv=132.0), _row("c", kv=11.0))
    one = bc.prepare_circuits(lake, WHEN)
    two = bc.prepare_circuits(lake.iloc[::-1].reset_index(drop=True), WHEN)
    pd.testing.assert_frame_equal(one, two)
    p1, p2 = tmp_path / "Cables" / "1.parquet", tmp_path / "Cables" / "2.parquet"
    pc.write_profile(one, _spec("circuits"), p1)
    pc.write_profile(two, _spec("circuits"), p2)
    assert p1.read_bytes() == p2.read_bytes()


@pytest.mark.parametrize("base, r0, expected", [
    ("percent_on_100mva", 2.0, 2.0 / 100 * 33.0 ** 2 / 100),
    ("pu_on_100mva", 0.02, 0.02 * 33.0 ** 2 / 100),
    ("ohmic_referred", 0.7, 0.7),
])
def test_zero_sequence_to_ohms(base, r0, expected):
    r = bc.prepare_circuits(_lake(_row("c1", impedance_base=base, r0_raw=r0, x0_raw=r0 * 3)), WHEN).iloc[0]
    assert r.r0_ohm == pytest.approx(expected) and r.x0_ohm == pytest.approx(expected * 3)


def test_zero_sequence_sentinel_and_unknown_base():
    r = bc.prepare_circuits(_lake(_row("c1", r0_raw=9999.0, x0_raw=1.0)), WHEN).iloc[0]
    assert np.isnan(r.r0_ohm) and np.isnan(r.x0_ohm) and "sentinel_9999_zero_sequence" in r.quality_flags
    with pytest.raises(pc.ProfilesError, match="no conversion rule"):
        bc.prepare_circuits(_lake(_row("c1", impedance_base="furlongs")), WHEN)


def test_rate_a_is_winter_and_b_c_unpublished():
    r = bc.prepare_circuits(_lake(_row("c1")), WHEN).iloc[0]
    assert r.rate_a_mva == 30.0 and r.rate_a_basis == "winter continuous"
    assert np.isnan(r.rate_b_mva) and np.isnan(r.rate_c_mva) and pd.isna(r.rate_b_basis)
