-- 기준일(as_of_date)마다 판매자의 최근 30일 창을 계산한다. 기준일은 data 마지막 날과 그 1·2주 전이다.
with as_of as (
    select max(day) - (7 * w) as as_of_date
    from {{ ref('int_calendar_days') }}, (select unnest([0, 1, 2]) as w)
    group by w
),
buyer as (
    select a.as_of_date, o.seller_id, o.member_id, count(*) as orders
    from as_of a
    join {{ ref('int_orders') }} o on o.order_date between a.as_of_date - 29 and a.as_of_date
    group by all
)
select
    as_of_date,
    seller_id,
    sum(orders) as order_count_30d,
    count(*) as buyers_30d,
    count(*) filter (where orders >= 2) as repeat_buyers_30d
from buyer
group by all
