CREATE SCHEMA IF NOT EXISTS `dev-shop-bi-catalog`.silver;

-- 상점 dimension. 상점 하나에 row 하나다. 판매자 한 곳이 상점을 여럿 열 수 있다.
CREATE TABLE IF NOT EXISTS `dev-shop-bi-catalog`.silver.dim_store (
  store_id BIGINT, seller_id BIGINT, opened_date DATE
) USING delta;

INSERT OVERWRITE `dev-shop-bi-catalog`.silver.dim_store
SELECT s.id AS store_id, s.seller_id, to_date(from_utc_timestamp(s.opened_at, 'Asia/Seoul')) AS opened_date
FROM `dev-shop-bi-catalog`.bronze.commerce__store s
WHERE coalesce(s.closed_yn, 'N') <> 'Y';
