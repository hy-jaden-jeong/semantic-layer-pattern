-- 판매자 헬스스코어 스냅샷(기준일 × 판매자, wide).
--   기준일(as_of_date)마다 쌓인다. 질의할 때 기준일 하나를 고른다(보통 MAX).
--   tier는 코드에서 1이 가장 위험하다. 문서는 1을 최우수로 적어 방향이 다르다(확인 질문 Q-tier-direction).
--   repeat_buyer_rate의 분모는 코드에서 "최근 30일 구매 회원 수"다. 문서는 "누적 구매 회원 수"로 적는다(Q-repeat-rate-denominator).
--   내부·테스트 판매자는 여기서 뺐다.
with scored as (
    select
        as_of_date,
        seller_id,
        order_count_30d,
        repeat_buyers_30d / nullif(buyers_30d, 0) as repeat_buyer_rate,
        least(100, order_count_30d * 0.6 + 60 * repeat_buyers_30d / nullif(buyers_30d, 0)) as score
    from {{ ref('int_seller_window_30d') }}
    where {{ exclude_internal('seller_id') }}
)
select
    as_of_date,
    seller_id,
    cast(round(score, 1) as double) as score,
    cast(case when score < 40 then 1 when score < 70 then 2 else 3 end as bigint) as tier,
    cast(order_count_30d as bigint) as order_count_30d,
    cast(repeat_buyer_rate as double) as repeat_buyer_rate
from scored
