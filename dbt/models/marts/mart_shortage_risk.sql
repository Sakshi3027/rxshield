with drug_products as (
    select distinct pd.drug_rxcui, se.product_ndc
    from {{ ref('stg_package_drugs') }} pd
    join {{ ref('stg_shortage_events') }} se on se.package_ndc = pd.package_ndc
    where pd.drug_rxcui is not null
),

manufacturing as (
    select
        dp.drug_rxcui,
        count(distinct o.duns) as manufacturing_site_count,
        string_agg(distinct f.country, ', ' order by f.country) as manufacturing_countries
    from drug_products dp
    join {{ ref('stg_establishment_operations') }} o
        on o.product_ndc = dp.product_ndc and o.operation = 'MANUFACTURE'
    join {{ ref('stg_facilities') }} f on f.duns = o.duns
    group by dp.drug_rxcui
),

recalls as (
    select
        dp.drug_rxcui,
        count(distinct re.recall_number) as recalls_5y,
        count(distinct re.recall_number) filter (where re.is_class_1) as class_1_recalls_5y
    from drug_products dp
    join {{ ref('stg_recall_products') }} rp on rp.product_ndc = dp.product_ndc
    join {{ ref('stg_recall_events') }} re on re.recall_number = rp.recall_number
    where re.recall_initiation_date >= current_date - interval '5 years'
    group by dp.drug_rxcui
),

combined as (
    select
        s.drug_rxcui,
        s.drug_name,
        s.is_pack,
        s.has_current_shortage,
        s.alternative_status,
        s.alternative_labeler_count,
        s.generic_alternative_labeler_count,
        m.manufacturing_site_count,
        m.manufacturing_countries,
        coalesce(r.recalls_5y, 0) as recalls_5y,
        coalesce(r.class_1_recalls_5y, 0) as class_1_recalls_5y
    from {{ ref('mart_drug_supply') }} s
    left join manufacturing m on m.drug_rxcui = s.drug_rxcui
    left join recalls r on r.drug_rxcui = s.drug_rxcui
)

select
    *,
    case
        when not has_current_shortage then 'watch'
        when alternative_status = 'no_listed_alternative' then 'critical'
        when alternative_status = 'single_alternative' or manufacturing_site_count = 1 then 'high'
        else 'elevated'
    end as risk_tier,
    concat_ws('; ',
        case when alternative_status = 'no_listed_alternative' then 'no other listed source' end,
        case when alternative_status = 'single_alternative' then 'only one other listed source' end,
        case when manufacturing_site_count = 1 then 'single manufacturing site' end,
        case when class_1_recalls_5y > 0 then class_1_recalls_5y || ' Class I recall(s) in 5 years' end
    ) as risk_reasons
from combined