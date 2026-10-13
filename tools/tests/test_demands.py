"""Tests for build_demands: the site classifier (positives, exclusions and rule
order) and the load-centre readers."""

from datetime import datetime, timezone

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import build_demands as bd
import profiles_common as pc

WHEN = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _spec(table):
    return pc.load_spec(bd.FIELDS_JSON, table)


# --------------------------------------------------------------------------- #
# Classifier
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name, site, rtype, folder", [
    ("Gloucestershire hospitals nhs foundation trust", "Cheltenham general hospital", "large_demand", "Hospitals"),
    ("CHRISTIE NHS TRUST", "Proton beam", "der", "Hospitals"),
    # specific before general: a university hospital is a hospital
    ("Nottingham university hospitals nhs trust", "Queens medical centre", "generation", "Hospitals"),
    ("Kings College Hospital", "Kings College Hospital", "generation", "Hospitals"),
    ("Devonport royal dockyard limited", "Plymouth devonport royal dockyard", "der", "Military/Naval"),
    ("Defence infrastructure organisation", "Imjin barracks", "der", "Military/Land"),
    ("Ministry of defence", "Newquay raf st mawgan intake", "der", "Military/Land"),
    ("Specialist computer centres plc", "Cole valley data centre", "solar", "Datacentres"),
    ("Tower Hamlets datacentres", None, "datacentre", "Datacentres"),
    ("University of birmingham", "Edgbaston", "generation", "Universities"),
    # a university building at the docks is a university (port is tried last)
    ("University of wales trinity saint david", "Innovation matrix, swansea docks", "der", "Universities"),
    ("Nottingham college", "Basford hall college", "solar", "Colleges"),
    ("Benfield School PV", "Benfield School PV", "solar", "Schools"),
    ("Associated british ports", "Port of swansea", "der", "Port"),
    ("Port of Tillbury London Limited", "Tilbury Freeport", "storage", "Port"),
])
def test_classify_positives(name, site, rtype, folder):
    assert bd.classify(name, site, rtype)[0] == folder


@pytest.mark.parametrize("name, site", [
    ("School farm solar park limited", "School farm"),                 # generation project
    ("Croome airfield solar limited", "Croome airfield solar farm"),
    ("Port of Tyne BESS", "Port of Tyne BESS"),
    ("Thameswey", "Land Off Board School Road"),                       # place name
    ("University of Hertfordshire", "College Lane"),                  # university, not a college
    ("Barracks farm ltd", "Barracks farm wind turbine"),
    ("Treloy touring park", "nr raf st mawgan"),
    ("LAND SECURITIES PROPERTIES LIMITED", "MOD 3A"),
    ("Biomass uk no 2 limited", "Barry docks"),
    ("Newport city council", "Docks way waste disposal site"),
    ("South west water ltd", "Falmouth docks stw"),
    ("Coldharbour farm", "Coldharbour"),                               # no word boundary
    ("Teesside Renewable Energy Plant", "Port Clarence"),
])
def test_classify_exclusions(name, site):
    folder, _ = bd.classify(name, site, "der")
    assert folder in (None, "Universities"), (name, site, folder)


def test_university_on_college_lane_is_a_university():
    assert bd.classify("University of Hertfordshire", "College Lane", "der")[0] == "Universities"


def test_match_rule_names_the_rule_and_text():
    assert bd.classify("X", "Cheltenham general hospital", "der")[1] == "hospital: hospital"


@pytest.mark.parametrize("mw, band", [(214.0, "Datacentres/Hyperscale"), (50.0, "Datacentres/Hyperscale"),
                                      (49.9, "Datacentres/Other"), (5.0, "Datacentres/Other"),
                                      (4.99, "Datacentres/SME")])
def test_datacentre_bands(mw, band):
    assert bd.datacentre_band(mw) == band


def _consumers(*rows):
    base = {"consumer_id": "c1", "name": "Some hospital", "site": "Site", "type": "large_demand",
            "import_mw": 10.0, "export_mw": 1.0, "storage_mwh": np.nan, "poc_voltage_kv": 11.0,
            "gsp_name": "G", "bsp": "B", "primary": "P", "easting": 1.0, "northing": 2.0, "postcode": "AB1",
            "local_authority": "LA", "connection_status": "connected", "energy_tech": "Large Demand",
            "evidence_source": "UKPN/Large_Demand_List"}
    return pd.DataFrame([{**base, **r} for r in (rows or ({},))])


def test_build_sites_import_rule_bands_and_gate():
    out, notes = bd.build_sites(_consumers(
        {},
        {"consumer_id": "c2", "import_mw": np.nan},                                  # no import: out
        {"consumer_id": "c3", "name": "Big data centre", "import_mw": 80.0},
        {"consumer_id": "c4", "name": "Ealing datacentres", "type": "datacentre", "import_mw": 30.0,
         "evidence_source": "UKPN/Data_Centres_by_Local_Authority"},
        {"consumer_id": "c5", "name": "Corner shop", "import_mw": 1.0},              # no rule: out
        {"consumer_id": "c6", "poc_voltage_kv": np.nan}), WHEN)
    pc.check(out, _spec("sites"))
    x = out.set_index("source_key")
    assert set(x.index) == {"c1", "c3", "c4", "c6"}
    assert x.loc["c3", "site_type"] == "Datacentres/Hyperscale"
    assert x.loc["c4", "site_type"] == "Datacentres/ByLocalAuthority"
    assert x.loc["c6", "quality_flags"] == "no_poc_voltage"
    assert notes["matched_without_import_capacity"] == {"Hospitals": 1}
    assert out[["base_load_mw", "crane_peak_mw", "shore_power_peak_mw"]].isna().all().all()


# --------------------------------------------------------------------------- #
# Load centres
# --------------------------------------------------------------------------- #

def _ukpn_t3(**kw):
    row = {"GridSupplyPoint": "Amersham", "Substation": "Chinnor Primary 11kV", "Season": "Winter",
           "Maximum_Demand_24_25_MW": 4.3, "Maximum_Demand_24_25_PF": 0.96, "Forecast_M_D_MW_25_26": 4.2,
           "Forecast_M_D_MW_26_27": 4.1, "Forecast_M_D_MW_27_28": 4.1, "Forecast_M_D_MW_28_29": 4.1,
           "Forecast_M_D_MW_29_30": 4.2, "Firm_Capacity_MW": 14.4, "Minimum Load Scaling Factor": "34.3%",
           "LicenceArea": "Eastern Power Networks (EPN)", "ID": 1}
    row.update(kw)
    return pd.DataFrame([row])


def _npg_t3(**kw):
    row = {"row_id": 0, "S/S Group": "Annfield", "S/S or Busbar Name": "Annfield 66/20kV", "Voltage Level (kV)": 66.0,
           "2024/25 Net (Observed) Maximum Load (MVA)": 20.0, "2024/25 Net (Observed) Maximum Load (PF)": 0.95,
           **{f"20{y}/{y + 1} Forecast Load Information (MVA)": 21.0 for y in range(25, 30)},
           "Firm Capacity (MVA)": 27.7, "2024/25 Minimum Load MVA (MW if net exporter)": -12.0, "License": "Northeast"}
    row.update(kw)
    return pd.DataFrame([row])


def _nged_t3(**kw):
    row = {"Licence": "EMIDS", "GSP Group": "Berkswell 132kV", "BSP Group": "Coventry", "Primary Substation": "X 11",
           "Node": "N1", "Status": "Unchanged", "Operating Voltage": "11", "Current Year Max Demand": "11.7",
           "Current Year Power Factor": "0.96", **{f"Forecast Year {i}": "12" for i in range(1, 6)},
           "Firm Capacity of Substation": "23", "Minimum demand Scaling Factor (%)": "50.77%"}
    row.update(kw)
    return pd.DataFrame([row])


def test_load_centres_all_operators():
    raw = pd.concat([bd.read_ukpn_t3(_ukpn_t3()), bd.read_npg_t3(_npg_t3()), bd.read_nged_t3(_nged_t3(), "2025")],
                    ignore_index=True)
    out, notes = bd.build_load_centres(raw, WHEN)
    pc.check(out, _spec("load_centres"))
    x = out.set_index("operator")
    u, n, g = x.loc["ukpn"], x.loc["npg"], x.loc["nged"]
    assert u.voltage_kv == 11.0 and u.base_year == "2024/25" and u.season == "Winter"
    assert u.peak_demand_mw == 4.3 and u.peak_demand_mva == pytest.approx(4.3 / 0.96)
    assert u.headroom_pct == pytest.approx((14.4 - 4.3) / 14.4 * 100) and u.min_load_scaling_pct == 34.3
    assert u.forecast_y5 == 4.2 and "voltage_from_name" in u.quality_flags
    assert n.demand_unit == "MVA" and n.peak_demand_mw == pytest.approx(19.0) and n.min_load_mva == -12.0
    assert n.headroom_pct == pytest.approx((27.7 - 20.0) / 27.7 * 100)
    assert g.status == "energised" and g.firm_capacity_unit == "unknown" and np.isnan(g.headroom_pct)
    assert notes["load_centres_by_operator"] == {"nged": 1, "npg": 1, "ukpn": 1}


def test_ukpn_substation_without_kv_in_name_is_dropped():
    out, notes = bd.build_load_centres(bd.read_ukpn_t3(_ukpn_t3(Substation="Chinnor Primary")), WHEN)
    assert len(out) == 0 and notes["rows_without_voltage"] == 1
    pc.check(out, _spec("load_centres"))


def test_bad_power_factor_is_flagged_not_used():
    out, _ = bd.build_load_centres(bd.read_ukpn_t3(_ukpn_t3(Maximum_Demand_24_25_PF=1.7)), WHEN)
    r = out.iloc[0]
    assert np.isnan(r.peak_demand_mva) and "power_factor_out_of_range" in r.quality_flags


def test_changed_column_layout_fails_loud():
    with pytest.raises(pc.ProfilesError, match="forecast"):
        bd.read_ukpn_t3(_ukpn_t3().drop(columns=["Forecast_M_D_MW_29_30"]))
    with pytest.raises(pc.ProfilesError, match="unknown licence"):
        bd.read_npg_t3(_npg_t3(License="Atlantis"))


# --------------------------------------------------------------------------- #
# Datacentre demand profiles and hand-kept names
# --------------------------------------------------------------------------- #

def _dc_readings(name, values, start, step_min=30, dc_type="Enterprise", level="High Voltage Import"):
    n = len(values)
    return pd.DataFrame({"name": pd.Categorical([name] * n), "dc_type": pd.Categorical([dc_type] * n),
                         "level": pd.Categorical([level] * n),
                         "t": pd.Series([start + pd.Timedelta(minutes=step_min * i) for i in range(n)],
                                        dtype="datetime64[us, UTC]"),
                         "u": np.array(values, dtype="float64")})


def test_dc_profiles_statistics_and_ramps():
    start = pd.Timestamp(WHEN) - pd.Timedelta(days=2)
    a = _dc_readings("Data Centre #8", [0.2, 0.3, 0.25, 0.25], start)
    gap = _dc_readings("Data Centre #8", [0.9], start + pd.Timedelta(hours=5))      # not consecutive
    b = _dc_readings("Data Centre #13", [0.0, 0.0], start, dc_type="Co-located")
    c = _dc_readings("Data Centre #2", [0.5, 1.4], start)
    out = bd.build_dc_profiles(pd.concat([a, gap, b, c], ignore_index=True), WHEN)
    pc.check(out, _spec("datacentre_profiles"))
    x = out.set_index("profile_id")
    r = x.loc["dc-ukpn-08"]
    assert r.n_readings == 5 and r.utilisation_max == 0.9 and r.dc_number == 8
    assert r.ramp_up_max == pytest.approx(0.1) and r.ramp_down_max == pytest.approx(0.05)   # 0.9 jump excluded
    assert r.load_factor == pytest.approx(np.mean([0.2, 0.3, 0.25, 0.25, 0.9]) / 0.9)
    assert pd.isna(r.named_site)                       # names are applied at write time
    z = x.loc["dc-ukpn-13"]
    assert z.quality_flags == "zero_peak" and np.isnan(z.load_factor)
    assert x.loc["dc-ukpn-02", "quality_flags"] == "utilisation_above_capacity"


def test_dc_window_is_latest_year_per_site():
    old = _dc_readings("Data Centre #1", [0.5], pd.Timestamp("2023-01-01", tz="UTC"))
    new = _dc_readings("Data Centre #1", [0.1, 0.2], pd.Timestamp(WHEN) - pd.Timedelta(days=1))
    r = bd.build_dc_profiles(pd.concat([old, new], ignore_index=True), WHEN).iloc[0]
    assert r.n_readings == 2 and r.utilisation_max == 0.2
