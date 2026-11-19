-- 검색 로그를 seed(search_metric_rules)의 규칙으로 지표 code에 붙인다. 규칙에 없는 path는 빠진다.
select
    r.metric,
    r.metric_label,
    strftime(l.log_date, '%Y-%m') as event_month,
    l.store_id,
    l.user_key
from {{ ref('stg_search_logs') }} l
join {{ ref('search_metric_rules') }} r on r.path = l.path
