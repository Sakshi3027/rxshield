select
    package_ndc,
    {{ to_ndc11('package_ndc') }} as ndc11,
    rxcui as drug_rxcui,
    concept_name as drug_name,
    left(concept_name, 1) = '{' as is_pack,
    ndc_status
from {{ source('silver', 'package_rxcui') }}