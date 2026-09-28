select
    duns,
    fei,
    firm_name,
    address,
    country_code,
    country,
    registration_expires,
    registered_operations,
    registrant_name,
    registrant_duns
from {{ source('silver', 'facilities') }}