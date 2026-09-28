select *
from {{ ref('mart_shortage_risk') }}
where risk_tier = 'critical'
  and (alternative_status <> 'no_listed_alternative' or not has_current_shortage)