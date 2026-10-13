"""Build the Transformers profiles from the GDA data lake.

Inputs (under the lake's DataSources folder):
  UkPowerNetworks/Parquet/..._LTDS_Table_2a_Transformer_Data_2W   UKPN two-winding units
  UkPowerNetworks/Parquet/..._LTDS_Table_2b_Transformer_Data_3W   UKPN three-winding units
  NorthernPowerGrid/Parquet/LTDS_Appendix_4_Transformer_Data       NPG units
  NationalGrid/RAWData/LTDS Tabular Model/ltds-table-2a/2b-*.csv   NGED units
  Derived/tap_changers, Derived/bsp_power_factor, Derived/asset_stress_ledger

Outputs:
  Transformers/<voltage_class>/units.parquet   one row per published transformer, by HV voltage
  Transformers/observed/taps.parquet           tap changer behaviour seen in voltage readings
  Transformers/observed/flows.parquet          P, Q, MVA, power factor and kV statistics
  Transformers/observed/stress.parquet         tap operations and time at high loading
  Transformers/FIELDS.md

Impedance conventions. Every operator's transformer impedance turns out to be
percent on a 100 MVA base, whatever its column name or GDA's normaliser says:
  NPG   documented as percent on 100 MVA.
  UKPN  GDA treats it as percent on the unit's own rating. Read that way, the
        median unit has X of 99% on its own rating, which is physically
        impossible (typical is 5 to 30%).
  NGED  GDA labels it ohmic. Read as ohms referred to either side, a 12 MVA
        33/11kV unit gives 4% or 70%; as percent on 100 MVA it gives 12%.
  Test (2026-10-05 lake): log-log slope of reported X against rating is -0.76
  (NPG), -0.61 (UKPN), -0.74 (NGED). Percent on a fixed 100 MVA base falls with
  rating; percent on own rating would be flat (slope near 0). Read on 100 MVA, the
  median X on own rating is 18% (NPG), 23% (UKPN), 11% (NGED): all typical.
  So UKPN and NGED are treated as percent on 100 MVA and every such row carries
  the quality flag convention_inferred. Reported values are kept as published.

Nothing is guessed: a unit with no rating keeps its percent-on-100-MVA values but
has no percent-on-rating values (flag no_rating).

Run:  python tools/build_transformers.py [--as-of YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import profiles_common as pc

FAMILY = "Transformers"
FIELDS_JSON = pc.PROFILES_ROOT / FAMILY / "fields.json"

UKPN_2W = "UkPowerNetworks/Parquet/Long_Term_Development_Statement_LTDS_Table_2a_Transformer_Data_2W/ukpn-ltds-table-2a-transformer-2w.parquet"
UKPN_3W = "UkPowerNetworks/Parquet/Long_Term_Development_Statement_LTDS_Table_2b_Transformer_Data_3W/ukpn-ltds-table-2b-transformer-data-3w.parquet"
NPG_TX = "NorthernPowerGrid/Parquet/LTDS_Appendix_4_Transformer_Data/ltds-appendix-4.parquet"
NGED_2W = "NationalGrid/RAWData/LTDS Tabular Model/ltds-table-2a-two-winding-transformer.csv"
NGED_3W = "NationalGrid/RAWData/LTDS Tabular Model/ltds-table-2b-three-winding-transformer.csv"
TAPS = "Derived/tap_changers"
FLOWS = "Derived/bsp_power_factor"
STRESS = "Derived/asset_stress_ledger"

# Licence names as each operator publishes them -> canonical codes (the same maps
# GDA's NetworkModel/sources normalisers use).
UKPN_LIC = {"Eastern Power Networks (EPN)": "EPN", "London Power Networks (LPN)": "LPN",
            "South Eastern Power Networks (SPN)": "SPN"}
NPG_LIC = {"Northeast": "NPGN", "Yorkshire": "NPGY"}
NGED_LIC = {"EMIDS": "EMID", "WMIDS": "WMID", "WMID": "WMID", "SWEST": "SWEST", "SWALES": "SWALES"}

FLOW_WINDOW_DAYS = 365

# What each operator's published continuous rating is (GridSim Rate A basis).
RATE_A_BASIS = {"ukpn": "winter continuous", "npg": "continuous (season not stated)",
                "nged": "nominal (season not stated)"}

# Columns every operator reader hands to finish_units (before derived values).
RAW_UNIT_COLUMNS = [
    "source_dataset", "source_key", "operator", "licence", "gsp_group", "winding_count",
    "hv_node", "hv_substation", "hv_kv", "lv_node", "lv_substation", "lv_kv",
    "tertiary_node", "tertiary_kv", "status", "vector_group",
    "rating_mva", "rating_summer_mva", "rating_emergency_mva",
    "reported_impedance_base", "reported_r1", "reported_x1", "reported_x0",
    "reported_x_lv_tert", "reported_x_hv_tert",
    "reported_tap_min", "reported_tap_max", "reported_tap_convention",
    "reverse_power_reported", "reverse_power_unit",
    "earthing_hv", "earthing_lv",
]


# --------------------------------------------------------------------------- #
# Operator readers: published table -> common raw unit columns
# --------------------------------------------------------------------------- #

def _frame(n: int, **cols) -> pd.DataFrame:
    """Assemble a raw-unit frame, filling any column not given with nulls."""
    out = pd.DataFrame(index=range(n))
    for c in RAW_UNIT_COLUMNS:
        v = cols.get(c, None)
        out[c] = v.to_numpy() if isinstance(v, pd.Series) else v
    return out


def _lic(series: pd.Series, mapping: dict, what: str) -> pd.Series:
    """Map licence names, failing loud on one we do not know (a new licence name
    would otherwise silently become null)."""
    s = series.astype("string").str.strip()
    unknown = sorted(set(s.dropna()) - set(mapping))
    if unknown:
        raise pc.ProfilesError(f"{what}: unknown licence values {unknown}")
    return s.map(mapping)


def read_ukpn_2w(t: pd.DataFrame) -> pd.DataFrame:
    return _frame(
        len(t), source_dataset=UKPN_2W,
        source_key=("ukpn:2a:" + t["ID"].astype(str)).reset_index(drop=True),
        operator="ukpn", licence=_lic(t["LicenceArea"], UKPN_LIC, "UKPN 2a"),
        gsp_group=t["GridSupplyPoint"], winding_count=2,
        hv_node=t["HV_Node"], hv_substation=t["HV_Substation"], hv_kv=pc.to_num(t["Voltage_HV (kV)"]),
        lv_node=t["LV_Node"], lv_substation=t["LV_Substation"], lv_kv=pc.to_num(t["Voltage_LV (kV)"]),
        vector_group=t["Vector_Group"],
        rating_mva=pc.to_num(t["Transformer_Rating_MVA_Winter"]),
        rating_summer_mva=pc.to_num(t["Transformer_Rating_MVA_Summer"]),
        reported_impedance_base="percent_on_100mva_inferred",
        reported_r1=pc.to_num(t["Positive_Sequence_Impedance_R_Percent"]),
        reported_x1=pc.to_num(t["Positive_Sequence_Impedance_X_Percent"]),
        reported_x0=pc.to_num(t["Zero_Sequence_Impedance_X_Percent"]),
        reported_tap_min=pc.to_num(t["Tap_Range_Min_Percent"]), reported_tap_max=pc.to_num(t["Tap_Range_Max_Percent"]),
        reported_tap_convention="percent_of_nominal_ratio",
        reverse_power_reported=pc.to_num(t["Reverse_Power_Capability_Percent"]), reverse_power_unit="%",
        earthing_hv=t["Method_of_Earthing_HV"], earthing_lv=t["Method_of_Earthing_LV"],
    )


def read_ukpn_3w(t: pd.DataFrame) -> pd.DataFrame:
    vg = (t["Vector_Group_HV"].astype("string").fillna("").str.strip() + "/"
          + t["Vector_Group_LV1"].astype("string").fillna("").str.strip() + "/"
          + t["Vector_Group_LV2"].astype("string").fillna("").str.strip())
    return _frame(
        len(t), source_dataset=UKPN_3W,
        source_key=("ukpn:2b:" + t["ID"].astype(str)).reset_index(drop=True),
        operator="ukpn", licence=_lic(t["LicenceArea"], UKPN_LIC, "UKPN 2b"),
        gsp_group=t["GridSupplyPoint"], winding_count=3,
        hv_node=t["HV_Node"], hv_substation=t["HV_Substation"], hv_kv=pc.to_num(t["Voltage_HV (kV)"]),
        lv_node=t["LV_Node_1"], lv_substation=t["LV_Substation_1"], lv_kv=pc.to_num(t["Voltage_LV_1 (kV)"]),
        tertiary_node=t["LV_Node_2"], tertiary_kv=pc.to_num(t["Voltage_LV_2 (kV)"]),
        vector_group=vg.where(vg != "//"),
        rating_mva=pc.to_num(t["Transformer_Rating_MVA_Winter_HV"]),
        rating_summer_mva=pc.to_num(t["Transformer_Rating_MVA_Summer_HV"]),
        reported_impedance_base="percent_on_100mva_inferred",
        reported_r1=pc.to_num(t["Positive_Sequence_Impedance_R_HV_LV1_Percent"]),
        reported_x1=pc.to_num(t["Positive_Sequence_Impedance_X_HV_LV1_Percent"]),
        reported_x0=pc.to_num(t["Zero_Sequence_Impedance_X_HV_LV1_Percent"]),
        reported_x_lv_tert=pc.to_num(t["Positive_Sequence_Impedance_X_LV1_LV2_Percent"]),
        reported_x_hv_tert=pc.to_num(t["Positive_Sequence_Impedance_X_HV_LV2_Percent"]),
        reported_tap_min=pc.to_num(t["Tap_Range_Min_Percent_HV"]), reported_tap_max=pc.to_num(t["Tap_Range_Max_Percent_HV"]),
        reported_tap_convention="percent_of_nominal_ratio",
        reverse_power_reported=pc.to_num(t["Reverse_Power_Capability_Percent"]), reverse_power_unit="%",
        earthing_hv=t["Method_of_Earthing_HV"], earthing_lv=t["Method_of_Earthing_LV1"],
    )


def read_npg(t: pd.DataFrame) -> pd.DataFrame:
    t = t.reset_index(drop=True)
    name = t["S/S or Busbar Name Node"]
    return _frame(
        len(t), source_dataset=NPG_TX,
        source_key=pd.Series([f"npg:a4:row{i}" for i in range(len(t))]),
        operator="npg", licence=_lic(t["License"], NPG_LIC, "NPG appendix 4"),
        gsp_group=t["S/S Group"], winding_count=2,
        hv_node=name, hv_kv=pc.to_num(t["Primary Voltage (kV)"]),
        lv_node=name, lv_kv=pc.to_num(t["Secondary Voltage (kV)"]),
        vector_group=t["Vector Group"],
        rating_mva=pc.to_num(t["Transformer Rating (MVA)"]),
        reported_impedance_base="percent_on_100mva",
        reported_r1=pc.to_num(t["Positive Sequence Impedance R (% on 100 MVA Base)"]),
        reported_x1=pc.to_num(t["Positive Sequence Impedance X (% on 100 MVA Base)"]),
        reported_x0=pc.to_num(t["Zero Sequence Reactance X (% on 100 MVA Base)"]),
        reported_tap_min=pc.to_num(t["Minimum Tap %"]), reported_tap_max=pc.to_num(t["Maximum Tap %"]),
        reported_tap_convention="percent_change",
        reverse_power_reported=pc.to_num(t["Reverse Power Capability (MVA)"]), reverse_power_unit="MVA",
        earthing_hv=t["Method of Earthing"],
    )


def read_nged(t: pd.DataFrame, three_winding: bool) -> pd.DataFrame:
    t = t.reset_index(drop=True)
    tag = "2b" if three_winding else "2a"
    cols = dict(
        source_dataset=NGED_3W if three_winding else NGED_2W,
        source_key=pd.Series([f"nged:{tag}:row{i}" for i in range(len(t))]),
        operator="nged", licence=_lic(t["Licence"], NGED_LIC, f"NGED {tag}"),
        gsp_group=t["GSP Group"], winding_count=3 if three_winding else 2,
        hv_node=t["Node 1"], hv_kv=pc.to_num(t["Operating Voltage 1"]),
        lv_node=t["Node 2"], lv_kv=pc.to_num(t["Operating Voltage 2"]),
        status=t["Status"].map(pc.norm_status), vector_group=t["Vector Group"],
        rating_mva=pc.to_num(t["Nominal Rating"]), rating_emergency_mva=pc.to_num(t["Emergency Rating"]),
        reported_impedance_base="percent_on_100mva_inferred",
        reported_r1=pc.to_num(t["R1"]),
        reported_tap_min=pc.to_num(t["Min Tap"]), reported_tap_max=pc.to_num(t["Max Tap"]),
        reported_tap_convention="percent_change",
        reverse_power_reported=pc.to_num(t["Reverse Power Capability"]), reverse_power_unit="unknown",
        earthing_hv=t["Method of Earthing"],
    )
    if three_winding:
        cols.update(tertiary_node=t["Node 3"], tertiary_kv=pc.to_num(t["Operating Voltage 3"]),
                    reported_x1=pc.to_num(t["X1 HV-LV"]), reported_x0=pc.to_num(t["X0 HV-LV"]),
                    reported_x_lv_tert=pc.to_num(t["X1 LV-Tertiary"]),
                    reported_x_hv_tert=pc.to_num(t["X1 HV-Tertiary"]))
    else:
        cols.update(reported_x1=pc.to_num(t["X1"]), reported_x0=pc.to_num(t["X0"]))
    return _frame(len(t), **cols)


# --------------------------------------------------------------------------- #
# Units: harmonise, derive, flag
# --------------------------------------------------------------------------- #

def finish_units(raw: pd.DataFrame, last_updated: datetime) -> tuple[pd.DataFrame, dict]:
    """Harmonise impedance, derive per-rating values, flag issues. Returns the
    units frame in spec order plus counts of rows left out (and why)."""
    df = raw.copy().reset_index(drop=True)
    dropped = {}

    no_kv = df["hv_kv"].isna() | df["lv_kv"].isna() | df["hv_kv"].le(0) | df["lv_kv"].le(0)
    dropped["no_winding_voltage"] = int(no_kv.sum())
    df = df[~no_kv].reset_index(drop=True)
    df["voltage_class"] = df["hv_kv"].map(pc.voltage_folder)
    no_class = df["voltage_class"].isna()
    dropped["hv_voltage_has_no_folder"] = {str(k): int(v) for k, v in
                                           df.loc[no_class, "hv_kv"].value_counts().sort_index().items()}
    df = df[~no_class].reset_index(drop=True)

    flags: list[list[str]] = [[] for _ in range(len(df))]

    def flag(mask, name):
        for i in np.flatnonzero(np.asarray(mask, dtype=bool)):
            flags[i].append(name)

    rating = df["rating_mva"].where(df["rating_mva"].gt(0))
    flag(rating.isna(), "no_rating")
    flag(df["hv_kv"].lt(df["lv_kv"]), "hv_below_lv")

    # Factor that takes each row's reported percentages to percent on 100 MVA.
    # Every source in use is on 100 MVA (see the module notes); any other base
    # is refused rather than converted by a rule nobody has checked.
    base = df["reported_impedance_base"]
    known = {"percent_on_100mva", "percent_on_100mva_inferred"}
    unknown = sorted(set(base) - known)
    if unknown:
        raise pc.ProfilesError(f"transformer impedance base(s) with no conversion rule: {unknown}")
    to_100 = pd.Series(1.0, index=df.index)
    flag(base.eq("percent_on_100mva_inferred"), "convention_inferred")

    # Tap limits to percent change from nominal ratio. UKPN publishes percent OF
    # nominal ratio (81 means 19% below); the band check stops a file that mixes
    # the two forms from being converted wrongly.
    conv = df["reported_tap_convention"]
    unknown_conv = sorted(set(conv) - {"percent_change", "percent_of_nominal_ratio"})
    if unknown_conv:
        raise pc.ProfilesError(f"tap convention(s) with no conversion rule: {unknown_conv}")
    of_ratio = conv.eq("percent_of_nominal_ratio")
    for col in ("reported_tap_min", "reported_tap_max"):
        v = df.loc[of_ratio, col]
        bad = v.notna() & ~v.between(50, 150)
        if bad.any():
            raise pc.ProfilesError(f"{int(bad.sum())} {col} values outside 50-150 in a percent-of-ratio source, "
                                   f"for example {v[bad].head(3).tolist()}")
    shift = np.where(of_ratio, 100.0, 0.0)
    tap_min = df["reported_tap_min"].astype("float64") - shift
    tap_max = df["reported_tap_max"].astype("float64") - shift

    r100 = df["reported_r1"] * to_100
    x100 = df["reported_x1"] * to_100
    zero_imp = r100.eq(0) & x100.eq(0)
    flag(zero_imp, "zero_impedance")
    flag(df["reported_x1"].isna(), "no_reactance")

    out = pd.DataFrame({
        "profile_id": df["source_key"].map(lambda k: pc.sha_id("txf", k)).astype(object),
        "source_dataset": df["source_dataset"].astype(object),
        "source_key": df["source_key"].astype(str).astype(object),
        "last_updated_utc": pc.last_updated_column(len(df), last_updated).to_numpy(),
        "operator": df["operator"].astype(object),
        "licence": df["licence"].astype(object),
        "gsp_group": pc.str_or_none(df["gsp_group"]),
        "winding_count": df["winding_count"].astype("int64"),
        "hv_node": pc.str_or_none(df["hv_node"]),
        "hv_substation": pc.str_or_none(df["hv_substation"]),
        "hv_kv": df["hv_kv"].astype("float64"),
        "lv_node": pc.str_or_none(df["lv_node"]),
        "lv_substation": pc.str_or_none(df["lv_substation"]),
        "lv_kv": df["lv_kv"].astype("float64"),
        "tertiary_node": pc.str_or_none(df["tertiary_node"]),
        "tertiary_kv": pd.to_numeric(df["tertiary_kv"]).astype("float64"),
        "voltage_class": df["voltage_class"].astype(object),
        "status": pc.str_or_none(df["status"]),
        "vector_group": pc.str_or_none(df["vector_group"]),
        "rating_mva": rating.astype("float64"),
        "rating_summer_mva": pd.to_numeric(df["rating_summer_mva"]).astype("float64"),
        "rating_emergency_mva": pd.to_numeric(df["rating_emergency_mva"]).astype("float64"),
        "rate_a_mva": rating.astype("float64"),
        "rate_a_basis": pd.Series([RATE_A_BASIS[op] if pd.notna(r) else None
                                   for op, r in zip(df["operator"], rating)], dtype=object),
        "rate_b_mva": np.full(len(df), np.nan),
        "rate_b_basis": pd.Series([None] * len(df), dtype=object),
        "rate_c_mva": pd.to_numeric(df["rating_emergency_mva"]).astype("float64"),
        "rate_c_basis": pd.Series(np.where(pd.to_numeric(df["rating_emergency_mva"]).notna(),
                                           "emergency (duration not stated)", None), dtype=object),
        "r_pct_100mva": r100.astype("float64"),
        "x_pct_100mva": x100.astype("float64"),
        "x0_pct_100mva": (df["reported_x0"] * to_100).astype("float64"),
        "x_lv_tert_pct_100mva": (pd.to_numeric(df["reported_x_lv_tert"]) * to_100).astype("float64"),
        "x_hv_tert_pct_100mva": (pd.to_numeric(df["reported_x_hv_tert"]) * to_100).astype("float64"),
        "r_pct_on_rating": (r100 * rating / 100.0).astype("float64"),
        "x_pct_on_rating": (x100 * rating / 100.0).astype("float64"),
        "x_over_r": (x100 / r100).where(r100.gt(0)).astype("float64"),
        "tap_min_pct": tap_min,
        "tap_max_pct": tap_max,
        "tap_range_pct": (tap_max - tap_min).astype("float64"),
        "reported_tap_min": df["reported_tap_min"].astype("float64"),
        "reported_tap_max": df["reported_tap_max"].astype("float64"),
        "reported_tap_convention": df["reported_tap_convention"].astype(object),
        "reverse_power_reported": pd.to_numeric(df["reverse_power_reported"]).astype("float64"),
        "reverse_power_unit": pc.str_or_none(df["reverse_power_unit"]),
        "earthing_hv": pc.str_or_none(df["earthing_hv"]),
        "earthing_lv": pc.str_or_none(df["earthing_lv"]),
        "reported_impedance_base": df["reported_impedance_base"].astype(object),
        "reported_r1": df["reported_r1"].astype("float64"),
        "reported_x1": df["reported_x1"].astype("float64"),
        "reported_x0": df["reported_x0"].astype("float64"),
        "winding_temp_max_degc": np.full(len(df), np.nan),
        "top_oil_temp_max_degc": np.full(len(df), np.nan),
        "quality_flags": pd.Series([";".join(f) for f in flags], dtype=object),
    })
    pc.ensure_unique(out["source_key"], "transformer source_key")
    pc.ensure_unique(out["profile_id"], "transformer profile_id")
    _spec = pc.load_spec(FIELDS_JSON, "units")
    out = pc.spec_order(pc.utc_timestamps(out, _spec), _spec)
    out = out.sort_values(["hv_kv", "lv_kv", "source_key"], kind="mergesort").reset_index(drop=True)
    return out, dropped


# --------------------------------------------------------------------------- #
# Observed tables
# --------------------------------------------------------------------------- #

def _utc(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, utc=True).astype("datetime64[us, UTC]")


def build_taps(raw: pd.DataFrame, last_updated: datetime) -> tuple[pd.DataFrame, int]:
    """Tap changer observations whose readings end on or before the last-updated date."""
    df = raw.copy()
    df["observed_to_utc"] = _utc(df["span_end"])
    keep = df["observed_to_utc"] <= last_updated
    excluded = int((~keep).sum())
    df = df[keep].reset_index(drop=True)
    out = pd.DataFrame({
        "profile_id": ("tap-" + df["gsp"].map(pc.slug) + "-" + df["sgt"].map(pc.slug)).astype(object),
        "source_dataset": TAPS,
        "source_key": (df["gsp"].astype(str) + ":" + df["sgt"].astype(str)).astype(object),
        "last_updated_utc": pc.last_updated_column(len(df), last_updated).to_numpy(),
        "gsp": df["gsp"].astype(str).astype(object),
        "transformer": df["sgt"].astype(str).astype(object),
        "voltage_kv": df["vnom_kv"].astype("float64"),
        "n_obs": df["n_obs"].astype("int64"),
        "observed_from_utc": _utc(df["span_start"]).to_numpy(),
        "observed_to_utc": df["observed_to_utc"].to_numpy(),
        "is_oltc": df["is_oltc"].astype(bool),
        "tap_step_kv": df["step_kv"].astype("float64"),
        "tap_step_pct": df["step_pct"].astype("float64"),
        "visible_steps": df["n_visible_steps"].astype("Int64"),
        "span_steps": df["span_steps"].astype("float64"),
        "lattice_residual": df["lattice_residual"].astype("float64"),
        "ltds_tap_span_pct": df["ltds_tap_span_pct"].astype("float64"),
        "ltds_expected_steps": df["ltds_expected_steps"].astype("float64"),
    })
    pc.ensure_unique(out["profile_id"], "taps profile_id")
    _spec = pc.load_spec(FIELDS_JSON, "taps")
    out = pc.spec_order(pc.utc_timestamps(out, _spec), _spec)
    return out.sort_values("profile_id", kind="mergesort").reset_index(drop=True), excluded


def build_flows(readings: pd.DataFrame, last_updated: datetime) -> pd.DataFrame:
    """Per-transformer flow statistics over each transformer's latest 365 days
    of readings on or before the last-updated date."""
    keys = ["dno", "region", "substation", "transformer"]
    df = readings[(readings["DATETIME"] <= last_updated) & readings["MW"].notna()]
    for k in keys:   # categories keep memory low; groupby only sees keys that occur
        if not isinstance(df[k].dtype, pd.CategoricalDtype):
            df = df.assign(**{k: df[k].astype(str).astype("category")})
    end = df.groupby(keys, observed=True, sort=False)["DATETIME"].transform("max")
    df = df[df["DATETIME"] > end - timedelta(days=FLOW_WINDOW_DAYS)]
    g = df.groupby(keys, sort=True, observed=True)

    def q(col, p):
        return g[col].quantile(p)

    stats = pd.DataFrame({
        "window_start_utc": g["DATETIME"].min(),
        "window_end_utc": g["DATETIME"].max(),
        "n_obs": g["MW"].size(),
        "p_mw_min": g["MW"].min(), "p_mw_p05": q("MW", 0.05), "p_mw_p50": q("MW", 0.50),
        "p_mw_p95": q("MW", 0.95), "p_mw_max": g["MW"].max(),
        "q_mvar_min": g["MVAr"].min(), "q_mvar_p05": q("MVAr", 0.05), "q_mvar_p50": q("MVAr", 0.50),
        "q_mvar_p95": q("MVAr", 0.95), "q_mvar_max": g["MVAr"].max(),
        "s_mva_p50": q("MVA", 0.50), "s_mva_p95": q("MVA", 0.95), "s_mva_max": g["MVA"].max(),
        "pf_p05": q("power_factor", 0.05), "pf_p50": q("power_factor", 0.50),
        "kv_p05": q("kV", 0.05), "kv_p50": q("kV", 0.50), "kv_p95": q("kV", 0.95),
        "reverse_flow_share": g["MW"].apply(lambda s: float((s < 0).mean())),
        "zero_flow_share": g["MW"].apply(lambda s: float((s == 0).mean())),
    }).reset_index()
    for k in keys:
        stats[k] = stats[k].astype(str)
    n = len(stats)
    key = stats["dno"] + ":" + stats["region"] + ":" + stats["substation"] + ":" + stats["transformer"]
    out = pd.DataFrame({
        "profile_id": ("flow-" + stats["dno"].map(pc.slug) + "-" + stats["region"].map(pc.slug) + "-"
                       + stats["substation"].map(pc.slug) + "-" + stats["transformer"].map(pc.slug)).astype(object),
        "source_dataset": FLOWS,
        "source_key": key.astype(object),
        "last_updated_utc": pc.last_updated_column(n, last_updated).to_numpy(),
        "operator": stats["dno"].astype(object),
        "region": stats["region"].astype(object),
        "substation": stats["substation"].astype(object),
        "transformer": stats["transformer"].astype(object),
        "window_start_utc": stats["window_start_utc"].astype("datetime64[us, UTC]").to_numpy(),
        "window_end_utc": stats["window_end_utc"].astype("datetime64[us, UTC]").to_numpy(),
        "n_obs": stats["n_obs"].astype("int64"),
    })
    for c in ["p_mw_min", "p_mw_p05", "p_mw_p50", "p_mw_p95", "p_mw_max", "q_mvar_min", "q_mvar_p05",
              "q_mvar_p50", "q_mvar_p95", "q_mvar_max", "s_mva_p50", "s_mva_p95", "s_mva_max",
              "pf_p05", "pf_p50", "kv_p05", "kv_p50", "kv_p95", "reverse_flow_share", "zero_flow_share"]:
        out[c] = stats[c].astype("float64").to_numpy()
    pc.ensure_unique(out["profile_id"], "flows profile_id")
    _spec = pc.load_spec(FIELDS_JSON, "flows")
    out = pc.spec_order(pc.utc_timestamps(out, _spec), _spec)
    return out.sort_values("profile_id", kind="mergesort").reset_index(drop=True)


def build_stress(raw: pd.DataFrame, last_updated: datetime) -> tuple[pd.DataFrame, int]:
    """Stress ledger rows whose window ends on or before the last-updated date."""
    df = raw.copy()
    df["window_end_utc"] = _utc(df["window_end"])
    keep = df["window_end_utc"] <= last_updated
    excluded = int((~keep).sum())
    df = df[keep].reset_index(drop=True)
    flag = df["thermal_exceedance_flag"]
    out = pd.DataFrame({
        "profile_id": ("stress-" + df["asset_id"].map(pc.slug)).astype(object),
        "source_dataset": STRESS,
        "source_key": df["asset_id"].astype(str).astype(object),
        "last_updated_utc": pc.last_updated_column(len(df), last_updated).to_numpy(),
        "operator": df["operator"].astype(str).astype(object),
        "asset_name": df["asset_name"].astype(str).astype(object),
        "asset_type": df["asset_type"].astype(str).astype(object),
        "voltage_kv": df["voltage_kv"].astype("float64"),
        "window_start_utc": _utc(df["window_start"]).to_numpy(),
        "window_end_utc": df["window_end_utc"].to_numpy(),
        "tap_ops_total": df["tap_ops_total"].astype("float64"),
        "tap_ops_last_6mo": df["tap_ops_last_6mo"].astype("float64"),
        "tap_ops_prior_2yr": df["tap_ops_prior_2yr"].astype("float64"),
        "tap_rate_ratio": df["tap_rate_anomaly_ratio"].astype("float64"),
        "tap_step_kv": df["tap_step_kv"].astype("float64"),
        "tap_step_source": pc.str_or_none(df["tap_step_source"]),
        "hours_over_80pct": df["hours_over_80pct"].astype("float64"),
        "worst_loading_pct": df["worst_loading_pct"].astype("float64"),
        "thermal_exceedance": pd.array([None if pd.isna(v) else bool(v) for v in flag], dtype="boolean"),
    })
    pc.ensure_unique(out["profile_id"], "stress profile_id")
    _spec = pc.load_spec(FIELDS_JSON, "stress")
    out = pc.spec_order(pc.utc_timestamps(out, _spec), _spec)
    return out.sort_values("profile_id", kind="mergesort").reset_index(drop=True), excluded


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #

def _need(path: Path) -> Path:
    if not path.exists():
        raise pc.ProfilesError(f"input not found: {path}")
    return path


def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(_need(path), dtype=str, encoding="utf-8-sig", keep_default_na=False)
    df.columns = [str(c).strip() for c in df.columns]
    if df.empty:
        raise pc.ProfilesError(f"{path} has no data rows (a retired source stub?)")
    return df


def read_flow_readings(lake: Path, last_updated: datetime) -> pd.DataFrame:
    """Read the half-hourly transformer readings that can fall inside any
    transformer's statistics window.

    The full set is about 22 million rows, too many to hold at once with string
    keys, so this makes two passes over the partition files:
      1. find each transformer's newest reading on or before the last-updated date;
      2. keep only readings within FLOW_WINDOW_DAYS of that transformer's newest.
    build_flows applies the same window again, so its result does not depend on
    this pre-filter; the pre-filter only saves memory."""
    root = _need(lake / FLOWS)
    files = sorted(p for p in root.glob("year=*/week=*/*.parquet")
                   if int(p.parent.parent.name.split("=")[1]) <= last_updated.year)
    keys = ["dno", "region", "substation", "transformer"]
    stamp = pd.Timestamp(last_updated)

    def key_of(d: pd.DataFrame) -> pd.Series:
        return (d["dno"].astype(str) + "|" + d["region"].astype(str) + "|"
                + d["substation"].astype(str) + "|" + d["transformer"].astype(str))

    newest: dict[str, pd.Timestamp] = {}
    for f in files:                                           # pass 1
        d = pd.read_parquet(f, columns=["DATETIME", "MW", *keys])
        d = d[(d["DATETIME"] <= stamp) & d["MW"].notna()]
        if d.empty:
            continue
        for k, ts in d.groupby(key_of(d), sort=False)["DATETIME"].max().items():
            if k not in newest or ts > newest[k]:
                newest[k] = ts

    window = timedelta(days=FLOW_WINDOW_DAYS)
    starts = {k: v - window for k, v in newest.items()}
    parts = []
    cols = ["DATETIME", *keys, "MW", "MVAr", "MVA", "kV", "power_factor"]
    for f in files:                                           # pass 2
        d = pd.read_parquet(f, columns=cols)
        d = d[(d["DATETIME"] <= stamp) & d["MW"].notna()]
        if d.empty:
            continue
        start = key_of(d).map(starts)
        d = d[d["DATETIME"] > start]
        if d.empty:
            continue
        d = d.assign(**{k: d[k].astype(str).astype("category") for k in keys},
                     **{c: d[c].astype("float64") for c in ("MW", "MVAr", "MVA", "kV", "power_factor")})
        parts.append(d)
    if not parts:
        raise pc.ProfilesError(f"no transformer flow readings on or before {last_updated.date()}")
    out = pd.concat(parts, ignore_index=True)
    for k in keys:   # concat of differing categories falls back to object; re-categorise
        out[k] = out[k].astype(str).astype("category")
    return out


def build(lake: Path, last_updated: datetime, out_root: Path = pc.PROFILES_ROOT) -> dict:
    raw = pd.concat([
        read_ukpn_2w(pd.read_parquet(_need(lake / UKPN_2W))),
        read_ukpn_3w(pd.read_parquet(_need(lake / UKPN_3W))),
        read_npg(pd.read_parquet(_need(lake / NPG_TX))),
        read_nged(_read_csv(lake / NGED_2W), three_winding=False),
        read_nged(_read_csv(lake / NGED_3W), three_winding=True),
    ], ignore_index=True)
    units, dropped = finish_units(raw, last_updated)
    taps, taps_excluded = build_taps(pc.single_parquet(lake / TAPS), last_updated)
    flows = build_flows(read_flow_readings(lake, last_updated), last_updated)
    stress, stress_excluded = build_stress(pc.single_parquet(lake / STRESS), last_updated)

    written = []
    units_spec = pc.load_spec(FIELDS_JSON, "units")
    for vclass in ("6.6kv", "11kv", "33kv", "66kv", "132kv", "275kv", "400kv"):
        part = units[units["voltage_class"].eq(vclass)].reset_index(drop=True)
        path = out_root / FAMILY / vclass / "units.parquet"
        if len(part):
            written.append(pc.write_profile(part, units_spec, path))
        elif path.exists():
            path.unlink()
    for table, frame in (("taps", taps), ("flows", flows), ("stress", stress)):
        written.append(pc.write_profile(frame, pc.load_spec(FIELDS_JSON, table),
                                        out_root / FAMILY / "observed" / f"{table}.parquet"))
    named = pc.verify_names_used(FAMILY)
    pc.write_fields_md(FIELDS_JSON)
    return {
        "family": FAMILY,
        "inputs": [UKPN_2W, UKPN_3W, NPG_TX, NGED_2W, NGED_3W, TAPS, FLOWS, STRESS],
        "files": written,
        "notes": {"profiles_named": named, 
            "units_by_operator": units["operator"].value_counts().sort_index().to_dict(),
            "units_dropped": dropped,
            "units_with_quality_flags": int(units["quality_flags"].ne("").sum()),
            "taps_after_last_updated_excluded": taps_excluded,
            "stress_after_last_updated_excluded": stress_excluded,
            "not_in_lake": "SPD and SPM (SP Energy Networks) transformer tables",
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
