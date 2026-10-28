{#- Median that works on both engines: DuckDB has median(), PostgreSQL needs percentile_cont. -#}
{% macro median(expr) -%}
    {{ return(adapter.dispatch('median', 'wos')(expr)) }}
{%- endmacro %}

{% macro default__median(expr) -%}
    percentile_cont(0.5) within group (order by {{ expr }})
{%- endmacro %}

{% macro duckdb__median(expr) -%}
    median({{ expr }})
{%- endmacro %}
