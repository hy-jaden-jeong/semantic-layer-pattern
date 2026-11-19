-- 상점 dimension. 상점 하나에 row 하나다. 판매자 한 곳이 상점을 여럿 열 수 있다. 닫은 상점은 뺀다.
select store_id, seller_id, opened_date
from {{ ref('stg_stores') }}
where not is_closed
