-- 옛 헬스스코어(월 단위, 주문 수만 본 점수). 대시보드는 seller_health_score를 읽는다. 지우기 전까지 남겨 둔다.
select event_month, seller_id, cast(least(100, count(*) * 2) as double) as score
from {{ ref('int_orders') }}
group by event_month, seller_id
