{% macro digits10(col) -%}
    nullif(right(regexp_replace(coalesce({{ col }}, ''), '[^0-9]', '', 'g'), 10), '')
{%- endmacro %}

{% macro norm_name(col) -%}
    nullif(upper(trim(regexp_replace(coalesce({{ col }}, ''), '[^A-Za-z ]', '', 'g'))), '')
{%- endmacro %}

{% macro norm_key(col) -%}
    nullif(lower(regexp_replace(coalesce({{ col }}, ''), '[^A-Za-z0-9]', '', 'g')), '')
{%- endmacro %}

{# use custom schema names as-is (staging, core, ...) rather than prefixing target schema #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name else target.schema }}
{%- endmacro %}
