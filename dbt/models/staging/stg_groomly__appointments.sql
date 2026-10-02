-- Grooming appointments: customer and pet attributes repeated on every row.
select
    'groomly'                                              as source_system,
    appointment_id                                         as source_event_id,
    customer_id || '|' || pet_name                         as source_pet_key,
    location                                               as location_id,
    strptime(appt_datetime, '%m/%d/%Y %I:%M %p')           as event_ts,
    strptime(appt_datetime, '%m/%d/%Y %I:%M %p')::date     as event_date,
    {{ norm_name('customer_first') }}                      as owner_first,
    {{ norm_name('customer_last') }}                       as owner_last,
    {{ digits10('customer_phone') }}                       as owner_phone,
    nullif(lower(trim(customer_email)), '')                as owner_email,
    {{ norm_name('pet_name') }}                            as pet_name,
    pet_breed                                              as breed_raw,
    service                                                as source_service,
    cast(price as double)                                  as amount,
    nullif(trim(groomer_notes), '')                        as staff_note
from read_csv('{{ var("raw_dir") }}/groomly_appointments.csv', header = true, all_varchar = true)
