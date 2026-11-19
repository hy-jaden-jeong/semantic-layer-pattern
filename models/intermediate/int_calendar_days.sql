-- 로그인 기록이 있는 첫날부터 마지막 날까지 하루에 row 하나. rolling 지표와 일말 스냅샷의 날짜 축이다.
select cast(unnest(generate_series(b.first_day, b.last_day, interval 1 day)) as date) as day
from (select min(login_date) as first_day, max(login_date) as last_day from {{ ref('stg_logins') }}) b
