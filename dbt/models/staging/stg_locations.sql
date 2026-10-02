select location_id, channel, source_system, market, open_day
from read_csv('{{ var("raw_dir") }}/locations.csv', header = true)
