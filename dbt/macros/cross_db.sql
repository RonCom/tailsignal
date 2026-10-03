{#- Dialect shims so the same models build on DuckDB (local) and Snowflake.
    Each macro emits DuckDB SQL unless target.type is 'snowflake'. -#}

{#- Raw inputs: DuckDB reads the files in place; Snowflake reads tables loaded by
    `python -m tailsignal.snowflake load` into the RAW schema. -#}
{% macro raw_csv(file, table, delim=',', all_varchar=true) -%}
    {%- if ts_is_snowflake() -%}
        {{ source('raw', table) }}
    {%- else -%}
        read_csv('{{ var("raw_dir") }}/{{ file }}', header = true{% if delim != ',' %}, delim = '{{ delim }}'{% endif %}{% if all_varchar %}, all_varchar = true{% endif %})
    {%- endif -%}
{%- endmacro %}

{% macro parse_date(col, duck_fmt, sf_fmt) -%}
    {%- if ts_is_snowflake() -%} to_date({{ col }}, '{{ sf_fmt }}')
    {%- else -%} strptime({{ col }}, '{{ duck_fmt }}')::date {%- endif -%}
{%- endmacro %}

{% macro parse_ts(col, duck_fmt, sf_fmt) -%}
    {%- if ts_is_snowflake() -%} to_timestamp_ntz({{ col }}, '{{ sf_fmt }}')
    {%- else -%} strptime({{ col }}, '{{ duck_fmt }}') {%- endif -%}
{%- endmacro %}

{#- date_expr minus n whole days -#}
{% macro minus_days(date_expr, n) -%}
    {%- if ts_is_snowflake() -%} dateadd(day, -1 * ({{ n }}), {{ date_expr }})::date
    {%- else -%} ({{ date_expr }} - to_days({{ n }}))::date {%- endif -%}
{%- endmacro %}

{% macro plus_days(date_expr, n) -%}
    {%- if ts_is_snowflake() -%} dateadd(day, {{ n }}, {{ date_expr }})::date
    {%- else -%} ({{ date_expr }} + to_days({{ n }}))::date {%- endif -%}
{%- endmacro %}

{% macro days_between(a, b) -%}
    {%- if ts_is_snowflake() -%} datediff(day, {{ a }}, {{ b }})
    {%- else -%} date_diff('day', {{ a }}, {{ b }}) {%- endif -%}
{%- endmacro %}

{% macro arg_max(val, by) -%}
    {%- if ts_is_snowflake() -%} max_by({{ val }}, {{ by }}) {%- else -%} arg_max({{ val }}, {{ by }}) {%- endif -%}
{%- endmacro %}

{% macro arg_min(val, by) -%}
    {%- if ts_is_snowflake() -%} min_by({{ val }}, {{ by }}) {%- else -%} arg_min({{ val }}, {{ by }}) {%- endif -%}
{%- endmacro %}

{% macro count_where(cond) -%}
    {%- if ts_is_snowflake() -%} count_if({{ cond }}) {%- else -%} count(*) filter (where {{ cond }}) {%- endif -%}
{%- endmacro %}

{% macro distinct_sorted_list(col, cond=none) -%}
    {%- if ts_is_snowflake() -%}
        array_agg(distinct {% if cond %}iff({{ cond }}, {{ col }}, null){% else %}{{ col }}{% endif %}) within group (order by {% if cond %}iff({{ cond }}, {{ col }}, null){% else %}{{ col }}{% endif %})
    {%- else -%}
        list(distinct {{ col }} order by {{ col }}){% if cond %} filter (where {{ cond }}){% endif %}
    {%- endif -%}
{%- endmacro %}

{% macro empty_list() -%}
    {%- if ts_is_snowflake() -%} array_construct() {%- else -%} [] {%- endif -%}
{%- endmacro %}

{% macro sha256_hex(expr) -%}
    {%- if ts_is_snowflake() -%} sha2({{ expr }}, 256) {%- else -%} sha256({{ expr }}) {%- endif -%}
{%- endmacro %}

{#- Jaro-Winkler on a 0-1 scale (Snowflake returns an integer 0-100) -#}
{% macro jaro_winkler(a, b) -%}
    {%- if ts_is_snowflake() -%} jarowinkler_similarity({{ a }}, {{ b }}) / 100.0
    {%- else -%} jaro_winkler_similarity({{ a }}, {{ b }}) {%- endif -%}
{%- endmacro %}

{% macro first_int(col) -%}
    {%- if ts_is_snowflake() -%} try_cast(regexp_substr({{ col }}, '[0-9]+') as integer)
    {%- else -%} try_cast(regexp_extract({{ col }}, '(\d+)', 1) as integer) {%- endif -%}
{%- endmacro %}

{% macro regex_like(col, pattern) -%}
    {%- if ts_is_snowflake() -%} regexp_instr({{ col }}, '{{ pattern }}') > 0
    {%- else -%} regexp_matches({{ col }}, '{{ pattern }}') {%- endif -%}
{%- endmacro %}

{#- most frequent value, optionally among rows meeting cond; ties are arbitrary in both engines -#}
{% macro mode_where(col, cond=none) -%}
    {%- if ts_is_snowflake() -%}
        mode({% if cond %}iff({{ cond }}, {{ col }}, null){% else %}{{ col }}{% endif %})
    {%- else -%}
        mode({{ col }}){% if cond %} filter (where {{ cond }}){% endif %}
    {%- endif -%}
{%- endmacro %}

{#- true on the Snowflake target; `--vars '{sf_dialect_check: true}'` renders Snowflake SQL on any target
    so CI can parse it without a Snowflake connection -#}
{% macro ts_is_snowflake() -%}
    {{- return(target.type == 'snowflake' or var('sf_dialect_check', false)) -}}
{%- endmacro %}
