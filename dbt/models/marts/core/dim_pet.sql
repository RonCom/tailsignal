-- One row per resolved pet. Attributes are reconciled across sources:
-- exact birth dates beat estimates; the most frequently recorded value wins.
-- Every choice has an explicit tie-break (earliest date, then smallest value), so DuckDB and
-- Snowflake build identical rows and repeated builds don't change.
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
    qualify row_number() over (partition by v.source_system, v.source_pet_key
                               order by v.birth_date_precision, v.birth_date, v.sex) = 1
), base as (
    select r.*, vb.birth_date, vb.sex,
           case vb.birth_date_precision when 'exact' then 1 when 'year_only' then 2 else 3 end as birth_rank
    from recs r
    left join vet_birth vb using (unique_id)
),
{% set modes = [
    ('species', 'species', none),
    ('breed', 'breed', "breed <> 'Unmapped'"),
    ('breed_group', 'breed_group', "breed <> 'Unmapped'"),
    ('sex', 'sex', none),
    ('market', 'market', none),
    ('zip3', 'left(owner_zip, 3)', none),
] %}
{% for name, expr, cond in modes %}
m_{{ name }} as (
    select pet_id, v as {{ name }}
    from (
        select pet_id, {{ expr }} as v, count(*) as n
        from base
        where {{ expr }} is not null{% if cond %} and {{ cond }}{% endif %}
        group by pet_id, {{ expr }}
    ) t
    qualify row_number() over (partition by pet_id order by n desc, v) = 1
),
{% endfor %}
birth as (
    select pet_id, birth_date
    from base
    where birth_date is not null
    qualify row_number() over (partition by pet_id order by birth_rank, birth_date) = 1
), agg as (
    select pet_id,
           min(household_id)                       as household_id,
           cast(median(birth_year) as integer)     as median_birth_year,
           min(first_seen)                         as first_seen,
           count(*)                                as n_source_records,
           {{ distinct_sorted_list('source_system') }} as source_systems
    from base
    group by pet_id
)
select
    a.pet_id,
    a.household_id,
    s.species,
    coalesce(b.breed, 'Unknown')                    as breed,
    coalesce(g.breed_group, 'Unknown')              as breed_group,
    bd.birth_date,
    coalesce(year(bd.birth_date), a.median_birth_year) as birth_year,
    x.sex,
    mk.market,
    z.zip3,
    a.first_seen,
    a.n_source_records,
    a.source_systems
from agg a
left join m_species s using (pet_id)
left join m_breed b using (pet_id)
left join m_breed_group g using (pet_id)
left join birth bd using (pet_id)
left join m_sex x using (pet_id)
left join m_market mk using (pet_id)
left join m_zip3 z using (pet_id)
