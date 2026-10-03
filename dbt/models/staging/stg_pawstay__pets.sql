-- Daycare/boarding registrations. Owner name arrives as "First Last" or "Last, First";
-- age is free text ("3 yrs", "10 mos", "7").
with src as (
    select * from {{ raw_csv('pawstay_pets.csv', 'pawstay_pets') }}
), parsed as (
    select *,
        case when owner_name like '%,%' then trim(split_part(owner_name, ',', 2)) else split_part(owner_name, ' ', 1) end as first_raw,
        case when owner_name like '%,%' then trim(split_part(owner_name, ',', 1)) else split_part(owner_name, ' ', 2) end as last_raw,
        {{ first_int('age_text') }} as age_num,
        age_text like '%mo%' as age_in_months
    from src
)
select
    'pawstay'                                      as source_system,
    site_id                                        as location_id,
    pawstay_pet_id                                 as source_pet_key,
    {{ norm_name('first_raw') }}                   as owner_first,
    {{ norm_name('last_raw') }}                    as owner_last,
    {{ digits10('owner_phone') }}                  as owner_phone,
    nullif(lower(trim(owner_email)), '')           as owner_email,
    left(owner_zip, 5)                             as owner_zip,
    {{ norm_name('pet_name') }}                    as pet_name,
    breed                                          as breed_raw,
    cast(registered_on as date)                    as registered_on,
    case when age_in_months then {{ minus_days('cast(registered_on as date)', 'cast(age_num * 30.4 as integer)') }}
         else {{ minus_days('cast(registered_on as date)', 'cast((age_num + 0.5) * 365.25 as integer)') }} end as birth_date,
    'estimated_from_age'                           as birth_date_precision,
    cast(weight_lb as double)                      as weight_lb
from parsed
