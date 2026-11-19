-- raw timestamp는 UTC다. 여기서 KST(Asia/Seoul, UTC+9) 일자로 바꾼다. 뒤 layer는 다시 바꾸지 않는다.
select
    seller_id,
    plan_code,
    cast(start_date as date) as start_date,
    cast(end_date as date) as end_date
from {{ ref('raw_seller_plans') }}
