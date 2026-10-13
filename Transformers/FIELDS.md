# Transformers fields

Generated from `fields.json` by `tools/profiles_common.py`. Do not edit by hand.

Units marked * are not yet in GridSim's unit vocabulary (proposed additions).

## units (reference)

One row per published transformer (LTDS Table 2: two- and three-winding), filed under the HV winding's voltage class. Impedance is harmonised to percent on 100 MVA and on the unit's own rating; values exactly as reported are kept alongside. profile_id is 'txf-' plus 16 hex of SHA-256 of source_key. SP Energy Networks (SPD, SPM) transformer tables are not held in the lake copy these profiles were built from.

| Field | Type | Unit | Provenance | Null | Sensitive | Source | Description |
|---|---|---|---|---|---|---|---|
| `profile_id` | string |  | DerivedFromRecorded | no | no | derived: identity | Stable profile identifier (see the table description for its form). |
| `profile_rev` | int64 | 1 | DerivedFromRecorded | no | no | derived: previous build's revision and content_sha256 | Revision of this profile. It stays the same while the profile's content is unchanged and goes up by one when any value changes, so profile_id@profile_rev always means one fixed set of values. |
| `content_sha256` | string |  | DerivedFromRecorded | no | no | derived: row values | SHA-256 of the profile's values (every field except profile_rev, content_sha256 and last_updated_utc, floats by their exact bits). Used to decide when profile_rev goes up. |
| `source_dataset` | string |  | Recorded | no | no | derived: input file | Lake dataset the row was built from. |
| `source_key` | string |  | Recorded | no | yes | source row identity | The row's key in its source (an operator ID, or the source row number where the operator publishes no ID). |
| `last_updated_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: build date | Profiles last updated: the date these profiles were brought up to. |
| `operator` | string |  | Recorded | no | no | derived: source file | Network operator group (ukpn, npg, nged). |
| `licence` | string |  | Recorded | no | no | LTDS licence column | Licence area (EPN, LPN, SPN, NPGN, NPGY, EMID, WMID, SWEST, SWALES). |
| `gsp_group` | string |  | Recorded | yes | yes | LTDS GSP / group column | Grid supply point or substation group as published. |
| `winding_count` | int64 | 1 | Recorded | no | no | derived: source table | 2 for a two-winding transformer (LTDS Table 2a), 3 for three-winding (Table 2b). |
| `hv_node` | string |  | Recorded | yes | yes | LTDS node column | HV winding connection node as published. |
| `hv_substation` | string |  | Recorded | yes | yes | LTDS substation column | HV substation name where published (UKPN only). |
| `hv_kv` | float64 | kV | Recorded | no | no | LTDS HV voltage column | HV winding voltage. |
| `lv_node` | string |  | Recorded | yes | yes | LTDS node column | LV winding connection node as published. |
| `lv_substation` | string |  | Recorded | yes | yes | LTDS substation column | LV substation name where published (UKPN only). |
| `lv_kv` | float64 | kV | Recorded | no | no | LTDS LV voltage column | LV winding voltage. |
| `tertiary_node` | string |  | Recorded | yes | yes | LTDS Table 2b | Third winding node (three-winding units only). |
| `tertiary_kv` | float64 | kV | Recorded | yes | no | LTDS Table 2b | Third winding voltage (three-winding units only). |
| `voltage_class` | string |  | DerivedFromRecorded | no | no | derived: hv_kv mapped to GB voltage classes | Profiles folder, taken from the HV winding voltage. |
| `status` | string |  | Recorded | yes | no | LTDS status column (NGED only) | energised, out, planned or unknown. Null where the operator publishes no status (UKPN, NPG). |
| `vector_group` | string |  | Recorded | yes | no | LTDS vector group | Winding vector group as published (three-winding: HV/LV1/LV2). |
| `rating_mva` | float64 | MVA | Recorded | yes | no | LTDS rating column | Nominal or continuous rating (UKPN: winter rating; NPG: transformer rating; NGED: nominal rating). |
| `rating_summer_mva` | float64 | MVA | Recorded | yes | no | LTDS summer rating | Summer rating (UKPN only). |
| `rating_emergency_mva` | float64 | MVA | Recorded | yes | no | LTDS emergency rating | Emergency rating (NGED only). |
| `rate_a_mva` | float64 | MVA | Recorded | yes | no | LTDS rating column | GridSim Rate A (normal, continuous): the published continuous rating (UKPN winter, NPG and NGED season not stated). |
| `rate_a_basis` | string |  | DerivedFromRecorded | yes | no | derived: source table | What Rate A is: the season or condition the published rating applies to. |
| `rate_b_mva` | float64 | MVA | CuratedPlaceholder | yes | no | none | [VERIFY] GridSim Rate B (short-term). Not published for these assets, so null; GridSim applies its own documented default. |
| `rate_b_basis` | string |  | CuratedPlaceholder | yes | no | none | [VERIFY] What Rate B is (null while Rate B is not published). |
| `rate_c_mva` | float64 | MVA | Recorded | yes | no | NGED LTDS Emergency Rating | GridSim Rate C (emergency): NGED's published emergency rating; null for UKPN and NPG, who publish none. |
| `rate_c_basis` | string |  | DerivedFromRecorded | yes | no | derived: source table | What Rate C is: the condition or duration of the published emergency rating. |
| `r_pct_100mva` | float64 | % | DerivedFromRecorded | yes | no | derived: reported R on reported_impedance_base | Positive-sequence resistance in percent on a 100 MVA base (three-winding: HV-LV1 pair). |
| `x_pct_100mva` | float64 | % | DerivedFromRecorded | yes | no | derived: reported X on reported_impedance_base | Positive-sequence reactance in percent on a 100 MVA base (three-winding: HV-LV1 pair). |
| `x0_pct_100mva` | float64 | % | DerivedFromRecorded | yes | no | derived: reported X0 on reported_impedance_base | Zero-sequence reactance in percent on a 100 MVA base (three-winding: HV-LV1 pair). |
| `x_lv_tert_pct_100mva` | float64 | % | DerivedFromRecorded | yes | no | derived: LTDS Table 2b | Three-winding only: LV1 to LV2 (tertiary) reactance in percent on 100 MVA. |
| `x_hv_tert_pct_100mva` | float64 | % | DerivedFromRecorded | yes | no | derived: LTDS Table 2b | Three-winding only: HV to LV2 (tertiary) reactance in percent on 100 MVA. |
| `r_pct_on_rating` | float64 | % | DerivedFromRecorded | yes | no | derived: r_pct_100mva, rating_mva | Resistance in percent on the transformer's own rating: r_pct_100mva x rating_mva / 100. |
| `x_pct_on_rating` | float64 | % | DerivedFromRecorded | yes | no | derived: x_pct_100mva, rating_mva | Reactance (impedance voltage) in percent on the transformer's own rating: x_pct_100mva x rating_mva / 100. |
| `x_over_r` | float64 | 1 | DerivedFromRecorded | yes | no | derived: x / r | X/R ratio, set only when R is above zero. |
| `tap_min_pct` | float64 | % | DerivedFromRecorded | yes | no | derived: reported_tap_min | Lowest tap position as a percent change from nominal ratio (UKPN values converted: published value minus 100). |
| `tap_max_pct` | float64 | % | DerivedFromRecorded | yes | no | derived: reported_tap_max | Highest tap position as a percent change from nominal ratio (UKPN values converted: published value minus 100). |
| `tap_range_pct` | float64 | % | DerivedFromRecorded | yes | no | derived: tap_max_pct - tap_min_pct | Total tap range: tap_max_pct minus tap_min_pct. |
| `reported_tap_min` | float64 | per `reported_tap_convention` | Recorded | yes | no | LTDS minimum tap | Lowest tap exactly as published, in reported_tap_convention. |
| `reported_tap_max` | float64 | per `reported_tap_convention` | Recorded | yes | no | LTDS maximum tap | Highest tap exactly as published, in reported_tap_convention. |
| `reported_tap_convention` | string |  | DerivedFromRecorded | no | no | derived: source table | How the operator published tap limits: percent_change (NPG, NGED: for example -12 and +6) or percent_of_nominal_ratio (UKPN: for example 81 and 104). |
| `reverse_power_reported` | float64 | per `reverse_power_unit` | Recorded | yes | no | LTDS reverse power column | Reverse power capability exactly as reported, in reverse_power_unit. |
| `reverse_power_unit` | string |  | DerivedFromRecorded | yes | no | derived: source table | Unit of reverse_power_reported: % (UKPN, percent of rating), MVA (NPG), or unknown (NGED). |
| `earthing_hv` | string |  | Recorded | yes | no | LTDS earthing column | Method of earthing as published: the HV winding for UKPN; the single published value for NPG and NGED. |
| `earthing_lv` | string |  | Recorded | yes | no | LTDS earthing column | LV method of earthing as published (UKPN only). |
| `reported_impedance_base` | string |  | DerivedFromRecorded | no | no | derived: source table | Base the operator published impedance on: percent_on_100mva (NPG, documented) or percent_on_100mva_inferred (UKPN and NGED: GDA's normalisers label these percent on own rating and ohmic, but the magnitudes and their fall with rating fit percent on 100 MVA only; see quality_flags and the builder notes). |
| `reported_r1` | float64 | per `reported_impedance_base` | Recorded | yes | no | LTDS R column | Positive-sequence resistance exactly as reported, on reported_impedance_base. |
| `reported_x1` | float64 | per `reported_impedance_base` | Recorded | yes | no | LTDS X column | Positive-sequence reactance exactly as reported, on reported_impedance_base. |
| `reported_x0` | float64 | per `reported_impedance_base` | Recorded | yes | no | LTDS X0 column | Zero-sequence reactance exactly as reported, on reported_impedance_base. |
| `winding_temp_max_degc` | float64 | degC | CuratedPlaceholder | yes | no | none | [VERIFY] Hot-spot winding temperature. No temperature telemetry is held for these units; reserved for a future source. |
| `top_oil_temp_max_degc` | float64 | degC | CuratedPlaceholder | yes | no | none | [VERIFY] Top-oil temperature. No temperature telemetry is held for these units; reserved for a future source. |
| `named_operator` | string |  | CuratedPlaceholder | yes | yes | Transformers/names.csv operator | [VERIFY] Operator or owner of the asset, from Transformers/names.csv (named by hand, not published). Null where not named. |
| `named_site` | string |  | CuratedPlaceholder | yes | yes | Transformers/names.csv site_name | [VERIFY] Site name, from Transformers/names.csv. Null where not named. |
| `named_address` | string |  | CuratedPlaceholder | yes | yes | Transformers/names.csv address | [VERIFY] Site address, from Transformers/names.csv. Null where not named. |
| `named_by` | string |  | CuratedPlaceholder | yes | no | Transformers/names.csv named_by | [VERIFY] Who named the asset and when, from Transformers/names.csv. |
| `quality_flags` | string |  | DerivedFromRecorded | no | no | derived: builder checks | Semicolon list of issues found while building the row (for example no_rating, zero_impedance, convention_inferred, hv_below_lv). Empty when none. |

## taps (observed)

On-load tap changer behaviour observed from busbar voltage readings at supergrid transformers (UKPN). profile_id is 'tap-<gsp>-<transformer>'. Filed under Transformers/observed.

| Field | Type | Unit | Provenance | Null | Sensitive | Source | Description |
|---|---|---|---|---|---|---|---|
| `profile_id` | string |  | DerivedFromRecorded | no | no | derived: identity | Stable profile identifier (see the table description for its form). |
| `profile_rev` | int64 | 1 | DerivedFromRecorded | no | no | derived: previous build's revision and content_sha256 | Revision of this profile. It stays the same while the profile's content is unchanged and goes up by one when any value changes, so profile_id@profile_rev always means one fixed set of values. |
| `content_sha256` | string |  | DerivedFromRecorded | no | no | derived: row values | SHA-256 of the profile's values (every field except profile_rev, content_sha256 and last_updated_utc, floats by their exact bits). Used to decide when profile_rev goes up. |
| `source_dataset` | string |  | Recorded | no | no | derived: input file | Lake dataset the row was built from. |
| `source_key` | string |  | Recorded | no | yes | source row identity | The row's key in its source (an operator ID, or the source row number where the operator publishes no ID). |
| `last_updated_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: build date | Profiles last updated: the date these profiles were brought up to. |
| `gsp` | string |  | Recorded | no | yes | Derived/tap_changers.gsp | Grid supply point the supergrid transformer serves. |
| `transformer` | string |  | Recorded | no | yes | Derived/tap_changers.sgt | Transformer name at the GSP (AGGREGATE where the source only publishes a site total). |
| `voltage_kv` | float64 | kV | Recorded | no | no | Derived/tap_changers.vnom_kv | Nominal voltage of the measured (LV) busbar. |
| `n_obs` | int64 | 1 | DerivedFromRecorded | no | no | Derived/tap_changers.n_obs | Voltage readings the tap analysis used. |
| `observed_from_utc` | timestamp |  | Recorded | no | no | Derived/tap_changers.span_start | First reading used. |
| `observed_to_utc` | timestamp |  | Recorded | no | no | Derived/tap_changers.span_end | Last reading used. |
| `is_oltc` | bool |  | DerivedFromRecorded | no | no | Derived/tap_changers.is_oltc | True when the voltage moves on a discrete tap lattice, so an on-load tap changer is evident. |
| `tap_step_kv` | float64 | kV | DerivedFromRecorded | yes | no | Derived/tap_changers.step_kv | Observed voltage step per tap. |
| `tap_step_pct` | float64 | % | DerivedFromRecorded | yes | no | Derived/tap_changers.step_pct | Observed step per tap as a percent of nominal voltage. |
| `visible_steps` | int64 | 1 | DerivedFromRecorded | yes | no | Derived/tap_changers.n_visible_steps | Distinct tap positions seen in the readings. |
| `span_steps` | float64 | 1 | DerivedFromRecorded | yes | no | Derived/tap_changers.span_steps | Spread of positions seen, in steps. |
| `lattice_residual` | float64 | 1 | DerivedFromRecorded | yes | no | Derived/tap_changers.lattice_residual | How far readings sit from the fitted tap lattice (lower is a cleaner fit). |
| `ltds_tap_span_pct` | float64 | % | Recorded | yes | no | Derived/tap_changers.ltds_tap_span_pct | Published tap range for this unit, where matched to LTDS. |
| `ltds_expected_steps` | float64 | 1 | DerivedFromRecorded | yes | no | Derived/tap_changers.ltds_expected_steps | Tap positions the published range implies. |
| `named_operator` | string |  | CuratedPlaceholder | yes | yes | Transformers/names.csv operator | [VERIFY] Operator or owner of the asset, from Transformers/names.csv (named by hand, not published). Null where not named. |
| `named_site` | string |  | CuratedPlaceholder | yes | yes | Transformers/names.csv site_name | [VERIFY] Site name, from Transformers/names.csv. Null where not named. |
| `named_address` | string |  | CuratedPlaceholder | yes | yes | Transformers/names.csv address | [VERIFY] Site address, from Transformers/names.csv. Null where not named. |
| `named_by` | string |  | CuratedPlaceholder | yes | no | Transformers/names.csv named_by | [VERIFY] Who named the asset and when, from Transformers/names.csv. |

## flows (observed)

Active and reactive power flow statistics per transformer from half-hourly readings, over each transformer's latest 365 days up to the last-updated date. profile_id is 'flow-<operator>-<region>-<substation>-<transformer>'. Filed under Transformers/observed.

| Field | Type | Unit | Provenance | Null | Sensitive | Source | Description |
|---|---|---|---|---|---|---|---|
| `profile_id` | string |  | DerivedFromRecorded | no | no | derived: identity | Stable profile identifier (see the table description for its form). |
| `profile_rev` | int64 | 1 | DerivedFromRecorded | no | no | derived: previous build's revision and content_sha256 | Revision of this profile. It stays the same while the profile's content is unchanged and goes up by one when any value changes, so profile_id@profile_rev always means one fixed set of values. |
| `content_sha256` | string |  | DerivedFromRecorded | no | no | derived: row values | SHA-256 of the profile's values (every field except profile_rev, content_sha256 and last_updated_utc, floats by their exact bits). Used to decide when profile_rev goes up. |
| `source_dataset` | string |  | Recorded | no | no | derived: input file | Lake dataset the row was built from. |
| `source_key` | string |  | Recorded | no | yes | source row identity | The row's key in its source (an operator ID, or the source row number where the operator publishes no ID). |
| `last_updated_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: build date | Profiles last updated: the date these profiles were brought up to. |
| `operator` | string |  | Recorded | no | no | Derived/bsp_power_factor.dno | Network operator group. |
| `region` | string |  | Recorded | no | no | Derived/bsp_power_factor.region | Published data set the readings come from (for example ukpn_sgt, nged_south_west). |
| `substation` | string |  | Recorded | no | yes | Derived/bsp_power_factor.substation | Substation name as published. |
| `transformer` | string |  | Recorded | no | yes | Derived/bsp_power_factor.transformer | Transformer name as published. |
| `window_start_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: readings | First reading in the statistics window (up to 365 days before window_end_utc). |
| `window_end_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: readings | Last reading in the window: the newest reading on or before the last-updated date. |
| `n_obs` | int64 | 1 | DerivedFromRecorded | no | no | derived: count | Half-hourly readings in the window with an active power value. |
| `p_mw_min` | float64 | MW | DerivedFromRecorded | no | no | derived: MW | Lowest active power (negative is reverse flow). |
| `p_mw_p05` | float64 | MW | DerivedFromRecorded | no | no | derived: MW | 5th percentile of active power. |
| `p_mw_p50` | float64 | MW | DerivedFromRecorded | no | no | derived: MW | Median active power. |
| `p_mw_p95` | float64 | MW | DerivedFromRecorded | no | no | derived: MW | 95th percentile of active power. |
| `p_mw_max` | float64 | MW | DerivedFromRecorded | no | no | derived: MW | Highest active power. |
| `q_mvar_min` | float64 | Mvar | DerivedFromRecorded | yes | no | derived: MVAr | Lowest reactive power. |
| `q_mvar_p05` | float64 | Mvar | DerivedFromRecorded | yes | no | derived: MVAr | 5th percentile of reactive power. |
| `q_mvar_p50` | float64 | Mvar | DerivedFromRecorded | yes | no | derived: MVAr | Median reactive power. |
| `q_mvar_p95` | float64 | Mvar | DerivedFromRecorded | yes | no | derived: MVAr | 95th percentile of reactive power. |
| `q_mvar_max` | float64 | Mvar | DerivedFromRecorded | yes | no | derived: MVAr | Highest reactive power. |
| `s_mva_p50` | float64 | MVA | DerivedFromRecorded | yes | no | derived: MVA | Median apparent power. |
| `s_mva_p95` | float64 | MVA | DerivedFromRecorded | yes | no | derived: MVA | 95th percentile of apparent power. |
| `s_mva_max` | float64 | MVA | DerivedFromRecorded | yes | no | derived: MVA | Highest apparent power. |
| `pf_p05` | float64 | 1 | DerivedFromRecorded | yes | no | derived: power_factor | 5th percentile of power factor (a low power factor is the stressed end). |
| `pf_p50` | float64 | 1 | DerivedFromRecorded | yes | no | derived: power_factor | Median power factor. |
| `kv_p05` | float64 | kV | DerivedFromRecorded | yes | no | derived: kV | 5th percentile of measured voltage, where published. |
| `kv_p50` | float64 | kV | DerivedFromRecorded | yes | no | derived: kV | Median measured voltage, where published. |
| `kv_p95` | float64 | kV | DerivedFromRecorded | yes | no | derived: kV | 95th percentile of measured voltage, where published. |
| `reverse_flow_share` | float64 | 1 | DerivedFromRecorded | no | no | derived: MW < 0 | Fraction of readings with negative active power. |
| `zero_flow_share` | float64 | 1 | DerivedFromRecorded | no | no | derived: MW == 0 | Fraction of readings with exactly zero active power (often out of service or not metered). |
| `named_operator` | string |  | CuratedPlaceholder | yes | yes | Transformers/names.csv operator | [VERIFY] Operator or owner of the asset, from Transformers/names.csv (named by hand, not published). Null where not named. |
| `named_site` | string |  | CuratedPlaceholder | yes | yes | Transformers/names.csv site_name | [VERIFY] Site name, from Transformers/names.csv. Null where not named. |
| `named_address` | string |  | CuratedPlaceholder | yes | yes | Transformers/names.csv address | [VERIFY] Site address, from Transformers/names.csv. Null where not named. |
| `named_by` | string |  | CuratedPlaceholder | yes | no | Transformers/names.csv named_by | [VERIFY] Who named the asset and when, from Transformers/names.csv. |

## stress (observed)

Accumulated wear indicators per transformer: tap operations and time at high loading (UKPN supergrid transformers). profile_id is 'stress-<asset_id>'. Filed under Transformers/observed.

| Field | Type | Unit | Provenance | Null | Sensitive | Source | Description |
|---|---|---|---|---|---|---|---|
| `profile_id` | string |  | DerivedFromRecorded | no | no | derived: identity | Stable profile identifier (see the table description for its form). |
| `profile_rev` | int64 | 1 | DerivedFromRecorded | no | no | derived: previous build's revision and content_sha256 | Revision of this profile. It stays the same while the profile's content is unchanged and goes up by one when any value changes, so profile_id@profile_rev always means one fixed set of values. |
| `content_sha256` | string |  | DerivedFromRecorded | no | no | derived: row values | SHA-256 of the profile's values (every field except profile_rev, content_sha256 and last_updated_utc, floats by their exact bits). Used to decide when profile_rev goes up. |
| `source_dataset` | string |  | Recorded | no | no | derived: input file | Lake dataset the row was built from. |
| `source_key` | string |  | Recorded | no | yes | source row identity | The row's key in its source (an operator ID, or the source row number where the operator publishes no ID). |
| `last_updated_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: build date | Profiles last updated: the date these profiles were brought up to. |
| `operator` | string |  | Recorded | no | no | Derived/asset_stress_ledger.operator | Network operator group. |
| `asset_name` | string |  | Recorded | no | yes | Derived/asset_stress_ledger.asset_name | Transformer name as recorded in the stress ledger. |
| `asset_type` | string |  | Recorded | no | no | Derived/asset_stress_ledger.asset_type | Asset type in the stress ledger (for example sgt_ukpn). |
| `voltage_kv` | float64 | kV | Recorded | no | no | Derived/asset_stress_ledger.voltage_kv | Nominal voltage of the measured busbar. |
| `window_start_utc` | timestamp |  | Recorded | no | no | Derived/asset_stress_ledger.window_start | Start of the ledger window. |
| `window_end_utc` | timestamp |  | Recorded | no | no | Derived/asset_stress_ledger.window_end | End of the ledger window. |
| `tap_ops_total` | float64 | 1 | DerivedFromRecorded | yes | no | Derived/asset_stress_ledger.tap_ops_total | Tap operations counted over all readings. |
| `tap_ops_last_6mo` | float64 | 1 | DerivedFromRecorded | yes | no | Derived/asset_stress_ledger.tap_ops_last_6mo | Tap operations in the last 6 months of the window. |
| `tap_ops_prior_2yr` | float64 | 1 | DerivedFromRecorded | yes | no | Derived/asset_stress_ledger.tap_ops_prior_2yr | Tap operations in the 2 years before that. |
| `tap_rate_ratio` | float64 | 1 | DerivedFromRecorded | yes | no | Derived/asset_stress_ledger.tap_rate_anomaly_ratio | Recent tap rate over the prior rate (above 1 means the tap changer is working harder recently). |
| `tap_step_kv` | float64 | kV | DerivedFromRecorded | yes | no | Derived/asset_stress_ledger.tap_step_kv | Tap step used to count operations. |
| `tap_step_source` | string |  | DerivedFromRecorded | yes | no | Derived/asset_stress_ledger.tap_step_source | Where the tap step came from (tap_changers or estimated). |
| `hours_over_80pct` | float64 | h * | DerivedFromRecorded | yes | no | Derived/asset_stress_ledger.hours_over_80pct | Hours loaded at or above 80% of rating. |
| `worst_loading_pct` | float64 | % | DerivedFromRecorded | yes | no | Derived/asset_stress_ledger.worst_loading_pct | Highest loading seen, as a percent of rating. |
| `thermal_exceedance` | bool |  | DerivedFromRecorded | yes | no | Derived/asset_stress_ledger.thermal_exceedance_flag | True when the recent rate of high loading exceeds the asset's own history. Null where loading is not known. |
| `named_operator` | string |  | CuratedPlaceholder | yes | yes | Transformers/names.csv operator | [VERIFY] Operator or owner of the asset, from Transformers/names.csv (named by hand, not published). Null where not named. |
| `named_site` | string |  | CuratedPlaceholder | yes | yes | Transformers/names.csv site_name | [VERIFY] Site name, from Transformers/names.csv. Null where not named. |
| `named_address` | string |  | CuratedPlaceholder | yes | yes | Transformers/names.csv address | [VERIFY] Site address, from Transformers/names.csv. Null where not named. |
| `named_by` | string |  | CuratedPlaceholder | yes | no | Transformers/names.csv named_by | [VERIFY] Who named the asset and when, from Transformers/names.csv. |
