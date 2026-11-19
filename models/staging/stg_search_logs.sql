-- raw timestamp는 UTC다. 여기서 KST(Asia/Seoul, UTC+9) 일자로 바꾼다. 뒤 layer는 다시 바꾸지 않는다.
select
    cast(logged_at + interval 9 hour as date) as log_date,
    store_id,
    user_key,
    path
from {{ ref('raw_search_logs') }}
