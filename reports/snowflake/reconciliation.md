# Reconciliation: Snowflake vs DuckDB

## Row counts

| Model | DuckDB | Snowflake | Match |
|---|---|---|---|
| staging.stg_vet_alpha__visits | 18,881 | 18,881 | yes |
| staging.stg_vet_beta__encounters | 17,571 | 17,571 | yes |
| staging.stg_vet_gamma__visits | 16,715 | 16,715 | yes |
| staging.stg_groomly__appointments | 62,042 | 62,042 | yes |
| staging.stg_pawstay__pets | 6,877 | 6,877 | yes |
| staging.stg_pawstay__daycare_visits | 719,927 | 719,927 | yes |
| staging.stg_pawstay__boarding_stays | 30,661 | 30,661 | yes |
| staging.stg_wellplan__memberships | 3,604 | 3,604 | yes |
| staging.stg_wellplan__campaign | 3,061 | 3,061 | yes |
| staging.stg_locations | 21 | 21 | yes |
| core.dim_location | 21 | 21 | yes |
| intermediate.int_pet_clusters | 26,099 | 26,099 | yes |
| intermediate.int_breed_map | 114 | 114 | yes |
| intermediate.int_source_pet_profiles | 26,099 | 26,099 | yes |
| intermediate.int_vet_visits | 53,167 | 53,167 | yes |
| core.dim_pet | 12,666 | 12,666 | yes |
| core.fct_service_event | 865,797 | 865,797 | yes |
| core.fct_wellness_membership | 3,604 | 3,604 | yes |
| product.product_pet_cohort | 11,614 | 11,614 | yes |
| product.product_condition_prevalence | 1,728 | 1,728 | yes |
| product.product_service_benchmark | 1,262 | 1,262 | yes |
| qa.qa_privacy_release | 4 | 4 | yes |

## Row-by-row comparison

Rows are matched on the key; each cell counts rows whose value differs.

- **intermediate.int_breed_map**: 114 matched rows; only in DuckDB 0; only in Snowflake 0; differing columns: score 10 (known: Snowflake's Jaro-Winkler returns whole percentages; the mapped breed is identical)
- **intermediate.int_source_pet_profiles**: 26,099 matched rows; only in DuckDB 0; only in Snowflake 0; differing columns: none
- **intermediate.int_vet_visits**: 53,167 matched rows; only in DuckDB 0; only in Snowflake 0; differing columns: none
- **core.dim_pet**: 12,666 matched rows; only in DuckDB 0; only in Snowflake 0; differing columns: none
- **core.fct_service_event**: 865,797 matched rows; only in DuckDB 0; only in Snowflake 0; differing columns: none
- **core.fct_wellness_membership**: 3,604 matched rows; only in DuckDB 0; only in Snowflake 0; differing columns: none
- **product.product_pet_cohort**: 11,614 matched rows; only in DuckDB 0; only in Snowflake 0; differing columns: none
- **product.product_condition_prevalence**: 1,728 matched rows; only in DuckDB 0; only in Snowflake 0; differing columns: none
- **product.product_service_benchmark**: 1,262 matched rows; only in DuckDB 0; only in Snowflake 0; differing columns: revenue_per_active_pet 2 (known: half-cent rounding of floating-point values differs by engine)
- **qa.qa_privacy_release**: 4 matched rows; only in DuckDB 0; only in Snowflake 0; differing columns: none

**Result: MATCH**
