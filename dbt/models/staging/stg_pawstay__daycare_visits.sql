select
    'pawstay'                       as source_system,
    visit_id                        as source_event_id,
    pawstay_pet_id                  as source_pet_key,
    site_id                         as location_id,
    cast(visit_date as date)        as event_date,
    service                         as source_service,
    cast(price as double)           as amount,
    nullif(trim(staff_note), '')    as staff_note
from read_csv('{{ var("raw_dir") }}/pawstay_daycare_visits.csv', header = true, all_varchar = true)
