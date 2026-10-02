-- Fails if any product table exposes a column that looks like a direct identifier.
select table_name, column_name
from information_schema.columns
where table_schema = 'product'
  and regexp_matches(lower(column_name), '(owner|phone|email|first|last|street|address|pet_name|pet_id|^zip$)')
