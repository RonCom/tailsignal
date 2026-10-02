select location_id, channel, source_system, market,
       date '2022-01-01' + to_days(cast(open_day as integer)) as opened_on
from {{ ref('stg_locations') }}
