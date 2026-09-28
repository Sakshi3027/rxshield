select
    recall_number || '|' || product_ndc as recall_product_id,
    recall_number,
    product_ndc,
    bool_or(link_method = 'text') as linked_by_text,
    bool_or(link_method = 'openfda') as linked_by_openfda
from {{ source('silver', 'recall_products') }}
where product_ndc is not null
group by recall_number, product_ndc