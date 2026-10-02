-- Privacy/utility trade-off of the cohort release: how many pets at each generalization level.
{{ config(schema='qa') }}
with total as (select count(*) as n from {{ ref('dim_pet') }} where species is not null),
rel as (select generalization, count(*) as n from {{ ref('product_pet_cohort') }} group by 1)
select generalization, n as pets, round(n / (select n from total), 4) as share from rel
union all
select 'suppressed', (select n from total) - (select sum(n) from rel),
       round(((select n from total) - (select sum(n) from rel)) / (select n from total), 4)
