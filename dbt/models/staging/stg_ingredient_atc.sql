select
    ingredient_rxcui || '|' || atc_code as ingredient_atc_id,
    ingredient_rxcui,
    ingredient_name,
    atc_code,
    atc_name,
    atc3_code
from {{ source('silver', 'ingredient_atc') }}