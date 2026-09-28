select
    package_ndc,
    {{ to_ndc11('package_ndc') }} as ndc11,
    rxcui as drug_rxcui,
    concept_name as drug_name,
    ndc_status
from {{ source('silver', 'package_rxcui') }}