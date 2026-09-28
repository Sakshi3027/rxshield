select
    rxcui || '|' || ndc11 as concept_ndc_id,
    rxcui as concept_rxcui,
    ndc11,
    labeler_code
from {{ source('silver', 'concept_ndcs') }}