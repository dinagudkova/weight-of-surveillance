{#- autoconsent reports rule names (sourcepoint-top, Sourcepoint-frame, ...); map them to platform names. -#}
{% macro normalize_cmp(col) -%}
    case
        when {{ col }} is null then null
        when lower({{ col }}) like '%sourcepoint%' then 'Sourcepoint'
        when lower({{ col }}) like '%onetrust%' then 'OneTrust'
        when lower({{ col }}) like '%usercentrics%' then 'Usercentrics'
        when lower({{ col }}) like '%consentmanager%' then 'consentmanager'
        when lower({{ col }}) like '%didomi%' then 'Didomi'
        when lower({{ col }}) like '%cookiebot%' then 'Cookiebot'
        when lower({{ col }}) like '%tealium%' then 'Tealium'
        when lower({{ col }}) like '%trustarc%' then 'TrustArc'
        when lower({{ col }}) like '%quantcast%' then 'Quantcast'
        when lower({{ col }}) like 'heuristic%' then 'Unknown (generic banner)'
        else {{ col }}
    end
{%- endmacro %}
