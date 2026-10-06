select *
from {{ ref('ml_product_features') }}
where first_posted < date '{{ var("ml_cutoff", "2025-10-01") }}'