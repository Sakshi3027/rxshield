with sites as (
    select
        f.duns,
        coalesce(f.registrant_duns, f.duns) as company_duns,
        coalesce(f.registrant_name, f.firm_name) as company_name,
        f.country
    from {{ ref('stg_facilities') }} f
    where f.duns in (select duns from {{ ref('stg_establishment_operations') }})
),

made as (
    select distinct s.company_duns, o.product_ndc
    from {{ ref('stg_establishment_operations') }} o
    join sites s on s.duns = o.duns
    join {{ ref('mart_product_manufacturing') }} pm on pm.product_ndc = o.product_ndc
    where o.operation = 'MANUFACTURE'
),

companies_per_product as (
    select product_ndc, count(*) as company_count
    from made
    group by product_ndc
),

company_products as (
    select
        m.company_duns,
        count(*) as shortage_products_manufactured,
        count(*) filter (where c.company_count = 1) as sole_company_products
    from made m
    join companies_per_product c on c.product_ndc = m.product_ndc
    group by m.company_duns
),

company_sites as (
    select
        company_duns,
        min(company_name) as company_name,
        count(*) as facility_count,
        string_agg(distinct country, ', ' order by country) as countries
    from sites
    group by company_duns
)

select
    cs.company_duns,
    cs.company_name,
    cs.facility_count,
    cs.countries,
    coalesce(cp.shortage_products_manufactured, 0) as shortage_products_manufactured,
    coalesce(cp.sole_company_products, 0) as sole_company_products
from company_sites cs
left join company_products cp on cp.company_duns = cs.company_duns