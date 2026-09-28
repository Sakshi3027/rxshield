select
    drug_rxcui || '|' || related_rxcui as drug_ingredient_id,
    drug_rxcui,
    related_rxcui as ingredient_rxcui,
    related_name as ingredient_name
from {{ source('silver', 'drug_concepts') }}
where related_tty = 'IN'