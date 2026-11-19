-- 회원 × 단골 판매자 bridge. 회원 한 명이 판매자 여럿을 단골로 둘 수 있고, 판매자도 단골 회원이 여럿이다.
--   user_key는 검색 로그가 남기는 회원 key(로그인 id의 hash)다.
select f.member_id, f.seller_id, substr(md5(m.login_id), 1, 16) as user_key
from {{ ref('stg_seller_follows') }} f
join {{ ref('stg_members') }} m on m.member_id = f.member_id
