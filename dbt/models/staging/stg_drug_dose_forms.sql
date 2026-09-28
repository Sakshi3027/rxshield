select
    drug_rxcui || '|' || related_rxcui as drug_dose_form_id,
    drug_rxcui,
    related_rxcui as dose_form_group_rxcui,
    related_name as dose_form_group_name
from {{ source('silver', 'drug_concepts') }}
where related_tty = 'SCDF'