-- Vet PIMS "alpha": flat CSV, one row per visit, client and patient denormalized.
with src as (
    select * from {{ raw_csv('vet_alpha_visits.csv', 'vet_alpha_visits') }}
)
select
    'vet_alpha'                                   as source_system,
    clinic_id                                     as location_id,
    clinic_id || '|' || patient_id                as source_pet_key,
    visit_id                                      as source_event_id,
    cast(visit_date as date)                      as event_date,
    {{ norm_name('client_first_name') }}          as owner_first,
    {{ norm_name('client_last_name') }}           as owner_last,
    {{ digits10('client_phone') }}                as owner_phone,
    nullif(lower(trim(client_email)), '')         as owner_email,
    left(client_zip, 5)                           as owner_zip,
    {{ norm_name('patient_name') }}               as pet_name,
    case species when 'Canine' then 'dog' when 'Feline' then 'cat' end as species,
    breed                                         as breed_raw,
    left(sex, 1)                                  as sex,
    cast(dob as date)                             as birth_date,
    'exact'                                       as birth_date_precision,
    cast(weight_lb as double)                     as weight_lb,
    dx_code                                       as dx_source_value,
    dx_desc                                       as dx_source_label,
    line_items,
    cast(invoice_total as double)                 as amount
from src
