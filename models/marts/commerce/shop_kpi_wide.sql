{{ config(materialized='view') }}
-- shop_kpi_daily를 일자 × 지표 column으로 펼친 view. 시트로 내보낼 때만 쓴다. 뜻은 shop_kpi_daily를 따른다.
select
    event_date,
    max(case when metric = 'dau' then value end) as dau,
    max(case when metric = 'order_count' then value end) as order_count,
    max(case when metric = 'order_amount_krw' then value end) as order_amount_krw
from {{ ref('shop_kpi_daily') }}
group by event_date
