-- 판매자 × 월 × 지표 사용량(long view). 가상 예제다.
--   출처(metric_source)마다 갈래 하나다. search 갈래는 gold.search_metric_monthly의 code를 그대로 넘겨받는다.
--   내부·테스트 판매자는 view 안에서 뺐다. event_month는 KST 기준 yyyy-MM 문자열이다.
CREATE OR REPLACE VIEW `dev-shop-bi-catalog`.gold.seller_usage_monthly AS
SELECT o.seller_id AS seller_id, o.event_month AS event_month, 'order' AS metric_source, 'order_count' AS metric, CAST(COUNT(*) AS DOUBLE) AS value
FROM `dev-shop-bi-catalog`.silver.fact_order o
WHERE o.seller_id NOT IN (SELECT seller_id FROM `dev-shop-bi-catalog`.ref.internal_seller_id)
GROUP BY o.seller_id, o.event_month
UNION ALL
SELECT o.seller_id, o.event_month, 'order', 'order_amount_krw', CAST(SUM(o.total_amount) AS DOUBLE)
FROM `dev-shop-bi-catalog`.silver.fact_order o
WHERE o.seller_id NOT IN (SELECT seller_id FROM `dev-shop-bi-catalog`.ref.internal_seller_id)
GROUP BY o.seller_id, o.event_month
UNION ALL
-- 그달에 주문이 하루라도 있었던 날 수. 달 안에서 이미 중복을 뺀 값이라 달을 넘어 더하지 않는다.
SELECT o.seller_id, o.event_month, 'order', 'active_days', CAST(COUNT(DISTINCT o.event_date) AS DOUBLE)
FROM `dev-shop-bi-catalog`.silver.fact_order o
WHERE o.seller_id NOT IN (SELECT seller_id FROM `dev-shop-bi-catalog`.ref.internal_seller_id)
GROUP BY o.seller_id, o.event_month
UNION ALL
-- 고객문의 건수. 사용이 아니라서 "활성 판매자"를 셀 때는 뺀다.
SELECT t.seller_id, t.event_month, 'cs', 'cs_ticket_count', CAST(COUNT(*) AS DOUBLE)
FROM `dev-shop-bi-catalog`.silver.fact_cs_ticket t
WHERE t.seller_id NOT IN (SELECT seller_id FROM `dev-shop-bi-catalog`.ref.internal_seller_id)
GROUP BY t.seller_id, t.event_month
UNION ALL
-- 상점 내 검색. code는 search_metric_monthly(ref.search_metric_rules seed)의 것을 그대로 쓴다.
SELECT ds.seller_id, s.event_month, 'search', s.metric, CAST(SUM(s.cnt) AS DOUBLE)
FROM `dev-shop-bi-catalog`.gold.search_metric_monthly s
JOIN `dev-shop-bi-catalog`.silver.dim_store ds ON ds.store_id = s.store_id
WHERE ds.seller_id NOT IN (SELECT seller_id FROM `dev-shop-bi-catalog`.ref.internal_seller_id)
GROUP BY ds.seller_id, s.event_month, s.metric;
