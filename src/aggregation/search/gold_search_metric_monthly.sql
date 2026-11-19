CREATE SCHEMA IF NOT EXISTS `dev-shop-bi-catalog`.gold;

-- 상점 내 검색 사용량(월 × 상점 × 검색 사용자 × 지표, long). 가상 예제다.
--   분류는 silver.search_events에서 끝났다(ref.search_metric_rules). gold는 세기만 한다.
--   검색 로그는 회원 번호가 아니라 user_key(로그인 id의 hash)를 남긴다. member_id와 더하거나 섞지 않는다.
CREATE TABLE IF NOT EXISTS `dev-shop-bi-catalog`.gold.search_metric_monthly (
  metric STRING, metric_label STRING, event_month STRING, store_id BIGINT, user_key STRING, cnt BIGINT
) USING delta PARTITIONED BY (event_month);

INSERT INTO `dev-shop-bi-catalog`.gold.search_metric_monthly REPLACE WHERE event_month = :m
SELECT metric, metric_label, event_month, store_id, user_key, COUNT(*) AS cnt
FROM `dev-shop-bi-catalog`.silver.search_events
WHERE event_month = :m
GROUP BY metric, metric_label, event_month, store_id, user_key;
