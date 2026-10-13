"""Build the Generator profiles from the GDA data lake.

Inputs (under the lake's DataSources folder):
  Elexon/Reference/bmunits_all.json             BM unit registration (fuel, capacity, GSP group)
  Elexon/Parquet/{rure,rdre,ruri,rdri}          run-up / run-down rates (export, import)
  Elexon/Parquet/{sel,sil,mels}                 stable and maximum export/import limits
  Elexon/Parquet/{ndz,mzt,mnzt}                 notice to deviate, minimum zero / non-zero times
  Elexon/Parquet/b1610                          metered output per BM unit per half-hour
  DUKES/Parquet/stations                        DESNZ DUKES 5.11 power stations
  REPD/Parquet/snapshot                         DESNZ Renewable Energy Planning Database
  Derived/asset_geography                       DNO and GSP region for DUKES / REPD sites
  GDA Scripts/build_inertia_reconstructed.py    H_BY_FUEL (typical inertia constants), read as data

Outputs:
  Generator/<fuel folder>/bm_units.parquet   one row per BM unit that can generate
  Generator/<fuel folder>/stations.parquet   one row per DUKES / REPD station
  Generator/FIELDS.md

Every statistic over time uses the 365 days ending at the last-updated date.

Values set by rule rather than measured are marked as such in the spec:
  * max_rating_mw = capacity / 0.8 (Mark's rule: nameplate is 80% of maximum).
  * inertia_h_s comes from GDA's documented H_BY_FUEL table, a typical value per fuel.
Pole count, speed, torque and per-asset CO2 have no source in the lake and stay null.

Run:  python tools/build_generators.py [--as-of YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import ast
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import profiles_common as pc

FAMILY = "Generator"
FIELDS_JSON = pc.PROFILES_ROOT / FAMILY / "fields.json"
WINDOW_DAYS = 365

BMU_REF = "Elexon/Reference/bmunits_all.json"
ELEXON = "Elexon/Parquet"
DUKES = "DUKES/Parquet/stations"
REPD = "REPD/Parquet/snapshot"
GEOGRAPHY = "Derived/asset_geography"

# Nameplate is taken to be 80% of a machine's maximum (Mark's rule).
NAMEPLATE_SHARE_OF_MAX = 0.8
# Ramp rate units notify to mean "no limit" (Elexon RURE/RDRE convention).
RAMP_NO_LIMIT = 999.0

# MW to MVA for stored energy, the same assumption GDA's inertia work uses.
POWER_FACTOR = 0.9

# --------------------------------------------------------------------------- #
# Fuel and technology -> Generator folder. One table per source. A value not in
# its table stops the build, so a new category is noticed rather than misfiled.
# --------------------------------------------------------------------------- #
ELEXON_FUEL = {
    "CCGT": "Gas", "OCGT": "Gas", "NUCLEAR": "Nuclear", "BIOMASS": "OtherThermal/BIO",
    "WIND": "Wind", "COAL": "Coal", "NPSHYD": "Hydro", "PS": "PumpedStorage", "OTHER": "Other",
    "OIL": "OtherThermal/Oil",
}
UNCLASSIFIED = "Unclassified"       # BM units Elexon publishes no fuel for

# Fields of the BM unit reference this builder reads (repeats are judged on these).
REF_COLUMNS_USED = ["elexonBmUnit", "nationalGridBmUnit", "fuelType", "leadPartyName", "bmUnitType", "bmUnitName",
                    "demandCapacity", "generationCapacity", "transmissionLossFactor", "gspGroupName"]

DUKES_FUEL = {
    "Natural Gas": "Gas", "Nuclear": "Nuclear", "Biomass": "OtherThermal/BIO", "MSW": "OtherThermal/Waste",
    "Diesel/Gas Oil": "OtherThermal/Oil", "Hydro": "Hydro", "Pumped hydro": "PumpedStorage",
    "Solar": "Solar", "Wind": "Wind",
}
REPD_TECH = {
    "Solar Photovoltaics": "Solar", "Wind Onshore": "Wind", "Wind Offshore": "Wind",
    "Battery": "Storage", "Compressed Air Energy Storage": "Storage", "Flywheels": "Storage",
    "Liquid Air Energy Storage": "Storage", "Pumped Storage Hydroelectricity": "PumpedStorage",
    "Large Hydro": "Hydro", "Small Hydro": "Hydro",
    "Biomass (co-firing)": "OtherThermal/BIO", "Biomass (dedicated)": "OtherThermal/BIO",
    "Anaerobic Digestion": "OtherThermal/BIO", "Advanced Conversion Technologies": "OtherThermal/BIO",
    "Landfill Gas": "OtherThermal/BIO", "Sewage Sludge Digestion": "OtherThermal/BIO",
    "EfW Incineration": "OtherThermal/Waste",
    "Shoreline Wave": "Marine", "Tidal Lagoon": "Marine", "Tidal Stream": "Marine",
    "Geothermal": "Other", "Hot Dry Rocks (HDR)": "Other", "Hydrogen": "Other", "Fuel Cell (Hydrogen)": "Other",
    "Unknown": UNCLASSIFIED,
    # heat, not electricity generation: left out of Generator (counted in the report)
    "Air Source Heat Pumps": None,
}
CHP_FOLDER = "OtherThermal/CHP"     # any station flagged CHP is filed here, whatever its fuel

REPD_KEEP_STATUS = {"Operational", "Under Construction", "Awaiting Construction", "Application Submitted",
                    "Appeal Lodged", "No Application Required"}

# Fuel folders that are synchronous machines, and the GDA H_BY_FUEL key for each.
H_KEY_BY_ELEXON_FUEL = {"NUCLEAR": "NUCLEAR", "CCGT": "CCGT", "OCGT": "OCGT", "COAL": "COAL",
                        "BIOMASS": "BIOMASS", "PS": "PS", "NPSHYD": "NPSHYD"}
H_KEY_BY_STATION = {  # (folder, technology hint) -> key; gas needs CCGT vs single cycle
    "Nuclear": "NUCLEAR", "OtherThermal/BIO": "BIOMASS", "OtherThermal/Waste": "BIOMASS",
    "PumpedStorage": "PS", "Hydro": "NPSHYD", "Coal": "COAL",
}

ALL_FOLDERS = sorted(set(ELEXON_FUEL.values()) | set(DUKES_FUEL.values())
                     | {v for v in REPD_TECH.values() if v} | {CHP_FOLDER, UNCLASSIFIED})


# --------------------------------------------------------------------------- #
# Inertia table, read from GDA as data
# --------------------------------------------------------------------------- #

GDA_H_FILE = "build_inertia_reconstructed.py"


def load_h_by_fuel() -> dict[str, float]:
    """Read H_BY_FUEL from GDA's script without importing it (the script has
    lake side effects on import). Fails loud if the table is not there."""
    scripts = Path(pc._import_gda_helpers()[0].__file__).parent
    tree = ast.parse((scripts / GDA_H_FILE).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "H_BY_FUEL" for t in node.targets):
            table = ast.literal_eval(node.value)
            if not table or not all(isinstance(v, (int, float)) and v > 0 for v in table.values()):
                raise pc.ProfilesError(f"H_BY_FUEL in {GDA_H_FILE} is empty or has a non-positive value")
            return {str(k): float(v) for k, v in table.items()}
    raise pc.ProfilesError(f"H_BY_FUEL not found in GDA {GDA_H_FILE}")


def machine_columns(capacity: pd.Series, h: pd.Series) -> dict:
    """The rule-based and placeholder machine fields shared by both tables."""
    cap = capacity.where(capacity > 0)
    max_rating = cap / NAMEPLATE_SHARE_OF_MAX
    n = len(capacity)
    mva = cap / POWER_FACTOR          # assumed MVA base, labelled as such in the spec
    return {
        "rated_mva_assumed": mva.astype("float64"),
        "max_rating_mw": max_rating.astype("float64"),
        "thermal_headroom_mw": (max_rating - cap).astype("float64"),
        "inertia_h_s": h.astype("float64"),
        "stored_energy_s_mva": (h * mva).astype("float64"),
        "pole_count": pd.Series([pd.NA] * n, dtype="Int64"),
        "rated_speed_rpm": np.full(n, np.nan),
        "rated_torque_knm": np.full(n, np.nan),
        "co2_t_per_mwh": np.full(n, np.nan),
    }


# --------------------------------------------------------------------------- #
# Elexon dynamic data and metered output
# --------------------------------------------------------------------------- #

def _elexon_files(lake: Path, dataset: str, start: datetime, end: datetime) -> list[Path]:
    """Partition files for a dataset whose year can overlap [start, end]."""
    root = lake / ELEXON / dataset
    if not root.is_dir():
        raise pc.ProfilesError(f"Elexon dataset not found: {root}")
    return sorted(p for p in root.glob("year=*/week=*/*.parquet")
                  if start.year <= int(p.parent.parent.name.split("=")[1]) <= end.year)


def read_elexon(lake: Path, dataset: str, cols: list[str], time_col: str,
                start: datetime, end: datetime) -> pd.DataFrame:
    """Rows of an Elexon dataset with time_col in (start, end]: bmUnit plus cols.

    A year of some datasets (MELS) runs to millions of rows, so memory is kept
    low: the time column is dropped once used and bmUnit is held as a category
    (one string per unit, not per row). Value columns stay float64, so the
    statistics are bit-for-bit what they would be with plain strings."""
    from pandas.api.types import union_categoricals
    parts = []
    for f in _elexon_files(lake, dataset, start, end):
        d = pd.read_parquet(f, columns=["bmUnit", time_col, *cols])
        d = d[(d[time_col] > start) & (d[time_col] <= end)].drop(columns=[time_col])
        if len(d):
            parts.append(d.assign(bmUnit=d["bmUnit"].astype(str).astype("category")))
    if not parts:
        return pd.DataFrame({"bmUnit": pd.Series(dtype="category"),
                             **{c: pd.Series(dtype="float64") for c in cols}})
    units = union_categoricals([p["bmUnit"] for p in parts], sort_categories=True)
    out = pd.concat([p.drop(columns=["bmUnit"]) for p in parts], ignore_index=True)
    out.insert(0, "bmUnit", units)
    return out


def _by_unit(df: pd.DataFrame):
    """Group by BM unit (category or string) in sorted unit order."""
    unit = df["bmUnit"]
    if not isinstance(unit.dtype, pd.CategoricalDtype):
        unit = unit.astype(str).astype("category")
    return unit.cat.as_ordered().cat.reorder_categories(sorted(unit.cat.categories))


def ramp_stats(rates: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Per BM unit: median and p90 of the fastest band, median of the slowest
    positive band, and the notification count. rates has bmUnit, rate1..3."""
    r = rates[["rate1", "rate2", "rate3"]].astype("float64")
    fastest = r.max(axis=1)
    slowest = r.where(r > 0).min(axis=1)
    d = pd.DataFrame({"bmUnit": _by_unit(rates), "fast": fastest, "slow": slowest})
    g = d.groupby("bmUnit", sort=True, observed=True)
    out = pd.DataFrame({
        f"{prefix}_p50": g["fast"].median(), f"{prefix}_p90": g["fast"].quantile(0.9),
        f"{prefix}_slowest_p50": g["slow"].median(), f"{prefix}_n": g["fast"].size(),
    })
    out.index = out.index.astype(str)
    return out


def median_by_unit(df: pd.DataFrame, col: str, name: str) -> pd.Series:
    out = df.assign(bmUnit=_by_unit(df)).groupby("bmUnit", sort=True, observed=True)[col].median().rename(name)
    out.index = out.index.astype(str)
    return out


def dynamics(lake: Path, start: datetime, end: datetime) -> pd.DataFrame:
    """All Elexon dynamic statistics, one row per BM unit that appears in any."""
    rate_cols = ["rate1", "rate2", "rate3"]
    parts = [
        ramp_stats(read_elexon(lake, "rure", rate_cols, "time", start, end), "up"),
        ramp_stats(read_elexon(lake, "rdre", rate_cols, "time", start, end), "down"),
        ramp_stats(read_elexon(lake, "ruri", rate_cols, "time", start, end), "imp_up"),
        ramp_stats(read_elexon(lake, "rdri", rate_cols, "time", start, end), "imp_down"),
        median_by_unit(read_elexon(lake, "sel", ["level"], "time", start, end), "level", "sel"),
        median_by_unit(read_elexon(lake, "sil", ["level"], "time", start, end), "level", "sil"),
        median_by_unit(read_elexon(lake, "ndz", ["notice"], "time", start, end), "notice", "ndz"),
        median_by_unit(read_elexon(lake, "mzt", ["periodMin"], "time", start, end), "periodMin", "mzt"),
        median_by_unit(read_elexon(lake, "mnzt", ["periodMin"], "time", start, end), "periodMin", "mnzt"),
    ]
    mels = read_elexon(lake, "mels", ["levelTo"], "timeFrom", start, end)
    mels = mels.assign(bmUnit=_by_unit(mels)).groupby("bmUnit", sort=True, observed=True)["levelTo"]
    mel_max, mel_p50 = mels.max().rename("mel_max"), mels.median().rename("mel_p50")
    mel_max.index = mel_max.index.astype(str)
    mel_p50.index = mel_p50.index.astype(str)
    parts += [mel_max, mel_p50]
    return pd.concat(parts, axis=1)


# Metered percentiles are taken from per-unit histograms at this resolution.
METERED_BIN_MW = 0.1


def histogram_quantile(bins: pd.Series, q: float) -> float:
    """Nearest-rank quantile from a histogram: bins is a Series indexed by bin
    number (value / METERED_BIN_MW) holding counts. Returns the value of the
    first bin whose cumulative count reaches ceil(q x total)."""
    b = bins.sort_index()
    target = max(1, int(np.ceil(q * b.sum())))
    return float(b.index[np.searchsorted(b.cumsum().to_numpy(), target)]) * METERED_BIN_MW


def metered(lake: Path, start: datetime, end: datetime) -> pd.DataFrame:
    """B1610 metered output per BM unit. quantity is energy per half-hour (MWh),
    so mean MW over the half-hour is quantity x 2.

    A year is well over 100 million rows, so files are streamed and each unit
    keeps only a count, a sum, a maximum and a histogram of 0.1 MW bins. Mean and
    maximum are exact; median and p99 are nearest-rank values on those bins."""
    count = pd.Series(dtype="int64")
    total = pd.Series(dtype="float64")
    peak = pd.Series(dtype="float64")
    hist_parts: list[pd.Series] = []
    hist: pd.Series | None = None              # (unit, bin) -> count, built up in batches

    def fold(acc, parts):
        merged = pd.concat(([acc] if acc is not None else []) + parts)
        return merged.groupby(level=[0, 1]).sum()
    for i, f in enumerate(_elexon_files(lake, "b1610", start, end)):
        d = pd.read_parquet(f, columns=["bmUnit", "halfHourEndTime", "quantity"])
        d = d[(d["halfHourEndTime"] > start) & (d["halfHourEndTime"] <= end) & d["quantity"].notna()]
        if d.empty:
            continue
        mw = d["quantity"].astype("float64") * 2.0
        unit = d["bmUnit"].astype(str)
        g = mw.groupby(unit)
        count = count.add(g.size(), fill_value=0)
        total = total.add(g.sum(), fill_value=0.0)
        peak = pd.concat([peak, g.max()]).groupby(level=0).max()
        b = np.round(mw / METERED_BIN_MW).astype("int64")
        hist_parts.append(b.groupby([unit, b]).size())
        if len(hist_parts) >= 30:                 # fold in batches to bound memory
            hist = fold(hist, hist_parts)
            hist_parts = []
    if hist_parts:
        hist = fold(hist, hist_parts)
    if count.empty or hist is None:
        return pd.DataFrame(columns=["metered_periods", "out_mean", "out_p50", "out_p99", "out_max"], dtype="float64")
    p50, p99 = {}, {}
    for unit, h in hist.groupby(level=0):
        h = h.droplevel(0)
        p50[unit] = histogram_quantile(h, 0.50)
        p99[unit] = histogram_quantile(h, 0.99)
    idx = count.index.sort_values()
    return pd.DataFrame({"metered_periods": count.reindex(idx).astype("int64"),
                         "out_mean": (total / count).reindex(idx),
                         "out_p50": pd.Series(p50).reindex(idx), "out_p99": pd.Series(p99).reindex(idx),
                         "out_max": peak.reindex(idx)})


# --------------------------------------------------------------------------- #
# BM units table
# --------------------------------------------------------------------------- #

def build_bm_units(ref: pd.DataFrame, dyn: pd.DataFrame, met: pd.DataFrame, h_by_fuel: dict,
                   last_updated: datetime, window_start: datetime) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """For every BM unit that can generate: the reference row (registration and
    machine data, table bm_units) and the observed row (dynamics and metered
    statistics, table bm_dynamics). Interconnector units (fuel INT*) go to the
    Interconnects family."""
    # The reference can list a unit twice (T_WLNYO-4, 2026-09 copy: the two
    # records differ only in EIC code, which Profiles does not use). Repeats that
    # agree on every field this builder reads (blanks treated alike) are dropped
    # and counted; repeats that disagree on any of them are caught by the
    # uniqueness check below and stop the build.
    used = ref[[c for c in REF_COLUMNS_USED if c in ref.columns]]
    as_text = used.apply(lambda col: col.map(lambda v: "" if v is None or (isinstance(v, float) and v != v) else str(v)))
    exact_repeat = as_text.duplicated()
    df = ref[~exact_repeat.to_numpy()].reset_index(drop=True).copy()
    df["fuelType"] = pc.str_or_none(df["fuelType"])
    cap = pc.to_num(df["generationCapacity"])
    fuel = df["fuelType"]
    is_ic = fuel.fillna("").str.startswith("INT")
    unknown = sorted(set(fuel.dropna()[~is_ic]) - set(ELEXON_FUEL))
    if unknown:
        raise pc.ProfilesError(f"Elexon fuel types with no Generator folder: {unknown}")
    can_generate = fuel.notna() | cap.gt(0)
    notes = {"repeat_records_dropped": int(exact_repeat.sum()),
             "interconnector_units_left_for_interconnects": int(is_ic.sum()),
             "units_without_fuel_or_generation_capacity": int((~can_generate & ~is_ic).sum())}
    df = df[can_generate & ~is_ic].reset_index(drop=True)
    cap = pc.to_num(df["generationCapacity"])
    fuel = df["fuelType"]
    folder = fuel.map(ELEXON_FUEL).fillna(UNCLASSIFIED)
    h = fuel.map(lambda f: h_by_fuel.get(H_KEY_BY_ELEXON_FUEL.get(f, ""), np.nan) if f else np.nan)

    # The Elexon id is the key. NESO also lists units with only a National Grid
    # id (no Elexon registration); those are keyed "ng:<id>" and flagged. A unit
    # with neither id cannot be identified, so it stops the build.
    elexon = pc.str_or_none(df["elexonBmUnit"])
    ng = pc.str_or_none(df["nationalGridBmUnit"])
    no_id = elexon.isna() & ng.isna()
    if no_id.any():
        raise pc.ProfilesError(f"{int(no_id.sum())} BM units have neither an Elexon nor a National Grid id")
    no_elexon = elexon.isna()
    key = elexon.where(~no_elexon, "ng:" + ng.astype(str)).astype(str)
    dj = dyn.reindex(key.to_numpy())
    mj = met.reindex(key.to_numpy())

    def flags_of(*checks) -> pd.Series:
        lists = [[] for _ in range(len(df))]
        for mask, name in checks:
            for i in np.flatnonzero(np.asarray(mask, dtype=bool)):
                lists[i].append(name)
        return pd.Series([";".join(x) for x in lists], dtype=object)

    n = len(df)
    units = pd.DataFrame({
        "profile_id": ("gen-bmu-" + key.map(pc.slug)).astype(object),
        "source_dataset": BMU_REF,
        "source_key": key.astype(object),
        "last_updated_utc": pc.last_updated_column(n, last_updated).to_numpy(),
        "bmu_id": key.astype(object),
        "ng_bmu_id": pc.str_or_none(df["nationalGridBmUnit"]),
        "unit_name": pc.str_or_none(df["bmUnitName"]),
        "lead_party": pc.str_or_none(df["leadPartyName"]),
        "bmu_type": pc.str_or_none(df["bmUnitType"]),
        "fuel_type": fuel.astype(object),
        "fuel_folder": folder.astype(object),
        "gsp_group": pc.str_or_none(df["gspGroupName"]),
        "transmission_loss_factor": pc.to_num(df["transmissionLossFactor"]),
        "capacity_mw": cap,
        "demand_capacity_mw": pc.to_num(df["demandCapacity"]),
        **machine_columns(cap, h),
        "quality_flags": flags_of((fuel.isna(), "no_fuel_type"), (~cap.gt(0), "no_capacity"),
                                  (no_elexon.to_numpy(), "no_elexon_registration")),
    })

    def num(series) -> np.ndarray:
        return pd.to_numeric(pd.Series(series)).astype("float64").to_numpy()

    dyn = pd.DataFrame({
        "profile_id": ("gen-dyn-" + key.map(pc.slug)).astype(object),
        "source_dataset": "Elexon/Parquet (RURE, RDRE, RURI, RDRI, SEL, SIL, MELS, NDZ, MZT, MNZT, B1610)",
        "source_key": key.astype(object),
        "last_updated_utc": pc.last_updated_column(n, last_updated).to_numpy(),
        "bmu_id": key.astype(object),
        "fuel_folder": folder.astype(object),
        "dynamics_window_start_utc": pc.last_updated_column(n, window_start).to_numpy(),
        "ramp_up_mw_per_min_p50": num(dj["up_p50"]),
        "ramp_up_mw_per_min_p90": num(dj["up_p90"]),
        "ramp_up_slowest_mw_per_min_p50": num(dj["up_slowest_p50"]),
        "ramp_down_mw_per_min_p50": num(dj["down_p50"]),
        "ramp_down_mw_per_min_p90": num(dj["down_p90"]),
        "ramp_down_slowest_mw_per_min_p50": num(dj["down_slowest_p50"]),
        "import_ramp_up_mw_per_min_p50": num(dj["imp_up_p50"]),
        "import_ramp_down_mw_per_min_p50": num(dj["imp_down_p50"]),
        "ramp_notifications": pd.array((dj["up_n"].fillna(0) + dj["down_n"].fillna(0)).astype("int64").to_numpy(),
                                       dtype="Int64"),
        "stable_export_limit_mw_p50": num(dj["sel"]),
        "stable_import_limit_mw_p50": num(dj["sil"]),
        "max_export_limit_mw_max": num(dj["mel_max"]),
        "max_export_limit_mw_p50": num(dj["mel_p50"]),
        "notice_to_deviate_min_p50": num(dj["ndz"]),
        "min_zero_time_min_p50": num(dj["mzt"]),
        "min_non_zero_time_min_p50": num(dj["mnzt"]),
        "metered_periods": pd.array(mj["metered_periods"].to_numpy(), dtype="Int64"),
        "output_mw_mean": num(mj["out_mean"]),
        "output_mw_p50": num(mj["out_p50"]),
        "output_mw_p99": num(mj["out_p99"]),
        "output_mw_max": num(mj["out_max"]),
        "capacity_factor": (num(mj["out_mean"]) / cap.where(cap > 0).to_numpy()).astype("float64"),
        "dynamics_window_end_utc": pc.last_updated_column(n, last_updated).to_numpy(),
        "quality_flags": flags_of(
            (mj["metered_periods"].isna().to_numpy(), "no_metered_output"),
            (dj.isna().all(axis=1).to_numpy(), "no_dynamic_data"),
            # 999 MW/min is how units (mostly batteries) notify "no ramp limit":
            # kept as published, flagged so nobody reads it as a physical rate.
            ((num(dj["up_p90"]) >= RAMP_NO_LIMIT) | (num(dj["down_p90"]) >= RAMP_NO_LIMIT), "ramp_rate_999_notified"),
            # metered output above the 80%-rule maximum: the rule is too tight here.
            (num(mj["out_max"]) > (cap.where(cap > 0) / NAMEPLATE_SHARE_OF_MAX).to_numpy(), "output_above_rule_max_rating")),
    })
    pc.ensure_unique(units["profile_id"], "bm_units profile_id")
    pc.ensure_unique(dyn["profile_id"], "bm_dynamics profile_id")
    us, ds = pc.load_spec(FIELDS_JSON, "bm_units"), pc.load_spec(FIELDS_JSON, "bm_dynamics")
    units = pc.spec_order(pc.utc_timestamps(units, us), us)
    dyn = pc.spec_order(pc.utc_timestamps(dyn, ds), ds)
    return (units.sort_values("profile_id", kind="mergesort").reset_index(drop=True),
            dyn.sort_values("profile_id", kind="mergesort").reset_index(drop=True), notes)


# --------------------------------------------------------------------------- #
# Stations table (DUKES + REPD)
# --------------------------------------------------------------------------- #

def _yes_no(s: pd.Series) -> pd.Series:
    t = s.astype("string").str.strip().str.lower()
    return pd.array([None if pd.isna(v) else {"yes": True, "no": False}.get(v) for v in t], dtype="boolean")


def _station_h(folder: pd.Series, technology: pd.Series, h_by_fuel: dict) -> pd.Series:
    """Typical H for synchronous station types. Gas needs the plant type: CCGT
    gets the CCGT value, single cycle the OCGT value. CHP is left null: its
    prime mover varies (engines, turbines) and is not published."""
    out = []
    for f, t in zip(folder, technology.fillna("")):
        if f == "Gas":
            key = "CCGT" if "ccgt" in t.lower() else ("OCGT" if "single cycle" in t.lower() else None)
        else:
            key = H_KEY_BY_STATION.get(f)
        out.append(h_by_fuel.get(key, np.nan) if key else np.nan)
    return pd.Series(out, dtype="float64")


def build_stations(dukes: pd.DataFrame, repd: pd.DataFrame, geo: pd.DataFrame, h_by_fuel: dict,
                   last_updated: datetime, dukes_src: str, repd_src: str) -> tuple[pd.DataFrame, dict]:
    notes = {}
    # --- DUKES ----------------------------------------------------------------
    unknown = sorted(set(dukes["primary_fuel"].dropna()) - set(DUKES_FUEL))
    if unknown:
        raise pc.ProfilesError(f"DUKES fuels with no Generator folder: {unknown}")
    d = dukes.reset_index(drop=True)
    d_key = "dukes:" + d["desnz_site_code"].astype(str).where(d["desnz_site_code"].notna(),
                                                              "row" + d.index.astype(str))
    d_chp = _yes_no(d["chp"])
    d_folder = d["primary_fuel"].map(DUKES_FUEL).where(~pd.Series(d_chp).fillna(False).to_numpy(), CHP_FOLDER)
    dk = pd.DataFrame({
        "source_key": d_key, "source": "dukes", "source_dataset": dukes_src,
        "station_name": d["site_name"], "company": d["company_name"], "technology": d["type"],
        "primary_fuel": d["primary_fuel"], "secondary_fuel": d["secondary_fuel"], "chp": d_chp,
        "fuel_folder": d_folder, "development_status": "Operational",
        "capacity_mw": pc.to_num(d["installedcapacity_mw"]),
        "year_commissioned": pd.array(pd.to_numeric(d["year_commissioned"], errors="coerce"), dtype="Int64"),
        "region": d["region"], "easting": pc.to_num(d["x_coordinate"]), "northing": pc.to_num(d["y_coordinate"]),
        "postcode": d["postcode"], "turbines": pd.array([pd.NA] * len(d), dtype="Int64"),
        "turbine_capacity_mw": np.nan, "geo_key": "dukes:" + d["site_name"].astype(str),
    })
    # --- REPD -----------------------------------------------------------------
    unknown = sorted(set(repd["technology_type"].dropna()) - set(REPD_TECH))
    if unknown:
        raise pc.ProfilesError(f"REPD technologies with no Generator folder: {unknown}")
    status = repd["development_status_short"].astype("string").str.strip()
    keep = status.isin(REPD_KEEP_STATUS) & repd["technology_type"].map(REPD_TECH).notna()
    notes["repd_rows_left_out_by_status"] = {str(k): int(v) for k, v in
                                             status[~status.isin(REPD_KEEP_STATUS)].value_counts().items()}
    notes["repd_rows_left_out_not_generation"] = int((status.isin(REPD_KEEP_STATUS)
                                                      & repd["technology_type"].map(REPD_TECH).isna()).sum())
    r = repd[keep].reset_index(drop=True)
    r_chp = _yes_no(r["chp_enabled"])
    r_folder = r["technology_type"].map(REPD_TECH).where(~pd.Series(r_chp).fillna(False).to_numpy(), CHP_FOLDER)
    op_year = pd.to_datetime(r["operational"], errors="coerce").dt.year
    rp = pd.DataFrame({
        "source_key": "repd:" + r["ref_id"].astype(str), "source": "repd", "source_dataset": repd_src,
        "station_name": r["site_name"], "company": r["operator_or_applicant"], "technology": r["technology_type"],
        "primary_fuel": None, "secondary_fuel": None, "chp": r_chp, "fuel_folder": r_folder,
        "development_status": status[keep].to_numpy(),
        "capacity_mw": pc.to_num(r["installed_capacity_mwelec"]),
        "year_commissioned": pd.array(op_year, dtype="Int64"),
        "region": r["region"], "easting": pc.to_num(r["x_coordinate"]), "northing": pc.to_num(r["y_coordinate"]),
        "postcode": r["post_code"], "turbines": pd.array(pd.to_numeric(r["no_of_turbines"], errors="coerce").round(),
                                                         dtype="Int64"),
        "turbine_capacity_mw": pc.to_num(r["turbine_capacity_mw"]),
        "geo_key": "repd:" + r["ref_id"].astype(str),
    })
    allst = pd.concat([dk, rp], ignore_index=True)

    # --- geography (DNO licence area, GSP region) -----------------------------
    g = geo.copy()
    g["geo_key"] = g["source"].astype(str) + ":" + g["asset_id"].astype(str).str.split(":").str[-1]
    g = g.drop_duplicates("geo_key", keep=False)          # ambiguous keys are not used
    allst = allst.merge(g[["geo_key", "dno_license_area", "gsp_region"]], on="geo_key", how="left")

    flags = [[] for _ in range(len(allst))]
    for i in np.flatnonzero(~allst["capacity_mw"].gt(0).to_numpy()):
        flags[i].append("no_capacity")
    h = _station_h(allst["fuel_folder"], allst["technology"], h_by_fuel)
    cap = allst["capacity_mw"]
    out = pd.DataFrame({
        "profile_id": allst["source_key"].map(lambda k: "gen-" + pc.slug(k)).astype(object),
        "source_dataset": allst["source_dataset"].astype(object),
        "source_key": allst["source_key"].astype(object),
        "last_updated_utc": pc.last_updated_column(len(allst), last_updated).to_numpy(),
        "source": allst["source"].astype(object),
        "station_name": pc.str_or_none(allst["station_name"]),
        "company": pc.str_or_none(allst["company"]),
        "technology": pc.str_or_none(allst["technology"]),
        "primary_fuel": pc.str_or_none(allst["primary_fuel"]),
        "secondary_fuel": pc.str_or_none(allst["secondary_fuel"]),
        "chp": pd.array(allst["chp"], dtype="boolean"),
        "fuel_folder": allst["fuel_folder"].astype(object),
        "development_status": pc.str_or_none(allst["development_status"]),
        "capacity_mw": cap.astype("float64"),
        "storage_mwh": np.full(len(allst), np.nan),
        **machine_columns(cap, h),
        "year_commissioned": pd.array(allst["year_commissioned"], dtype="Int64"),
        "region": pc.str_or_none(allst["region"]),
        "dno_licence_area": pc.str_or_none(allst["dno_license_area"]),
        "gsp_region": pc.str_or_none(allst["gsp_region"]),
        "easting": allst["easting"].astype("float64"),
        "northing": allst["northing"].astype("float64"),
        "postcode": pc.str_or_none(allst["postcode"]),
        "turbines": pd.array(allst["turbines"], dtype="Int64"),
        "turbine_capacity_mw": allst["turbine_capacity_mw"].astype("float64"),
        "quality_flags": pd.Series([";".join(f) for f in flags], dtype=object),
    })
    pc.ensure_unique(out["source_key"], "stations source_key")
    pc.ensure_unique(out["profile_id"], "stations profile_id")
    _spec = pc.load_spec(FIELDS_JSON, "stations")
    out = pc.spec_order(pc.utc_timestamps(out, _spec), _spec)
    notes["stations_by_source"] = out["source"].value_counts().sort_index().to_dict()
    return out.sort_values("profile_id", kind="mergesort").reset_index(drop=True), notes


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #

def build(lake: Path, last_updated: datetime, out_root: Path = pc.PROFILES_ROOT) -> dict:
    h_by_fuel = load_h_by_fuel()
    start = last_updated - timedelta(days=WINDOW_DAYS)
    ref = pd.DataFrame(json.loads((lake / BMU_REF).read_text(encoding="utf-8")))
    bm, bm_dyn, bm_notes = build_bm_units(ref, dynamics(lake, start, last_updated), metered(lake, start, last_updated),
                                  h_by_fuel, last_updated, start)

    dukes_path = pc.latest_snapshot(lake / DUKES, "edition_year=*/*.parquet", "edition_year", last_updated)
    repd_path = pc.latest_snapshot(lake / REPD, "snapshot_date=*/*.parquet", "snapshot_date", last_updated)
    dukes_src = dukes_path.relative_to(lake).as_posix()
    repd_src = repd_path.relative_to(lake).as_posix()
    geo = pd.read_parquet(sorted((lake / GEOGRAPHY).glob("*.parquet"))[0])
    st, st_notes = build_stations(pd.read_parquet(dukes_path), pd.read_parquet(repd_path), geo, h_by_fuel,
                                  last_updated, dukes_src, repd_src)

    written = []
    specs = {t: pc.load_spec(FIELDS_JSON, t) for t in ("bm_units", "bm_dynamics", "stations")}
    for folder in ALL_FOLDERS:
        for table, frame in (("bm_units", bm), ("bm_dynamics", bm_dyn), ("stations", st)):
            part = frame[frame["fuel_folder"].eq(folder)].reset_index(drop=True)
            path = out_root / FAMILY / Path(folder) / f"{table}.parquet"
            if len(part):
                written.append(pc.write_profile(part, specs[table], path))
            elif path.exists():
                path.unlink()
    named = pc.verify_names_used(FAMILY)
    pc.write_fields_md(FIELDS_JSON)
    return {
        "family": FAMILY,
        "inputs": [BMU_REF, *(f"{ELEXON}/{d}" for d in ("rure", "rdre", "ruri", "rdri", "sel", "sil", "mels",
                                                         "ndz", "mzt", "mnzt", "b1610")),
                   dukes_src, repd_src, GEOGRAPHY, f"GDA Scripts/{GDA_H_FILE} (H_BY_FUEL)"],
        "files": written,
        "notes": {"profiles_named": named, **bm_notes, **st_notes,
                  "bm_units_by_folder": bm["fuel_folder"].value_counts().sort_index().to_dict(),
                  "bm_units_with_metered_output": int(bm_dyn["metered_periods"].notna().sum()),
                  "bm_units_with_ramp_rates": int(bm_dyn["ramp_up_mw_per_min_p50"].notna().sum())},
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
