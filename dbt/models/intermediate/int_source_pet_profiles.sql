-- One row per pet record per source system: the input to entity resolution.
-- Vet and grooming records repeat on every visit; the most recent values win.
with vet as (
    {% for m in ['stg_vet_alpha__visits', 'stg_vet_beta__encounters', 'stg_vet_gamma__visits'] %}
    select source_system, source_pet_key, location_id, event_date, owner_first, owner_last, owner_phone,
           owner_email, owner_zip, pet_name, species, breed_raw, birth_date, birth_date_precision
    from {{ ref(m) }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
), vet_profiles as (
    select source_system, source_pet_key,
        {{ arg_max('location_id', 'event_date') }} as location_id,
        {{ arg_max('owner_first', 'event_date') }} as owner_first, {{ arg_max('owner_last', 'event_date') }} as owner_last,
        {{ arg_max('owner_phone', 'event_date') }} as owner_phone, {{ arg_max('owner_email', 'event_date') }} as owner_email,
        {{ arg_max('owner_zip', 'event_date') }} as owner_zip, {{ arg_max('pet_name', 'event_date') }} as pet_name,
        {{ arg_max('species', 'event_date') }} as species, {{ arg_max('breed_raw', 'event_date') }} as breed_raw,
        {{ arg_max('birth_date', 'event_date') }} as birth_date, min(event_date) as first_seen
    from vet group by 1, 2
), groom_profiles as (
    select source_system, source_pet_key,
        {{ arg_max('location_id', 'event_date') }} as location_id,
        {{ arg_max('owner_first', 'event_date') }} as owner_first, {{ arg_max('owner_last', 'event_date') }} as owner_last,
        {{ arg_max('owner_phone', 'event_date') }} as owner_phone, {{ arg_max('owner_email', 'event_date') }} as owner_email,
        cast(null as varchar) as owner_zip, {{ arg_max('pet_name', 'event_date') }} as pet_name,
        cast(null as varchar) as species, {{ arg_max('breed_raw', 'event_date') }} as breed_raw,
        cast(null as date) as birth_date, min(event_date) as first_seen
    from {{ ref('stg_groomly__appointments') }} group by 1, 2
), all_profiles as (
    select * from vet_profiles
    union all select * from groom_profiles
    union all
    select source_system, source_pet_key, location_id, owner_first, owner_last, owner_phone, owner_email,
           owner_zip, pet_name, cast(null as varchar), breed_raw, birth_date, registered_on
    from {{ ref('stg_pawstay__pets') }}
    union all
    select source_system, source_pet_key, location_id, owner_first, owner_last, owner_phone, owner_email,
           cast(null as varchar), pet_name, species, cast(null as varchar), cast(null as date), start_date
    from {{ ref('stg_wellplan__memberships') }}
)
select
    p.source_system || ':' || p.source_pet_key        as unique_id,
    p.source_system,
    p.source_pet_key,
    p.location_id,
    l.market,
    p.owner_first,
    p.owner_last,
    p.owner_phone,
    p.owner_email,
    p.owner_zip,
    p.pet_name,
    coalesce(p.species, b.species)                    as species,
    b.breed,
    b.breed_group,
    year(p.birth_date)                                as birth_year,
    p.first_seen
from all_profiles p
left join {{ ref('stg_locations') }} l on l.location_id = p.location_id
left join {{ ref('int_breed_map') }} b on b.breed_raw = p.breed_raw
