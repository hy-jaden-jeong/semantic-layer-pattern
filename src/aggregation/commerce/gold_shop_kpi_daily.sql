CREATE SCHEMA IF NOT EXISTS `dev-shop-bi-catalog`.gold;

-- 쇼핑몰 일일 운영 KPI mart (long: event_date × metric). 가상 예제다.
--   날짜는 모두 KST(Asia/Seoul). 원천 timestamp는 UTC라 from_utc_timestamp(ts, 'Asia/Seoul')로 바꿔 일자를 자른다.
--   값이 0인 날은 그 지표의 row가 없다. REPLACE WHERE 창(:d1 ~ :d2, KST)만 다시 쓴다.
--   내부·테스트 판매자의 주문을 빼지 않는다(판매자 차원이 없다).
CREATE TABLE IF NOT EXISTS `dev-shop-bi-catalog`.gold.shop_kpi_daily (
  event_date DATE, category STRING, metric STRING, value DOUBLE
) USING delta PARTITIONED BY (event_date);

INSERT INTO `dev-shop-bi-catalog`.gold.shop_kpi_daily
REPLACE WHERE event_date >= DATE(:d1) AND event_date < DATE(:d2)
WITH spine AS (SELECT explode(sequence(DATE(:d1), date_sub(DATE(:d2), 1), INTERVAL 1 DAY)) AS d),
-- 로그인 이벤트의 KST 일자(dau·wau·mau가 함께 쓴다)
login_kst AS (
  SELECT to_date(from_utc_timestamp(created_at, 'Asia/Seoul')) AS ed, member_id
  FROM `dev-shop-bi-catalog`.bronze.account__login_history
  WHERE created_at IS NOT NULL),
-- 주문의 KST 일자. is_first_order = 1이면 그 회원의 첫 주문이다.
order_kst AS (
  SELECT to_date(from_utc_timestamp(ordered_at, 'Asia/Seoul')) AS ed, order_id, member_id, total_amount,
         pay_method, is_first_order
  FROM `dev-shop-bi-catalog`.bronze.commerce__order
  WHERE ordered_at IS NOT NULL),
-- 배송 완료 건의 소요 일수(주문일 → 배송 완료일, KST)
delivery_kst AS (
  SELECT to_date(from_utc_timestamp(delivered_at, 'Asia/Seoul')) AS ed,
         datediff(to_date(from_utc_timestamp(delivered_at, 'Asia/Seoul')),
                  to_date(from_utc_timestamp(ordered_at, 'Asia/Seoul'))) AS days
  FROM `dev-shop-bi-catalog`.bronze.commerce__order
  WHERE delivered_at IS NOT NULL)
-- 회원: 활성 회원(로그인 기준), 가입
SELECT ed AS event_date, 'overview' category, 'dau' metric, COUNT(DISTINCT member_id) value
FROM login_kst GROUP BY ed
UNION ALL
SELECT sp.d, 'overview', 'wau', COUNT(DISTINCT l.member_id)
FROM spine sp JOIN login_kst l ON l.ed BETWEEN date_sub(sp.d, 6) AND sp.d
GROUP BY sp.d
UNION ALL
SELECT sp.d, 'overview', 'mau', COUNT(DISTINCT l.member_id)
FROM spine sp JOIN login_kst l ON l.ed BETWEEN date_sub(sp.d, 29) AND sp.d
GROUP BY sp.d
UNION ALL
SELECT to_date(from_utc_timestamp(m.created_at, 'Asia/Seoul')), 'overview', 'signup_count', COUNT(*)
FROM `dev-shop-bi-catalog`.bronze.account__member m
GROUP BY to_date(from_utc_timestamp(m.created_at, 'Asia/Seoul'))
UNION ALL
-- 주문: 건수, 금액, 구매 회원 수
SELECT ed, 'order', 'order_count', COUNT(*)
FROM order_kst GROUP BY ed
UNION ALL
SELECT ed, 'order', 'order_amount_krw', SUM(total_amount)
FROM order_kst GROUP BY ed
UNION ALL
SELECT ed, 'order', 'buyers', COUNT(DISTINCT member_id)
FROM order_kst GROUP BY ed
UNION ALL
-- 첫 주문과 재주문을 가른다
SELECT ed, 'order', CASE WHEN is_first_order = 1 THEN 'order_count_new' ELSE 'order_count_repeat' END, COUNT(*)
FROM order_kst
GROUP BY ed, CASE WHEN is_first_order = 1 THEN 'order_count_new' ELSE 'order_count_repeat' END
UNION ALL
-- 결제 수단별 주문 수. 결제 수단이 늘면 code도 늘어난다(data가 만드는 code).
SELECT ed, 'order', 'order_pay_' || lower(pay_method) || '_count', COUNT(*)
FROM order_kst
GROUP BY ed, lower(pay_method)
UNION ALL
SELECT to_date(from_utc_timestamp(c.canceled_at, 'Asia/Seoul')), 'order', 'order_cancel_count', COUNT(*)
FROM `dev-shop-bi-catalog`.bronze.commerce__order_cancel c
GROUP BY to_date(from_utc_timestamp(c.canceled_at, 'Asia/Seoul'))
UNION ALL
SELECT to_date(from_utc_timestamp(r.refunded_at, 'Asia/Seoul')), 'order', 'refund_krw', SUM(r.refund_amount)
FROM `dev-shop-bi-catalog`.bronze.commerce__refund r
GROUP BY to_date(from_utc_timestamp(r.refunded_at, 'Asia/Seoul'))
UNION ALL
-- 배송: 그날 완료된 배송의 소요 일수 p90
SELECT ed, 'delivery', 'delivery_days_p90', percentile_approx(days, 0.9)
FROM delivery_kst GROUP BY ed
UNION ALL
-- 일말 스냅샷: 유효한 유료 입점 플랜 수(BASIC·PLUS만 센다. ENTERPRISE는 계약이 따로라 빠진다)
SELECT sp.d, 'snapshot', 'seller_plan_active_eod', COUNT(*)
FROM spine sp
JOIN `dev-shop-bi-catalog`.bronze.billing__seller_plan p
  ON p.start_date <= sp.d AND p.end_date > sp.d
 AND p.plan_code IN ('BASIC', 'PLUS')
GROUP BY sp.d
UNION ALL
-- 일말 스냅샷: 탈퇴하지 않은 회원 수
SELECT sp.d, 'snapshot', 'member_eod', COUNT(*)
FROM spine sp
JOIN `dev-shop-bi-catalog`.bronze.account__member m
  ON to_date(from_utc_timestamp(m.created_at, 'Asia/Seoul')) <= sp.d
 AND coalesce(m.deleted_yn, 'N') <> 'Y'
GROUP BY sp.d;
