select
    drug_rxcui || '|' || equivalent_rxcui as drug_equivalent_id,
    drug_rxcui,
    equivalent_rxcui,
    equivalent_name,
    equivalent_tty = 'SBD' as is_brand
from {{ source('silver', 'drug_equivalents') }}