"""Build the Interconnects profiles from the GDA data lake.

Inputs (under the lake's DataSources folder):
  InterconnectorRegister/Parquet/snapshot    NESO interconnector register (built and pipeline)
  Elexon/Parquet/fuelinst                    five-minute generation by fuel, one INT* fuel per link
  NESO/Parquet/<link>_neso_s_*               NESO's transfer limits per link (where usable)

Outputs:
  Interconnects/<link folder>/links.parquet   one row per register entry; Pipeline for unbuilt projects
  Interconnects/FIELDS.md

Flow sign: Elexon publishes interconnector flow as generation, so positive is into
GB and negative is out of GB. Statistics use the 365 days to the last-updated date.

Run:  python tools/build_interconnectors.py [--as-of YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import profiles_common as pc

FAMILY = "Interconnects"
FIELDS_JSON = pc.PROFILES_ROOT / FAMILY / "fields.json"
REGISTER = "InterconnectorRegister/Parquet/snapshot"
FUELINST = "Elexon/Parquet/fuelinst"
NESO = "NESO/Parquet"
WINDOW_DAYS = 365
PIPELINE = "Pipeline"
# Extreme flow beyond this multiple of registered capacity is flagged as a spike.
FLOW_SPIKE_RATIO = 1.1

# Built links: register project name -> (folder, Elexon fuel code, NESO limit dataset or None).
# A built project missing from this table stops the build, so a new link is noticed.
# BritNed and Nemo Link limit series carry dates that cannot be read (for example
# '202405210 17:00-18:00'), so no limit statistics are taken for them.
LINKS = {
    "Britned": ("Britned", "INTNED", None),
    "Viking Link Denmark Interconnector": ("Viking", "INTVKL", "viking_link_neso_s_net_transfer_capacity"),
    "IFA Interconnector": ("IFA", "INTFR", "ifa_neso_s_intraday_transfer_limit"),
    "IFA2 Interconnector": ("IFA2", "INTIFA2", "ifa2_neso_s_intraday_transfer_limit"),
    "ElecLink": ("ElecLink", "INTELEC", "eleclink_neso_s_net_transfer_capacity"),
    "Nemo Link": ("Nemo", "INTNEM", None),
    "East West Interconnector": ("EastWest", "INTEW", None),
    "Auchencrosh (interconnector CCT)": ("Moyle", "INTIRL", None),
    "NS Link": ("NSL", "INTNSL", None),
    "Greenlink": ("Greenlink", "INTGRNL", None),
    "Isle of Man Interconnector": ("IsleOfMan", None, None),
}

_KV = re.compile(r"(\d+(?:\.\d+)?)\s*kv", re.I)

LIMIT_TIME = "Operational Period Start Date & Time (GMT)"
LIMIT_TO, LIMIT_FROM = "Flow (MW) To GB", "Flow (MW) From GB"
REASON_TO, REASON_FROM = "Reason For Restriction To GB", "Reason For Restriction From GB"


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #

def flow_stats(readings: pd.DataFrame) -> pd.DataFrame:
    """Per Elexon fuel code: count, min, p05, p50, p95, max, mean, share into GB.
    readings has fuelType and generation (MW, into GB positive)."""
    g = readings.assign(generation=readings["generation"].astype("float64")).groupby("fuelType", sort=True)["generation"]
    return pd.DataFrame({
        "flow_readings": g.size(), "flow_mw_min": g.min(), "flow_mw_p05": g.quantile(0.05),
        "flow_mw_p50": g.median(), "flow_mw_p95": g.quantile(0.95), "flow_mw_max": g.max(),
        "flow_mw_mean": g.mean(), "into_gb_share": g.apply(lambda s: float((s > 0).mean())),
        "abs_p95": g.apply(lambda s: float(np.quantile(s.abs().to_numpy(), 0.95))),
    })


def limit_stats(limits: pd.DataFrame) -> dict:
    """Limit statistics for one link from its NESO series (already windowed).
    A period counts as restricted when either reason column says anything other
    than 'No Restriction'."""
    if limits.empty:
        return {}
    to_gb = pc.to_num(limits[LIMIT_TO])
    from_gb = pc.to_num(limits[LIMIT_FROM])

    def restricted(col):
        s = limits[col].astype("string").str.strip().str.lower() if col in limits else pd.Series(pd.NA, index=limits.index)
        return s.notna() & (s != "") & (s != "no restriction") & (s != "nan")

    return {"limit_to_gb_mw_p05": float(to_gb.quantile(0.05)), "limit_to_gb_mw_p50": float(to_gb.median()),
            "limit_from_gb_mw_p05": float(from_gb.quantile(0.05)), "limit_from_gb_mw_p50": float(from_gb.median()),
            "limit_restricted_share": float((restricted(REASON_TO) | restricted(REASON_FROM)).mean())}


def build_links(register: pd.DataFrame, last_updated: datetime, register_src: str) -> pd.DataFrame:
    """Reference rows: one per register entry, built or pipeline."""
    r = register.reset_index(drop=True)
    status = r["project_status"].astype("string").str.strip()
    built = status.eq("Built")
    unknown = sorted(set(r.loc[built, "project_name"].astype(str)) - set(LINKS))
    if unknown:
        raise pc.ProfilesError(f"built interconnectors with no entry in LINKS: {unknown}")
    name = r["project_name"].astype(str)
    info = [LINKS.get(n) if b else None for n, b in zip(name, built)]
    stage = pc.str_or_none(r["stage"].astype("string").str.replace(r"\.0$", "", regex=True))
    kv = r["connection_site"].astype("string").str.extract(_KV, expand=False)
    stage_slug = stage.map(lambda s: f"-stage-{pc.slug(s)}" if s else "")
    out = pd.DataFrame({
        "profile_id": ("ic-" + name.map(pc.slug) + stage_slug).astype(object),
        "source_dataset": register_src,
        "source_key": r["project_number"].astype(str).astype(object),
        "last_updated_utc": pc.last_updated_column(len(r), last_updated).to_numpy(),
        "project_name": name.astype(object),
        "owner": pc.str_or_none(r["customer_name"]),
        "connection_site": pc.str_or_none(r["connection_site"]),
        "connection_kv": pd.to_numeric(kv, errors="coerce").astype("float64"),
        "stage": stage,
        "project_status": status.astype(object),
        "is_built": built.astype(bool),
        "link_folder": pd.Series([i[0] if i else PIPELINE for i in info], dtype=object),
        "register_import_mw": pc.to_num(r["mw_import_total"]),
        "register_export_mw": pc.to_num(r["mw_export_total"]),
        "effective_from_utc": pd.to_datetime(r["mw_effective_from"], errors="coerce"),
        "elexon_fuel_code": pd.Series([i[1] if i else None for i in info], dtype=object),
        "quality_flags": pd.Series([""] * len(r), dtype=object),
    })
    pc.ensure_unique(out["source_key"], "links source_key")
    pc.ensure_unique(out["profile_id"], "links profile_id")
    spec = pc.load_spec(FIELDS_JSON, "links")
    out = pc.spec_order(pc.utc_timestamps(out, spec), spec)
    return out.sort_values("profile_id", kind="mergesort").reset_index(drop=True)


def build_link_flows(links: pd.DataFrame, flows: pd.DataFrame, limits: dict[str, pd.DataFrame],
                     last_updated: datetime, window_start: datetime) -> tuple[pd.DataFrame, list[str]]:
    """Observed rows: one per built link (stages summed) that has flow readings.
    Returns the frame and the built link folders with no flow readings."""
    built = links[links["is_built"]]
    fs = flow_stats(flows) if len(flows) else pd.DataFrame()
    rows, no_flow = [], []
    for folder, g in built.groupby("link_folder", sort=True):
        code = g["elexon_fuel_code"].iloc[0]
        if not code or code not in fs.index:
            no_flow.append(folder)
            continue
        s = fs.loc[code]
        cap = max(g["register_import_mw"].sum(min_count=1), g["register_export_mw"].sum(min_count=1))
        cap = float(cap) if pd.notna(cap) and cap > 0 else np.nan
        flags = []
        if cap == cap and max(abs(s["flow_mw_min"]), abs(s["flow_mw_max"])) > FLOW_SPIKE_RATIO * cap:
            flags.append("flow_exceeds_capacity")
        limit_ds = next(v[2] for v in LINKS.values() if v[0] == folder)
        row = {"profile_id": f"icflow-{pc.slug(folder)}",
               "source_dataset": FUELINST + (f"; {NESO}/{limit_ds}" if limit_ds else ""),
               "source_key": code, "link_folder": folder, "capacity_mw": cap,
               **{k: float(s[k]) for k in ("flow_mw_min", "flow_mw_p05", "flow_mw_p50", "flow_mw_p95",
                                           "flow_mw_max", "flow_mw_mean", "into_gb_share")},
               "flow_readings": int(s["flow_readings"]),
               "utilisation_p95": float(s["abs_p95"]) / cap if cap == cap else np.nan,
               "limit_source": f"{NESO}/{limit_ds}" if limit_ds else None,
               "quality_flags": ";".join(flags)}
        if limit_ds:
            row.update(limit_stats(limits.get(limit_ds, pd.DataFrame())))
        rows.append(row)
    spec = pc.load_spec(FIELDS_JSON, "link_flows")
    if not rows:
        return pc.spec_order(pc.empty_frame(spec), spec), no_flow
    out = pd.DataFrame(rows)
    n = len(out)
    out["last_updated_utc"] = pc.last_updated_column(n, last_updated).to_numpy()
    out["flow_window_start_utc"] = pc.last_updated_column(n, window_start).to_numpy()
    out["flow_window_end_utc"] = pc.last_updated_column(n, last_updated).to_numpy()
    out["flow_readings"] = out["flow_readings"].astype("int64")
    for c in ("limit_to_gb_mw_p05", "limit_to_gb_mw_p50", "limit_from_gb_mw_p05", "limit_from_gb_mw_p50",
              "limit_restricted_share"):
        out[c] = out[c].astype("float64") if c in out else np.nan
    for c in ("profile_id", "source_dataset", "source_key", "link_folder", "limit_source", "quality_flags"):
        out[c] = out[c].astype(object)
    pc.ensure_unique(out["profile_id"], "link_flows profile_id")
    out = pc.spec_order(pc.utc_timestamps(out, spec), spec)
    return out.sort_values("profile_id", kind="mergesort").reset_index(drop=True), no_flow


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #

def _partition_files(root: Path, start: datetime, end: datetime) -> list[Path]:
    """year=YYYY/week=WW files whose year can overlap [start, end]. Partitions
    whose year cannot be read (for example year=unknown) are skipped: their rows
    cannot be placed in time."""
    out = []
    for p in root.glob("year=*/week=*/*.parquet"):
        y = p.parent.parent.name.split("=", 1)[1]
        if y.isdigit() and start.year <= int(y) <= end.year:
            out.append(p)
    return sorted(out)


def read_flows(lake: Path, start: datetime, end: datetime) -> pd.DataFrame:
    parts = []
    for f in _partition_files(lake / FUELINST, start, end):
        d = pd.read_parquet(f, columns=["fuelType", "generation", "startTime"])
        d = d[d["fuelType"].astype(str).str.startswith("INT") & (d["startTime"] > start) & (d["startTime"] <= end)]
        if len(d):
            parts.append(d.assign(fuelType=d["fuelType"].astype(str)))
    if not parts:
        return pd.DataFrame({"fuelType": pd.Series(dtype=object), "generation": pd.Series(dtype="float64")})
    # FUELINST is republished; keep one reading per fuel and start time (the first after sorting).
    flows = pd.concat(parts, ignore_index=True).sort_values(["fuelType", "startTime", "generation"], kind="mergesort")
    return flows.drop_duplicates(["fuelType", "startTime"], keep="first").reset_index(drop=True)


def read_limits(lake: Path, dataset: str, start: datetime, end: datetime) -> pd.DataFrame:
    parts = []
    for f in _partition_files(lake / NESO / dataset, start, end):
        d = pd.read_parquet(f)
        t = pd.to_datetime(d[LIMIT_TIME], errors="coerce", utc=True)
        d = d[(t > start) & (t <= end)]
        if len(d):
            parts.append(d.assign(_t=t[d.index]))
    if not parts:
        return pd.DataFrame()
    lim = pd.concat(parts, ignore_index=True)
    # Limits are re-issued per auction; keep the latest upload per operational period.
    upload = pd.to_datetime(lim.get("Data Upload Time (GMT)"), errors="coerce", utc=True)
    lim = lim.assign(_u=upload).sort_values(["_t", "_u"], kind="mergesort")
    return lim.drop_duplicates("_t", keep="last").reset_index(drop=True)


def build(lake: Path, last_updated: datetime, out_root: Path = pc.PROFILES_ROOT) -> dict:
    start = last_updated - timedelta(days=WINDOW_DAYS)
    reg_path = pc.latest_snapshot(lake / REGISTER, "snapshot_date=*/*.parquet", "snapshot_date", last_updated)
    reg_src = reg_path.relative_to(lake).as_posix()
    limits = {ds: read_limits(lake, ds, start, last_updated) for _, _, ds in LINKS.values() if ds}
    links = build_links(pd.read_parquet(reg_path), last_updated, reg_src)
    flows, no_flow = build_link_flows(links, read_flows(lake, start, last_updated), limits, last_updated, start)
    specs = {t: pc.load_spec(FIELDS_JSON, t) for t in ("links", "link_flows")}
    written = []
    for folder in sorted({v[0] for v in LINKS.values()} | {PIPELINE}):
        for table, frame in (("links", links), ("link_flows", flows)):
            part = frame[frame["link_folder"].eq(folder)].reset_index(drop=True)
            path = out_root / FAMILY / folder / f"{table}.parquet"
            if len(part):
                written.append(pc.write_profile(part, specs[table], path))
            elif path.exists():
                path.unlink()
    named = pc.verify_names_used(FAMILY)
    pc.write_fields_md(FIELDS_JSON)
    return {"family": FAMILY, "inputs": [reg_src, FUELINST, *(f"{NESO}/{d}" for d in limits)], "files": written,
            "notes": {"profiles_named": named, "links_by_status": links["project_status"].value_counts().sort_index().to_dict(),
                      "limit_rows_used": {d: int(len(v)) for d, v in limits.items()},
                      "built_links_without_flow_data": no_flow,
                      "no_limit_statistics": "BritNed and Nemo Link (NESO limit dates cannot be read)"}}


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
