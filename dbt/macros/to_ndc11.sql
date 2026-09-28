{% macro to_ndc11(column) %}
    lpad(split_part({{ column }}, '-', 1), 5, '0')
    || lpad(split_part({{ column }}, '-', 2), 4, '0')
    || lpad(split_part({{ column }}, '-', 3), 2, '0')
{% endmacro %}