-- 쇼핑몰 일일 운영 KPI mart (long: event_date × metric).
--   날짜는 모두 KST다(staging에서 바꿨다). 값이 0인 날은 그 지표의 row가 없다.
--   내부·테스트 판매자의 주문을 빼지 않는다(판매자 차원이 없다).
--   지표 code는 literal·CASE·앞 literal 이어 붙이기로만 쓴다. semantic/catalog.py가 이 SQL에서 code를 읽어
--   정의(semantic/manifest/metrics/)와 견준다. 다른 식으로 code를 만들면 검사가 "읽지 못했다"로 실패한다.
with logins as (
    select * from {{ ref('stg_logins') }}
),
orders as (
    select * from {{ ref('int_orders') }}
),
members as (
    select * from {{ ref('stg_members') }}
),
spine as (
    select day as d from {{ ref('int_calendar_days') }}
),
unioned as (
    -- 회원: 활성 회원(로그인 기준), 가입
    select login_date as event_date, 'overview' as category, 'dau' as metric, count(distinct member_id) as value
    from logins group by login_date
    union all
    select sp.d, 'overview', 'wau', count(distinct l.member_id)
    from spine sp join logins l on l.login_date between sp.d - 6 and sp.d
    group by sp.d
    union all
    select sp.d, 'overview', 'mau', count(distinct l.member_id)
    from spine sp join logins l on l.login_date between sp.d - 29 and sp.d
    group by sp.d
    union all
    select signup_date, 'overview', 'signup_count', count(*)
    from members group by signup_date
    union all
    -- 주문: 건수, 금액, 구매 회원 수
    select order_date, 'order', 'order_count', count(*)
    from orders group by order_date
    union all
    select order_date, 'order', 'order_amount_krw', sum(total_amount)
    from orders group by order_date
    union all
    select order_date, 'order', 'buyers', count(distinct member_id)
    from orders group by order_date
    union all
    -- 첫 주문과 재주문을 가른다
    select order_date, 'order', case when is_first_order then 'order_count_new' else 'order_count_repeat' end, count(*)
    from orders
    group by order_date, case when is_first_order then 'order_count_new' else 'order_count_repeat' end
    union all
    -- 결제 수단별 주문 수. 결제 수단이 늘면 code도 늘어난다(data가 만드는 code)
    select order_date, 'order', 'order_pay_' || pay_method || '_count', count(*)
    from orders
    group by order_date, pay_method
    union all
    select c.cancel_date, 'order', 'order_cancel_count', count(*)
    from {{ ref('stg_order_cancels') }} c
    group by c.cancel_date
    union all
    select r.refund_date, 'order', 'refund_krw', sum(r.refund_amount)
    from {{ ref('stg_refunds') }} r
    group by r.refund_date
    union all
    -- 배송: 그날 완료된 배송의 소요 일수 p90
    select delivered_date, 'delivery', 'delivery_days_p90', quantile_cont(delivered_date - order_date, 0.9)
    from orders
    where delivered_date is not null
    group by delivered_date
    union all
    -- 일말 스냅샷: 유효한 유료 입점 플랜 수(BASIC·PLUS만 센다. ENTERPRISE는 계약이 따로라 빠진다)
    select sp.d, 'snapshot', 'seller_plan_active_eod', count(*)
    from spine sp
    join {{ ref('stg_seller_plans') }} p
      on p.start_date <= sp.d and p.end_date > sp.d
     and p.plan_code in ('BASIC', 'PLUS')
    group by sp.d
    union all
    -- 일말 스냅샷: 탈퇴하지 않은 회원 수
    select sp.d, 'snapshot', 'member_eod', count(*)
    from spine sp
    join members m
      on m.signup_date <= sp.d
     and not m.is_deleted
    group by sp.d
)
select event_date, category, metric, cast(value as double) as value
from unioned
