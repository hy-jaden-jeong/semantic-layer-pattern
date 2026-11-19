CREATE SCHEMA IF NOT EXISTS `dev-shop-bi-catalog`.ref;

-- 내부·테스트 판매자 목록. 새 내부 판매자는 손으로 더한다. src/bi/shop_rules.py가 이 table로 내부 판매자를 뺀다.
CREATE TABLE IF NOT EXISTS `dev-shop-bi-catalog`.ref.internal_seller_id (
  seller_id BIGINT, note STRING
) USING delta;
