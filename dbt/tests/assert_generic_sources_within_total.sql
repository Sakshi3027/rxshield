select *
from {{ ref('mart_drug_supply') }}
where generic_alternative_labeler_count > alternative_labeler_count