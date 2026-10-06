{% set cutoff = var('ml_cutoff', '2025-10-01') %}

with product_concepts as (
    select distinct on (substring(n.ndc11, 1, 9))
        substring(n.ndc11, 1, 9) as product,
        substring(n.ndc11, 1, 5) as labeler_code,
        n.concept_rxcui,
        e.equivalent_name as concept_name,
        e.is_brand
    from {{ ref('stg_concept_ndcs') }} n
    join {{ ref('stg_drug_equivalents') }} e on e.equivalent_rxcui = n.concept_rxcui
    order by substring(n.ndc11, 1, 9), n.concept_rxcui
),

first_shortage as (
    select substring(ndc11, 1, 9) as product, min(initial_posting_date) as first_posted
    from {{ ref('stg_shortage_events') }}
    group by 1
),

recalls as (
    select
        lpad(split_part(rp.product_ndc, '-', 1), 5, '0') || lpad(split_part(rp.product_ndc, '-', 2), 4, '0') as product,
        lpad(split_part(rp.product_ndc, '-', 1), 5, '0') as labeler_code,
        re.recall_number, re.recall_initiation_date, re.is_class_1,
        re.reason_cgmp or re.reason_sterility as quality_reason
    from {{ ref('stg_recall_products') }} rp
    join {{ ref('stg_recall_events') }} re on re.recall_number = rp.recall_number
    where re.recall_initiation_date < date '{{ cutoff }}'
),

product_recalls as (
    select
        product,
        count(distinct recall_number) as recalls_before,
        count(distinct recall_number) filter (where is_class_1) as class_1_recalls_before,
        count(distinct recall_number) filter (
            where recall_initiation_date >= date '{{ cutoff }}' - interval '2 years') as recalls_last_2y,
        count(distinct recall_number) filter (where quality_reason) as quality_recalls_before
    from recalls
    group by product
),

labeler_recalls as (
    select labeler_code, count(distinct recall_number) as labeler_recalls_before
    from recalls
    group by labeler_code
),

labeler_shortages as (
    select substring(product, 1, 5) as labeler_code, count(*) as labeler_prior_shortages
    from first_shortage
    where first_posted < date '{{ cutoff }}'
    group by 1
),

family_shortages as (
    select pc.concept_rxcui, count(*) as family_prior_shortages
    from product_concepts pc
    join first_shortage fs on fs.product = pc.product
    where fs.first_posted < date '{{ cutoff }}'
    group by 1
),

competition as (
    select concept_rxcui, count(distinct substring(ndc11, 1, 5)) as labelers_for_drug
    from {{ ref('stg_concept_ndcs') }}
    group by 1
)

select
    pc.product,
    pc.labeler_code,
    pc.concept_rxcui,
    pc.concept_name,
    pc.is_brand::int as is_brand,
    (pc.concept_name ilike any (array['%inject%', '%syringe%', '%cartridge%']))::int as is_injectable,
    coalesce(pr.recalls_before, 0) as recalls_before,
    coalesce(pr.class_1_recalls_before, 0) as class_1_recalls_before,
    coalesce(pr.recalls_last_2y, 0) as recalls_last_2y,
    coalesce(pr.quality_recalls_before, 0) as quality_recalls_before,
    coalesce(lr.labeler_recalls_before, 0) as labeler_recalls_before,
    coalesce(ls.labeler_prior_shortages, 0) as labeler_prior_shortages,
    coalesce(fam.family_prior_shortages, 0) as family_prior_shortages,
    coalesce(c.labelers_for_drug, 1) as labelers_for_drug,
    fs.first_posted,
    case when fs.first_posted >= date '{{ cutoff }}'
              and fs.first_posted < date '{{ cutoff }}' + interval '1 year' then 1 else 0 end as label
from product_concepts pc
left join first_shortage fs on fs.product = pc.product
left join product_recalls pr on pr.product = pc.product
left join labeler_recalls lr on lr.labeler_code = pc.labeler_code
left join labeler_shortages ls on ls.labeler_code = pc.labeler_code
left join family_shortages fam on fam.concept_rxcui = pc.concept_rxcui
left join competition c on c.concept_rxcui = pc.concept_rxcui
where fs.first_posted is null or fs.first_posted >= date '{{ cutoff }}'