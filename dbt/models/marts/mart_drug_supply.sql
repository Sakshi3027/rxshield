with shortage_drugs as (
    select
        pd.drug_rxcui,
        min(pd.drug_name) as drug_name,
        bool_or(pd.is_pack) as is_pack,
        count(distinct pd.package_ndc) as shortage_package_count,
        bool_or(se.is_current) as has_current_shortage
    from {{ ref('stg_package_drugs') }} pd
    join {{ ref('stg_shortage_events') }} se on se.package_ndc = pd.package_ndc
    where pd.drug_rxcui is not null
    group by pd.drug_rxcui
),

shortage_ndc11 as (
    select distinct ndc11
    from {{ ref('stg_shortage_events') }}
),

alternative_ndcs as (
    select e.drug_rxcui, n.ndc11, n.labeler_code, e.is_brand
    from {{ ref('stg_drug_equivalents') }} e
    join {{ ref('stg_concept_ndcs') }} n on n.concept_rxcui = e.equivalent_rxcui
    where n.ndc11 not in (select ndc11 from shortage_ndc11)
)

select
    d.drug_rxcui,
    d.drug_name,
    d.is_pack,
    d.shortage_package_count,
    d.has_current_shortage,
    count(distinct a.labeler_code) as alternative_labeler_count,
    count(distinct a.labeler_code) filter (where not a.is_brand) as generic_alternative_labeler_count,
    count(distinct a.ndc11) as alternative_ndc_count,
    case
        when count(distinct a.labeler_code) = 0 then 'no_listed_alternative'
        when count(distinct a.labeler_code) = 1 then 'single_alternative'
        else 'multiple_alternatives'
    end as alternative_status
from shortage_drugs d
left join alternative_ndcs a on a.drug_rxcui = d.drug_rxcui
group by d.drug_rxcui, d.drug_name, d.is_pack, d.shortage_package_count, d.has_current_shortage