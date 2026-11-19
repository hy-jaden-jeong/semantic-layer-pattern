-- raw timestamp는 UTC다. 여기서 KST(Asia/Seoul, UTC+9) 일자로 바꾼다. 뒤 layer는 다시 바꾸지 않는다.
select
    id as ticket_id,
    seller_id,
    cast(created_at + interval 9 hour as date) as ticket_date
from {{ ref('raw_cs_tickets') }}
