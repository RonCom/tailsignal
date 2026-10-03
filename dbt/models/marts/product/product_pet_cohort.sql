-- De-identified pet-level cohort (Data Product tier 2).
-- Direct identifiers removed; pet_id replaced by a salted hash; geography at 3-digit ZIP or coarser.
-- k-anonymity on quasi-identifiers (species, breed_group, birth period, geography, sex),
-- with progressive generalization. Each pass counts class sizes ONLY among records not
-- already released, so mixed generalization levels can never overstate k:
--   pass 1: birth year + zip3
--   pass 2: 5-year birth band + zip3
--   pass 3: 5-year birth band + market (metro)
--   otherwise suppressed
{% set k = var('k_anonymity') %}
with base as (
    select
        {{ sha256_hex("p.pet_id || '" ~ env_var('TAILSIGNAL_SALT', 'dev-salt-change-me') ~ "'") }} as pet_token,
        p.pet_id, p.species, p.breed_group, p.birth_year,
        cast(cast(floor(p.birth_year / 5) * 5 as integer) as varchar) || '-' || cast(cast(floor(p.birth_year / 5) * 5 + 4 as integer) as varchar) as birth_band,
        coalesce(p.zip3, 'UNK') as zip3, coalesce(p.market, 'UNK') as market, coalesce(p.sex, 'U') as sex
    from {{ ref('dim_pet') }} p
    where p.species is not null
), p1 as (
    select *, count(*) over (partition by species, breed_group, birth_year, zip3, sex) as n1 from base
), p2 as (
    select *, case when n1 < {{ k }} then {{ count_where('n1 < ' ~ k) }}
                   over (partition by species, breed_group, birth_band, zip3, sex) end as n2
    from p1
), p3 as (
    select *, case when n1 < {{ k }} and n2 < {{ k }} then {{ count_where('n1 < ' ~ k ~ ' and n2 < ' ~ k) }}
                   over (partition by species, breed_group, birth_band, market, sex) end as n3
    from p2
), released as (
    select pet_token, pet_id, species, breed_group, sex,
        case when n1 >= {{ k }} then cast(birth_year as varchar) else birth_band end as birth_period,
        case when n1 >= {{ k }} or n2 >= {{ k }} then zip3 else market end         as geography,
        case when n1 >= {{ k }} then 'pass1_year_zip3'
             when n2 >= {{ k }} then 'pass2_band_zip3'
             else 'pass3_band_market' end                                        as generalization
    from p3
    where n1 >= {{ k }} or n2 >= {{ k }} or n3 >= {{ k }}
), usage as (
    select pet_id,
        {{ count_where("channel = 'vet'") }} as vet_visits,
        {{ count_where("channel = 'daycare'") }} as daycare_visits,
        {{ count_where("channel = 'boarding'") }} as boarding_stays,
        {{ count_where("channel = 'grooming'") }} as grooming_appts,
        {{ distinct_sorted_list('condition', "condition is not null and condition <> 'wellness'") }} as conditions
    from {{ ref('fct_service_event') }} group by pet_id
)
select r.pet_token, r.species, r.breed_group, r.birth_period, r.geography, r.sex, r.generalization,
       coalesce(u.vet_visits, 0) as vet_visits, coalesce(u.daycare_visits, 0) as daycare_visits,
       coalesce(u.boarding_stays, 0) as boarding_stays, coalesce(u.grooming_appts, 0) as grooming_appts,
       coalesce(u.conditions, {{ empty_list() }}) as conditions
from released r left join usage u using (pet_id)
