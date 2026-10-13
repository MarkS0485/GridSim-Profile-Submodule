"""Build the Demands profiles from the GDA data lake.

Inputs (under the lake's DataSources folder):
  Derived/demand_consumers                                   GDA's unified large-consumer register
  UkPowerNetworks/Parquet/..._LTDS_Table_3a_Observed_Peak_Demand   UKPN substation demand
  NationalGrid/RAWData/LTDS Tabular Model/table-3-2025.csv        NGED substation demand
  NorthernPowerGrid/Parquet/LTDS_Appendix_5_Load_Information      NPG substation demand

Outputs:
  Demands/<site type>/sites.parquet                 classified large demand sites
  Demands/LoadCentres/<voltage class>/load_centres.parquet   substation peak demand and forecasts
  Demands/FIELDS.md

Classifying sites. The register gives no site type, so names are matched by an
ordered rule table (SITE_RULES). The first rule that matches wins, so specific
types come before general ones: a "University Hospitals NHS Trust" is a hospital,
"Devonport Royal Dockyard" is naval rather than a port. Two kinds of name are
excluded before any rule runs:
  * generation projects named after a place (School Farm Solar Park, Airfield Wind
    Farm, Port of Tyne BESS): GENERATION_PROJECT;
  * each rule's own place-name uses (School Lane, College Farm).
A matched row must have an import capacity: it is the size of the site's demand.

Run:  python tools/build_demands.py [--as-of YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import profiles_common as pc

FAMILY = "Demands"
FIELDS_JSON = pc.PROFILES_ROOT / FAMILY / "fields.json"

CONSUMERS = "Derived/demand_consumers/demand_consumers.parquet"
UKPN_T3 = "UkPowerNetworks/Parquet/Long_Term_Development_Statement_LTDS_Table_3a_Observed_Peak_Demand"
NGED_T3 = "NationalGrid/RAWData/LTDS Tabular Model/table-3-2025.csv"
NPG_T3 = "NorthernPowerGrid/Parquet/LTDS_Appendix_5_Load_Information"

UKPN_LIC = {"Eastern Power Networks (EPN)": "EPN", "London Power Networks (LPN)": "LPN",
            "South Eastern Power Networks (SPN)": "SPN"}
NPG_LIC = {"Northeast": "NPGN", "Yorkshire": "NPGY"}
NGED_LIC = {"EMIDS": "EMID", "WMIDS": "WMID", "WMID": "WMID", "SWEST": "SWEST", "SWALES": "SWALES"}

# --------------------------------------------------------------------------- #
# Site classification
# --------------------------------------------------------------------------- #

# Names that mark a generation or storage project, not a demand site.
GENERATION_PROJECT = re.compile(r"solar (?:farm|park)|wind (?:farm|park)|\bbess\b|battery storage|"
                                r"solar (?:limited|ltd|llp)|pv generation", re.I)

# (folder, rule name, include pattern, place-name exclusion or None). Order matters.
SITE_RULES = [
    ("Hospitals", "hospital", r"\bhospitals?\b|\bnhs\b|\binfirmary\b",
     r"hospital (?:farm|lane|road|street|hill)"),
    ("Military/Naval", "naval", r"\bhmnb\b|\bnaval\b|royal dockyard|\bfaslane\b", None),
    ("Military/Land", "military", r"\bbarracks\b|\bgarrison\b|\braf\b|ministry of defence|defence infrastructure|"
     r"\barmy\b", r"former raf|raf (?:solar|wind)|\b(?:nr|near) raf\b|barracks farm"),
    ("Datacentres", "datacentre", r"data ?cent(?:re|er)s?|datacent|data hall", None),
    ("Universities", "university", r"\buniversit(?:y|ies)\b", None),
    ("Colleges", "college", r"\bcolleges?\b", r"college (?:lane|farm|road|street)"),
    ("Schools", "school", r"\bschools?\b", r"school (?:farm|lane|road|street|hill)|school aycliffe"),
    # Port evidence is a location word, the weakest kind, so it is tried last.
    ("Port", "port", r"\bport of\b|\bfreeport\b|container terminal|\bdocks\b|\bharbour\b|\bport authority\b|"
     r"associated british ports", r"harbour (?:farm|lane|road)|docks way|biomass|\bstw\b|sewage|water ltd"),
]
_COMPILED = [(folder, name, re.compile(inc, re.I), re.compile(exc, re.I) if exc else None)
             for folder, name, inc, exc in SITE_RULES]

# The UKPN register that sums datacentre demand per local authority.
DATACENTRES_BY_LA = "Data_Centres_by_Local_Authority"

# Datacentre size bands by site import capacity (MW).
DATACENTRE_HYPERSCALE_MW = 50.0
DATACENTRE_SME_MAX_MW = 5.0


def datacentre_band(import_mw: float) -> str:
    if import_mw >= DATACENTRE_HYPERSCALE_MW:
        return "Datacentres/Hyperscale"
    if import_mw < DATACENTRE_SME_MAX_MW:
        return "Datacentres/SME"
    return "Datacentres/Other"


def classify(name, site, register_type) -> tuple[str | None, str | None]:
    """(folder, match_rule) for one register row, or (None, None)."""
    text = f"{name or ''} | {site or ''}"
    if GENERATION_PROJECT.search(text):
        return None, None
    if str(register_type or "").strip().lower() == "datacentre":
        return "Datacentres", "datacentre: register type datacentre"
    for folder, rule, inc, exc in _COMPILED:
        m = inc.search(text)
        if m and not (exc and exc.search(text)):
            return folder, f"{rule}: {m.group(0).lower()}"
    return None, None


def build_sites(consumers: pd.DataFrame, last_updated: datetime) -> tuple[pd.DataFrame, dict]:
    df = consumers.reset_index(drop=True)
    pairs = [classify(n, s, t) for n, s, t in zip(df["name"], df["site"], df["type"])]
    df["site_type"] = [p[0] for p in pairs]
    df["match_rule"] = [p[1] for p in pairs]
    matched = df[df["site_type"].notna()].copy()
    imp = pc.to_num(matched["import_mw"])
    has_import = imp.gt(0)
    notes = {"matched_without_import_capacity": {str(k): int(v) for k, v in
                                                 matched.loc[~has_import, "site_type"].value_counts().sort_index().items()}}
    matched = matched[has_import].reset_index(drop=True)
    imp = pc.to_num(matched["import_mw"])
    # UKPN publishes datacentre demand summed per local authority: those rows are
    # many sites added together, so they are not banded by size.
    is_dc = matched["site_type"].eq("Datacentres")
    by_la = is_dc & matched["evidence_source"].astype("string").str.contains(DATACENTRES_BY_LA, regex=False).fillna(False)
    matched.loc[by_la, "site_type"] = "Datacentres/ByLocalAuthority"
    single = is_dc & ~by_la
    matched.loc[single, "site_type"] = [datacentre_band(v) for v in imp[single]]

    flags = [[] for _ in range(len(matched))]
    for i in np.flatnonzero(pc.to_num(matched["poc_voltage_kv"]).isna().to_numpy()):
        flags[i].append("no_poc_voltage")
    n = len(matched)
    null = np.full(n, np.nan)
    key = matched["consumer_id"].astype(str)
    out = pd.DataFrame({
        "profile_id": key.map(lambda k: pc.sha_id("dem", k)).astype(object),
        "source_dataset": CONSUMERS,
        "source_key": key.astype(object),
        "last_updated_utc": pc.last_updated_column(n, last_updated).to_numpy(),
        "site_type": matched["site_type"].astype(object),
        "match_rule": matched["match_rule"].astype(object),
        "name": pc.str_or_none(matched["name"]),
        "site": pc.str_or_none(matched["site"]),
        "register_type": pc.str_or_none(matched["type"]),
        "energy_tech": pc.str_or_none(matched["energy_tech"]),
        "import_mw": imp.astype("float64"),
        "export_mw": pc.to_num(matched["export_mw"]),
        "storage_mwh": pc.to_num(matched["storage_mwh"]),
        "poc_voltage_kv": pc.to_num(matched["poc_voltage_kv"]),
        "gsp_name": pc.str_or_none(matched["gsp_name"]),
        "bsp": pc.str_or_none(matched["bsp"]),
        "primary": pc.str_or_none(matched["primary"]),
        "local_authority": pc.str_or_none(matched["local_authority"]),
        "easting": pc.to_num(matched["easting"]),
        "northing": pc.to_num(matched["northing"]),
        "postcode": pc.str_or_none(matched["postcode"]),
        "connection_status": pc.str_or_none(matched["connection_status"]),
        "evidence_source": pc.str_or_none(matched["evidence_source"]),
        **{c: null.copy() for c in ("base_load_mw", "peak_load_mw", "load_factor", "fluctuation_band_pct",
                                    "ramp_up_mw_per_min", "ramp_down_mw_per_min", "power_factor",
                                    "voltage_sag_pct", "shore_power_peak_mw", "shore_power_connections_per_week",
                                    "crane_peak_mw", "crane_cycle_s")},
        "quality_flags": pd.Series([";".join(f) for f in flags], dtype=object),
    })
    pc.ensure_unique(out["profile_id"], "sites profile_id")
    _spec = pc.load_spec(FIELDS_JSON, "sites")
    out = pc.spec_order(pc.utc_timestamps(out, _spec), _spec)
    notes["sites_by_type"] = out["site_type"].value_counts().sort_index().to_dict()
    return out.sort_values(["site_type", "profile_id"], kind="mergesort").reset_index(drop=True), notes


# --------------------------------------------------------------------------- #
# Load centres (LTDS Table 3)
# --------------------------------------------------------------------------- #

LC_RAW = ["source_dataset", "source_key", "operator", "licence", "gsp_group", "bsp_group", "substation", "node",
          "voltage_kv", "status", "season", "base_year", "peak_demand_reported", "demand_unit",
          "peak_power_factor", "forecast_y1", "forecast_y2", "forecast_y3", "forecast_y4", "forecast_y5",
          "firm_capacity_reported", "firm_capacity_unit", "min_load_scaling_pct", "min_load_mva", "voltage_from_name"]

_KV_IN_NAME = re.compile(r"(\d+(?:\.\d+)?)\s*kv\b", re.I)


def _lic(series: pd.Series, mapping: dict, what: str) -> pd.Series:
    s = series.astype("string").str.strip()
    unknown = sorted(set(s.dropna()) - set(mapping))
    if unknown:
        raise pc.ProfilesError(f"{what}: unknown licence values {unknown}")
    return s.map(mapping)


def _year_columns(columns, pattern: str) -> list[str]:
    """Columns matching pattern, ordered by the year captured in group 1."""
    found = [(m.group(1), c) for c in columns if (m := re.search(pattern, c))]
    return [c for _, c in sorted(found)]


def _lc_frame(n: int, **cols) -> pd.DataFrame:
    out = pd.DataFrame(index=range(n))
    for c in LC_RAW:
        v = cols.get(c, None)
        out[c] = v.to_numpy() if isinstance(v, pd.Series) else v
    return out


def read_ukpn_t3(t: pd.DataFrame) -> pd.DataFrame:
    t = t.reset_index(drop=True)
    peak_col = _year_columns(t.columns, r"^Maximum_Demand_(\d\d_\d\d)_MW$")
    if len(peak_col) != 1:
        raise pc.ProfilesError(f"UKPN Table 3a: expected one Maximum_Demand_YY_YY_MW column, found {peak_col}")
    yy = re.search(r"(\d\d)_(\d\d)", peak_col[0]).groups()
    pf_col = f"Maximum_Demand_{yy[0]}_{yy[1]}_PF"
    fc = _year_columns(t.columns, r"^Forecast_M_D_MW_(\d\d_\d\d)$")
    if len(fc) != 5:
        raise pc.ProfilesError(f"UKPN Table 3a: expected five forecast columns, found {fc}")
    kv = t["Substation"].astype("string").str.extract(_KV_IN_NAME, expand=False)
    return _lc_frame(
        len(t), source_dataset=UKPN_T3, source_key="ukpn:3a:" + t["ID"].astype(str),
        operator="ukpn", licence=_lic(t["LicenceArea"], UKPN_LIC, "UKPN Table 3a"),
        gsp_group=t["GridSupplyPoint"], substation=t["Substation"], voltage_kv=pd.to_numeric(kv, errors="coerce"),
        season=t["Season"], base_year=f"20{yy[0]}/{yy[1]}",
        peak_demand_reported=pc.to_num(t[peak_col[0]]), demand_unit="MW", peak_power_factor=pc.to_num(t[pf_col]),
        **{f"forecast_y{i + 1}": pc.to_num(t[c]) for i, c in enumerate(fc)},
        firm_capacity_reported=pc.to_num(t["Firm_Capacity_MW"]), firm_capacity_unit="MW",
        min_load_scaling_pct=pc.to_num(t["Minimum Load Scaling Factor"]), voltage_from_name=True,
    )


def read_nged_t3(t: pd.DataFrame, base_year: str) -> pd.DataFrame:
    t = t.reset_index(drop=True)
    return _lc_frame(
        len(t), source_dataset=NGED_T3, source_key=pd.Series([f"nged:t3:row{i}" for i in range(len(t))]),
        operator="nged", licence=_lic(t["Licence"], NGED_LIC, "NGED Table 3"),
        gsp_group=t["GSP Group"], bsp_group=t["BSP Group"], substation=t["Primary Substation"], node=t["Node"],
        voltage_kv=pc.to_num(t["Operating Voltage"]), status=t["Status"].map(pc.norm_status),
        base_year=base_year, peak_demand_reported=pc.to_num(t["Current Year Max Demand"]), demand_unit="MW",
        peak_power_factor=pc.to_num(t["Current Year Power Factor"]),
        **{f"forecast_y{i}": pc.to_num(t[f"Forecast Year {i}"]) for i in range(1, 6)},
        firm_capacity_reported=pc.to_num(t["Firm Capacity of Substation"]), firm_capacity_unit="unknown",
        min_load_scaling_pct=pc.to_num(t["Minimum demand Scaling Factor (%)"]), voltage_from_name=False,
    )


def read_npg_t3(t: pd.DataFrame) -> pd.DataFrame:
    t = t.reset_index(drop=True)
    peak = _year_columns(t.columns, r"^(\d{4}/\d\d) Net \(Observed\) Maximum Load \(MVA\)$")
    if len(peak) != 1:
        raise pc.ProfilesError(f"NPG Appendix 5: expected one observed maximum load column, found {peak}")
    year = re.match(r"^(\d{4}/\d\d)", peak[0]).group(1)
    fc = _year_columns(t.columns, r"^(\d{4}/\d\d) Forecast Load Information \(MVA\)$")
    if len(fc) != 5:
        raise pc.ProfilesError(f"NPG Appendix 5: expected five forecast columns, found {fc}")
    min_col = _year_columns(t.columns, r"^(\d{4}/\d\d) Minimum Load MVA")
    return _lc_frame(
        len(t), source_dataset=NPG_T3, source_key="npg:a5:" + t["row_id"].astype(str),
        operator="npg", licence=_lic(t["License"], NPG_LIC, "NPG Appendix 5"),
        gsp_group=t["S/S Group"], substation=t["S/S or Busbar Name"], voltage_kv=pc.to_num(t["Voltage Level (kV)"]),
        base_year=year, peak_demand_reported=pc.to_num(t[peak[0]]), demand_unit="MVA",
        peak_power_factor=pc.to_num(t[f"{year} Net (Observed) Maximum Load (PF)"]),
        **{f"forecast_y{i + 1}": pc.to_num(t[c]) for i, c in enumerate(fc)},
        firm_capacity_reported=pc.to_num(t["Firm Capacity (MVA)"]), firm_capacity_unit="MVA",
        min_load_mva=pc.to_num(t[min_col[0]]) if min_col else None, voltage_from_name=False,
    )


def build_load_centres(raw: pd.DataFrame, last_updated: datetime) -> tuple[pd.DataFrame, dict]:
    df = raw.reset_index(drop=True)
    kv = pd.to_numeric(df["voltage_kv"], errors="coerce")
    df["voltage_class"] = kv.map(pc.voltage_folder)
    notes = {"rows_without_voltage": int(kv.isna().sum()),
             "rows_voltage_has_no_folder": {str(k): int(v) for k, v in
                                            kv[kv.notna() & df["voltage_class"].isna()].value_counts().sort_index().items()}}
    df = df[df["voltage_class"].notna()].reset_index(drop=True)
    kv = pd.to_numeric(df["voltage_kv"])
    peak = pd.to_numeric(df["peak_demand_reported"]).astype("float64")
    pf = pd.to_numeric(df["peak_power_factor"]).astype("float64")
    pf_ok = pf.gt(0) & pf.le(1)
    is_mw = df["demand_unit"].eq("MW")
    mw = peak.where(is_mw, peak * pf.where(pf_ok))
    mva = (peak / pf.where(pf_ok)).where(is_mw, peak)
    firm = pd.to_numeric(df["firm_capacity_reported"]).astype("float64")
    same_unit = df["firm_capacity_unit"].eq(df["demand_unit"])
    headroom = ((firm - peak) / firm * 100.0).where(same_unit & firm.gt(0))

    flags = [[] for _ in range(len(df))]
    for mask, name in ((peak.isna(), "no_peak_demand"), (df["voltage_from_name"].astype(bool), "voltage_from_name"),
                       (pf.notna() & ~pf_ok, "power_factor_out_of_range")):
        for i in np.flatnonzero(mask.to_numpy()):
            flags[i].append(name)
    out = pd.DataFrame({
        "profile_id": df["source_key"].map(lambda k: pc.sha_id("load", k)).astype(object),
        "source_dataset": df["source_dataset"].astype(object),
        "source_key": df["source_key"].astype(object),
        "last_updated_utc": pc.last_updated_column(len(df), last_updated).to_numpy(),
        "operator": df["operator"].astype(object), "licence": df["licence"].astype(object),
        "gsp_group": pc.str_or_none(df["gsp_group"]), "bsp_group": pc.str_or_none(df["bsp_group"]),
        "substation": pc.str_or_none(df["substation"]), "node": pc.str_or_none(df["node"]),
        "voltage_kv": kv.astype("float64"), "voltage_class": df["voltage_class"].astype(object),
        "status": pc.str_or_none(df["status"]), "season": pc.str_or_none(df["season"]),
        "base_year": df["base_year"].astype(object),
        "peak_demand_reported": peak, "demand_unit": df["demand_unit"].astype(object),
        "peak_power_factor": pf, "peak_demand_mw": mw.astype("float64"), "peak_demand_mva": mva.astype("float64"),
        **{f"forecast_y{i}": pd.to_numeric(df[f"forecast_y{i}"]).astype("float64") for i in range(1, 6)},
        "firm_capacity_reported": firm, "firm_capacity_unit": df["firm_capacity_unit"].astype(object),
        "headroom_pct": headroom.astype("float64"),
        "min_load_scaling_pct": pd.to_numeric(df["min_load_scaling_pct"]).astype("float64"),
        "min_load_mva": pd.to_numeric(df["min_load_mva"]).astype("float64"),
        "quality_flags": pd.Series([";".join(f) for f in flags], dtype=object),
    })
    pc.ensure_unique(out["source_key"], "load_centres source_key")
    pc.ensure_unique(out["profile_id"], "load_centres profile_id")
    _spec = pc.load_spec(FIELDS_JSON, "load_centres")
    out = pc.spec_order(pc.utc_timestamps(out, _spec), _spec)
    notes["load_centres_by_operator"] = out["operator"].value_counts().sort_index().to_dict()
    return out.sort_values(["voltage_kv", "source_key"], kind="mergesort").reset_index(drop=True), notes


# --------------------------------------------------------------------------- #
# Datacentre demand profiles (UKPN, anonymised) and their hand-kept names
# --------------------------------------------------------------------------- #

DC_PROFILES = "UkPowerNetworks/Parquet/data_centre_demand_profiles"
DC_WINDOW_DAYS = 365
_DC_NAME = re.compile(r"^Data Centre #(\d+)$")


def read_dc_readings(lake: Path, last_updated: datetime) -> pd.DataFrame:
    """Half-hourly utilisation readings on or before the last-updated date.
    About 5.4 million rows: names, types and levels are held as categories."""
    root = lake / DC_PROFILES
    if not root.is_dir():
        raise pc.ProfilesError(f"datacentre profiles not found: {root}")
    cols = ["anonymised_data_centre_name", "dc_type", "cleansed_voltage_level", "utc_timestamp", "hh_utilisation_ratio"]
    stamp = pd.Timestamp(last_updated)
    parts = []
    for f in sorted(root.glob("year=*/week=*/*.parquet")):
        y = f.parent.parent.name.split("=", 1)[1]
        if not y.isdigit() or int(y) > last_updated.year:
            continue
        d = pd.read_parquet(f, columns=cols)
        t = pd.to_datetime(d["utc_timestamp"], utc=True, format="ISO8601")
        keep = (t <= stamp) & d["hh_utilisation_ratio"].notna()
        if keep.any():
            parts.append(pd.DataFrame({
                "name": d.loc[keep, "anonymised_data_centre_name"].astype(str).astype("category"),
                "dc_type": d.loc[keep, "dc_type"].astype(str).astype("category"),
                "level": d.loc[keep, "cleansed_voltage_level"].astype(str).astype("category"),
                "t": t[keep].astype("datetime64[us, UTC]"),
                "u": d.loc[keep, "hh_utilisation_ratio"].astype("float64")}))
    if not parts:
        raise pc.ProfilesError(f"no datacentre readings on or before {last_updated.date()}")
    from pandas.api.types import union_categoricals
    out = pd.concat([x.drop(columns=["name", "dc_type", "level"]) for x in parts], ignore_index=True)
    for c in ("name", "dc_type", "level"):
        out[c] = union_categoricals([x[c] for x in parts], sort_categories=True)
    return out


def build_dc_profiles(readings: pd.DataFrame, last_updated: datetime) -> pd.DataFrame:
    """One row per anonymised data centre: utilisation statistics over its
    latest DC_WINDOW_DAYS of readings. Names come from Demands/names.csv at
    write time, like every other profile."""
    r = readings.copy()
    r["name"] = r["name"].astype(str)
    bad = sorted({n for n in r["name"].unique() if not _DC_NAME.match(n)})
    if bad:
        raise pc.ProfilesError(f"unexpected anonymised names in the source: {bad[:5]}")
    end = r.groupby("name")["t"].transform("max")
    r = r[r["t"] > end - timedelta(days=DC_WINDOW_DAYS)]
    r = r.sort_values(["name", "t"], kind="mergesort")
    step = r.groupby("name")["u"].diff()
    gap = r.groupby("name")["t"].diff()
    step = step.where(gap == pd.Timedelta(minutes=30))
    r["rise"], r["fall"] = step.where(step > 0), (-step).where(step < 0)
    rows = []
    for name, g in r.groupby("name", sort=False):
        u = g["u"]
        flags = []
        types, levels = g["dc_type"].astype(str).unique(), g["level"].astype(str).unique()
        if len(types) > 1:
            flags.append("several_types_published")
        if len(levels) > 1:
            flags.append("several_levels_published")
        peak = float(u.max())
        if peak == 0:
            flags.append("zero_peak")
        if peak > 1:
            flags.append("utilisation_above_capacity")
        q = lambda s, p: float(np.quantile(s.dropna().to_numpy(), p)) if s.notna().any() else np.nan
        rows.append({
            "profile_id": f"dc-ukpn-{int(_DC_NAME.match(name).group(1)):02d}",
            "source_dataset": DC_PROFILES, "source_key": name, "operator": "ukpn", "anonymised_name": name,
            "dc_number": int(_DC_NAME.match(name).group(1)),
            "dc_type": types[-1] if len(types) == 1 else ";".join(sorted(types)),
            "connection_level": levels[-1] if len(levels) == 1 else ";".join(sorted(levels)),
            "window_start_utc": g["t"].min(), "window_end_utc": g["t"].max(), "n_readings": int(len(g)),
            "utilisation_min": float(u.min()), "utilisation_p05": q(u, 0.05), "utilisation_p50": q(u, 0.50),
            "utilisation_p95": q(u, 0.95), "utilisation_max": peak, "utilisation_mean": float(u.mean()),
            "load_factor": float(u.mean()) / peak if peak > 0 else np.nan,
            "fluctuation_band": q(u, 0.95) - q(u, 0.05),
            "ramp_up_p99": q(g["rise"], 0.99), "ramp_down_p99": q(g["fall"], 0.99),
            "ramp_up_max": float(g["rise"].max()) if g["rise"].notna().any() else np.nan,
            "ramp_down_max": float(g["fall"].max()) if g["fall"].notna().any() else np.nan,
            "quality_flags": ";".join(flags)})
    spec = pc.load_spec(FIELDS_JSON, "datacentre_profiles")
    out = pd.DataFrame(rows)
    out["last_updated_utc"] = pc.last_updated_column(len(out), last_updated).to_numpy()
    for c in ("dc_number", "n_readings"):
        out[c] = out[c].astype("int64")
    for f in spec.fields:
        if f.type == "string" and f.name in out.columns:
            out[f.name] = pc.str_or_none(out[f.name])
    out["quality_flags"] = out["quality_flags"].fillna("").astype(object)
    pc.ensure_unique(out["profile_id"], "datacentre_profiles profile_id")
    out = pc.spec_order(pc.utc_timestamps(out, spec), spec)
    return out.sort_values("profile_id", kind="mergesort").reset_index(drop=True)


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #

SITE_FOLDERS = ["Hospitals", "Schools", "Universities", "Colleges", "Datacentres/Hyperscale", "Datacentres/SME",
                "Datacentres/Other", "Datacentres/ByLocalAuthority", "Port", "Military/Land", "Military/Naval"]


def build(lake: Path, last_updated: datetime, out_root: Path = pc.PROFILES_ROOT) -> dict:
    sites, s_notes = build_sites(pd.read_parquet(lake / CONSUMERS), last_updated)
    nged = pd.read_csv(lake / NGED_T3, dtype=str, encoding="utf-8-sig", keep_default_na=False)
    nged.columns = [str(c).strip() for c in nged.columns]
    nged_year = re.search(r"(\d{4})", Path(NGED_T3).name).group(1)
    raw = pd.concat([read_ukpn_t3(pc.single_parquet(lake / UKPN_T3)), read_nged_t3(nged, nged_year),
                     read_npg_t3(pc.single_parquet(lake / NPG_T3))], ignore_index=True)
    lc, lc_notes = build_load_centres(raw, last_updated)
    dc = build_dc_profiles(read_dc_readings(lake, last_updated), last_updated)

    written = []
    s_spec, lc_spec = pc.load_spec(FIELDS_JSON, "sites"), pc.load_spec(FIELDS_JSON, "load_centres")
    for folder in SITE_FOLDERS:
        part = sites[sites["site_type"].eq(folder)].reset_index(drop=True)
        path = out_root / FAMILY / Path(folder) / "sites.parquet"
        if len(part):
            written.append(pc.write_profile(part, s_spec, path))
        elif path.exists():
            path.unlink()
    for vclass in pc.VOLTAGE_CLASSES.values():
        part = lc[lc["voltage_class"].eq(vclass)].reset_index(drop=True)
        path = out_root / FAMILY / "LoadCentres" / vclass / "load_centres.parquet"
        if len(part):
            written.append(pc.write_profile(part, lc_spec, path))
        elif path.exists():
            path.unlink()
    written.append(pc.write_profile(dc, pc.load_spec(FIELDS_JSON, "datacentre_profiles"),
                                    out_root / FAMILY / "Datacentres" / "Profiles" / "datacentre_profiles.parquet"))
    pc.write_fields_md(FIELDS_JSON)
    return {"family": FAMILY, "inputs": [CONSUMERS, UKPN_T3, NGED_T3, NPG_T3, DC_PROFILES], "files": written,
            "notes": {**s_notes, **lc_notes, "datacentre_profiles": int(len(dc)),
                      "profiles_named": pc.verify_names_used(FAMILY)}}


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
