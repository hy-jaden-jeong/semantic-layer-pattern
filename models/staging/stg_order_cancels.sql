-- raw timestamp는 UTC다. 여기서 KST(Asia/Seoul, UTC+9) 일자로 바꾼다. 뒤 layer는 다시 바꾸지 않는다.
select
    order_id,
    cast(canceled_at + interval 9 hour as date) as cancel_date
from {{ ref('raw_order_cancels') }}
