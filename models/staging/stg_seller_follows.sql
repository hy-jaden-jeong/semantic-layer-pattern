-- raw timestamp는 UTC다. 여기서 KST(Asia/Seoul, UTC+9) 일자로 바꾼다. 뒤 layer는 다시 바꾸지 않는다.
select
    member_id,
    seller_id
from {{ ref('raw_seller_follows') }}
where unfollowed_at is null
