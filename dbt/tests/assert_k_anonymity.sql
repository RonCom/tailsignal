-- Fails if any quasi-identifier combination in the released cohort has fewer than k pets.
select species, breed_group, birth_period, geography, sex, count(*) as n
from {{ ref('product_pet_cohort') }}
group by all
having count(*) < {{ var('k_anonymity') }}
