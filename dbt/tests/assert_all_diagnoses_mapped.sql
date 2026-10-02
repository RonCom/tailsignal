-- Fails if any vet visit diagnosis did not map to the condition taxonomy.
select source_system, dx_source_value, dx_source_label, count(*) as n
from {{ ref('int_vet_visits') }}
where condition = 'unmapped'
group by all
