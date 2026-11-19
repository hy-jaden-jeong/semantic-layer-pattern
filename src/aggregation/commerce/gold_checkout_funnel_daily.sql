CREATE SCHEMA IF NOT EXISTS `dev-shop-bi-catalog`.gold;

-- 결제 퍼널(일자 × 판매자 × 상점 × 기기 × 단계, wide). 가상 예제다.
--   세션 단위로 "그 단계에 도달한 세션 수"를 센다. 주문 건수가 아니다(건수는 shop_kpi_daily의 order_count).
--   일자는 세션 첫 이벤트의 KST 일자다. 세션이 자정을 넘겨도 시작일에 붙는다.
--   재시도(retry) = 같은 세션이 같은 단계를 다시 요청한 것.
CREATE TABLE IF NOT EXISTS `dev-shop-bi-catalog`.gold.checkout_funnel_daily (
  event_date DATE COMMENT '세션 시작 일자(KST).',
  seller_id BIGINT COMMENT '세션이 일어난 상점의 판매자 id.',
  store_id BIGINT COMMENT '세션이 일어난 상점 id.',
  device_type STRING COMMENT '세션 첫 이벤트의 기기: APP | MOBILE_WEB | PC_WEB.',
  step_no INT COMMENT '단계 순번(1 장바구니, 2 주문서, 3 결제 수단, 4 결제 완료).',
  step_label STRING COMMENT '단계 이름.',
  sessions BIGINT COMMENT '그 단계에 도달한 세션 수(세션 중복 제거).',
  retry_sessions BIGINT COMMENT '그 단계를 다시 요청한 세션 수.',
  store_name STRING COMMENT '옛 대시보드 호환 column. 이름을 수집하지 않아 늘 NULL이다.'
) USING delta PARTITIONED BY (event_date);

INSERT INTO `dev-shop-bi-catalog`.gold.checkout_funnel_daily
REPLACE WHERE event_date >= DATE(:d1) AND event_date < DATE(:d2)
SELECT s.event_date, s.seller_id, s.store_id, s.device_type, s.step_no, s.step_label,
       COUNT(DISTINCT s.session_id) AS sessions,
       COUNT(DISTINCT CASE WHEN s.retry_count > 0 THEN s.session_id END) AS retry_sessions,
       CAST(NULL AS STRING) AS store_name
FROM `dev-shop-bi-catalog`.silver.checkout_session_steps s
WHERE s.event_date >= DATE(:d1) AND s.event_date < DATE(:d2)
GROUP BY s.event_date, s.seller_id, s.store_id, s.device_type, s.step_no, s.step_label;
