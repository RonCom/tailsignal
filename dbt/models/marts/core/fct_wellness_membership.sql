select
    m.membership_id,
    c.pet_id,
    m.location_id as clinic_id,
    m.plan_tier,
    m.monthly_fee,
    m.start_date,
    m.end_date,
    m.cancel_reason,
    k.arm            as campaign_arm,
    k.campaign_date
from {{ ref('stg_wellplan__memberships') }} m
join {{ source('er', 'int_pet_clusters') }} c on c.unique_id = 'wellplan:' || m.source_pet_key
left join {{ ref('stg_wellplan__campaign') }} k using (membership_id)
