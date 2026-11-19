CREATE SCHEMA IF NOT EXISTS `dev-shop-bi-catalog`.silver;

-- 회원 × 단골 판매자 bridge. 회원 한 명이 판매자 여럿을 단골로 둘 수 있고, 판매자도 단골 회원이 여럿이다.
--   user_key는 검색 로그가 남기는 회원 key(로그인 id의 hash)다.
CREATE TABLE IF NOT EXISTS `dev-shop-bi-catalog`.silver.dim_member_seller (
  member_id BIGINT, seller_id BIGINT, user_key STRING
) USING delta;

INSERT OVERWRITE `dev-shop-bi-catalog`.silver.dim_member_seller
SELECT f.member_id, f.seller_id, sha2(m.login_id, 256) AS user_key
FROM `dev-shop-bi-catalog`.bronze.commerce__seller_follow f
JOIN `dev-shop-bi-catalog`.bronze.account__member m ON m.id = f.member_id
WHERE f.unfollowed_at IS NULL;
