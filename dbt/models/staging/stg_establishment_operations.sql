select distinct
    establishment_duns || '|' || product_ndc || '|' || operation as operation_id,
    establishment_duns as duns,
    product_ndc,
    operation
from {{ source('silver', 'establishment_operations') }}
where product_ndc is not null