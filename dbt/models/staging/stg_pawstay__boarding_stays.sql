select
    'pawstay'                                               as source_system,
    stay_id                                                 as source_event_id,
    pawstay_pet_id                                          as source_pet_key,
    site_id                                                 as location_id,
    cast(check_in as date)                                  as event_date,
    cast(check_out as date)                                 as check_out_date,
    {{ days_between('cast(check_in as date)', 'cast(check_out as date)') }} as nights,
    room_type                                               as source_service,
    cast(price as double)                                   as amount,
    nullif(trim(staff_note), '')                            as staff_note
from {{ raw_csv('pawstay_boarding_stays.csv', 'pawstay_boarding_stays') }}
