-- One row per resolved pet. Attributes are reconciled across sources:
-- exact birth dates beat estimates; the most frequently recorded breed wins.
with recs as (
    select c.pet_id, c.household_id, p.*
    from {{ source('er', 'int_pet_clusters') }} c
    join {{ ref('int_source_pet_profiles') }} p using (unique_id)
), vet_birth as (
    select v.source_system || ':' || v.source_pet_key as unique_id, v.birth_date, v.birth_date_precision, v.sex
    from (
        select source_system, source_pet_key, birth_date, birth_date_precision, sex from {{ ref('stg_vet_alpha__visits') }}
        union all select source_system, source_pet_key, birth_date, birth_date_precision, sex from {{ ref('stg_vet_beta__encounters') }}
        union all select source_system, source_pet_key, birth_date, birth_date_precision, sex from {{ ref('stg_vet_gamma__visits') }}
    ) v
    qualify row_number() over (partition by v.source_system, v.source_pet_key order by v.birth_date_precision) = 1
)
select
    r.pet_id,
    any_value(r.household_id)                                                  as household_id,
    mode(r.species)                                                            as species,
    coalesce(mode(r.breed) filter (where r.breed <> 'Unmapped'), 'Unknown')   as breed,
    coalesce(mode(r.breed_group) filter (where r.breed <> 'Unmapped'), 'Unknown') as breed_group,
    arg_min(vb.birth_date, case vb.birth_date_precision when 'exact' then 1 when 'year_only' then 2 else 3 end) as birth_date,
    coalesce(year(arg_min(vb.birth_date, case vb.birth_date_precision when 'exact' then 1 when 'year_only' then 2 else 3 end)),
             cast(median(r.birth_year) as integer))                            as birth_year,
    mode(vb.sex)                                                               as sex,
    mode(r.market)                                                             as market,
    mode(left(r.owner_zip, 3))                                                 as zip3,
    min(r.first_seen)                                                          as first_seen,
    count(*)                                                                   as n_source_records,
    list(distinct r.source_system order by r.source_system)                    as source_systems
from recs r
left join vet_birth vb using (unique_id)
group by r.pet_id
