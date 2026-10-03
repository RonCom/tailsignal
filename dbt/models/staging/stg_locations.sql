select location_id, channel, source_system, market, open_day
from {{ raw_csv('locations.csv', 'locations', all_varchar=false) }}
