select location_id, channel, source_system, market,
       {{ plus_days("date '2022-01-01'", 'cast(open_day as integer)') }} as opened_on
from {{ ref('stg_locations') }}
