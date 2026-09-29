select distinct
    se.product_ndc || '|' || sp.spl_set_id as product_label_id,
    se.product_ndc,
    sp.spl_set_id
from {{ source('silver', 'shortage_products') }} sp
join {{ ref('stg_shortage_events') }} se on se.shortage_id = sp.shortage_id
where sp.spl_set_id is not null