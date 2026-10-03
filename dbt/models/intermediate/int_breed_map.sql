-- Map every raw breed string seen in any source to the canonical breed taxonomy:
-- 1) exact match on the curated alias table, 2) fuzzy match (Jaro-Winkler >= 0.90) to an alias,
-- 3) otherwise 'Unmapped' (monitored by a coverage test).
with raw as (
    select distinct breed_raw from (
        select breed_raw from {{ ref('stg_vet_alpha__visits') }}
        union all select breed_raw from {{ ref('stg_vet_beta__encounters') }}
        union all select breed_raw from {{ ref('stg_vet_gamma__visits') }}
        union all select breed_raw from {{ ref('stg_pawstay__pets') }}
        union all select breed_raw from {{ ref('stg_groomly__appointments') }}
    ) where breed_raw is not null
), keyed as (
    select breed_raw, {{ norm_key('breed_raw') }} as k from raw
), exact as (
    select k.breed_raw, a.breed, a.species, a.breed_group, a.size_class, 'exact' as match_type, 1.0 as score
    from keyed k join {{ ref('breed_aliases') }} a on a.alias_key = k.k
), fuzzy as (
    select breed_raw, breed, species, breed_group, size_class, 'fuzzy' as match_type, score
    from (
        select k.breed_raw, a.breed, a.species, a.breed_group, a.size_class,
               {{ jaro_winkler('k.k', 'a.alias_key') }} as score,
               row_number() over (partition by k.breed_raw order by {{ jaro_winkler('k.k', 'a.alias_key') }} desc) as rn
        from keyed k cross join {{ ref('breed_aliases') }} a
        where k.breed_raw not in (select breed_raw from exact)
    ) where rn = 1 and score >= 0.90
)
select * from exact
union all select * from fuzzy
union all
select breed_raw, 'Unmapped', null, null, null, 'none', 0.0
from keyed where breed_raw not in (select breed_raw from exact) and breed_raw not in (select breed_raw from fuzzy)
