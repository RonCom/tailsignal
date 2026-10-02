-- Fails if more than 3% of source pet records have a breed string we could not map.
with p as (select breed from {{ ref('int_source_pet_profiles') }} where breed is not null)
select count(*) filter (where breed = 'Unmapped') * 1.0 / count(*) as unmapped_share
from p
having count(*) filter (where breed = 'Unmapped') * 1.0 / count(*) > 0.03
