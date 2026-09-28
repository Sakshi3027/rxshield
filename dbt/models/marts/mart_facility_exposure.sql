with site_products as (
    select distinct duns, product_ndc
    from {{ ref('stg_establishment_operations') }}
    where operation = 'MANUFACTURE'
),

shortage_site_products as (
    select s.duns, s.product_ndc, pm.sourcing_status, pm.has_current_shortage
    from site_products s
    join {{ ref('mart_product_manufacturing') }} pm on pm.product_ndc = s.product_ndc
),

product_recalls as (
    select
        rp.product_ndc,
        count(*) as recall_count,
        count(*) filter (where re.is_class_1) as class_1_recall_count
    from {{ ref('stg_recall_products') }} rp
    join {{ ref('stg_recall_events') }} re on re.recall_number = rp.recall_number
    group by rp.product_ndc
)

select
    f.duns,
    f.fei,
    f.firm_name,
    f.country,
    f.country_code,
    count(distinct s.product_ndc) as shortage_products_manufactured,
    count(distinct s.product_ndc) filter (where s.sourcing_status = 'single_site') as sole_source_products,
    count(distinct s.product_ndc) filter (where s.has_current_shortage) as current_shortage_products,
    coalesce(sum(r.recall_count), 0) as recalls_on_products_made_here,
    coalesce(sum(r.class_1_recall_count), 0) as class_1_recalls_on_products_made_here
from shortage_site_products s
join {{ ref('stg_facilities') }} f on f.duns = s.duns
left join product_recalls r on r.product_ndc = s.product_ndc
group by f.duns, f.fei, f.firm_name, f.country, f.country_code