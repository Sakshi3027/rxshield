select *
from {{ ref('mart_facility_exposure') }}
where sole_source_products > shortage_products_manufactured