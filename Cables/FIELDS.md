# Cables fields

Generated from `fields.json` by `tools/profiles_common.py`. Do not edit by hand.

Units marked * are not yet in GridSim's unit vocabulary (proposed additions).

## circuits (reference)

One row per published circuit (overhead line or cable) at one voltage class. Electrical values come from the DNO Long Term Development Statements (LTDS Table 1) as harmonised in the GDA cable lake; 275kV and 400kV rows are SSEN transmission GIS circuits that carry route length but no published impedance. Sentinel values (9999) in the source are nulled here and recorded in quality_flags.

| Field | Type | Unit | Provenance | Null | Sensitive | Source | Description |
|---|---|---|---|---|---|---|---|
| `profile_id` | string |  | DerivedFromRecorded | no | no | derived: sha256(source_key) | Stable profile identifier: 'cable-' plus the first 16 hex characters of the SHA-256 of source_key. |
| `profile_rev` | int64 | 1 | DerivedFromRecorded | no | no | derived: previous build's revision and content_sha256 | Revision of this profile. It stays the same while the profile's content is unchanged and goes up by one when any value changes, so profile_id@profile_rev always means one fixed set of values. |
| `content_sha256` | string |  | DerivedFromRecorded | no | no | derived: row values | SHA-256 of the profile's values (every field except profile_rev, content_sha256 and last_updated_utc, floats by their exact bits). Used to decide when profile_rev goes up. |
| `source_dataset` | string |  | Recorded | no | no | constant: Derived/cable_lake/cable_lake.parquet | Lake dataset the row was built from. |
| `source_key` | string |  | Recorded | no | yes | cable_lake.cable_id | The cable lake's cable_id for this circuit. |
| `evidence_source` | string |  | Recorded | no | no | cable_lake.evidence_source | The original published file the cable lake read this circuit from. |
| `last_updated_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: build date | Profiles last updated: the date these profiles were brought up to. |
| `operator` | string |  | Recorded | no | no | cable_lake.operator | Network operator group (ukpn, npg, nged, spen, ssen). |
| `licence` | string |  | Recorded | yes | no | cable_lake.licence | Licence area within the operator group (for example EPN, SPM, NPGY). |
| `voltage_kv` | float64 | kV | Recorded | no | no | cable_lake.voltage_kv | Nominal voltage of the circuit. A published circuit runs at one voltage, so this is the voltage at both ends; voltage changes happen at transformers (see the Transformers family). |
| `voltage_class` | string |  | DerivedFromRecorded | no | no | derived: voltage_kv mapped to GB voltage classes | Profiles folder for the voltage (6.6kv, 11kv, 33kv, 66kv, 132kv, 275kv, 400kv). |
| `row_kind` | string |  | DerivedFromRecorded | no | no | derived: cable_lake.element_class | ltds_circuit (published impedance) or gis_circuit (route geometry and length only, no published impedance). |
| `circuit_name` | string |  | Recorded | yes | yes | cable_lake.circuit_name | Circuit name as published. |
| `circuit_code` | string |  | Recorded | yes | yes | cable_lake.circuit_code | Circuit code as published. |
| `from_node` | string |  | Recorded | yes | yes | cable_lake.from_node | Node (substation busbar) at the sending end, as published. |
| `to_node` | string |  | Recorded | yes | yes | cable_lake.to_node | Node (substation busbar) at the receiving end, as published. |
| `status` | string |  | Recorded | yes | no | cable_lake.status | Circuit state as published (energised or out). |
| `construction` | string |  | Recorded | no | no | cable_lake.ohl_or_underground | overhead, underground or unknown. |
| `conductor_type` | string |  | Recorded | yes | no | cable_lake.conductor_type | Conductor or cable type where published (mostly blank in LTDS). |
| `length_km` | float64 | km | Recorded | yes | no | cable_lake.length_km_published, else cable_lake.geom_length_km | Circuit length used for per-km values: the LTDS-published length for LTDS circuits, the computed route length for GIS circuits. |
| `length_km_published` | float64 | km | Recorded | yes | no | cable_lake.length_km_published | Length as published in the LTDS. |
| `length_km_route` | float64 | km | DerivedFromRecorded | yes | no | cable_lake.geom_length_km | Length computed from the GIS route geometry (geodesic). For NPG LTDS circuits this covers the overhead portion only. |
| `r_ohm` | float64 | ohm * | DerivedFromRecorded | yes | no | cable_lake.r_ohm | Positive-sequence series resistance of the whole circuit, harmonised to ohms by the cable lake. |
| `x_ohm` | float64 | ohm * | DerivedFromRecorded | yes | no | cable_lake.x_ohm | Positive-sequence series reactance of the whole circuit, harmonised to ohms. |
| `b_us` | float64 | uS * | DerivedFromRecorded | yes | no | derived: cable_lake.b_pct_100mva, voltage_kv | Total shunt susceptance of the whole circuit in microsiemens: (b_pct_100mva / 100) x 100 MVA / voltage_kv squared, x 1e6. |
| `r0_ohm` | float64 | ohm * | DerivedFromRecorded | yes | no | derived: reported_r0, reported_impedance_base, voltage_kv | Zero-sequence series resistance of the whole circuit in ohms, from reported_r0 on reported_impedance_base by the same rule that gives r_ohm (percent or per unit on 100 MVA x kV squared / 100; ohmic values as published). Published by some operators only. |
| `x0_ohm` | float64 | ohm * | DerivedFromRecorded | yes | no | derived: reported_x0, reported_impedance_base, voltage_kv | Zero-sequence series reactance of the whole circuit in ohms, converted as r0_ohm. |
| `r_pct_100mva` | float64 | % | DerivedFromRecorded | yes | no | cable_lake.r_pct_100mva | Series resistance in percent on a 100 MVA base. |
| `x_pct_100mva` | float64 | % | DerivedFromRecorded | yes | no | cable_lake.x_pct_100mva | Series reactance in percent on a 100 MVA base. |
| `b_pct_100mva` | float64 | % | DerivedFromRecorded | yes | no | cable_lake.b_pct_100mva | Shunt susceptance in percent on a 100 MVA base. |
| `r_ohm_per_km` | float64 | ohm/km | DerivedFromRecorded | yes | no | derived: r_ohm / length_km | r_ohm / length_km, set only when both are valid and the length is above zero. |
| `x_ohm_per_km` | float64 | ohm/km | DerivedFromRecorded | yes | no | derived: x_ohm / length_km | x_ohm / length_km, set only when both are valid and the length is above zero. |
| `b_us_per_km` | float64 | uS/km | DerivedFromRecorded | yes | no | derived: b_us / length_km | b_us / length_km, set only when both are valid and the length is above zero. |
| `x_over_r` | float64 | 1 | DerivedFromRecorded | yes | no | derived: x_ohm / r_ohm | X/R ratio, set only when r_ohm is above zero. |
| `reported_impedance_base` | string |  | Recorded | yes | no | cable_lake.impedance_base | The base the operator published its impedance on: percent_on_100mva, pu_on_100mva or ohmic_referred. |
| `reported_r1` | float64 | per `reported_impedance_base` | Recorded | yes | no | cable_lake.r1_raw | Positive-sequence resistance exactly as reported, on reported_impedance_base (no conversion). |
| `reported_x1` | float64 | per `reported_impedance_base` | Recorded | yes | no | cable_lake.x1_raw | Positive-sequence reactance exactly as reported, on reported_impedance_base. |
| `reported_b1` | float64 | per `reported_impedance_base` | Recorded | yes | no | cable_lake.b1_raw | Positive-sequence susceptance exactly as reported, on reported_impedance_base. |
| `reported_r0` | float64 | per `reported_impedance_base` | Recorded | yes | no | cable_lake.r0_raw | Zero-sequence resistance exactly as reported, on reported_impedance_base (published by some operators only). |
| `reported_x0` | float64 | per `reported_impedance_base` | Recorded | yes | no | cable_lake.x0_raw | Zero-sequence reactance exactly as reported, on reported_impedance_base. |
| `rating_winter_mva` | float64 | MVA | Recorded | yes | no | cable_lake.winter_rating_mva | Winter thermal rating as published. |
| `rating_summer_mva` | float64 | MVA | Recorded | yes | no | cable_lake.summer_rating_mva | Summer thermal rating as published. |
| `rating_mva` | float64 | MVA | Recorded | yes | no | cable_lake.rating_mva | Rating the cable lake uses as the circuit's main rating (the winter rating where published). |
| `rate_a_mva` | float64 | MVA | Recorded | yes | no | cable_lake.winter_rating_mva | GridSim Rate A (normal, continuous): the winter continuous rating where published. |
| `rate_a_basis` | string |  | DerivedFromRecorded | yes | no | derived: source table | What Rate A is: the season or condition the published rating applies to. |
| `rate_b_mva` | float64 | MVA | CuratedPlaceholder | yes | no | none | [VERIFY] GridSim Rate B (short-term). Not published for these assets, so null; GridSim applies its own documented default. |
| `rate_b_basis` | string |  | CuratedPlaceholder | yes | no | none | [VERIFY] What Rate B is (null while Rate B is not published). |
| `rate_c_mva` | float64 | MVA | CuratedPlaceholder | yes | no | none | [VERIFY] GridSim Rate C (emergency): not published for circuits in LTDS, so null. |
| `rate_c_basis` | string |  | CuratedPlaceholder | yes | no | none | [VERIFY] What Rate C is (null while Rate C is not published). |
| `geometry_wkt` | string |  | Recorded | yes | yes | cable_lake.geometry_wkt | Route geometry (WGS84 WKT) where the cable lake holds it. |
| `named_operator` | string |  | CuratedPlaceholder | yes | yes | Cables/names.csv operator | [VERIFY] Operator or owner of the asset, from Cables/names.csv (named by hand, not published). Null where not named. |
| `named_site` | string |  | CuratedPlaceholder | yes | yes | Cables/names.csv site_name | [VERIFY] Site name, from Cables/names.csv. Null where not named. |
| `named_address` | string |  | CuratedPlaceholder | yes | yes | Cables/names.csv address | [VERIFY] Site address, from Cables/names.csv. Null where not named. |
| `named_by` | string |  | CuratedPlaceholder | yes | no | Cables/names.csv named_by | [VERIFY] Who named the asset and when, from Cables/names.csv. |
| `quality_flags` | string |  | DerivedFromRecorded | no | no | derived: builder checks | Semicolon list of data issues found while building the row (for example sentinel_9999_impedance, zero_impedance, no_length, sentinel_9999_rating). Empty when none. |

## types (reference)

Cable and line archetypes per voltage class: circuits grouped by construction and conductor type, with the spread of per-km impedance, rating and length. Use these to pick a typical cable for a synthetic network. Built from ltds_circuit rows only, with no quality flags.

| Field | Type | Unit | Provenance | Null | Sensitive | Source | Description |
|---|---|---|---|---|---|---|---|
| `profile_id` | string |  | DerivedFromRecorded | no | no | derived: group keys | Stable identifier: cabletype-<voltage_class>-<construction>-<conductor_type>. |
| `profile_rev` | int64 | 1 | DerivedFromRecorded | no | no | derived: previous build's revision and content_sha256 | Revision of this profile. It stays the same while the profile's content is unchanged and goes up by one when any value changes, so profile_id@profile_rev always means one fixed set of values. |
| `content_sha256` | string |  | DerivedFromRecorded | no | no | derived: row values | SHA-256 of the profile's values (every field except profile_rev, content_sha256 and last_updated_utc, floats by their exact bits). Used to decide when profile_rev goes up. |
| `source_dataset` | string |  | Recorded | no | no | constant: Derived/cable_lake/cable_lake.parquet | Lake dataset the archetype was built from. |
| `last_updated_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: build date | Profiles last updated: the date these profiles were brought up to. |
| `voltage_kv` | float64 | kV | DerivedFromRecorded | no | no | derived: nominal voltage of voltage_class | Nominal voltage of the class (circuits or spans published at an operating voltage within 5% of it are included). |
| `voltage_class` | string |  | DerivedFromRecorded | no | no | circuits.voltage_class | Profiles voltage folder. |
| `construction` | string |  | Recorded | no | no | circuits.construction | overhead, underground or unknown. |
| `conductor_type` | string |  | Recorded | no | no | circuits.conductor_type | Conductor type, or 'unknown' where not published. |
| `n_circuits` | int64 | 1 | DerivedFromRecorded | no | no | derived: count | Number of circuits in the group. |
| `n_with_per_km` | int64 | 1 | DerivedFromRecorded | no | no | derived: count | Circuits in the group with valid per-km impedance (the sample behind the ohm/km percentiles). |
| `r_ohm_per_km_p10` | float64 | ohm/km | DerivedFromRecorded | yes | no | derived: circuits.r_ohm_per_km | 10th percentile of r_ohm_per_km. |
| `r_ohm_per_km_p50` | float64 | ohm/km | DerivedFromRecorded | yes | no | derived: circuits.r_ohm_per_km | Median r_ohm_per_km. |
| `r_ohm_per_km_p90` | float64 | ohm/km | DerivedFromRecorded | yes | no | derived: circuits.r_ohm_per_km | 90th percentile of r_ohm_per_km. |
| `x_ohm_per_km_p10` | float64 | ohm/km | DerivedFromRecorded | yes | no | derived: circuits.x_ohm_per_km | 10th percentile of x_ohm_per_km. |
| `x_ohm_per_km_p50` | float64 | ohm/km | DerivedFromRecorded | yes | no | derived: circuits.x_ohm_per_km | Median x_ohm_per_km. |
| `x_ohm_per_km_p90` | float64 | ohm/km | DerivedFromRecorded | yes | no | derived: circuits.x_ohm_per_km | 90th percentile of x_ohm_per_km. |
| `b_us_per_km_p50` | float64 | uS/km | DerivedFromRecorded | yes | no | derived: circuits.b_us_per_km | Median b_us_per_km. |
| `rating_mva_p10` | float64 | MVA | DerivedFromRecorded | yes | no | derived: circuits.rating_mva | 10th percentile of rating_mva. |
| `rating_mva_p50` | float64 | MVA | DerivedFromRecorded | yes | no | derived: circuits.rating_mva | Median rating_mva. |
| `rating_mva_p90` | float64 | MVA | DerivedFromRecorded | yes | no | derived: circuits.rating_mva | 90th percentile of rating_mva. |
| `length_km_p10` | float64 | km | DerivedFromRecorded | yes | no | derived: circuits.length_km | 10th percentile of length_km. |
| `length_km_p50` | float64 | km | DerivedFromRecorded | yes | no | derived: circuits.length_km | Median length_km. |
| `length_km_p90` | float64 | km | DerivedFromRecorded | yes | no | derived: circuits.length_km | 90th percentile of length_km. |
| `named_operator` | string |  | CuratedPlaceholder | yes | yes | Cables/names.csv operator | [VERIFY] Operator or owner of the asset, from Cables/names.csv (named by hand, not published). Null where not named. |
| `named_site` | string |  | CuratedPlaceholder | yes | yes | Cables/names.csv site_name | [VERIFY] Site name, from Cables/names.csv. Null where not named. |
| `named_address` | string |  | CuratedPlaceholder | yes | yes | Cables/names.csv address | [VERIFY] Site address, from Cables/names.csv. Null where not named. |
| `named_by` | string |  | CuratedPlaceholder | yes | no | Cables/names.csv named_by | [VERIFY] Who named the asset and when, from Cables/names.csv. |

## spans (reference)

Overhead line spans from operator GIS (no circuit identity, no impedance), summarised per voltage class, operator and conductor type. Gives route-length and conductor evidence for voltages, chiefly 11kV and 6.6kV, where published circuit impedance is thin.

| Field | Type | Unit | Provenance | Null | Sensitive | Source | Description |
|---|---|---|---|---|---|---|---|
| `profile_id` | string |  | DerivedFromRecorded | no | no | derived: group keys | Stable identifier: cablespan-<voltage_class>-<operator>-<construction>-<conductor_type>. |
| `profile_rev` | int64 | 1 | DerivedFromRecorded | no | no | derived: previous build's revision and content_sha256 | Revision of this profile. It stays the same while the profile's content is unchanged and goes up by one when any value changes, so profile_id@profile_rev always means one fixed set of values. |
| `content_sha256` | string |  | DerivedFromRecorded | no | no | derived: row values | SHA-256 of the profile's values (every field except profile_rev, content_sha256 and last_updated_utc, floats by their exact bits). Used to decide when profile_rev goes up. |
| `source_dataset` | string |  | Recorded | no | no | constant: Derived/cable_lake/cable_lake.parquet | Lake dataset the summary was built from. |
| `last_updated_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: build date | Profiles last updated: the date these profiles were brought up to. |
| `voltage_kv` | float64 | kV | DerivedFromRecorded | no | no | derived: nominal voltage of voltage_class | Nominal voltage of the class (circuits or spans published at an operating voltage within 5% of it are included). |
| `voltage_class` | string |  | DerivedFromRecorded | no | no | derived: voltage_kv | Profiles voltage folder. |
| `operator` | string |  | Recorded | no | no | cable_lake.operator | Network operator group. |
| `construction` | string |  | Recorded | no | no | cable_lake.ohl_or_underground | overhead, underground or unknown. |
| `conductor_type` | string |  | Recorded | no | no | cable_lake.conductor_type | Conductor type, or 'unknown' where not published. |
| `n_spans` | int64 | 1 | DerivedFromRecorded | no | no | derived: count | Number of GIS spans in the group. |
| `total_route_km` | float64 | km | DerivedFromRecorded | no | no | derived: sum of cable_lake.geom_length_km | Sum of geodesic span lengths. |
| `span_km_p10` | float64 | km | DerivedFromRecorded | yes | no | derived: cable_lake.geom_length_km | 10th percentile of span length. |
| `span_km_p50` | float64 | km | DerivedFromRecorded | yes | no | derived: cable_lake.geom_length_km | Median span length. |
| `span_km_p90` | float64 | km | DerivedFromRecorded | yes | no | derived: cable_lake.geom_length_km | 90th percentile of span length. |
| `named_operator` | string |  | CuratedPlaceholder | yes | yes | Cables/names.csv operator | [VERIFY] Operator or owner of the asset, from Cables/names.csv (named by hand, not published). Null where not named. |
| `named_site` | string |  | CuratedPlaceholder | yes | yes | Cables/names.csv site_name | [VERIFY] Site name, from Cables/names.csv. Null where not named. |
| `named_address` | string |  | CuratedPlaceholder | yes | yes | Cables/names.csv address | [VERIFY] Site address, from Cables/names.csv. Null where not named. |
| `named_by` | string |  | CuratedPlaceholder | yes | no | Cables/names.csv named_by | [VERIFY] Who named the asset and when, from Cables/names.csv. |
