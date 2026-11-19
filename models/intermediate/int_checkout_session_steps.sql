-- 결제 퍼널 이벤트를 세션 × 단계 한 row로 모은다. 일자와 기기는 세션 첫 이벤트의 것이다.
with first_event as (
    select session_id, min(event_date) as event_date, arg_min(device_type, event_at) as device_type
    from {{ ref('stg_checkout_events') }}
    group by session_id
)
select
    f.event_date,
    s.seller_id,
    e.store_id,
    f.device_type,
    e.session_id,
    e.step_no,
    case e.step_no when 1 then '장바구니' when 2 then '주문서' when 3 then '결제 수단' else '결제 완료' end as step_label,
    count(*) filter (where e.is_retry) as retry_count
from {{ ref('stg_checkout_events') }} e
join first_event f on f.session_id = e.session_id
join {{ ref('stg_stores') }} s on s.store_id = e.store_id
group by all
