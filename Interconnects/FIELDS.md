# Interconnects fields

Generated from `fields.json` by `tools/profiles_common.py`. Do not edit by hand.

Units marked * are not yet in GridSim's unit vocabulary (proposed additions).

## links (reference)

One row per interconnector in the NESO interconnector register (latest snapshot on or before the last-updated date): built links and pipeline projects with their registered capacity, connection and planned dates. Each built link has its own folder; projects not yet built are filed under Interconnects/Pipeline. Flow and limit statistics are in link_flows.

| Field | Type | Unit | Provenance | Null | Sensitive | Source | Description |
|---|---|---|---|---|---|---|---|
| `profile_id` | string |  | DerivedFromRecorded | no | no | derived: identity | Stable identifier: 'ic-' plus the slug of the project name (and stage where the register splits a link into stages). |
| `profile_rev` | int64 | 1 | DerivedFromRecorded | no | no | derived: previous build's revision and content_sha256 | Revision of this profile. It stays the same while the profile's content is unchanged and goes up by one when any value changes, so profile_id@profile_rev always means one fixed set of values. |
| `content_sha256` | string |  | DerivedFromRecorded | no | no | derived: row values | SHA-256 of the profile's values (every field except profile_rev, content_sha256 and last_updated_utc, floats by their exact bits). Used to decide when profile_rev goes up. |
| `source_dataset` | string |  | Recorded | no | no | derived: input file | Register snapshot the row was built from. |
| `source_key` | string |  | Recorded | no | no | InterconnectorRegister project_number | NESO interconnector register project number. |
| `last_updated_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: build date | Profiles last updated: the date these profiles were brought up to. |
| `project_name` | string |  | Recorded | no | no | InterconnectorRegister project_name | Project name as registered. |
| `owner` | string |  | Recorded | yes | no | InterconnectorRegister customer_name | Registered customer (owner or developer). |
| `connection_site` | string |  | Recorded | yes | no | InterconnectorRegister connection_site | GB connection substation as registered. |
| `connection_kv` | float64 | kV | DerivedFromRecorded | yes | no | derived: connection_site | Connection voltage, read from the connection site name (for example 'Grain 400kV Substation'). |
| `stage` | string |  | Recorded | yes | no | InterconnectorRegister stage | Register stage, where a link is registered in stages. |
| `project_status` | string |  | Recorded | no | no | InterconnectorRegister project_status | Built, Under Construction/Commissioning, Awaiting Consents or Scoping. |
| `is_built` | bool |  | DerivedFromRecorded | no | no | derived: project_status | True when project_status is Built. |
| `link_folder` | string |  | DerivedFromRecorded | no | no | derived: builder LINKS table | Profiles folder under Interconnects: one per built link, Pipeline for everything not yet built. |
| `register_import_mw` | float64 | MW | Recorded | yes | no | InterconnectorRegister mw_import_total | Total import capacity as registered by NESO. |
| `register_export_mw` | float64 | MW | Recorded | yes | no | InterconnectorRegister mw_export_total | Total export capacity as registered by NESO. |
| `effective_from_utc` | timestamp |  | Recorded | yes | no | InterconnectorRegister mw_effective_from | Date the registered capacity takes effect (pipeline projects: the planned connection date). |
| `elexon_fuel_code` | string |  | DerivedFromRecorded | yes | no | derived: builder LINKS table | Elexon fuel type the link's flows are published under (for example INTNED for BritNed). |
| `named_operator` | string |  | CuratedPlaceholder | yes | yes | Interconnects/names.csv operator | [VERIFY] Operator or owner of the asset, from Interconnects/names.csv (named by hand, not published). Null where not named. |
| `named_site` | string |  | CuratedPlaceholder | yes | yes | Interconnects/names.csv site_name | [VERIFY] Site name, from Interconnects/names.csv. Null where not named. |
| `named_address` | string |  | CuratedPlaceholder | yes | yes | Interconnects/names.csv address | [VERIFY] Site address, from Interconnects/names.csv. Null where not named. |
| `named_by` | string |  | CuratedPlaceholder | yes | no | Interconnects/names.csv named_by | [VERIFY] Who named the asset and when, from Interconnects/names.csv. |
| `quality_flags` | string |  | DerivedFromRecorded | no | no | derived: builder checks | Semicolon list of issues. Empty when none. |

## link_flows (observed)

Flow and NESO transfer-limit statistics for each built link over the 365 days to the last-updated date, one row per link (a link registered in stages has one row). Kept apart from links because they come from time-stamped operational data. profile_id is 'icflow-' plus the link folder slug.

| Field | Type | Unit | Provenance | Null | Sensitive | Source | Description |
|---|---|---|---|---|---|---|---|
| `profile_id` | string |  | DerivedFromRecorded | no | no | derived: identity | Stable identifier: 'ic-' plus the slug of the project name (and stage where the register splits a link into stages). |
| `profile_rev` | int64 | 1 | DerivedFromRecorded | no | no | derived: previous build's revision and content_sha256 | Revision of this profile. It stays the same while the profile's content is unchanged and goes up by one when any value changes, so profile_id@profile_rev always means one fixed set of values. |
| `content_sha256` | string |  | DerivedFromRecorded | no | no | derived: row values | SHA-256 of the profile's values (every field except profile_rev, content_sha256 and last_updated_utc, floats by their exact bits). Used to decide when profile_rev goes up. |
| `source_dataset` | string |  | Recorded | no | no | derived: input files | Datasets the statistics come from (Elexon FUELINST and, where usable, a NESO limit series). |
| `source_key` | string |  | Recorded | no | no | builder LINKS table | Elexon fuel type the link's flows are published under. |
| `last_updated_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: build date | Profiles last updated: the date these profiles were brought up to. |
| `link_folder` | string |  | DerivedFromRecorded | no | no | builder LINKS table | Profiles folder under Interconnects (joins to links.link_folder). |
| `capacity_mw` | float64 | MW | DerivedFromRecorded | yes | no | derived: links register capacity | Larger of the link's registered import and export capacity (summed over register stages), the base for utilisation_p95. |
| `flow_window_start_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: last updated minus 365 days | Start of the flow statistics window (365 days to the last-updated date). |
| `flow_readings` | int64 | 1 | DerivedFromRecorded | no | no | Elexon FUELINST | Five-minute flow readings in the window. |
| `flow_mw_min` | float64 | MW | DerivedFromRecorded | yes | no | Elexon FUELINST generation | Lowest flow. Positive flow is into GB, negative is out of GB. |
| `flow_mw_p05` | float64 | MW | DerivedFromRecorded | yes | no | Elexon FUELINST generation | 5th percentile of flow (into GB positive). |
| `flow_mw_p50` | float64 | MW | DerivedFromRecorded | yes | no | Elexon FUELINST generation | Median flow (into GB positive). |
| `flow_mw_p95` | float64 | MW | DerivedFromRecorded | yes | no | Elexon FUELINST generation | 95th percentile of flow (into GB positive). |
| `flow_mw_max` | float64 | MW | DerivedFromRecorded | yes | no | Elexon FUELINST generation | Highest flow (into GB positive). |
| `flow_mw_mean` | float64 | MW | DerivedFromRecorded | yes | no | Elexon FUELINST generation | Mean flow (into GB positive): the link's net position over the window. |
| `into_gb_share` | float64 | 1 | DerivedFromRecorded | yes | no | derived: flow > 0 | Fraction of readings with flow into GB. |
| `utilisation_p95` | float64 | 1 | DerivedFromRecorded | yes | no | derived: flow, register capacity | 95th percentile of absolute flow over the larger registered capacity. |
| `limit_source` | string |  | DerivedFromRecorded | yes | no | derived: builder LINKS table | NESO limit series used for the limit statistics. Null where none is usable (BritNed and Nemo Link publish limits whose dates cannot be read). |
| `limit_to_gb_mw_p05` | float64 | MW | DerivedFromRecorded | yes | no | NESO interconnector limit series, Flow (MW) To GB | 5th percentile of NESO's transfer limit into GB (the restricted end). |
| `limit_to_gb_mw_p50` | float64 | MW | DerivedFromRecorded | yes | no | NESO interconnector limit series, Flow (MW) To GB | Median NESO transfer limit into GB. |
| `limit_from_gb_mw_p05` | float64 | MW | DerivedFromRecorded | yes | no | NESO interconnector limit series, Flow (MW) From GB | 5th percentile of NESO's transfer limit out of GB. |
| `limit_from_gb_mw_p50` | float64 | MW | DerivedFromRecorded | yes | no | NESO interconnector limit series, Flow (MW) From GB | Median NESO transfer limit out of GB. |
| `limit_restricted_share` | float64 | 1 | DerivedFromRecorded | yes | no | NESO interconnector limit series, reason columns | Fraction of limit periods with a stated restriction in either direction. |
| `flow_window_end_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: last updated | End of the window: the profiles last-updated date. |
| `named_operator` | string |  | CuratedPlaceholder | yes | yes | Interconnects/names.csv operator | [VERIFY] Operator or owner of the asset, from Interconnects/names.csv (named by hand, not published). Null where not named. |
| `named_site` | string |  | CuratedPlaceholder | yes | yes | Interconnects/names.csv site_name | [VERIFY] Site name, from Interconnects/names.csv. Null where not named. |
| `named_address` | string |  | CuratedPlaceholder | yes | yes | Interconnects/names.csv address | [VERIFY] Site address, from Interconnects/names.csv. Null where not named. |
| `named_by` | string |  | CuratedPlaceholder | yes | no | Interconnects/names.csv named_by | [VERIFY] Who named the asset and when, from Interconnects/names.csv. |
| `quality_flags` | string |  | DerivedFromRecorded | no | no | derived: builder checks | Semicolon list of issues (for example flow_exceeds_capacity: an extreme published reading above 110% of registered capacity, kept as published). Empty when none. |
