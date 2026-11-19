-- raw timestamp는 UTC다. 여기서 KST(Asia/Seoul, UTC+9) 일자로 바꾼다. 뒤 layer는 다시 바꾸지 않는다.
select
    id as store_id,
    seller_id,
    cast(opened_at + interval 9 hour as date) as opened_date,
    coalesce(closed_yn, 'N') = 'Y' as is_closed
from {{ ref('raw_stores') }}
