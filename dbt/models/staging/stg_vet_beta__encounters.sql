-- Vet PIMS "beta": nested JSON lines; age at registration instead of DOB; weight in kg.
{% if ts_is_snowflake() %}
-- Snowflake: each JSON line is one VARIANT row in RAW.VET_BETA_ENCOUNTERS (column V).
with src as (
    select v from {{ source('raw', 'vet_beta_encounters') }}
), charges as (
    select s.v:encounter_id::varchar as encounter_id,
           array_to_string(array_agg(c.value:item::varchar || ':' || {{ money_text('c.value:amount::double') }}) within group (order by c.index), ';') as line_items,
           sum(c.value:amount::double) as amount
    from src s, lateral flatten(input => s.v:charges) c
    group by 1
)
select
    'vet_beta'                                              as source_system,
    s.v:site::varchar                                       as location_id,
    s.v:site::varchar || '|' || s.v:patient.id::varchar     as source_pet_key,
    s.v:encounter_id::varchar                               as source_event_id,
    {{ parse_date('s.v:date::varchar', '%m/%d/%Y', 'MM/DD/YYYY') }} as event_date,
    {{ norm_name("split_part(s.v:client.name::varchar, ',', 2)") }} as owner_first,
    {{ norm_name("split_part(s.v:client.name::varchar, ',', 1)") }} as owner_last,
    {{ digits10('s.v:client.phones[0]::varchar') }}         as owner_phone,
    nullif(lower(trim(s.v:client.email::varchar)), '')      as owner_email,
    left(s.v:client.zip::varchar, 5)                        as owner_zip,
    {{ norm_name('s.v:patient.name::varchar') }}            as pet_name,
    case s.v:patient.species::varchar when 'D' then 'dog' when 'C' then 'cat' end as species,
    s.v:patient.breed::varchar                              as breed_raw,
    s.v:patient.sex::varchar                                as sex,
    -- only age in whole years is known: midpoint estimate
    {{ minus_days('cast(s.v:patient.registered::varchar as date)', 'cast(round((s.v:patient.age_years_at_reg::integer + 0.5) * 365.25) as integer)') }} as birth_date,
    'estimated_from_age'                                    as birth_date_precision,
    round(s.v:patient.weight_kg::double / 0.45359237, 1)    as weight_lb,
    s.v:diagnoses[0].code::varchar                          as dx_source_value,
    s.v:diagnoses[0].text::varchar                          as dx_source_label,
    c.line_items,
    c.amount
from src s
left join charges c on c.encounter_id = s.v:encounter_id::varchar
{% else %}
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
    {{ parse_date('date', '%m/%d/%Y', 'MM/DD/YYYY') }} as event_date,
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
    array_to_string(list_transform(charges, c -> c.item || ':' || {{ money_text('c.amount') }}), ';') as line_items,
    list_sum(list_transform(charges, c -> c.amount))        as amount
from src
{% endif %}
