-- Vet PIMS "gamma": pipe-delimited export with no patient id and free-text visit reason.
-- A patient key is derived from clinic + owner account + normalized pet name.
with src as (
    select * from {{ raw_csv('vet_gamma_visits.txt', 'vet_gamma_visits', delim='|') }}
)
select
    'vet_gamma'                                                         as source_system,
    CLINIC                                                              as location_id,
    CLINIC || '|' || ACCT || '|' || {{ norm_key('PET_NAME') }}          as source_pet_key,
    VISIT_NO                                                            as source_event_id,
    {{ parse_date('VISIT_DT', '%Y%m%d', 'YYYYMMDD') }}                                 as event_date,
    {{ norm_name("split_part(OWNER_NAME, ' ', 1)") }}                   as owner_first,
    {{ norm_name("split_part(OWNER_NAME, ' ', 2)") }}                   as owner_last,
    {{ digits10('PHONE') }}                                             as owner_phone,
    nullif(lower(trim(EMAIL)), '')                                      as owner_email,
    left(ZIP, 5)                                                        as owner_zip,
    {{ norm_name('PET_NAME') }}                                         as pet_name,
    lower(SPECIES)                                                      as species,
    BREED                                                               as breed_raw,
    SEX                                                                 as sex,
    {{ parse_date('BIRTH', '%Y%m%d', 'YYYYMMDD') }}                                    as birth_date,
    case when right(BIRTH, 4) = '0101' then 'year_only' else 'exact' end as birth_date_precision,
    cast(null as double)                                                as weight_lb,
    {{ norm_key('REASON') }}                                            as dx_source_value,
    REASON                                                              as dx_source_label,
    cast(null as varchar)                                               as line_items,
    cast(TOTAL as double)                                               as amount
from src
