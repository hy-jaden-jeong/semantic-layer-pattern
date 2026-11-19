-- 옛 헬스스코어(월 단위, 주문 수만 본 점수). 대시보드는 seller_health_score를 읽는다. 지우기 전까지 남겨 둔다.
CREATE TABLE IF NOT EXISTS `dev-shop-bi-catalog`.gold.seller_health_score_legacy (
  event_month STRING, seller_id BIGINT, score DOUBLE
) USING delta;
