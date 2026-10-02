-- All vet visits from the three practice-management systems in one schema,
-- with diagnoses mapped to the canonical condition taxonomy.
with unioned as (
    {% for m in ['stg_vet_alpha__visits', 'stg_vet_beta__encounters', 'stg_vet_gamma__visits'] %}
    select source_system, location_id, source_pet_key, source_event_id, event_date, dx_source_value,
           dx_source_label, line_items, amount
    from {{ ref(m) }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)
select
    u.*,
    coalesce(t.condition, 'unmapped')     as condition,
    t.body_system
from unioned u
left join {{ ref('dx_taxonomy') }} t
    on t.source_system = u.source_system and t.source_value = u.dx_source_value
