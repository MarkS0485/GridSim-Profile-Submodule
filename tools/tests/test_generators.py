"""Tests for build_generators, driven by small synthetic registration, dynamics
and station tables."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

import build_generators as bg
import profiles_common as pc

UTC = timezone.utc
WHEN = datetime(2026, 9, 1, tzinfo=UTC)
START = WHEN - timedelta(days=365)
H = {"NUCLEAR": 4.5, "CCGT": 5.0, "OCGT": 3.0, "COAL": 4.0, "BIOMASS": 4.0, "PS": 3.0, "NPSHYD": 3.0}


def _spec(table):
    return pc.load_spec(bg.FIELDS_JSON, table)


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def test_h_by_fuel_is_read_from_gda():
    h = bg.load_h_by_fuel()
    assert h["CCGT"] > 0 and h["NUCLEAR"] > 0 and "WIND" not in h


def test_machine_columns_apply_the_80_percent_rule():
    m = bg.machine_columns(pd.Series([400.0, 0.0, np.nan]), pd.Series([5.0, 5.0, np.nan]))
    assert m["max_rating_mw"].tolist()[0] == 500.0 and m["thermal_headroom_mw"].tolist()[0] == 100.0
    assert np.isnan(m["max_rating_mw"].tolist()[1])               # no capacity, no rule value
    assert m["stored_energy_s_mva"].tolist()[0] == pytest.approx(5.0 * 400 / 0.9)
    assert m["rated_mva_assumed"].tolist()[0] == 400 / 0.9
    assert m["pole_count"].isna().all() and np.isnan(m["co2_t_per_mwh"]).all()


def test_ramp_stats():
    r = pd.DataFrame({"bmUnit": ["A", "A", "A", "B"], "rate1": [10.0, 4.0, 6.0, 1.0],
                      "rate2": [1.0, 20.0, 2.0, np.nan], "rate3": [5.0, 5.0, 0.0, np.nan]})
    s = bg.ramp_stats(r, "up")
    assert s.loc["A", "up_p50"] == 10.0                        # fastest bands 10, 20, 6
    assert s.loc["A", "up_slowest_p50"] == 2.0                  # slowest positive bands 1, 4, 2
    assert s.loc["A", "up_n"] == 3 and s.loc["B", "up_p50"] == 1.0


@pytest.mark.parametrize("q, expected", [(0.5, 0.2), (0.99, 0.5), (0.01, 0.0)])
def test_histogram_quantile_nearest_rank(q, expected):
    # values 0.0 x2, 0.1, 0.2 x3, 0.3, 0.5 (8 readings) as 0.1 MW bins
    h = pd.Series({0: 2, 1: 1, 2: 3, 3: 1, 5: 1})
    assert bg.histogram_quantile(h, q) == pytest.approx(expected)


# --------------------------------------------------------------------------- #
# BM units
# --------------------------------------------------------------------------- #

def _ref(*rows):
    base = {"nationalGridBmUnit": "X-1", "elexonBmUnit": "T_X-1", "fuelType": "CCGT", "leadPartyName": "P",
            "bmUnitType": "T", "bmUnitName": "X", "demandCapacity": "0.000", "generationCapacity": "400.000",
            "transmissionLossFactor": "0.01", "gspGroupName": "South Wales"}
    return pd.DataFrame([{**base, **r} for r in (rows or ({},))])


def _dyn(units):
    cols = ["up_p50", "up_p90", "up_slowest_p50", "up_n", "down_p50", "down_p90", "down_slowest_p50", "down_n",
            "imp_up_p50", "imp_up_p90", "imp_up_slowest_p50", "imp_up_n", "imp_down_p50", "imp_down_p90",
            "imp_down_slowest_p50", "imp_down_n", "sel", "sil", "ndz", "mzt", "mnzt", "mel_max", "mel_p50"]
    return pd.DataFrame({c: [7.0] * len(units) for c in cols}, index=units)


def _met(units):
    return pd.DataFrame({"metered_periods": [100] * len(units), "out_mean": [200.0] * len(units),
                         "out_p50": [210.0] * len(units), "out_p99": [390.0] * len(units),
                         "out_max": [401.0] * len(units)}, index=units)


def test_bm_units_join_and_gate():
    ref = _ref({}, {"elexonBmUnit": "T_N-1", "fuelType": "NUCLEAR"},
               {"elexonBmUnit": "I_IFA", "fuelType": "INTFR"},                      # interconnector: out
               {"elexonBmUnit": "2__SUP", "fuelType": None, "generationCapacity": "0"},  # supplier: out
               {"elexonBmUnit": "E_SOLAR", "fuelType": None, "generationCapacity": "12"})
    out, dyn, notes = bg.build_bm_units(ref, _dyn(["T_X-1"]), _met(["T_X-1", "T_N-1"]), H, WHEN, START)
    pc.check(out, _spec("bm_units"))
    pc.check(dyn, _spec("bm_dynamics"))
    assert set(out.bmu_id) == {"T_X-1", "T_N-1", "E_SOLAR"} and set(dyn.bmu_id) == set(out.bmu_id)
    assert notes == {"repeat_records_dropped": 0, "interconnector_units_left_for_interconnects": 1,
                     "units_without_fuel_or_generation_capacity": 1}
    x = out.set_index("bmu_id")
    d = dyn.set_index("bmu_id")
    assert x.loc["T_X-1", "fuel_folder"] == "Gas" and x.loc["T_X-1", "inertia_h_s"] == 5.0
    assert d.loc["T_X-1", "capacity_factor"] == 0.5 and x.loc["T_X-1", "max_rating_mw"] == 500.0
    assert x.loc["T_X-1", "quality_flags"] == "" and d.loc["T_X-1", "quality_flags"] == ""
    assert d.loc["T_X-1", "dynamics_window_end_utc"] == WHEN and d.loc["T_X-1", "ramp_notifications"] == 14
    assert x.loc["T_N-1", "inertia_h_s"] == 4.5 and "no_dynamic_data" in d.loc["T_N-1", "quality_flags"]
    assert x.loc["E_SOLAR", "fuel_folder"] == "Unclassified" and np.isnan(x.loc["E_SOLAR", "inertia_h_s"])
    assert "no_fuel_type" in x.loc["E_SOLAR", "quality_flags"]
    assert "no_metered_output" in d.loc["E_SOLAR", "quality_flags"]
    assert not any(c in out.columns for c in ("capacity_factor", "ramp_up_mw_per_min_p50"))   # observed kept apart


def test_wind_has_no_inertia():
    out, _, _ = bg.build_bm_units(_ref({"fuelType": "WIND"}), _dyn([]), _met([]), H, WHEN, START)
    assert out.iloc[0].fuel_folder == "Wind" and np.isnan(out.iloc[0].inertia_h_s)


def test_unknown_elexon_fuel_fails_loud():
    with pytest.raises(pc.ProfilesError, match="no Generator folder"):
        bg.build_bm_units(_ref({"fuelType": "FUSION"}), _dyn([]), _met([]), H, WHEN, START)


# --------------------------------------------------------------------------- #
# Stations
# --------------------------------------------------------------------------- #

def _dukes(*rows):
    base = {"company_name": "C", "site_name": "Site", "technology": "Fossil Fuel", "type": "CCGT", "chp": "No",
            "primary_fuel": "Natural Gas", "secondary_fuel": None, "installedcapacity_mw": 800.0,
            "region": "Wales", "postcode": "CF1", "x_coordinate": 300000.0, "y_coordinate": 200000.0,
            "year_commissioned": 2001, "desnz_site_code": "S1"}
    return pd.DataFrame([{**base, **r} for r in (rows or ({},))])


def _repd(*rows):
    base = {"ref_id": 1, "site_name": "Farm", "operator_or_applicant": "O", "technology_type": "Wind Onshore",
            "chp_enabled": None, "development_status_short": "Operational", "installed_capacity_mwelec": 30.0,
            "operational": pd.Timestamp("2015-06-01"), "region": "Scotland", "x_coordinate": 1.0,
            "y_coordinate": 2.0, "post_code": "AB1", "no_of_turbines": 10.0, "turbine_capacity_mw": 3.0}
    return pd.DataFrame([{**base, **r} for r in (rows or ({},))])


GEO = pd.DataFrame({"asset_id": ["repd:1", "dukes:Site"], "source": ["repd", "dukes"],
                    "dno_license_area": ["SHEPD", "SWALES"], "gsp_region": ["G1", "G2"]})


def _stations(dukes, repd, geo=GEO):
    out, notes = bg.build_stations(dukes, repd, geo, H, WHEN, "DUKES/x.parquet", "REPD/y.parquet")
    pc.check(out, _spec("stations"))
    return out, notes


def test_stations_folders_inertia_and_geography():
    out, notes = _stations(
        _dukes({}, {"desnz_site_code": "S2", "site_name": "Peaker", "type": "Single cycle"},
               {"desnz_site_code": "S3", "site_name": "Heat", "chp": "Yes"}),
        _repd({}, {"ref_id": 2, "technology_type": "Battery", "development_status_short": "Awaiting Construction"},
              {"ref_id": 3, "development_status_short": "Application Refused"},
              {"ref_id": 4, "technology_type": "Air Source Heat Pumps"}))
    x = out.set_index("source_key")
    assert x.loc["dukes:S1", "fuel_folder"] == "Gas" and x.loc["dukes:S1", "inertia_h_s"] == 5.0
    assert x.loc["dukes:S2", "inertia_h_s"] == 3.0                     # single cycle -> OCGT H
    assert x.loc["dukes:S3", "fuel_folder"] == "OtherThermal/CHP" and np.isnan(x.loc["dukes:S3", "inertia_h_s"])
    assert x.loc["repd:1", "fuel_folder"] == "Wind" and x.loc["repd:1", "year_commissioned"] == 2015
    assert x.loc["repd:1", "dno_licence_area"] == "SHEPD" and x.loc["repd:1", "turbines"] == 10
    assert x.loc["repd:2", "fuel_folder"] == "Storage" and x.loc["repd:2", "development_status"] == "Awaiting Construction"
    assert "repd:3" not in x.index and "repd:4" not in x.index
    assert notes["repd_rows_left_out_by_status"] == {"Application Refused": 1}
    assert notes["repd_rows_left_out_not_generation"] == 1
    assert x.loc["repd:1", "profile_id"] == "gen-repd-1"


def test_repd_chp_flag_any_case():
    out, _ = _stations(_dukes(), _repd({"chp_enabled": "yes", "technology_type": "Biomass (dedicated)"}))
    assert out.set_index("source_key").loc["repd:1", "fuel_folder"] == "OtherThermal/CHP"


@pytest.mark.parametrize("dukes, repd, message", [
    ({"primary_fuel": "Unobtainium"}, {}, "DUKES fuels"),
    ({}, {"technology_type": "Perpetual Motion"}, "REPD technologies"),
])
def test_unknown_station_categories_fail_loud(dukes, repd, message):
    with pytest.raises(pc.ProfilesError, match=message):
        bg.build_stations(_dukes(dukes), _repd(repd), GEO, H, WHEN, "d", "r")


def test_ambiguous_geography_is_not_used():
    geo = pd.concat([GEO, GEO.iloc[[0]]], ignore_index=True)        # repd:1 twice
    out, _ = _stations(_dukes(), _repd(), geo)
    assert pd.isna(out.set_index("source_key").loc["repd:1", "dno_licence_area"])


def test_latest_snapshot(tmp_path):
    for d in ("2026-07-01", "2026-08-03", "2026-09-29"):
        p = tmp_path / f"snapshot_date={d}"
        p.mkdir()
        (p / "x.parquet").write_bytes(b"")
    got = pc.latest_snapshot(tmp_path, "snapshot_date=*/*.parquet", "snapshot_date", WHEN)
    assert got.parent.name == "snapshot_date=2026-08-03"
    with pytest.raises(pc.ProfilesError, match="no .* snapshot"):
        pc.latest_snapshot(tmp_path, "snapshot_date=*/*.parquet", "snapshot_date", datetime(2026, 1, 1, tzinfo=UTC))


def _fake_b1610(tmp_path, days):
    """A fake lake with b1610 files: one file per day, unit A at 100 MW, unit B
    stepping 0, 10, 20 ... MW (quantity is MWh per half-hour, so MW / 2)."""
    for i, day in enumerate(days):
        folder = tmp_path / "Elexon" / "Parquet" / "b1610" / f"year={day.year}" / f"week={day.isocalendar()[1]:02d}"
        folder.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({
            "bmUnit": ["T_A", "T_B"],
            "halfHourEndTime": pd.Series([day, day], dtype="datetime64[us, UTC]"),
            "quantity": [50.0, 5.0 * i],
        }).to_parquet(folder / f"b1610_{day:%Y%m%d}.parquet")


def test_metered_streams_files_and_folds_batches(tmp_path):
    days = [WHEN - timedelta(days=d) for d in range(40, 0, -1)]     # 40 files: more than one 30-file batch
    _fake_b1610(tmp_path, days)
    m = bg.metered(tmp_path, START, WHEN)
    assert m.loc["T_A", "metered_periods"] == 40 and m.loc["T_A", "out_mean"] == 100.0
    assert m.loc["T_A", "out_p50"] == pytest.approx(100.0) and m.loc["T_A", "out_max"] == 100.0
    b = np.arange(40) * 10.0                                         # 0, 10, ... 390 MW
    assert m.loc["T_B", "out_mean"] == pytest.approx(b.mean()) and m.loc["T_B", "out_max"] == 390.0
    assert m.loc["T_B", "out_p50"] == pytest.approx(190.0)          # nearest rank: 20th of 40
    assert m.loc["T_B", "out_p99"] == pytest.approx(390.0)


def test_metered_ignores_readings_outside_window(tmp_path):
    _fake_b1610(tmp_path, [START - timedelta(days=1), WHEN + timedelta(hours=1), WHEN])
    m = bg.metered(tmp_path, START, WHEN)
    assert m.loc["T_A", "metered_periods"] == 1


def _fake_dataset(tmp_path, name, frame, day):
    folder = tmp_path / "Elexon" / "Parquet" / name / f"year={day.year}" / f"week={day.isocalendar()[1]:02d}"
    folder.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(folder / f"{name}_{day:%Y%m%d}.parquet")


def test_read_elexon_is_lean_and_stats_use_string_index(tmp_path):
    d1, d2 = WHEN - timedelta(days=10), WHEN - timedelta(days=3)
    for day, units, levels in ((d1, ["T_B", "T_A"], [10.0, 1.0]), (d2, ["T_C", "T_A"], [7.0, 3.0])):
        _fake_dataset(tmp_path, "sel", pd.DataFrame({
            "bmUnit": units, "level": levels,
            "time": pd.Series([day, day], dtype="datetime64[us, UTC]")}), day)
    r = bg.read_elexon(tmp_path, "sel", ["level"], "time", START, WHEN)
    assert list(r.columns) == ["bmUnit", "level"] and isinstance(r["bmUnit"].dtype, pd.CategoricalDtype)
    m = bg.median_by_unit(r, "level", "sel")
    assert m.to_dict() == {"T_A": 2.0, "T_B": 10.0, "T_C": 7.0} and list(m.index) == ["T_A", "T_B", "T_C"]
    rates = pd.DataFrame({"bmUnit": pd.Categorical(["T_B", "T_A"]), "rate1": [1.0, 2.0],
                          "rate2": [np.nan, 4.0], "rate3": [np.nan, np.nan]})
    s = bg.ramp_stats(rates, "up")
    assert list(s.index) == ["T_A", "T_B"] and s.loc["T_A", "up_p50"] == 4.0


def test_unit_without_elexon_id_keyed_by_ng_id():
    ref = _ref({"elexonBmUnit": None, "nationalGridBmUnit": "ACHYW-1", "fuelType": "WIND",
                "generationCapacity": None})
    out, dyn, _ = bg.build_bm_units(ref, _dyn([]), _met([]), H, WHEN, START)
    pc.check(out, _spec("bm_units"))
    r = out.iloc[0]
    assert r.bmu_id == "ng:ACHYW-1" and r.profile_id == "gen-bmu-ng-achyw-1"
    assert "no_elexon_registration" in r.quality_flags and dyn.iloc[0].bmu_id == "ng:ACHYW-1"


def test_unit_with_no_id_fails_loud():
    with pytest.raises(pc.ProfilesError, match="neither an Elexon nor a National Grid id"):
        bg.build_bm_units(_ref({"elexonBmUnit": None, "nationalGridBmUnit": None}), _dyn([]), _met([]),
                          H, WHEN, START)


def test_exact_repeat_dropped_but_conflicting_repeat_fails():
    out, _, notes = bg.build_bm_units(_ref({"eic": "A"}, {"eic": "B"}), _dyn([]), _met([]), H, WHEN, START)
    assert len(out) == 1 and notes["repeat_records_dropped"] == 1     # differs only in a field not used
    with pytest.raises(pc.ProfilesError, match="duplicate"):
        bg.build_bm_units(_ref({}, {"generationCapacity": "401.000"}), _dyn([]), _met([]), H, WHEN, START)


def test_dynamics_flags_999_ramp_and_output_above_rule():
    dyn_in = _dyn(["T_X-1"])
    dyn_in.loc["T_X-1", "up_p90"] = 999.0
    met = _met(["T_X-1"])
    met.loc["T_X-1", "out_max"] = 520.0                     # capacity 400 -> rule max 500
    _, dyn, _ = bg.build_bm_units(_ref({}), dyn_in, met, H, WHEN, START)
    f = dyn.iloc[0].quality_flags
    assert "ramp_rate_999_notified" in f and "output_above_rule_max_rating" in f
