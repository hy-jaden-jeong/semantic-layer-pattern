CREATE SCHEMA IF NOT EXISTS `dev-shop-bi-catalog`.gold;

-- 판매자 헬스스코어 스냅샷(기준일 × 판매자, wide). 가상 예제다.
--   기준일(as_of_date)마다 한 번 쌓인다. 질의할 때 기준일 하나를 고른다(보통 MAX).
--   tier는 코드에서 1이 가장 위험하다. 문서는 1을 최우수로 적어 방향이 다르다(확인 질문 Q-tier-direction).
--   repeat_buyer_rate의 분모는 코드에서 "최근 30일 구매 회원 수"다. 문서는 "누적 구매 회원 수"로 적는다(Q-repeat-rate-denominator).
--   내부·테스트 판매자는 여기서 뺐다.
CREATE TABLE IF NOT EXISTS `dev-shop-bi-catalog`.gold.seller_health_score (
  as_of_date DATE, seller_id BIGINT, score DOUBLE, tier INT, order_count_30d BIGINT, repeat_buyer_rate DOUBLE
) USING delta PARTITIONED BY (as_of_date);

INSERT INTO `dev-shop-bi-catalog`.gold.seller_health_score
REPLACE WHERE as_of_date = DATE(:as_of)
SELECT DATE(:as_of) AS as_of_date, w.seller_id, w.score,
       CASE WHEN w.score < 40 THEN 1 WHEN w.score < 70 THEN 2 ELSE 3 END AS tier,
       w.order_count_30d, w.repeat_buyers_30d / NULLIF(w.buyers_30d, 0) AS repeat_buyer_rate
FROM `dev-shop-bi-catalog`.silver.seller_window_30d w
WHERE w.as_of_date = DATE(:as_of)
  AND w.seller_id NOT IN (SELECT seller_id FROM `dev-shop-bi-catalog`.ref.internal_seller_id);
