select
    spl_set_id,
    labeler_name,
    labeler_duns,
    label_effective_date
from {{ source('silver', 'spl_labels') }}