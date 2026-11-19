format: 1
skill_min: 1

# shop-bi semantic layer 목차 (생성물, 손으로 고치지 않는다)

읽는 순서는 README.md의 "질문에 답하기"를 따른다.

## 뜻이 여럿인 용어

- **활성 판매자** (`active_seller`, 기본 `usage`, 확인 질문 Q-active-seller, 같은 말: 활성 입점사, 활성 셀러, active seller)
  - `usage` 활성 판매자(사용 기준) → su_active_sellers
  - `plan` 활성 판매자(유료 플랜 유효 기준) → seller_plan_active_eod
  - `listing` 활성 판매자(판매 중 상품 보유 기준) → mart에 없음: 상품 상태 이력이 warehouse에 적재되지 않는다.
- **활성 회원** (`active_user`, 기본 `login`, 확인 질문 Q-active-user, 같은 말: active user, 활성 사용자, 액티브 유저, DAU, WAU, MAU)
  - `login` 활성 회원(로그인 기준) → dau, wau, mau
  - `purchase` 활성 회원(구매 기준) → buyers
  - `search` 활성 회원(상점 내 검색 기준) → search_users
  - `app_event` 활성 회원(앱 이벤트 기준) → mart에 없음: 앱 분석 도구의 수치는 warehouse에 적재되지 않는다. 비로그인 사용자가 섞여 DB 기준보다 크게 나온다.

## entity와 관계(join 경로)

| from | to | cardinality | via table | 이 table의 key(같은 row에 함께 있음) |
|---|---|---|---|---|
| member | seller | many_to_many | mart.dim_member_seller | member_id, seller_id |
| search_user | seller | many_to_many | mart.dim_member_seller | user_key, seller_id |
| store | seller | many_to_one | mart.dim_store | store_id, seller_id |

## table과 metric

### checkout_funnel_daily

- table `mart.checkout_funnel_daily` · shape wide · grain ['event_date', 'seller_id', 'store_id', 'device_type', 'step_no']
- 읽을 파일: table 정의 `manifest/tables/commerce/checkout_funnel_daily.yml` + metric `manifest/metrics/commerce/checkout_funnel_daily/<metric>.yml`
- 주의할 규칙: exclude_internal=caller

| metric | 뜻 | 고르는 법 | kind | rollup | status | 세는 것 | 질문 |
|---|---|---|---|---|---|---|---|
| funnel_retry_sessions | 단계 재시도 세션 수 | `(filter 없음)` | count | sum | code_only | - | - |
| funnel_sessions | 단계 도달 세션 수 | `(filter 없음)` | count | sum | code_only | - | - |

### shop_kpi_daily

- table `mart.shop_kpi_daily` · shape long · grain ['event_date', 'metric']
- 읽을 파일: table 정의 `manifest/tables/commerce/shop_kpi_daily.yml` + metric `manifest/metrics/commerce/shop_kpi_daily/<metric>.yml`
- 주의할 규칙: exclude_internal=not_applied

| metric | 뜻 | 고르는 법 | kind | rollup | status | 세는 것 | 질문 |
|---|---|---|---|---|---|---|---|
| buyers | 구매 회원 수 | `metric = 'buyers'` | distinct_count | none | code_only | member | - |
| dau | DAU(로그인 회원 수) | `metric = 'dau'` | distinct_count | none | confirmed | member | - |
| delivery_days_p90 | 배송 소요 일수 p90 | `metric = 'delivery_days_p90'` | percentile | none | code_only | - | - |
| mau | MAU(최근 30일 로그인 회원 수) | `metric = 'mau'` | distinct_count | none | confirmed | member | - |
| member_eod | 회원 수(일말) | `metric = 'member_eod'` | count | last | code_only | - | - |
| order_amount_krw | 주문 금액 | `metric = 'order_amount_krw'` | amount | sum | confirmed | - | - |
| order_cancel_count | 주문 취소 수 | `metric = 'order_cancel_count'` | count | sum | code_only | - | - |
| order_cancel_rate | 주문 취소율 | `order_cancel_count` ÷ `order_count` | ratio | ratio | code_only | - | - |
| order_count | 주문 수 | `metric = 'order_count'` | count | sum | confirmed | - | - |
| order_count_new | 첫 주문 수 | `metric = 'order_count_new'` | count | sum | code_only | - | - |
| order_count_repeat | 재주문 수 | `metric = 'order_count_repeat'` | count | sum | code_only | - | - |
| order_pay_count_by_method | 결제 수단별 주문 수 | `metric LIKE 'order_pay_%_count'` | count | sum | code_only | - | - |
| refund_krw | 환불 금액 | `metric = 'refund_krw'` | amount | sum | code_only | - | - |
| seller_plan_active_eod | 유효 유료 입점 플랜 수(일말) | `metric = 'seller_plan_active_eod'` | count | last | conflict | - | Q-active-seller, Q-plan-scope |
| signup_count | 가입 수 | `metric = 'signup_count'` | count | sum | confirmed | - | - |
| wau | WAU(최근 7일 로그인 회원 수) | `metric = 'wau'` | distinct_count | none | confirmed | member | - |

### search_metric_monthly

- table `mart.search_metric_monthly` · shape long · grain ['event_month', 'store_id', 'user_key', 'metric']
- 읽을 파일: table 정의 `manifest/tables/search/search_metric_monthly.yml` + metric `manifest/metrics/search/search_metric_monthly/<metric>.yml`
- 주의할 규칙: exclude_internal=not_applied

| metric | 뜻 | 고르는 법 | kind | rollup | status | 세는 것 | 질문 |
|---|---|---|---|---|---|---|---|
| search_category_browse | 카테고리 탐색 건수 | `metric = 'category_browse'` | count | sum | confirmed | - | - |
| search_filter_search | 필터 검색 건수 | `metric = 'filter_search'` | count | sum | confirmed | - | - |
| search_keyword_search | 키워드 검색 건수 | `metric = 'keyword_search'` | count | sum | confirmed | - | - |
| search_users | 검색 사용자 수 | `(filter 없음)` | distinct_count | none | query_time | search_user | Q-active-user |

### seller_health_score

- table `mart.seller_health_score` · shape wide · grain ['as_of_date', 'seller_id']
- 읽을 파일: table 정의 `manifest/tables/seller/seller_health_score.yml` + metric `manifest/metrics/seller/seller_health_score/<metric>.yml`
- 주의할 규칙: latest_snapshot=caller

| metric | 뜻 | 고르는 법 | kind | rollup | status | 세는 것 | 질문 |
|---|---|---|---|---|---|---|---|
| hs_order_count_30d | 최근 30일 주문 수 | `(filter 없음)` | count | last | code_only | - | - |
| hs_repeat_buyer_rate | 재구매 회원 비율 | `(filter 없음)` | ratio | none | conflict | - | Q-repeat-rate-denominator |
| hs_score | 헬스스코어 점수 | `(filter 없음)` | score | none | confirmed | - | - |
| hs_tier | 헬스스코어 Tier | `(filter 없음)` | grade | none | conflict | - | Q-tier-direction |

### seller_usage_monthly

- table `mart.seller_usage_monthly` · shape long · grain ['seller_id', 'event_month', 'metric']
- 읽을 파일: table 정의 `manifest/tables/seller/seller_usage_monthly.yml` + metric `manifest/metrics/seller/seller_usage_monthly/<metric>.yml`
- 주의할 규칙: 없음

| metric | 뜻 | 고르는 법 | kind | rollup | status | 세는 것 | 질문 |
|---|---|---|---|---|---|---|---|
| su_active_days | 판매자 월 주문 발생 일수 | `metric = 'active_days'` | count | none | code_only | - | - |
| su_active_sellers | 사용 기록이 있는 판매자 수 | `metric_source != 'cs'` | distinct_count | none | query_time | seller | Q-active-seller |
| su_cs_ticket_count | 판매자 월 고객문의 수 | `metric = 'cs_ticket_count'` | count | sum | code_only | - | - |
| su_keyword_search | 판매자 월 키워드 검색 건수 | `metric = 'keyword_search'` | count | sum | confirmed | - | - |
| su_order_amount_krw | 판매자 월 주문 금액 | `metric = 'order_amount_krw'` | amount | sum | code_only | - | - |
| su_order_count | 판매자 월 주문 수 | `metric = 'order_count'` | count | sum | code_only | - | - |

## owner 확인 목록

| id | 물어볼 곳 | 질문 | 상태 |
|---|---|---|---|
| Q-active-seller | Sales, Product | 활성 판매자는 사용 기록이 있는 판매자인가, 유료 플랜이 유효한 판매자인가? | open |
| Q-active-user | Product | 전사 활성 회원의 공식 기준은 로그인인가, 구매인가, 앱 이벤트인가? | open |
| Q-plan-scope | Product | 유효 유료 플랜 수에 ENTERPRISE를 넣는가? | open |
| Q-repeat-rate-denominator | Sales | 재구매 회원 비율의 분모는 최근 30일 구매 회원 수인가, 누적 구매 회원 수인가? | open |
| Q-tier-direction | Sales | 헬스스코어 Tier는 1이 가장 좋은가, 가장 위험한가? | open |
