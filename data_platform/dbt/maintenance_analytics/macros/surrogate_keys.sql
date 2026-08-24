{% macro generate_surrogate_key(entity_name, key_expression) -%}
    md5(
        concat(
            '{{ entity_name }}',
            '||',
            coalesce(cast({{ key_expression }} as text), '__dbt_null__')
        )
    )
{%- endmacro %}


{% macro unknown_surrogate_key() -%}
    '00000000000000000000000000000000'
{%- endmacro %}


{% macro unknown_uuid() -%}
    '00000000-0000-0000-0000-000000000000'::uuid
{%- endmacro %}


{% macro unknown_text_id() -%}
    '__UNKNOWN__'::text
{%- endmacro %}
