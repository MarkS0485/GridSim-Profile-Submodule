# Demands fields

Generated from `fields.json` by `tools/profiles_common.py`. Do not edit by hand.

Units marked * are not yet in GridSim's unit vocabulary (proposed additions).

## sites (reference)

Large demand sites of a known type, classified from the unified large-consumer register (Derived/demand_consumers, built by GDA from DNO embedded capacity registers, large demand lists and the TEC register). A site needs an import capacity to count. Rules are tried in order, specific before general (hospitals before universities, naval before port); names that mark a generation project (solar farm or park, wind farm, BESS) and place-name uses (School Farm, College Lane, Port Clarence) are excluded. Demand-shape fields are defined but empty until a source exists. profile_id is 'dem-' plus 16 hex of SHA-256 of source_key.

| Field | Type | Unit | Provenance | Null | Sensitive | Source | Description |
|---|---|---|---|---|---|---|---|
| `profile_id` | string |  | DerivedFromRecorded | no | no | derived: identity | Stable profile identifier (see the table description for its form). |
| `profile_rev` | int64 | 1 | DerivedFromRecorded | no | no | derived: previous build's revision and content_sha256 | Revision of this profile. It stays the same while the profile's content is unchanged and goes up by one when any value changes, so profile_id@profile_rev always means one fixed set of values. |
| `content_sha256` | string |  | DerivedFromRecorded | no | no | derived: row values | SHA-256 of the profile's values (every field except profile_rev, content_sha256 and last_updated_utc, floats by their exact bits). Used to decide when profile_rev goes up. |
| `source_dataset` | string |  | Recorded | no | no | derived: input file | Lake dataset the row was built from. |
| `source_key` | string |  | Recorded | no | yes | source row identity | The row's key in its source. |
| `last_updated_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: build date | Profiles last updated: the date these profiles were brought up to. |
| `site_type` | string |  | DerivedFromRecorded | no | no | derived: classification rules | Profiles folder under Demands (Hospitals, Schools, Universities, Colleges, Datacentres/Hyperscale (import 50 MW or more), Datacentres/SME (under 5 MW), Datacentres/Other, Datacentres/ByLocalAuthority (UKPN's per-local-authority totals: many sites summed, not banded), Port, Military/Land, Military/Naval). |
| `match_rule` | string |  | DerivedFromRecorded | no | no | derived: classification rules | The classification rule that matched, as '<rule name>: <matched text>'. Rules are tried in a fixed order; the first match wins. |
| `name` | string |  | Recorded | yes | yes | Derived/demand_consumers.name | Customer or project name as published. |
| `site` | string |  | Recorded | yes | yes | Derived/demand_consumers.site | Site name as published. |
| `register_type` | string |  | Recorded | yes | no | Derived/demand_consumers.type | Row type in the unified consumer register (large_demand, der, generation, solar, datacentre and so on). |
| `energy_tech` | string |  | Recorded | yes | no | Derived/demand_consumers.energy_tech | On-site technology as published (for example Photovoltaic, CCGT, Large Demand). |
| `import_mw` | float64 | MW | Recorded | no | no | Derived/demand_consumers.import_mw | Site import capacity: the most the site may draw from the network. |
| `export_mw` | float64 | MW | Recorded | yes | no | Derived/demand_consumers.export_mw | Site export capacity (on-site generation or storage). |
| `storage_mwh` | float64 | MWh | Recorded | yes | no | Derived/demand_consumers.storage_mwh | On-site storage energy where published. |
| `poc_voltage_kv` | float64 | kV | Recorded | yes | no | Derived/demand_consumers.poc_voltage_kv | Point of connection voltage. |
| `gsp_name` | string |  | Recorded | yes | no | Derived/demand_consumers.gsp_name | Grid supply point as published. |
| `bsp` | string |  | Recorded | yes | yes | Derived/demand_consumers.bsp | Bulk supply point as published. |
| `primary` | string |  | Recorded | yes | yes | Derived/demand_consumers.primary | Primary substation as published. |
| `local_authority` | string |  | Recorded | yes | no | Derived/demand_consumers.local_authority | Local authority. |
| `easting` | float64 | m * | Recorded | yes | yes | Derived/demand_consumers.easting | OSGB easting in metres (British National Grid, EPSG:27700). Identifies the site, so sensitive. |
| `northing` | float64 | m * | Recorded | yes | yes | Derived/demand_consumers.northing | OSGB northing in metres (British National Grid, EPSG:27700). Identifies the site, so sensitive. |
| `postcode` | string |  | Recorded | yes | yes | Derived/demand_consumers.postcode | Postcode. |
| `connection_status` | string |  | Recorded | yes | no | Derived/demand_consumers.connection_status | Connection status as published (connected, accepted and so on). |
| `evidence_source` | string |  | Recorded | yes | no | Derived/demand_consumers.evidence_source | Published register the row came from. |
| `base_load_mw` | float64 | MW | CuratedPlaceholder | yes | no | none | [VERIFY] Typical steady demand. No source in the lake yet; reserved so the profile shape is fixed. |
| `peak_load_mw` | float64 | MW | CuratedPlaceholder | yes | no | none | [VERIFY] Observed peak demand. No source in the lake yet; reserved so the profile shape is fixed. |
| `load_factor` | float64 | 1 | CuratedPlaceholder | yes | no | none | [VERIFY] Mean demand over peak demand. No source in the lake yet; reserved so the profile shape is fixed. |
| `fluctuation_band_pct` | float64 | % | CuratedPlaceholder | yes | no | none | [VERIFY] Typical short-term swing around the base load (datacentres: small). No source in the lake yet; reserved so the profile shape is fixed. |
| `ramp_up_mw_per_min` | float64 | MW/min | CuratedPlaceholder | yes | no | none | [VERIFY] Fastest demand rise (datacentres: job start; ports: crane lift). No source in the lake yet; reserved so the profile shape is fixed. |
| `ramp_down_mw_per_min` | float64 | MW/min | CuratedPlaceholder | yes | no | none | [VERIFY] Fastest demand fall. No source in the lake yet; reserved so the profile shape is fixed. |
| `power_factor` | float64 | 1 | CuratedPlaceholder | yes | no | none | [VERIFY] Typical power factor at the connection. No source in the lake yet; reserved so the profile shape is fixed. |
| `voltage_sag_pct` | float64 | % | CuratedPlaceholder | yes | no | none | [VERIFY] Voltage dip at the connection under the largest load step (ports: crane and shore-power steps). No source in the lake yet; reserved so the profile shape is fixed. |
| `shore_power_peak_mw` | float64 | MW | CuratedPlaceholder | yes | no | none | [VERIFY] Ports: peak demand when ships connect to shore power. No source in the lake yet; reserved so the profile shape is fixed. |
| `shore_power_connections_per_week` | float64 | 1 | CuratedPlaceholder | yes | no | none | [VERIFY] Ports: ship shore-power connections per week. No source in the lake yet; reserved so the profile shape is fixed. |
| `crane_peak_mw` | float64 | MW | CuratedPlaceholder | yes | no | none | [VERIFY] Ports: peak demand of one crane lift. No source in the lake yet; reserved so the profile shape is fixed. |
| `crane_cycle_s` | float64 | s | CuratedPlaceholder | yes | no | none | [VERIFY] Ports: duration of one crane duty cycle. No source in the lake yet; reserved so the profile shape is fixed. |
| `named_operator` | string |  | CuratedPlaceholder | yes | yes | Demands/names.csv operator | [VERIFY] Operator or owner of the asset, from Demands/names.csv (named by hand, not published). Null where not named. |
| `named_site` | string |  | CuratedPlaceholder | yes | yes | Demands/names.csv site_name | [VERIFY] Site name, from Demands/names.csv. Null where not named. |
| `named_address` | string |  | CuratedPlaceholder | yes | yes | Demands/names.csv address | [VERIFY] Site address, from Demands/names.csv. Null where not named. |
| `named_by` | string |  | CuratedPlaceholder | yes | no | Demands/names.csv named_by | [VERIFY] Who named the asset and when, from Demands/names.csv. |
| `quality_flags` | string |  | DerivedFromRecorded | no | no | derived: builder checks | Semicolon list of issues (for example no_poc_voltage). Empty when none. |

## load_centres (reference)

Substation demand from the operators' Long Term Development Statements (LTDS Table 3): observed peak, power factor, firm capacity, minimum load and the operator's own five-year demand forecast, for forward planning. Filed under Demands/LoadCentres/<voltage class>. profile_id is 'load-' plus 16 hex of SHA-256 of source_key.

| Field | Type | Unit | Provenance | Null | Sensitive | Source | Description |
|---|---|---|---|---|---|---|---|
| `profile_id` | string |  | DerivedFromRecorded | no | no | derived: identity | Stable profile identifier (see the table description for its form). |
| `profile_rev` | int64 | 1 | DerivedFromRecorded | no | no | derived: previous build's revision and content_sha256 | Revision of this profile. It stays the same while the profile's content is unchanged and goes up by one when any value changes, so profile_id@profile_rev always means one fixed set of values. |
| `content_sha256` | string |  | DerivedFromRecorded | no | no | derived: row values | SHA-256 of the profile's values (every field except profile_rev, content_sha256 and last_updated_utc, floats by their exact bits). Used to decide when profile_rev goes up. |
| `source_dataset` | string |  | Recorded | no | no | derived: input file | Lake dataset the row was built from. |
| `source_key` | string |  | Recorded | no | yes | source row identity | The row's key in its source. |
| `last_updated_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: build date | Profiles last updated: the date these profiles were brought up to. |
| `operator` | string |  | Recorded | no | no | derived: source file | Network operator group (ukpn, npg, nged). |
| `licence` | string |  | Recorded | no | no | LTDS licence column | Licence area. |
| `gsp_group` | string |  | Recorded | yes | no | LTDS Table 3 GSP / group column | Grid supply point or group as published. |
| `bsp_group` | string |  | Recorded | yes | yes | NGED LTDS Table 3 BSP Group | Bulk supply point group (NGED only). |
| `substation` | string |  | Recorded | yes | yes | LTDS Table 3 substation column | Substation or busbar name as published. |
| `node` | string |  | Recorded | yes | yes | NGED LTDS Table 3 Node | Node code (NGED only). |
| `voltage_kv` | float64 | kV | Recorded | no | no | LTDS Table 3 voltage column / substation name | Voltage the demand is measured at (UKPN: taken from the substation name, for example 'Chinnor Primary 11kV'). |
| `voltage_class` | string |  | DerivedFromRecorded | no | no | derived: voltage_kv mapped to GB voltage classes | Profiles voltage folder. |
| `status` | string |  | Recorded | yes | no | NGED LTDS Table 3 Status | energised, out, planned or unknown (NGED only; null elsewhere). |
| `season` | string |  | Recorded | yes | no | UKPN LTDS Table 3a Season | Winter or Summer (UKPN publishes one row per season); null where the operator publishes one annual figure. |
| `base_year` | string |  | Recorded | no | no | LTDS Table 3 column heading | Year the observed maximum demand refers to (for example 2024/25). |
| `peak_demand_reported` | float64 | per `demand_unit` | Recorded | yes | no | LTDS Table 3 maximum demand | Observed maximum demand exactly as published, in demand_unit. |
| `demand_unit` | string |  | DerivedFromRecorded | no | no | derived: source table | Unit of peak_demand_reported and the forecasts: MW (UKPN, NGED) or MVA (NPG). |
| `peak_power_factor` | float64 | 1 | Recorded | yes | no | LTDS Table 3 power factor | Power factor at the observed maximum demand. |
| `peak_demand_mw` | float64 | MW | DerivedFromRecorded | yes | no | derived: peak_demand_reported, peak_power_factor | Observed maximum demand in MW (NPG: MVA x power factor). |
| `peak_demand_mva` | float64 | MVA | DerivedFromRecorded | yes | no | derived: peak_demand_reported, peak_power_factor | Observed maximum demand in MVA (UKPN, NGED: MW / power factor). |
| `forecast_y1` | float64 | per `demand_unit` | Recorded | yes | no | LTDS Table 3 forecast columns | Operator's own forecast of maximum demand for base year + 1, in demand_unit. |
| `forecast_y2` | float64 | per `demand_unit` | Recorded | yes | no | LTDS Table 3 forecast columns | Operator's forecast for base year + 2, in demand_unit. |
| `forecast_y3` | float64 | per `demand_unit` | Recorded | yes | no | LTDS Table 3 forecast columns | Operator's forecast for base year + 3, in demand_unit. |
| `forecast_y4` | float64 | per `demand_unit` | Recorded | yes | no | LTDS Table 3 forecast columns | Operator's forecast for base year + 4, in demand_unit. |
| `forecast_y5` | float64 | per `demand_unit` | Recorded | yes | no | LTDS Table 3 forecast columns | Operator's forecast for base year + 5, in demand_unit. |
| `firm_capacity_reported` | float64 | per `firm_capacity_unit` | Recorded | yes | no | LTDS Table 3 firm capacity | Firm capacity of the substation exactly as published, in firm_capacity_unit. |
| `firm_capacity_unit` | string |  | DerivedFromRecorded | no | no | derived: source table | Unit of firm_capacity_reported: MW (UKPN), MVA (NPG) or unknown (NGED does not state it). |
| `headroom_pct` | float64 | % | DerivedFromRecorded | yes | no | derived: firm_capacity_reported, peak_demand_reported | Firm capacity left unused at the observed peak: (firm - peak) / firm x 100, in the published units. Null where the units differ or are unknown. |
| `min_load_scaling_pct` | float64 | % | Recorded | yes | no | LTDS Table 3 minimum load scaling factor | Minimum demand as a percent of maximum (UKPN, NGED). |
| `min_load_mva` | float64 | MVA | Recorded | yes | no | NPG Appendix 5 minimum load | Observed minimum load (NPG; negative means the substation exports at minimum). |
| `named_operator` | string |  | CuratedPlaceholder | yes | yes | Demands/names.csv operator | [VERIFY] Operator or owner of the asset, from Demands/names.csv (named by hand, not published). Null where not named. |
| `named_site` | string |  | CuratedPlaceholder | yes | yes | Demands/names.csv site_name | [VERIFY] Site name, from Demands/names.csv. Null where not named. |
| `named_address` | string |  | CuratedPlaceholder | yes | yes | Demands/names.csv address | [VERIFY] Site address, from Demands/names.csv. Null where not named. |
| `named_by` | string |  | CuratedPlaceholder | yes | no | Demands/names.csv named_by | [VERIFY] Who named the asset and when, from Demands/names.csv. |
| `quality_flags` | string |  | DerivedFromRecorded | no | no | derived: builder checks | Semicolon list of issues (for example no_peak_demand, voltage_from_name). Empty when none. |

## datacentre_profiles (observed)

Half-hourly demand shape of each data centre in UKPN's Data Centre Demand Profiles (anonymised as 'Data Centre #N'), over each site's latest 365 days up to the last-updated date: base, median and peak utilisation, load factor, fluctuation band and half-hourly ramps, all as fractions of the site's capacity. Filed under Demands/Datacentres/Profiles.

| Field | Type | Unit | Provenance | Null | Sensitive | Source | Description |
|---|---|---|---|---|---|---|---|
| `profile_id` | string |  | DerivedFromRecorded | no | no | derived: anonymised_name | Stable identifier: 'dc-ukpn-' plus the anonymised number, two digits (Data Centre #8 is dc-ukpn-08). |
| `profile_rev` | int64 | 1 | DerivedFromRecorded | no | no | derived: previous build's revision and content_sha256 | Revision of this profile. It stays the same while the profile's content is unchanged and goes up by one when any value changes, so profile_id@profile_rev always means one fixed set of values. |
| `content_sha256` | string |  | DerivedFromRecorded | no | no | derived: row values | SHA-256 of the profile's values (every field except profile_rev, content_sha256 and last_updated_utc, floats by their exact bits). Used to decide when profile_rev goes up. |
| `source_dataset` | string |  | Recorded | no | no | constant: UkPowerNetworks/Parquet/data_centre_demand_profiles | Lake dataset the statistics come from. |
| `source_key` | string |  | Recorded | no | no | UkPowerNetworks/Parquet/data_centre_demand_profiles anonymised_data_centre_name | UKPN's anonymised data centre name. |
| `last_updated_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: build date | Profiles last updated: the date these profiles were brought up to. |
| `operator` | string |  | Recorded | no | no | derived: source | Network operator publishing the profile (ukpn). |
| `anonymised_name` | string |  | Recorded | no | no | UkPowerNetworks/Parquet/data_centre_demand_profiles anonymised_data_centre_name | UKPN's anonymised name, for example 'Data Centre #8'. The key that site_names.csv names. |
| `dc_number` | int64 | 1 | DerivedFromRecorded | no | no | derived: anonymised_name | The number in the anonymised name. |
| `dc_type` | string |  | Recorded | yes | no | UkPowerNetworks/Parquet/data_centre_demand_profiles dc_type | Enterprise (one owner's own estate) or Co-located (space let to many customers). |
| `connection_level` | string |  | Recorded | yes | no | UkPowerNetworks/Parquet/data_centre_demand_profiles cleansed_voltage_level | Voltage level of the import connection as published (Extra-High, High or Low Voltage Import). |
| `window_start_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: readings | First reading in the statistics window (up to 365 days before window_end_utc). |
| `window_end_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: readings | Last reading in the window: the newest on or before the last-updated date. |
| `n_readings` | int64 | 1 | DerivedFromRecorded | no | no | derived: count | Half-hourly readings in the window. |
| `utilisation_min` | float64 | 1 | DerivedFromRecorded | no | no | UkPowerNetworks/Parquet/data_centre_demand_profiles hh_utilisation_ratio | Lowest half-hourly utilisation: demand as a fraction of the site's capacity. |
| `utilisation_p05` | float64 | 1 | DerivedFromRecorded | no | no | UkPowerNetworks/Parquet/data_centre_demand_profiles hh_utilisation_ratio | 5th percentile of utilisation: the site's base load as a fraction of capacity. |
| `utilisation_p50` | float64 | 1 | DerivedFromRecorded | no | no | UkPowerNetworks/Parquet/data_centre_demand_profiles hh_utilisation_ratio | Median utilisation. |
| `utilisation_p95` | float64 | 1 | DerivedFromRecorded | no | no | UkPowerNetworks/Parquet/data_centre_demand_profiles hh_utilisation_ratio | 95th percentile of utilisation. |
| `utilisation_max` | float64 | 1 | DerivedFromRecorded | no | no | UkPowerNetworks/Parquet/data_centre_demand_profiles hh_utilisation_ratio | Highest half-hourly utilisation: the site's peak as a fraction of capacity. |
| `utilisation_mean` | float64 | 1 | DerivedFromRecorded | no | no | UkPowerNetworks/Parquet/data_centre_demand_profiles hh_utilisation_ratio | Mean utilisation. |
| `load_factor` | float64 | 1 | DerivedFromRecorded | yes | no | derived: utilisation_mean / utilisation_max | Mean over peak utilisation (1 is a perfectly flat load). Null when the peak is zero. |
| `fluctuation_band` | float64 | 1 | DerivedFromRecorded | no | no | derived: utilisation_p95 - utilisation_p05 | utilisation_p95 minus utilisation_p05: the normal swing, as a fraction of capacity. |
| `ramp_up_p99` | float64 | 1 | DerivedFromRecorded | yes | no | derived: consecutive readings | 99th percentile of the rise between consecutive half-hours, as a fraction of capacity per half-hour (only readings exactly 30 minutes apart). |
| `ramp_down_p99` | float64 | 1 | DerivedFromRecorded | yes | no | derived: consecutive readings | 99th percentile of the fall between consecutive half-hours, as a positive fraction of capacity per half-hour. |
| `ramp_up_max` | float64 | 1 | DerivedFromRecorded | yes | no | derived: consecutive readings | Largest rise between consecutive half-hours, as a fraction of capacity per half-hour. |
| `ramp_down_max` | float64 | 1 | DerivedFromRecorded | yes | no | derived: consecutive readings | Largest fall between consecutive half-hours, as a positive fraction of capacity per half-hour. |
| `named_operator` | string |  | CuratedPlaceholder | yes | yes | Demands/names.csv operator | [VERIFY] Operator or owner of the asset, from Demands/names.csv (named by hand, not published). Null where not named. |
| `named_site` | string |  | CuratedPlaceholder | yes | yes | Demands/names.csv site_name | [VERIFY] Site name, from Demands/names.csv. Null where not named. |
| `named_address` | string |  | CuratedPlaceholder | yes | yes | Demands/names.csv address | [VERIFY] Site address, from Demands/names.csv. Null where not named. |
| `named_by` | string |  | CuratedPlaceholder | yes | no | Demands/names.csv named_by | [VERIFY] Who named the asset and when, from Demands/names.csv. |
| `quality_flags` | string |  | DerivedFromRecorded | no | no | derived: builder checks | Semicolon list of issues (for example several_types_published, several_levels_published, zero_peak). Empty when none. |
