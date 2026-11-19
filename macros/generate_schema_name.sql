{#- custom schema를 target schema 뒤에 붙이지 않고 그대로 쓴다(main_mart가 아니라 mart). -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
