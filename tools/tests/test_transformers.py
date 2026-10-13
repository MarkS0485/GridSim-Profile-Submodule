"""Tests for build_transformers, driven by small synthetic source tables shaped
like each operator's published LTDS Table 2."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

import build_transformers as bt
import profiles_common as pc

UTC = timezone.utc
WHEN = datetime(2026, 9, 1, tzinfo=UTC)


def _spec(table):
    return pc.load_spec(bt.FIELDS_JSON, table)


def _ukpn_2w(**kw):
    row = {"GridSupplyPoint": "BARKING", "HV_Node": "H1", "HV_Substation": "Barking", "Voltage_HV (kV)": 33.0,
           "LV_Node": "L1", "LV_Substation": "Barking 11", "Voltage_LV (kV)": 11.0, "Vector_Group": "Dyn11",
           "Positive_Sequence_Impedance_R_Percent": 4.0, "Positive_Sequence_Impedance_X_Percent": 100.0,
           "Zero_Sequence_Impedance_X_Percent": 95.0, "Tap_Range_Max_Percent": 110.0,
           "Tap_Range_Min_Percent": 85.0, "Transformer_Rating_MVA_Winter": 20.0,
           "Transformer_Rating_MVA_Summer": 18.0, "Reverse_Power_Capability_Percent": 50.0,
           "Method_of_Earthing_HV": "Solid", "Method_of_Earthing_LV": "Resistance",
           "SiteFunctionalLocation": "X", "LicenceArea": "Eastern Power Networks (EPN)", "ID": 7}
    row.update(kw)
    return pd.DataFrame([row])


def _npg(**kw):
    row = {"S/S Group": "G", "S/S or Busbar Name Node": "KILLINGHALL ROAD", "Primary Voltage (kV)": 33.0,
           "Secondary Voltage (kV)": 11.0, "Vector Group": "Dyn11",
           "Positive Sequence Impedance R (% on 100 MVA Base)": 4.0,
           "Positive Sequence Impedance X (% on 100 MVA Base)": 80.0,
           "Zero Sequence Reactance X (% on 100 MVA Base)": 70.0, "Minimum Tap %": -15.0,
           "Maximum Tap %": 10.0, "Transformer Rating (MVA)": 24.0,
           "Reverse Power Capability (MVA)": "NOT KNOWN", "Method of Earthing": "Solid", "License": "Yorkshire"}
    row.update(kw)
    return pd.DataFrame([row])


def _nged(three=False, **kw):
    row = {"Licence": "EMIDS", "GSP Group": "G", "Node 1": "MELT3", "Operating Voltage 1": "33",
           "Node 2": "MELT1", "Operating Voltage 2": "11", "Status": "Removed", "Vector Group": "Dyn11",
           "R1": "5.0", "Min Tap": "-12", "Max Tap": "4", "Nominal Rating": "12",
           "Emergency Rating": "19", "Reverse Power Capability": "-", "Method of Earthing": "Solid"}
    if three:
        row.update({"Node 3": "MELT6", "Operating Voltage 3": "6.6", "X1 HV-LV": "100", "X1 LV-Tertiary": "50",
                    "X1 HV-Tertiary": "60", "X0 HV-LV": "90"})
    else:
        row.update({"X1": "109.168", "X0": "92.79"})
    row.update(kw)
    return pd.DataFrame([row])


def _units(*raws):
    out, dropped = bt.finish_units(pd.concat(raws, ignore_index=True), WHEN)
    pc.check(out, _spec("units"))
    return out, dropped


# --------------------------------------------------------------------------- #
# Units
# --------------------------------------------------------------------------- #

def test_ukpn_two_winding():
    u, _ = _units(bt.read_ukpn_2w(_ukpn_2w()))
    r = u.iloc[0]
    assert r.source_key == "ukpn:2a:7" and r.licence == "EPN" and r.winding_count == 2
    assert r.x_pct_100mva == 100.0 and r.x_pct_on_rating == pytest.approx(20.0)   # 100 % on 100 MVA at 20 MVA
    assert r.r_pct_on_rating == pytest.approx(0.8) and r.x_over_r == pytest.approx(25.0)
    assert (r.tap_min_pct, r.tap_max_pct, r.tap_range_pct) == (-15.0, 10.0, 25.0)
    assert (r.reported_tap_min, r.reported_tap_max) == (85.0, 110.0)
    assert r.reported_tap_convention == "percent_of_nominal_ratio"
    assert r.reverse_power_unit == "%" and r.status is None
    assert r.quality_flags == "convention_inferred" and r.voltage_class == "33kv"


def test_npg_is_documented_100mva_and_unflagged():
    u, _ = _units(bt.read_npg(_npg()))
    r = u.iloc[0]
    assert r.licence == "NPGY" and r.hv_node == "KILLINGHALL ROAD" and r.quality_flags == ""
    assert r.x_pct_on_rating == pytest.approx(80.0 * 24.0 / 100)
    assert (r.tap_min_pct, r.tap_max_pct) == (-15.0, 10.0)
    assert np.isnan(r.reverse_power_reported) and r.reverse_power_unit == "MVA"


def test_nged_two_and_three_winding():
    u, _ = _units(bt.read_nged(_nged(), three_winding=False), bt.read_nged(_nged(three=True), three_winding=True))
    two = u[u.winding_count == 2].iloc[0]
    three = u[u.winding_count == 3].iloc[0]
    assert two.status == "out" and two.licence == "EMID" and "convention_inferred" in two.quality_flags
    assert two.x_pct_on_rating == pytest.approx(109.168 * 12 / 100)
    assert three.tertiary_kv == 6.6 and three.x_lv_tert_pct_100mva == 50.0 and three.x_hv_tert_pct_100mva == 60.0
    assert three.source_key == "nged:2b:row0"


def test_no_rating_keeps_100mva_values_but_not_on_rating():
    u, _ = _units(bt.read_npg(_npg(**{"Transformer Rating (MVA)": 0.0})))
    r = u.iloc[0]
    assert r.x_pct_100mva == 80.0 and np.isnan(r.x_pct_on_rating) and np.isnan(r.rating_mva)
    assert "no_rating" in r.quality_flags


def test_unclassed_and_missing_voltages_dropped_and_counted():
    u, dropped = _units(bt.read_npg(_npg(**{"Primary Voltage (kV)": 22.0})),
                        bt.read_npg(_npg(**{"Secondary Voltage (kV)": "NOT KNOWN"})),
                        bt.read_ukpn_2w(_ukpn_2w(**{"Voltage_HV (kV)": 33.2})))
    assert len(u) == 1 and u.iloc[0].voltage_class == "33kv" and u.iloc[0].hv_kv == 33.2
    assert dropped == {"no_winding_voltage": 1, "hv_voltage_has_no_folder": {"22.0": 1}}


def test_unknown_licence_fails_loud():
    with pytest.raises(pc.ProfilesError, match="unknown licence"):
        bt.read_ukpn_2w(_ukpn_2w(LicenceArea="Mars Power Networks"))


def test_ukpn_tap_out_of_band_fails_loud():
    with pytest.raises(pc.ProfilesError, match="outside 50-150"):
        _units(bt.read_ukpn_2w(_ukpn_2w(Tap_Range_Min_Percent=-15.0)))


def test_unknown_impedance_base_fails_loud():
    raw = bt.read_npg(_npg())
    raw["reported_impedance_base"] = "ohmic_referred"
    with pytest.raises(pc.ProfilesError, match="no conversion rule"):
        bt.finish_units(raw, WHEN)


def test_duplicate_source_key_fails_loud():
    with pytest.raises(pc.ProfilesError, match="duplicate"):
        _units(bt.read_ukpn_2w(_ukpn_2w()), bt.read_ukpn_2w(_ukpn_2w()))


def test_temperatures_are_null_placeholders():
    u, _ = _units(bt.read_npg(_npg()))
    assert u["winding_temp_max_degc"].isna().all() and u["top_oil_temp_max_degc"].isna().all()


@pytest.mark.parametrize("value, status", [("Removed", "out"), ("Updated", "energised"), ("New", "energised"),
                                           ("Proposed", "planned"), ("-", "unknown"), ("", "unknown"),
                                           (None, "unknown"), ("Mystery", "unknown")])
def test_norm_status(value, status):
    assert pc.norm_status(value) == status


# --------------------------------------------------------------------------- #
# Observed tables
# --------------------------------------------------------------------------- #

def _taps(end="2026-08-01 00:00:00+00:00"):
    return pd.DataFrame([{"gsp": "BARKING C (EPN)", "sgt": "SGT1", "vnom_kv": 132.0, "n_obs": 100,
                          "span_start": "2023-04-01 00:00:00+00:00", "span_end": end, "step_kv": 1.3,
                          "step_pct": 1.0, "n_visible_steps": 8, "span_steps": 8.0, "lattice_residual": 0.2,
                          "is_oltc": True, "ltds_tap_span_pct": 31.0, "ltds_expected_steps": 30.0}])


def test_taps_after_last_updated_excluded():
    ok, excluded = bt.build_taps(_taps(), WHEN)
    pc.check(ok, _spec("taps"))
    assert ok.iloc[0].profile_id == "tap-barking-c-epn-sgt1" and excluded == 0
    late, excluded = bt.build_taps(_taps(end="2026-09-02 00:00:00+00:00"), WHEN)
    assert len(late) == 0 and excluded == 1
    pc.check(late, _spec("taps"))


def _readings(mw, start, step=timedelta(minutes=30), sub="S1", tx="T1"):
    n = len(mw)
    return pd.DataFrame({
        "DATETIME": pd.Series([start + i * step for i in range(n)], dtype="datetime64[ns, UTC]"),
        "dno": "ukpn", "region": "ukpn_sgt", "substation": sub, "transformer": tx,
        "MW": np.array(mw, dtype="float64"), "MVAr": np.zeros(n), "MVA": np.abs(np.array(mw, dtype="float64")),
        "kV": np.full(n, np.nan), "power_factor": np.ones(n)})


def test_flows_window_and_statistics():
    # 400 days of daily readings; only the last 365 days count. Values run 0..399.
    start = WHEN - timedelta(days=399)
    r = _readings(list(range(400)), start, step=timedelta(days=1))
    f = bt.build_flows(r, WHEN)
    pc.check(f, _spec("flows"))
    row = f.iloc[0]
    assert row.n_obs == 365 and row.p_mw_min == 35.0 and row.p_mw_max == 399.0
    assert row.p_mw_p50 == pytest.approx(np.quantile(np.arange(35, 400), 0.5))
    assert row.window_end_utc == WHEN and row.zero_flow_share == 0.0


def test_flows_ignore_readings_after_last_updated_and_count_reverse_flow():
    r = pd.concat([_readings([-5.0, 0.0, 5.0, 10.0], WHEN - timedelta(hours=2)),
                   _readings([999.0], WHEN + timedelta(hours=1))], ignore_index=True)
    # the four readings run WHEN-2h .. WHEN-0.5h (all kept); the 999 at WHEN+1h is dropped
    row = bt.build_flows(r, WHEN).iloc[0]
    assert row.p_mw_max == 10.0 and row.n_obs == 4
    assert row.reverse_flow_share == 0.25 and row.zero_flow_share == 0.25


def test_flows_are_per_transformer_with_own_windows():
    old = _readings([1.0, 2.0], datetime(2022, 3, 1, tzinfo=UTC), sub="OLD")
    new = _readings([3.0, 4.0], WHEN - timedelta(days=1), sub="NEW")
    f = bt.build_flows(pd.concat([old, new], ignore_index=True), WHEN)
    assert set(f.substation) == {"OLD", "NEW"}
    assert f.set_index("substation").loc["OLD", "window_end_utc"].year == 2022


def test_stress_flags_and_exclusion():
    raw = pd.DataFrame([{"asset_id": "ukpn:sgt:NORWICH:SGT4", "asset_name": "NORWICH SGT4",
                         "asset_type": "sgt_ukpn", "operator": "ukpn", "voltage_kv": 132.0,
                         "tap_ops_last_6mo": 10.0, "tap_ops_prior_2yr": 40.0, "tap_rate_anomaly_ratio": 1.0,
                         "hours_over_80pct": np.nan, "thermal_exceedance_flag": np.nan, "worst_loading_pct": np.nan,
                         "tap_step_kv": 0.57, "tap_step_source": "tap_changers", "tap_ops_total": 100.0,
                         "window_start": "2022-01-01T00:00:00+00:00", "window_end": "2026-08-08T04:39:57+00:00"}])
    s, excluded = bt.build_stress(raw, WHEN)
    pc.check(s, _spec("stress"))
    assert excluded == 0 and s.iloc[0].profile_id == "stress-ukpn-sgt-norwich-sgt4"
    assert pd.isna(s.iloc[0].thermal_exceedance)
    raw.loc[0, "thermal_exceedance_flag"] = 1.0
    assert bool(bt.build_stress(raw, WHEN)[0].iloc[0].thermal_exceedance) is True
    raw.loc[0, "window_end"] = "2026-09-05T00:00:00+00:00"
    assert bt.build_stress(raw, WHEN)[1] == 1


def test_rates_by_operator():
    u, _ = _units(bt.read_ukpn_2w(_ukpn_2w()), bt.read_nged(_nged(), three_winding=False), bt.read_npg(_npg()))
    x = u.set_index("operator")
    assert x.loc["ukpn", "rate_a_mva"] == 20.0 and x.loc["ukpn", "rate_a_basis"] == "winter continuous"
    assert np.isnan(x.loc["ukpn", "rate_c_mva"]) and pd.isna(x.loc["ukpn", "rate_c_basis"])
    assert x.loc["nged", "rate_a_mva"] == 12.0 and x.loc["nged", "rate_c_mva"] == 19.0
    assert x.loc["nged", "rate_c_basis"] == "emergency (duration not stated)"
    assert x.loc["npg", "rate_a_basis"] == "continuous (season not stated)"
    assert u["rate_b_mva"].isna().all()
