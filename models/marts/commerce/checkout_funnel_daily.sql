-- 결제 퍼널(일자 × 판매자 × 상점 × 기기 × 단계, wide).
--   세션 단위로 "그 단계에 도달한 세션 수"를 센다. 주문 건수가 아니다(건수는 shop_kpi_daily의 order_count).
--   일자는 세션 첫 이벤트의 KST 일자다. 재시도(retry) = 같은 세션이 같은 단계를 다시 요청한 것.
select
    event_date,
    seller_id,
    store_id,
    device_type,
    step_no,
    step_label,
    count(distinct session_id) as sessions,
    count(distinct case when retry_count > 0 then session_id end) as retry_sessions,
    cast(null as varchar) as store_name
from {{ ref('int_checkout_session_steps') }}
group by event_date, seller_id, store_id, device_type, step_no, step_label
