{#- 내부·테스트 판매자를 빼는 predicate. id_col은 seller_id column 참조식(예: 'o.seller_id').
    semantic/rules.yml의 exclude_internal SQL 조각은 이 macro의 출력과 같아야 한다(semantic/checks.py가 견준다). -#}
{% macro exclude_internal(id_col) -%}
{{ id_col }} NOT IN (SELECT seller_id FROM {{ ref('internal_seller_ids') }})
{%- endmacro %}
