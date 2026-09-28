select
    shortage_id,
    package_ndc,
    product_ndc,
    {{ to_ndc11('package_ndc') }} as ndc11,
    generic_name_raw as generic_name,
    company_name,
    status,
    status = 'Current' as is_current,
    availability,
    shortage_reason,
    dosage_form,
    update_type,
    initial_posting_date,
    update_date,
    discontinued_date,
    snapshot_ts
from {{ source('silver', 'shortage_events') }}