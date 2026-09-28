select
    shortage_id,
    therapeutic_category
from {{ source('silver', 'shortage_categories') }}