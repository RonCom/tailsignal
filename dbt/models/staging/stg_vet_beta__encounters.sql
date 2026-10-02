-- Vet PIMS "beta": nested JSON lines; age at registration instead of DOB; weight in kg.
with src as (
    select * from read_json('{{ var("raw_dir") }}/vet_beta_encounters.jsonl', format = 'newline_delimited',
        columns = {
            encounter_id: 'VARCHAR', site: 'VARCHAR', date: 'VARCHAR',
            client: 'STRUCT(id VARCHAR, name VARCHAR, phones VARCHAR[], email VARCHAR, zip VARCHAR)',
            patient: 'STRUCT(id VARCHAR, name VARCHAR, species VARCHAR, breed VARCHAR, sex VARCHAR, age_years_at_reg INTEGER, registered VARCHAR, weight_kg DOUBLE)',
            diagnoses: 'STRUCT(code INTEGER, text VARCHAR)[]',
            charges: 'STRUCT(item VARCHAR, amount DOUBLE)[]'
        })
)
select
    'vet_beta'                                              as source_system,
    site                                                    as location_id,
    site || '|' || patient.id                               as source_pet_key,
    encounter_id                                            as source_event_id,
    strptime(date, '%m/%d/%Y')::date                        as event_date,
    {{ norm_name("split_part(client.name, ',', 2)") }}      as owner_first,
    {{ norm_name("split_part(client.name, ',', 1)") }}      as owner_last,
    {{ digits10('client.phones[1]') }}                      as owner_phone,
    nullif(lower(trim(client.email)), '')                   as owner_email,
    left(client.zip, 5)                                     as owner_zip,
    {{ norm_name('patient.name') }}                         as pet_name,
    case patient.species when 'D' then 'dog' when 'C' then 'cat' end as species,
    patient.breed                                           as breed_raw,
    patient.sex                                             as sex,
    -- only age in whole years is known: midpoint estimate
    (cast(patient.registered as date) - to_days(cast(round((patient.age_years_at_reg + 0.5) * 365.25) as integer)))::date as birth_date,
    'estimated_from_age'                                    as birth_date_precision,
    round(patient.weight_kg / 0.45359237, 1)                as weight_lb,
    cast(diagnoses[1].code as varchar)                      as dx_source_value,
    diagnoses[1].text                                       as dx_source_label,
    array_to_string(list_transform(charges, c -> c.item || ':' || c.amount), ';') as line_items,
    list_sum(list_transform(charges, c -> c.amount))        as amount
from src
