"""Tests for build_interconnectors with small synthetic register, flow and limit
tables. links is reference data; link_flows holds the observed statistics."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

import build_interconnectors as bi
import profiles_common as pc

UTC = timezone.utc
WHEN = datetime(2026, 9, 1, tzinfo=UTC)
START = WHEN - timedelta(days=365)


def _register(*rows):
    base = {"project_name": "Britned", "customer_name": "BRITNED DEVELOPMENT LIMITED",
            "connection_site": "Grain 400kV Substation", "stage": pd.NA, "project_status": "Built",
            "mw_import_total": 1200.0, "mw_export_total": 1200.0, "mw_effective_from": pd.NaT, "project_number": "P1"}
    return pd.DataFrame([{**base, **r} for r in (rows or ({},))])


def _flows(code, values):
    return pd.DataFrame({"fuelType": [code] * len(values), "generation": np.array(values, dtype="float64")})


def _build(register, flows=None, limits=None):
    links = bi.build_links(register, WHEN, "InterconnectorRegister/x.parquet")
    pc.check(links, pc.load_spec(bi.FIELDS_JSON, "links"))
    lf, no_flow = bi.build_link_flows(links, flows if flows is not None else _flows("INTNED", [100.0]),
                                      limits or {}, WHEN, START)
    pc.check(lf, pc.load_spec(bi.FIELDS_JSON, "link_flows"))
    return links, lf, no_flow


def test_built_link_reference_and_flow_statistics():
    links, lf, no_flow = _build(_register(), _flows("INTNED", [-1000.0, 0.0, 500.0, 1000.0]))
    r = links.iloc[0]
    assert r.link_folder == "Britned" and r.elexon_fuel_code == "INTNED" and r.connection_kv == 400.0
    assert r.profile_id == "ic-britned" and r.quality_flags == ""
    f = lf.iloc[0]
    assert f.profile_id == "icflow-britned" and f.source_key == "INTNED" and f.capacity_mw == 1200.0
    assert f.flow_readings == 4 and f.flow_mw_min == -1000.0 and f.flow_mw_max == 1000.0
    assert f.flow_mw_mean == 125.0 and f.into_gb_share == 0.5 and f.quality_flags == ""
    assert f.utilisation_p95 == pytest.approx(np.quantile([1000, 0, 500, 1000], 0.95) / 1200)
    assert f.flow_window_start_utc == START and f.flow_window_end_utc == WHEN and no_flow == []


def test_pipeline_project_has_no_flow_row():
    links, lf, _ = _build(_register({"project_name": "Aquind Interconnector", "project_status": "Awaiting Consents",
                                     "project_number": "P9", "mw_effective_from": pd.Timestamp("2030-12-31")}))
    r = links.iloc[0]
    assert r.link_folder == "Pipeline" and not r.is_built and r.effective_from_utc.year == 2030
    assert len(lf) == 0


def test_staged_link_has_one_flow_row_with_summed_capacity():
    reg = _register({"project_name": "Auchencrosh (interconnector CCT)", "stage": 1.0, "project_number": "A1",
                     "mw_import_total": 475.0, "mw_export_total": 500.0},
                    {"project_name": "Auchencrosh (interconnector CCT)", "stage": 2.0, "project_number": "A2",
                     "mw_import_total": 500.0, "mw_export_total": 500.0})
    links, lf, _ = _build(reg, _flows("INTIRL", [-300.0, -200.0]))
    assert set(links.profile_id) == {"ic-auchencrosh-interconnector-cct-stage-1",
                                     "ic-auchencrosh-interconnector-cct-stage-2"}
    assert len(lf) == 1 and lf.iloc[0].link_folder == "Moyle" and lf.iloc[0].capacity_mw == 1000.0


def test_spike_beyond_capacity_is_flagged_not_changed():
    _, lf, _ = _build(_register(), _flows("INTNED", [100.0, 2500.0]))
    assert lf.iloc[0].flow_mw_max == 2500.0 and lf.iloc[0].quality_flags == "flow_exceeds_capacity"


def test_built_link_without_flows_is_reported():
    _, lf, no_flow = _build(_register({"project_name": "Isle of Man Interconnector"}))
    assert len(lf) == 0 and no_flow == ["IsleOfMan"]


def test_unknown_built_link_fails_loud():
    with pytest.raises(pc.ProfilesError, match="no entry in LINKS"):
        bi.build_links(_register({"project_name": "Atlantis Link"}), WHEN, "x")


def test_limit_statistics():
    lim = pd.DataFrame({bi.LIMIT_TO: [1000, 1000, 500, 1000], bi.LIMIT_FROM: [1000, 800, 1000, 1000],
                        bi.REASON_TO: ["No Restriction", "No Restriction", "Planned outage", "No Restriction"],
                        bi.REASON_FROM: ["No Restriction", "Network Constraints", "No Restriction", None]})
    s = bi.limit_stats(lim)
    assert s["limit_to_gb_mw_p50"] == 1000.0 and s["limit_restricted_share"] == 0.5
    _, lf, _ = _build(_register({"project_name": "IFA Interconnector", "mw_import_total": 1988.0}),
                      _flows("INTFR", [1000.0]), {"ifa_neso_s_intraday_transfer_limit": lim})
    f = lf.iloc[0]
    assert f.limit_source.endswith("ifa_neso_s_intraday_transfer_limit") and f.limit_restricted_share == 0.5


def test_partition_files_skip_unreadable_years(tmp_path):
    for y in ("2025", "2026", "unknown", "2019"):
        d = tmp_path / f"year={y}" / "week=01"
        d.mkdir(parents=True)
        (d / "x.parquet").write_bytes(b"")
    got = bi._partition_files(tmp_path, START, WHEN)
    assert sorted(p.parent.parent.name for p in got) == ["year=2025", "year=2026"]
