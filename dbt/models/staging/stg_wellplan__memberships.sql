select
    'wellplan'                                         as source_system,
    membership_id                                      as source_pet_key,
    membership_id,
    clinic_id                                          as location_id,
    {{ norm_name("split_part(member_name, ' ', 1)") }} as owner_first,
    {{ norm_name("split_part(member_name, ' ', 2)") }} as owner_last,
    nullif(lower(trim(member_email)), '')              as owner_email,
    {{ digits10('member_phone') }}                     as owner_phone,
    {{ norm_name('pet_name') }}                        as pet_name,
    lower(species)                                     as species,
    plan_tier,
    cast(monthly_fee as double)                        as monthly_fee,
    cast(start_date as date)                           as start_date,
    try_cast(nullif(end_date, '') as date)             as end_date,
    nullif(cancel_reason, '')                          as cancel_reason
from {{ raw_csv('wellplan_memberships.csv', 'wellplan_memberships') }}
