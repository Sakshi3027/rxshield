with shortage_products as (
    select
        product_ndc,
        min(generic_name) as generic_name,
        min(company_name) as company_name,
        bool_or(is_current) as has_current_shortage
    from {{ ref('stg_shortage_events') }}
    group by product_ndc
),

manufacturing as (
    select o.product_ndc, o.duns, f.country
    from {{ ref('stg_establishment_operations') }} o
    join {{ ref('stg_facilities') }} f on f.duns = o.duns
    where o.operation = 'MANUFACTURE'
)

select
    p.product_ndc,
    p.generic_name,
    p.company_name,
    p.has_current_shortage,
    count(distinct m.duns) as manufacturing_site_count,
    count(distinct m.country) as manufacturing_country_count,
    string_agg(distinct m.country, ', ' order by m.country) as manufacturing_countries,
    case
        when count(distinct m.duns) = 0 then 'unknown'
        when count(distinct m.duns) = 1 then 'single_site'
        else 'multi_site'
    end as sourcing_status
from shortage_products p
left join manufacturing m on m.product_ndc = p.product_ndc
group by p.product_ndc, p.generic_name, p.company_name, p.has_current_shortage