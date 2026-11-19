-- 상점 내 검색 사용량(월 × 상점 × 검색 사용자 × 지표, long).
--   분류는 int_search_events에서 끝났다(seed search_metric_rules). mart는 세기만 한다.
--   검색 로그는 회원 번호가 아니라 user_key(로그인 id의 hash)를 남긴다. member_id와 더하거나 섞지 않는다.
select metric, metric_label, event_month, store_id, user_key, count(*) as cnt
from {{ ref('int_search_events') }}
group by metric, metric_label, event_month, store_id, user_key
