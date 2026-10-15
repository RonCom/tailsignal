{#- Owner PII masking (Snowflake only; no-ops on DuckDB).

    Policies live in <database>.GOVERNANCE (created by snowflake/setup.sql). Only roles in
    var('pii_reader_roles') see clear values; every other role sees a masked form:
      names  -> ***
      email  -> ***@domain
      phone  -> ***-***-1234
      zip    -> 3-digit ZIP plus ** (the geography level the data products release)

    create_owner_masking_policies() runs on-run-start. mask_owner_columns() runs as a post-hook on
    every model: it reads the built relation's columns and attaches a policy to each owner_* column,
    so a new model that exposes an owner field is masked without extra config. dbt replaces tables
    and views on each build, which drops their policies; the hook re-attaches them every run. -#}

{% macro _owner_policies() -%}
    {{- return({
        'owner_first': 'mask_owner_name',
        'owner_last': 'mask_owner_name',
        'owner_name': 'mask_owner_name',
        'owner_email': 'mask_owner_email',
        'owner_phone': 'mask_owner_phone',
        'owner_zip': 'mask_owner_zip',
    }) -}}
{%- endmacro %}

{% macro _pii_reader_condition() -%}
    current_role() in ('{{ var("pii_reader_roles") | join("', '") }}')
{%- endmacro %}

{% macro create_owner_masking_policies() -%}
    {%- if execute and target.type == 'snowflake' -%}
        {%- set masked = {
            'mask_owner_name': "iff(val is null, null, '***')",
            'mask_owner_email': "regexp_replace(val, '^[^@]+', '***')",
            'mask_owner_phone': "iff(val is null, null, '***-***-' || right(val, 4))",
            'mask_owner_zip': "iff(val is null, null, left(val, 3) || '**')",
        } -%}
        {%- for name, expr in masked.items() -%}
            {%- set fq = target.database ~ '.governance.' ~ name -%}
            {%- set body = 'case when ' ~ _pii_reader_condition() ~ ' then val else ' ~ expr ~ ' end' -%}
            {% do run_query('create masking policy if not exists ' ~ fq ~ ' as (val string) returns string -> ' ~ body) %}
            {#- keep the body current if the policy already existed (it can't be replaced while attached) -#}
            {% do run_query('alter masking policy ' ~ fq ~ ' set body -> ' ~ body) %}
        {%- endfor -%}
    {%- endif -%}
{%- endmacro %}

{% macro mask_owner_columns() -%}
    {%- if execute and target.type == 'snowflake' -%}
        {%- set policies = _owner_policies() -%}
        {%- set kind = 'view' if config.get('materialized') == 'view' else 'table' -%}
        {%- for col in adapter.get_columns_in_relation(this) -%}
            {%- set policy = policies.get(col.name | lower) -%}
            {%- if policy -%}
                {% do run_query('alter ' ~ kind ~ ' ' ~ this ~ ' modify column ' ~ col.name
                                ~ ' set masking policy ' ~ target.database ~ '.governance.' ~ policy ~ ' force') %}
            {%- endif -%}
        {%- endfor -%}
    {%- endif -%}
{%- endmacro %}
