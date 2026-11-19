-- raw timestamp는 UTC다. 여기서 KST(Asia/Seoul, UTC+9) 일자로 바꾼다. 뒤 layer는 다시 바꾸지 않는다.
select
    id as order_id,
    member_id,
    store_id,
    ordered_at,
    cast(ordered_at + interval 9 hour as date) as order_date,
    cast(delivered_at + interval 9 hour as date) as delivered_date,
    total_amount,
    lower(pay_method) as pay_method
from {{ ref('raw_orders') }}
where ordered_at is not null
