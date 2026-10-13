# Profiles

Reusable electrical profiles of the GB grid for GridSim: one profile per asset (cable, transformer,
generator, demand site, substation load centre, interconnector), laid out by family and class so a
synthetic town or network can be assembled from them for simulation and forward planning.

Status: local working repo, not yet a GridSim submodule. The data is built from the GDA data lake
by the scripts in `tools/`.

## Layout

| Family | Folders | Tables | What a profile holds |
|---|---|---|---|
| Cables | `Cables/<kV>/` | `circuits`, `types`, `spans` | End nodes, voltage, R, X, B (ohms, per km, % on 100 MVA), zero sequence, ratings, published and route lengths, values exactly as reported; archetypes per conductor; GIS span lengths |
| Transformers | `Transformers/<kV>/` (by HV winding), `Transformers/observed/` | `units`; `taps`, `flows`, `stress` | Winding voltages, impedance (% on 100 MVA and on rating), tap range, ratings, vector group; observed tap steps, P/Q/MVA/power factor/kV over a year, tap wear and time at high load |
| Generator | `Generator/<Fuel>/` | `bm_units`, `stations` | Capacity, max rating and thermal headroom (nameplate = 80% of max), inertia H, ramp rates, stable and maximum limits, notice and run times, metered output and capacity factor; DUKES and REPD stations including the planning pipeline |
| Demands | `Demands/<Site type>/`, `Demands/LoadCentres/<kV>/` | `sites`, `load_centres` | Hospitals, schools, universities, colleges, datacentres, ports, military sites with import/export capacity and connection; substation peak, power factor, firm capacity and five-year forecast |
| Interconnects | `Interconnects/<Link>/`, `Interconnects/Pipeline/` | `links` | Registered capacity, connection, a year of flows and NESO transfer limits; pipeline projects with planned dates |

Voltage folders follow GB practice: 6.6kv, 11kv, 33kv, 66kv, 132kv, 275kv, 400kv. Equipment published at
an operating voltage within 5% of a class is filed under that class (33.2kV under 33kv).

Generator fuel folders: Gas, Nuclear, Wind, Solar, Coal, Hydro, PumpedStorage, Storage, Marine,
OtherThermal/{BIO, CHP, Waste, Oil}, Other, and Unclassified (BM units Elexon publishes no fuel for).

## Fields

Each family has a `fields.json`: the definition of every column (type, unit, description, source,
provenance tag, nullable, sensitive). `FIELDS.md` is generated from it for reading. Units use
GridSim's unit vocabulary; units it does not have yet are marked * in FIELDS.md. Every row carries
`last_updated_utc`, the date the profiles were last brought up to, and a `quality_flags` column
listing anything found while building it.

Fields with no source yet (generator poles, speed, torque and per-asset CO2; transformer
temperatures; site demand shapes, port shore power and crane cycles) are defined and empty, so the
shape of each profile is fixed and they can be filled when a source appears.

## Building

```
pip install -r tools/requirements.txt
set GDA_DATA_ROOT=W:\gda\DataSources        (the lake's DataSources folder)
python tools/build_all.py                   (every family, plus BUILD_MANIFEST.json)
python tools/build_cables.py                (or one family)
python -m pytest tools/tests                (tests; no lake needed)
```

`--as-of YYYY-MM-DD` sets the profiles last-updated date; by default the latest available date is
used. Builds are deterministic: the same lake and date give byte-identical files.
`BUILD_MANIFEST.json` lists every file with its rows, SHA-256, inputs, and what was left out and why.

## Rules

- Nothing is invented. A value with no source is null; values set by rule (the 80% rating rule,
  typical inertia by fuel) are marked as such in the spec.
- Values are kept exactly as published alongside any harmonised value (`reported_*` columns).
- Every builder checks its output against `fields.json` before writing and stops on any mismatch.
- Fields marked `sensitive` (names, nodes, coordinates, postcodes, geometry) are kept inline; Mark
  decides what can ship in a public release.
- Plain ASCII, EN-GB spelling, no em or en dashes, no smart quotes.
