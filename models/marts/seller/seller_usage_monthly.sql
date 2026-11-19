{{ config(materialized='view') }}
-- 판매자 × 월 × 지표 사용량(long view).
--   출처(metric_source)마다 갈래 하나다. search 갈래는 search_metric_monthly의 code를 그대로 넘겨받는다.
--   내부·테스트 판매자는 여기서 뺐다. event_month는 KST 기준 yyyy-MM 문자열이다.
with orders as (
    select * from {{ ref('int_orders') }}
    where {{ exclude_internal('seller_id') }}
),
tickets as (
    select seller_id, strftime(ticket_date, '%Y-%m') as event_month
    from {{ ref('stg_cs_tickets') }}
    where {{ exclude_internal('seller_id') }}
),
unioned as (
    select seller_id, event_month, 'order' as metric_source, 'order_count' as metric, count(*) as value
    from orders
    group by seller_id, event_month
    union all
    select seller_id, event_month, 'order', 'order_amount_krw', sum(total_amount)
    from orders
    group by seller_id, event_month
    union all
    -- 그달에 주문이 하루라도 있었던 날 수. 달 안에서 이미 중복을 뺀 값이라 달을 넘어 더하지 않는다
    select seller_id, event_month, 'order', 'active_days', count(distinct order_date)
    from orders
    group by seller_id, event_month
    union all
    -- 고객문의 건수. 사용이 아니라서 "활성 판매자"를 셀 때는 뺀다
    select seller_id, event_month, 'cs', 'cs_ticket_count', count(*)
    from tickets
    group by seller_id, event_month
    union all
    -- 상점 내 검색. code는 search_metric_monthly(seed search_metric_rules)의 것을 그대로 쓴다
    select d.seller_id, s.event_month, 'search', s.metric, sum(s.cnt)
    from {{ ref('search_metric_monthly') }} s
    join {{ ref('dim_store') }} d on d.store_id = s.store_id
    where {{ exclude_internal('d.seller_id') }}
    group by d.seller_id, s.event_month, s.metric
)
select seller_id, event_month, metric_source, metric, cast(value as double) as value
from unioned
