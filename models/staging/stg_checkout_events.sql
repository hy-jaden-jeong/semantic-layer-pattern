-- raw timestamp는 UTC다. 여기서 KST(Asia/Seoul, UTC+9) 일자로 바꾼다. 뒤 layer는 다시 바꾸지 않는다.
select
    session_id,
    store_id,
    device_type,
    step_no,
    event_at,
    cast(event_at + interval 9 hour as date) as event_date,
    is_retry = 1 as is_retry
from {{ ref('raw_checkout_events') }}
