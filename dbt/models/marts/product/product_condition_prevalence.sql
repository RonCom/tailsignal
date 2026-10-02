-- Research & Insights product: annual condition prevalence by species x breed group x market.
-- Cells with fewer than k pets (numerator 1..k-1 or denominator < k) are suppressed.
{% set k = var('k_anonymity') %}
with vet as (
    select e.pet_id, year(e.event_date) as yr, e.condition, p.species, p.breed_group, p.market
    from {{ ref('fct_service_event') }} e join {{ ref('dim_pet') }} p using (pet_id)
    where e.channel = 'vet'
), denom as (
    select yr, species, breed_group, market, count(distinct pet_id) as pets_seen from vet group by all
), numer as (
    select yr, species, breed_group, market, condition, count(distinct pet_id) as pets_with_condition
    from vet where condition not in ('wellness', 'unmapped') group by all
), grid as (
    select d.*, c.condition from denom d cross join (select distinct condition from numer) c
)
select
    g.yr as year, g.species, g.breed_group, g.market, g.condition,
    case when g.pets_seen >= {{ k }} then g.pets_seen end as pets_seen,
    case when g.pets_seen >= {{ k }} and (coalesce(n.pets_with_condition, 0) = 0 or n.pets_with_condition >= {{ k }})
         then coalesce(n.pets_with_condition, 0) end as pets_with_condition,
    case when g.pets_seen >= {{ k }} and (coalesce(n.pets_with_condition, 0) = 0 or n.pets_with_condition >= {{ k }})
         then round(coalesce(n.pets_with_condition, 0) / g.pets_seen, 4) end as prevalence,
    not (g.pets_seen >= {{ k }} and (coalesce(n.pets_with_condition, 0) = 0 or n.pets_with_condition >= {{ k }})) as suppressed
from grid g
left join numer n using (yr, species, breed_group, market, condition)
