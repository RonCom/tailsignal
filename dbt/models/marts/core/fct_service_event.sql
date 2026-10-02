-- Every service a pet received, across all channels, at one grain:
-- one row per visit / stay / appointment.
with clusters as (select unique_id, pet_id from {{ source('er', 'int_pet_clusters') }}),
vet as (
    select source_system, source_event_id, source_system || ':' || source_pet_key as unique_id, location_id,
           event_date, 'vet' as channel,
           case when condition = 'wellness' then 'wellness_exam' else 'clinical_visit' end as service_code,
           condition, amount, cast(null as varchar) as staff_note, cast(null as integer) as nights
    from {{ ref('int_vet_visits') }}
),
daycare as (
    select d.source_system, d.source_event_id, d.source_system || ':' || d.source_pet_key, d.location_id,
           d.event_date, 'daycare', t.service_code, null, d.amount, d.staff_note, null
    from {{ ref('stg_pawstay__daycare_visits') }} d
    left join {{ ref('service_taxonomy') }} t on t.source_service = d.source_service and t.channel = 'daycare'
),
boarding as (
    select b.source_system, b.source_event_id, b.source_system || ':' || b.source_pet_key, b.location_id,
           b.event_date, 'boarding', t.service_code, null, b.amount, b.staff_note, b.nights
    from {{ ref('stg_pawstay__boarding_stays') }} b
    left join {{ ref('service_taxonomy') }} t on t.source_service = b.source_service and t.channel = 'boarding'
),
grooming as (
    select g.source_system, g.source_event_id, g.source_system || ':' || g.source_pet_key, g.location_id,
           g.event_date, 'grooming', t.service_code, null, g.amount, g.staff_note, null
    from {{ ref('stg_groomly__appointments') }} g
    left join {{ ref('service_taxonomy') }} t on t.source_service = g.source_service and t.channel = 'grooming'
),
unioned as (
    select * from vet union all select * from daycare union all select * from boarding union all select * from grooming
)
select
    u.channel || ':' || u.source_event_id as event_id,
    c.pet_id,
    u.channel,
    u.source_system,
    u.location_id,
    u.event_date,
    u.service_code,
    u.condition,
    u.amount,
    u.nights,
    u.staff_note
from unioned u
join clusters c using (unique_id)
