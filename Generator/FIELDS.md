# Generator fields

Generated from `fields.json` by `tools/profiles_common.py`. Do not edit by hand.

Units marked * are not yet in GridSim's unit vocabulary (proposed additions).

## bm_units (reference)

One row per Balancing Mechanism unit that can generate (interconnector units are in the Interconnects family). Registration and machine data from Elexon; the statistics of its notified dynamics and metered output are in bm_dynamics. profile_id is 'gen-bmu-' plus the slug of the Elexon id.

| Field | Type | Unit | Provenance | Null | Sensitive | Source | Description |
|---|---|---|---|---|---|---|---|
| `profile_id` | string |  | DerivedFromRecorded | no | no | derived: identity | Stable profile identifier (see the table description for its form). |
| `profile_rev` | int64 | 1 | DerivedFromRecorded | no | no | derived: previous build's revision and content_sha256 | Revision of this profile. It stays the same while the profile's content is unchanged and goes up by one when any value changes, so profile_id@profile_rev always means one fixed set of values. |
| `content_sha256` | string |  | DerivedFromRecorded | no | no | derived: row values | SHA-256 of the profile's values (every field except profile_rev, content_sha256 and last_updated_utc, floats by their exact bits). Used to decide when profile_rev goes up. |
| `source_dataset` | string |  | Recorded | no | no | derived: input file | Lake dataset the row was built from. |
| `source_key` | string |  | Recorded | no | no | source row identity | Elexon BM unit id, or 'ng:' plus the National Grid id where Elexon has no registration. |
| `last_updated_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: build date | Profiles last updated: the date these profiles were brought up to. |
| `bmu_id` | string |  | Recorded | no | no | Elexon/Reference/bmunits_all.json elexonBmUnit | Elexon BM unit id; for a unit NESO lists without an Elexon registration, 'ng:' plus its National Grid id. |
| `ng_bmu_id` | string |  | Recorded | yes | no | bmunits_all.json nationalGridBmUnit | NESO (National Grid) BM unit id. |
| `unit_name` | string |  | Recorded | yes | no | bmunits_all.json bmUnitName | BM unit name as registered. |
| `lead_party` | string |  | Recorded | yes | no | bmunits_all.json leadPartyName | Registered lead party. |
| `bmu_type` | string |  | Recorded | yes | no | bmunits_all.json bmUnitType | Elexon BM unit type (T transmission, E embedded, I interconnector, S supplier, V virtual and so on). |
| `fuel_type` | string |  | Recorded | yes | no | bmunits_all.json fuelType | Elexon fuel type (CCGT, OCGT, NUCLEAR, WIND, BIOMASS and so on). Null for most embedded and supplier units: Elexon publishes no fuel for them. |
| `fuel_folder` | string |  | DerivedFromRecorded | no | no | derived: fuel_type via the builder's FUEL table | Profiles folder under Generator. |
| `gsp_group` | string |  | Recorded | yes | no | bmunits_all.json gspGroupName | GSP group name. |
| `transmission_loss_factor` | float64 | 1 | Recorded | yes | no | bmunits_all.json transmissionLossFactor | Transmission loss factor applied in settlement. |
| `capacity_mw` | float64 | MW | Recorded | yes | no | bmunits_all.json generationCapacity | Registered generation capacity. |
| `rated_mva_assumed` | float64 | MVA | CuratedPlaceholder | yes | no | derived: capacity_mw / 0.9 (assumed power factor) | [VERIFY] Machine MVA base for per-unit values (pu@machine, H): capacity_mw / 0.9, using the power factor GDA's inertia work assumes. Assumed, not published: replace when a published MVA rating is found. |
| `demand_capacity_mw` | float64 | MW | Recorded | yes | no | bmunits_all.json demandCapacity | Registered demand capacity (negative or zero for generators; storage and pumped units import). |
| `max_rating_mw` | float64 | MW | Synthetic | yes | no | derived: capacity / 0.8 (Mark's rule) | Estimated maximum rating, on the rule that nameplate capacity is 80% of the machine's maximum: capacity / 0.8. |
| `thermal_headroom_mw` | float64 | MW | Synthetic | yes | no | derived: max_rating_mw - capacity | Estimated thermal headroom above nameplate: max_rating_mw minus capacity. |
| `inertia_h_s` | float64 | s | CuratedPlaceholder | yes | no | GDA H_BY_FUEL by fuel | [VERIFY] Typical inertia constant H for the fuel, on the machine's own MVA base, from GDA's documented table (Scripts/build_inertia_reconstructed.py H_BY_FUEL: NESO, ENTSO-E and classical machine ranges). Null for converter-connected plant, which adds no true inertia. |
| `stored_energy_s_mva` | float64 | s.MVA * | CuratedPlaceholder | yes | no | derived: inertia_h_s, rated_mva_assumed | [VERIFY] Kinetic energy at rated speed: inertia_h_s x rated_mva_assumed. |
| `pole_count` | int64 | 1 | CuratedPlaceholder | yes | no | none | [VERIFY] Number of generator poles. Not held in the lake; reserved for a future source. |
| `rated_speed_rpm` | float64 | rpm * | CuratedPlaceholder | yes | no | none | [VERIFY] Rated shaft speed (120 x 50 / pole_count). Not held in the lake; set when pole_count is known. |
| `rated_torque_knm` | float64 | kN.m * | CuratedPlaceholder | yes | no | none | [VERIFY] Rated shaft torque (rated MW / shaft angular speed). Not held in the lake; set when rated speed is known. |
| `co2_t_per_mwh` | float64 | tCO2/MWh * | CuratedPlaceholder | yes | no | none | [VERIFY] Emission intensity of this asset. The lake holds only regional grid intensity, not per-asset figures; reserved for a future source. |
| `named_operator` | string |  | CuratedPlaceholder | yes | yes | Generator/names.csv operator | [VERIFY] Operator or owner of the asset, from Generator/names.csv (named by hand, not published). Null where not named. |
| `named_site` | string |  | CuratedPlaceholder | yes | yes | Generator/names.csv site_name | [VERIFY] Site name, from Generator/names.csv. Null where not named. |
| `named_address` | string |  | CuratedPlaceholder | yes | yes | Generator/names.csv address | [VERIFY] Site address, from Generator/names.csv. Null where not named. |
| `named_by` | string |  | CuratedPlaceholder | yes | no | Generator/names.csv named_by | [VERIFY] Who named the asset and when, from Generator/names.csv. |
| `quality_flags` | string |  | DerivedFromRecorded | no | no | derived: builder checks | Semicolon list of issues (for example no_fuel_type, no_capacity, no_elexon_registration). Empty when none. |

## bm_dynamics (observed)

Statistics of each BM unit's notified dynamic parameters (ramp rates, stable and maximum limits, notice and run times) and metered output, over the 365 days to the last-updated date. Kept apart from bm_units because they come from time-stamped operational data. profile_id is 'gen-dyn-' plus the slug of the Elexon id.

| Field | Type | Unit | Provenance | Null | Sensitive | Source | Description |
|---|---|---|---|---|---|---|---|
| `profile_id` | string |  | DerivedFromRecorded | no | no | derived: identity | Stable profile identifier (see the table description for its form). |
| `profile_rev` | int64 | 1 | DerivedFromRecorded | no | no | derived: previous build's revision and content_sha256 | Revision of this profile. It stays the same while the profile's content is unchanged and goes up by one when any value changes, so profile_id@profile_rev always means one fixed set of values. |
| `content_sha256` | string |  | DerivedFromRecorded | no | no | derived: row values | SHA-256 of the profile's values (every field except profile_rev, content_sha256 and last_updated_utc, floats by their exact bits). Used to decide when profile_rev goes up. |
| `source_dataset` | string |  | Recorded | no | no | derived: input files | Elexon datasets the statistics come from. |
| `source_key` | string |  | Recorded | no | no | Elexon bmUnit | Elexon BM unit id. |
| `last_updated_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: build date | Profiles last updated: the date these profiles were brought up to. |
| `bmu_id` | string |  | Recorded | no | no | Elexon bmUnit | Elexon BM unit id; for a unit NESO lists without an Elexon registration, 'ng:' plus its National Grid id. |
| `fuel_folder` | string |  | DerivedFromRecorded | no | no | derived: bm_units.fuel_folder | Profiles folder under Generator (as in bm_units). |
| `dynamics_window_start_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: last updated minus 365 days | Start of the 365-day window the statistics use. |
| `ramp_up_mw_per_min_p50` | float64 | MW/min | DerivedFromRecorded | yes | no | Elexon RURE rate1-3 | Median of the fastest notified run-up rate (the largest of the three RURE rate bands per notification). |
| `ramp_up_mw_per_min_p90` | float64 | MW/min | DerivedFromRecorded | yes | no | Elexon RURE rate1-3 | 90th percentile of the fastest notified run-up rate. |
| `ramp_up_slowest_mw_per_min_p50` | float64 | MW/min | DerivedFromRecorded | yes | no | Elexon RURE rate1-3 | Median of the slowest run-up band per notification (the rate near the elbows). |
| `ramp_down_mw_per_min_p50` | float64 | MW/min | DerivedFromRecorded | yes | no | Elexon RDRE rate1-3 | Median of the fastest notified run-down rate. |
| `ramp_down_mw_per_min_p90` | float64 | MW/min | DerivedFromRecorded | yes | no | Elexon RDRE rate1-3 | 90th percentile of the fastest notified run-down rate. |
| `ramp_down_slowest_mw_per_min_p50` | float64 | MW/min | DerivedFromRecorded | yes | no | Elexon RDRE rate1-3 | Median of the slowest run-down band per notification. |
| `import_ramp_up_mw_per_min_p50` | float64 | MW/min | DerivedFromRecorded | yes | no | Elexon RURI rate1-3 | Median fastest run-up rate on import (storage and pumped units). |
| `import_ramp_down_mw_per_min_p50` | float64 | MW/min | DerivedFromRecorded | yes | no | Elexon RDRI rate1-3 | Median fastest run-down rate on import. |
| `ramp_notifications` | int64 | 1 | DerivedFromRecorded | yes | no | derived: count | Run-up and run-down export notifications in the window. |
| `stable_export_limit_mw_p50` | float64 | MW | DerivedFromRecorded | yes | no | Elexon SEL level | Median stable export limit (the lowest steady output). |
| `stable_import_limit_mw_p50` | float64 | MW | DerivedFromRecorded | yes | no | Elexon SIL level | Median stable import limit. |
| `max_export_limit_mw_max` | float64 | MW | DerivedFromRecorded | yes | no | Elexon MELS levelTo | Highest maximum export limit notified in the window. |
| `max_export_limit_mw_p50` | float64 | MW | DerivedFromRecorded | yes | no | Elexon MELS levelTo | Median maximum export limit notified. |
| `notice_to_deviate_min_p50` | float64 | min | DerivedFromRecorded | yes | no | Elexon NDZ notice | Median notice needed to move from zero output. |
| `min_zero_time_min_p50` | float64 | min | DerivedFromRecorded | yes | no | Elexon MZT periodMin | Median minimum time the unit must stay at zero once there. |
| `min_non_zero_time_min_p50` | float64 | min | DerivedFromRecorded | yes | no | Elexon MNZT periodMin | Median minimum time the unit must run once started. |
| `metered_periods` | int64 | 1 | DerivedFromRecorded | yes | no | derived: count | Half-hours with a metered output value in the window. |
| `output_mw_mean` | float64 | MW | DerivedFromRecorded | yes | no | Elexon B1610 quantity | Mean metered output (B1610 energy per half-hour x 2). |
| `output_mw_p50` | float64 | MW | DerivedFromRecorded | yes | no | Elexon B1610 quantity | Median metered output (nearest rank on 0.1 MW bins). |
| `output_mw_p99` | float64 | MW | DerivedFromRecorded | yes | no | Elexon B1610 quantity | 99th percentile of metered output (nearest rank on 0.1 MW bins). |
| `output_mw_max` | float64 | MW | DerivedFromRecorded | yes | no | Elexon B1610 quantity | Highest metered output. |
| `capacity_factor` | float64 | 1 | DerivedFromRecorded | yes | no | derived: output_mw_mean, capacity_mw | output_mw_mean / capacity_mw. |
| `dynamics_window_end_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: last updated | End of the window: the profiles last-updated date. |
| `named_operator` | string |  | CuratedPlaceholder | yes | yes | Generator/names.csv operator | [VERIFY] Operator or owner of the asset, from Generator/names.csv (named by hand, not published). Null where not named. |
| `named_site` | string |  | CuratedPlaceholder | yes | yes | Generator/names.csv site_name | [VERIFY] Site name, from Generator/names.csv. Null where not named. |
| `named_address` | string |  | CuratedPlaceholder | yes | yes | Generator/names.csv address | [VERIFY] Site address, from Generator/names.csv. Null where not named. |
| `named_by` | string |  | CuratedPlaceholder | yes | no | Generator/names.csv named_by | [VERIFY] Who named the asset and when, from Generator/names.csv. |
| `quality_flags` | string |  | DerivedFromRecorded | no | no | derived: builder checks | Semicolon list of issues (no_metered_output, no_dynamic_data; ramp_rate_999_notified: the unit notifies 999 MW/min, the convention for no ramp limit, kept as published; output_above_rule_max_rating: metered output above capacity / 0.8). Empty when none. |

## stations (reference)

One row per generating station from DESNZ DUKES 5.11 and the Renewable Energy Planning Database (REPD). REPD rows are kept when the project is operational or still live (Operational, Under Construction, Awaiting Construction, Application Submitted, Appeal Lodged, No Application Required), so the table also serves forward planning; refused, withdrawn, abandoned, expired, revised and decommissioned records are left out. Each source's latest snapshot dated on or before the last-updated date is used. profile_id is 'gen-dukes-' or 'gen-repd-' plus the source key.

| Field | Type | Unit | Provenance | Null | Sensitive | Source | Description |
|---|---|---|---|---|---|---|---|
| `profile_id` | string |  | DerivedFromRecorded | no | no | derived: identity | Stable profile identifier (see the table description for its form). |
| `profile_rev` | int64 | 1 | DerivedFromRecorded | no | no | derived: previous build's revision and content_sha256 | Revision of this profile. It stays the same while the profile's content is unchanged and goes up by one when any value changes, so profile_id@profile_rev always means one fixed set of values. |
| `content_sha256` | string |  | DerivedFromRecorded | no | no | derived: row values | SHA-256 of the profile's values (every field except profile_rev, content_sha256 and last_updated_utc, floats by their exact bits). Used to decide when profile_rev goes up. |
| `source_dataset` | string |  | Recorded | no | no | derived: input file | Lake dataset the row was built from. |
| `source_key` | string |  | Recorded | no | no | source row identity | The row's key in its source. |
| `last_updated_utc` | timestamp |  | DerivedFromRecorded | no | no | derived: build date | Profiles last updated: the date these profiles were brought up to. |
| `source` | string |  | Recorded | no | no | derived: input file | dukes (DESNZ DUKES 5.11 power stations) or repd (DESNZ Renewable Energy Planning Database). Large sites can appear in both. |
| `station_name` | string |  | Recorded | yes | yes | DUKES site_name / REPD site_name | Site name as published. |
| `company` | string |  | Recorded | yes | no | DUKES company_name / REPD operator_or_applicant | Owner, operator or applicant as published. |
| `technology` | string |  | Recorded | yes | no | DUKES type / REPD technology_type | Technology or plant type as published (for example CCGT, Wind Onshore, Battery). |
| `primary_fuel` | string |  | Recorded | yes | no | DUKES primary_fuel | Primary fuel (DUKES only). |
| `secondary_fuel` | string |  | Recorded | yes | no | DUKES secondary_fuel | Secondary fuel (DUKES only). |
| `chp` | bool |  | Recorded | yes | no | DUKES chp / REPD chp_enabled | True when the site is combined heat and power (DUKES chp, REPD chp_enabled). Null where not stated. |
| `fuel_folder` | string |  | DerivedFromRecorded | no | no | derived: technology and fuel via the builder's FUEL tables | Profiles folder under Generator. |
| `development_status` | string |  | Recorded | yes | no | REPD development_status_short | REPD development status (Operational, Under Construction, Awaiting Construction, Application Submitted and so on). DUKES lists operating stations, so its rows read Operational. |
| `capacity_mw` | float64 | MW | Recorded | yes | no | DUKES installedcapacity_mw / REPD installed_capacity_mwelec | Installed electrical capacity. |
| `rated_mva_assumed` | float64 | MVA | CuratedPlaceholder | yes | no | derived: capacity_mw / 0.9 (assumed power factor) | [VERIFY] Machine MVA base for per-unit values (pu@machine, H): capacity_mw / 0.9, using the power factor GDA's inertia work assumes. Assumed, not published: replace when a published MVA rating is found. |
| `storage_mwh` | float64 | MWh | CuratedPlaceholder | yes | no | none | [VERIFY] Storage energy capacity. Not published in the REPD columns held; reserved for a future source. |
| `max_rating_mw` | float64 | MW | Synthetic | yes | no | derived: capacity / 0.8 (Mark's rule) | Estimated maximum rating, on the rule that nameplate capacity is 80% of the machine's maximum: capacity / 0.8. |
| `thermal_headroom_mw` | float64 | MW | Synthetic | yes | no | derived: max_rating_mw - capacity | Estimated thermal headroom above nameplate: max_rating_mw minus capacity. |
| `inertia_h_s` | float64 | s | CuratedPlaceholder | yes | no | GDA H_BY_FUEL by fuel | [VERIFY] Typical inertia constant H for the fuel, on the machine's own MVA base, from GDA's documented table (Scripts/build_inertia_reconstructed.py H_BY_FUEL: NESO, ENTSO-E and classical machine ranges). Null for converter-connected plant, which adds no true inertia. |
| `stored_energy_s_mva` | float64 | s.MVA * | CuratedPlaceholder | yes | no | derived: inertia_h_s, rated_mva_assumed | [VERIFY] Kinetic energy at rated speed: inertia_h_s x rated_mva_assumed. |
| `pole_count` | int64 | 1 | CuratedPlaceholder | yes | no | none | [VERIFY] Number of generator poles. Not held in the lake; reserved for a future source. |
| `rated_speed_rpm` | float64 | rpm * | CuratedPlaceholder | yes | no | none | [VERIFY] Rated shaft speed (120 x 50 / pole_count). Not held in the lake; set when pole_count is known. |
| `rated_torque_knm` | float64 | kN.m * | CuratedPlaceholder | yes | no | none | [VERIFY] Rated shaft torque (rated MW / shaft angular speed). Not held in the lake; set when rated speed is known. |
| `co2_t_per_mwh` | float64 | tCO2/MWh * | CuratedPlaceholder | yes | no | none | [VERIFY] Emission intensity of this asset. The lake holds only regional grid intensity, not per-asset figures; reserved for a future source. |
| `year_commissioned` | int64 | 1 | Recorded | yes | no | DUKES year_commissioned / REPD operational | Year commissioned (DUKES) or year it became operational (REPD). |
| `region` | string |  | Recorded | yes | no | DUKES region / REPD region | Region as published. |
| `dno_licence_area` | string |  | DerivedFromRecorded | yes | no | Derived/asset_geography.dno_license_area | DNO licence area the site's coordinates fall in. |
| `gsp_region` | string |  | DerivedFromRecorded | yes | no | Derived/asset_geography.gsp_region | GSP region the site's coordinates fall in. |
| `easting` | float64 | m * | Recorded | yes | yes | DUKES / REPD x_coordinate | OSGB easting in metres (British National Grid, EPSG:27700). Identifies the site, so sensitive. |
| `northing` | float64 | m * | Recorded | yes | yes | DUKES / REPD y_coordinate | OSGB northing in metres (British National Grid, EPSG:27700). Identifies the site, so sensitive. |
| `postcode` | string |  | Recorded | yes | yes | DUKES / REPD postcode | Postcode as published. |
| `turbines` | int64 | 1 | Recorded | yes | no | REPD no_of_turbines | Number of turbines (REPD wind). |
| `turbine_capacity_mw` | float64 | MW | Recorded | yes | no | REPD turbine_capacity_mw | Capacity per turbine (REPD wind). |
| `named_operator` | string |  | CuratedPlaceholder | yes | yes | Generator/names.csv operator | [VERIFY] Operator or owner of the asset, from Generator/names.csv (named by hand, not published). Null where not named. |
| `named_site` | string |  | CuratedPlaceholder | yes | yes | Generator/names.csv site_name | [VERIFY] Site name, from Generator/names.csv. Null where not named. |
| `named_address` | string |  | CuratedPlaceholder | yes | yes | Generator/names.csv address | [VERIFY] Site address, from Generator/names.csv. Null where not named. |
| `named_by` | string |  | CuratedPlaceholder | yes | no | Generator/names.csv named_by | [VERIFY] Who named the asset and when, from Generator/names.csv. |
| `quality_flags` | string |  | DerivedFromRecorded | no | no | derived: builder checks | Semicolon list of issues (for example no_capacity). Empty when none. |
