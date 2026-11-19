-- 주문에 판매자와 "그 회원의 첫 주문인가"를 붙인다.
select
    o.order_id,
    o.member_id,
    o.store_id,
    s.seller_id,
    o.order_date,
    strftime(o.order_date, '%Y-%m') as event_month,
    o.delivered_date,
    o.total_amount,
    o.pay_method,
    row_number() over (partition by o.member_id order by o.ordered_at, o.order_id) = 1 as is_first_order
from {{ ref('stg_orders') }} o
join {{ ref('stg_stores') }} s on s.store_id = o.store_id
