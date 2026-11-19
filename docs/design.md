# semantic layer 설계

회사 업무에서 설계한 semantic layer를 가상 도메인으로 다시 썼다. 가상 도메인은 오픈마켓이다. 판매자(seller)가 상점(store)을 열고 회원(member)이 구매한다. 정의를 담는 저장소 이름은 `shop-bi`(가상)이고, 이 repo가 그 저장소 모양을 그대로 따른다.

같이 읽을 문서
- [decisions.md](decisions.md): 결정과 이유, 버린 후보, 치르는 값
- [llm-entry.md](llm-entry.md): LLM이 들어오는 길, 두 저장소 약속, 최신 강제, 답의 모양
- [verification.md](verification.md): 검사, 망가뜨려 보는 test, 질문 eval, 검증에서 잡힌 구멍

## 푼 문제

gold table과 대시보드는 돌아가지만, 지표의 뜻은 SQL 안과 wiki 여러 곳에 흩어져 있었다.

- 같은 이름이 다른 뜻으로 쓰인다. 가상 도메인에서 "활성 회원"은 로그인한 회원, 구매한 회원, 검색한 사용자, 앱 이벤트를 남긴 회원 넷 중 하나다. "활성 판매자"도 그달 쓴 판매자인지, 유료 plan이 살아 있는 판매자인지, 상품을 올린 판매자인지 문서마다 다르다.
- wiki 원본은 owner와 최신성이 제각각이라 어느 것을 믿을지 사람이 매번 판단한다.
- 사람이든 LLM이든 새 질문에 SQL을 쓸 때마다 table·column·공통 filter(내부·테스트 판매자 제외, KST, 스냅샷 기준일)를 다시 찾아야 하고, 틀리기 쉽다.

## 목표와 하지 않을 것

- 목표: LLM agent가 skill로 들어와 정의 파일만 읽고 gold 지표를 맞게 고르고 SQL을 쓴다.
- 목표: gold 지표의 정의마다 원본(코드, wiki)과 원본의 신뢰도가 붙는다. 뜻이 다른 같은 이름은 나눠 모두 두고, 공식 정의는 owner 확인 목록으로 남긴다.
- 목표: LLM이 지표 하나에 답할 때 그 지표에 필요한 파일만 읽고, 사람이 지표 하나를 더하면 diff가 그 파일에만 생긴다.
- 하지 않을 것: 새 집계 SQL이나 새 gold table(wiki에만 있는 지표). 정의 충돌의 정본 고르기(정본은 지표의 owner 팀이 정하므로 뒤집힐 수 있다). warehouse 배포(metric view, column comment, 자연어 질의 도구는 다음 일).

## 제약

- 런타임에 관리형 커넥터나 3rd-party 도구(dbt 포함)를 쓰지 않는다. metricflow는 test 의존성으로만 쓴다.
- PII를 어느 파일에도 남기지 않는다. 판매자 이름·회원 이름 예시를 정의 파일에 넣지 않는다.
- 로컬 검사(`make ci-local`)는 오프라인이다. 네트워크·인증이 필요한 검사는 넣지 않는다.
- owner 확인은 목록으로만 남긴다. 설계자는 정의를 확정하지 않는다.

## 설계 한 문단 요약

정의의 정본은 dbt MetricFlow semantic manifest YAML이다. gold table마다 table 정의 파일 하나(`manifest/tables/`, YAML key는 표준 `semantic_model`)와 metric마다 파일 하나(`manifest/metrics/`)를 둔다. 표준에 없는 이 저장소의 뜻(rollup none, status, 원본, owner 질문, 공통 규칙 상태, metric 접두어)은 `config.meta.shop`에, 어느 표준에도 자리가 없는 것(용어 variant, entity 설명, 공통 규칙, 원본 등급, owner 질문)은 옆 파일에 둔다. LLM은 skill 저장소의 얇은 skill로 들어와 정의 폴더 README를 따라 YAML을 읽고 SQL을 직접 쓴다. metricflow는 test에서 형식 검사기로만 쓰고, 표준이 못 잡는 것은 이 저장소의 검사가 잡는다. 의존은 한 방향이다. 정의가 gold SQL을 가리키고, gold SQL과 대시보드는 semantic layer를 모른다.

원본은 Databricks SQL warehouse 위에서 돌았다. 이 문서는 그 자리를 "warehouse"로 쓴다.

## 정본 형식 3층

정의 한 건은 세 층 중 한 곳에만 산다. 아래 층일수록 표준에서 멀다.

| 층 | 담는 것 | 읽는 도구 |
|---|---|---|
| 1. MetricFlow 표준 YAML | `semantic_model`(table 위치, entity, dimension, measure), `metric`(type, type_params, filter), label, description | metricflow parser·validator, LLM |
| 2. `config.meta.shop` 확장 | 표준 칸에 붙는 이 저장소의 뜻: rollup, status, docs(원본), questions, counts, kind, unit, rules 적용 상태, metric_prefix, long table 모양 | 이 저장소의 검사, LLM |
| 3. 옆 파일 | 어느 표준에도 자리가 없는 것: 용어 → variant → metric, entity 설명·synonyms, 공통 규칙의 SQL 조각, 원본 등급, owner 질문, 정의하지 않은 table과 이유 | 이 저장소의 검사, LLM |

- 1층 YAML key는 표준 이름 그대로 쓴다(`semantic_model`, `measures`, `type_params`, `label`, `description`). 옆 파일도 같은 낱말(label, description, synonyms)을 쓴다.
- 2층은 표준이 허락하는 `config.meta` 안에만 둔다. 그래서 metricflow validator가 1·2층을 함께 읽어도 모르는 key 오류가 나지 않는다.
- 3층 파일은 `manifest/` 밖에 둔다. 안에 두면 metricflow parser가 모르는 문서로 보고 실패한다.

## 파일 구성

```
src/bi/semantic/
  README.md                                    손. 진입 절차("질문에 답하기")와 정의 쓰는 법("정의 쓰기")
  index.md                                     생성. 용어, entity 관계, table별 "읽을 파일"과 metric 표, owner 확인 목록
  manifest/                                    표준. metricflow validator가 읽는다
    project.yml                                project_configuration 하나만(time spine 없음)
    tables/<domain>/<table>.yml                semantic_model 하나. meta.shop.metric_prefix
    tables/relations/<via>.yml                 join 경로용(measure 없음, meta.shop.role: relation)
    metrics/<domain>/<table>/<metric>.yml      metric 하나. 파일 이름 = metric 이름
  glossary/<term id>.yml                       용어 하나에 파일 하나
  questions/<question id>.yml                  owner 질문 하나에 파일 하나
  entities.yml rules.yml sources.yml not_modeled.yml   한 파일 등록부. manifest/ 밖
  catalog.py checks.py render.py               SQL에서 table·code 뽑기 / 검사 / index.md 생성(--graph F는 node·edge JSON, commit 안 함)
src/bi/shop_rules.py                           exclude_internal(): 내부·테스트 판매자 제외 SQL 조각의 정본
tests/bi/semantic/test_repo_definitions.py     실제 정의 검사
tests/bi/semantic/test_semantic_layer.py       정의를 망가뜨려 보는 검사 test
tests/bi/semantic/eval/questions.yml           질문 eval 문항
scripts/semantic_eval.py                       질문 eval(pack, score)
skill/shop-data-analytics/                     얇은 skill(SKILL.md, VERSION, scripts/locate.sh, scripts/test_locate.py)
```

가상 예제 기준 table 5개, 관계 2개, metric 32개, 용어 2개, question 5개, 원본 5개다. 실제 적용에서는 table 18개, metric 약 300개였다.

| gold table | 모양 | metric 접두어 | metric |
|---|---|---|---|
| `shop_kpi_daily` | long(일자 × 지표) | `""` | dau, wau, mau, signup_count, member_eod, order_count, order_amount_krw, order_cancel_count, refund_krw, buyers, order_count_new, order_count_repeat, order_pay_count_by_method(family), delivery_days_p90, seller_plan_active_eod, order_cancel_rate |
| `checkout_funnel_daily` | wide | `funnel_` | funnel_sessions, funnel_retry_sessions |
| `search_metric_monthly` | long(code를 seed SQL이 정함) | `search_` | search_keyword_search, search_category_browse, search_filter_search, search_users(query_time) |
| `seller_usage_monthly` | long view(search_metric_monthly의 code를 물려받음) | `su_` | su_order_count, su_order_amount_krw, su_active_days, su_cs_ticket_count, su_keyword_search, su_active_sellers(query_time) |
| `seller_health_score` | wide 스냅샷 | `hs_` | hs_score, hs_tier, hs_order_count_30d, hs_repeat_buyer_rate |

관계는 둘이다. `silver.dim_store`(store → seller, many_to_one)와 `silver.dim_member_seller`(member ↔ seller, many_to_many).

## 칸 대응

이 저장소의 뜻 하나를 어느 층의 어느 칸에 적는지 정한 표다.

| 뜻 | 표준 칸 | config.meta.shop | 옆 파일 |
|---|---|---|---|
| table, 이름·설명 | node_relation(catalog는 backtick, 예: `` `dev-shop-bi-catalog` ``), label, description | defined_in, metric_prefix | |
| time·dimension | dimensions(type, time_granularity), defaults.agg_time_dimension | format, values | |
| long table의 지표 code | measure {agg: sum, expr: value} + metric filter `= '<code>'` | shape, long{key, value, inherits, seed}, grain | |
| family(prefix로 묶은 code) | metric filter `LIKE '<prefix>%<suffix>'` | | |
| rollup sum / last | agg: sum / non_additive_dimension {window_choice: max} | rollup(표준 칸과 일치 검사) | |
| rollup none | 표준 칸은 last로 두고 막음 | rollup: none | |
| query_time | measure agg: count_distinct + metric | status: query_time | |
| wide column | measure(expr: column) + metric | skip_columns | |
| kind·unit·counts·status·docs·questions | | metric의 meta | sources.yml, questions/ |
| entity 관계 | via table semantic_model의 entities | relations[{from, to, cardinality}] | |
| entity 설명·synonyms | | | entities.yml |
| 공통 규칙 적용 상태 | | rules{kst, exclude_internal, latest_snapshot} | rules.yml(SQL 조각) |
| term → variant → metric, 기본 variant | | | glossary/ |

- long table은 지표 이름이 row 값이다. 예를 들어 `dau`는 measure `shop_kpi_daily_value_distinct`에 filter `{{ Dimension('shop_kpi_daily_row__metric') }} = 'dau'`를 건 metric이다.
- family는 data가 만드는 code를 metric 하나로 덮는다. `order_pay_count_by_method`는 `LIKE 'order_pay_%_count'`로 결제 수단별 code를 모두 고른다.
- seed가 code를 정하는 long table은 `long.seed`에 seed SQL 경로를 적고, code를 넘겨받는 table은 `long.inherits`에 넘겨주는 table을 적는다. `search_metric_monthly`가 seed를 갖고 `seller_usage_monthly`가 물려받는다.
- 공통 규칙은 table마다 규칙 하나에 상태 하나를 적는다. `applied`(table이 이미 걸었다), `caller`(질의하는 쪽이 건다), `not_applied`(걸 수 없어 답에 밝힌다), `na`(해당 없음). `rules.yml`은 규칙 셋(kst, exclude_internal, latest_snapshot)과 SQL 조각을 담는다. 내부 판매자 제외 조각은 `src/bi/shop_rules.py`의 `exclude_internal()` 출력과 같아야 한다.
- 코드 원본은 줄 번호 대신 `defined_in`(gold SQL 경로)과 filter literal로 찾는다. 줄 번호는 gold SQL을 고칠 때마다 낡는다.

## status 4종과 원본 등급

metric마다 status 하나를 적는다. status는 원본 등급과 묶여 있고, 검사가 그 묶음을 지킨다.

| status | 뜻 | 반드시 있어야 하는 것 | 가상 예 |
|---|---|---|---|
| `confirmed` | A·B 등급 문서와 코드가 맞는다 | `docs`에 A·B 원본 | dau |
| `code_only` | A·B 문서가 없어 코드로만 정했다 | | order_cancel_count |
| `conflict` | 문서와 코드가 다르다. SQL은 코드(gold) 기준이다 | `questions` | seller_plan_active_eod, hs_tier |
| `query_time` | 저장된 값이 아니라 질의 때 계산한다 | `questions`, 이 metric을 가리키는 glossary variant | su_active_sellers, search_users |

`query_time`은 glossary variant가 가리킬 gold 값이 없을 때만 둔다. 두지 않으면 LLM이 매번 식을 지어내고, 마음대로 두면 새 집계가 된다.

원본(`sources.yml`)에는 등급을 붙인다.

| 등급 | 뜻 | 쓰는 법 |
|---|---|---|
| A | 정본. owner가 쓴 확정 문서이고 코드와 맞다 | confirmed 근거 |
| B | 쓸 만하다. 일부가 낡았을 수 있다 | confirmed 근거 |
| C | 참고만 한다 | 설명에만 인용 |
| D | 쓰지 않는다 | 인용하면 검사 실패 |

가상 예제의 원본은 다섯이다. wiki.metric-criteria(A), wiki.seller-health(A), wiki.pricing-plans(A), wiki.pipeline-notes(B), wiki.quarterly-report(C). 어디서도 인용하지 않는 원본은 두지 않는다. owner 칸에는 팀·역할만 적고 사람 이름은 적지 않는다.

## rollup: sum · last · none

measure마다 `meta.shop.rollup`으로 기간을 넘어 합칠 수 있는지 적는다. 표준 칸과 어긋나면 검사가 실패한다.

| rollup | 뜻 | 표준 칸 | 질문에 답할 때 | 가상 예 |
|---|---|---|---|---|
| `sum` | 기간으로 더해도 된다 | agg: sum | 기간 합을 쓴다 | order_count |
| `last` | 그 시점 잔량이다 | non_additive_dimension {window_choice: max} | 기간 마지막 날(또는 마지막 as_of_date) 값을 쓴다. 그날 row가 없으면 기간 안 가장 늦은 날 값을 쓰고 그 날짜를 밝힌다 | member_eod |
| `none` | 저장된 grain에서만 맞다 | 표준에는 자리가 없어 last처럼 두고 meta로 막는다 | 날짜·판매자를 넘어 더하지 않는다. "월 DAU"처럼 더 긴 기간을 물으면 mau·일평균 같은 다른 metric을 제안하거나 마지막 날 값임을 밝힌다 | dau |

`dau`는 그날 distinct 회원 수라 날짜를 넘어 더하면 같은 회원을 여러 번 센다. MetricFlow는 이미 집계된 distinct 값을 "어느 축으로도 더하지 않음"으로 적을 칸이 없어서, 표준 칸에는 agg: sum과 non_additive_dimension을 두고 `rollup: none`과 README 규칙으로 막는다.

## 이름 규칙

- metric = table의 `meta.shop.metric_prefix` + gold column(long table은 gold code). 접두어는 table 하나에 하나이고 그 table의 metric 전부에 붙는다. `shop_kpi_daily`만 접두어가 `""`다. 예: `hs_repeat_buyer_rate`, `su_active_sellers`, `dau`.
- family는 `<prefix><code 앞부분>_by_<무엇별>`이다. 예: `order_pay_count_by_method`.
- measure는 `<table>_<column>`(예: `shop_kpi_daily_value_distinct`), primary_entity는 `<table>_row`다.
- 검사는 metric 이름이 자기 table의 접두어로 시작하는지 본다. 실패 메시지가 제안하는 이름도 접두어를 붙이고, column이 이미 접두어로 시작하면 다시 붙이지 않는다(`su_su_` 같은 이름을 만들지 않는다).
- 접두어 낱말은 gold column에 이미 쓰는 낱말에 맞추고, 다른 table 접두어와 헷갈리지 않는 짧은 낱말로 고른다.

## graph의 node와 edge

정의 파일은 그대로 graph로 읽힌다. `render.graph()`가 node와 edge를 만들고 test가 본다. JSON 파일은 commit하지 않고 `python -m src.bi.semantic.render --graph F`로 필요할 때 만든다.

- edge는 적는 곳이 하나다. 역방향은 생성한 graph에만 보인다.
- edge 이름은 "출발 node의 무엇"으로 읽히는 명사다. 예: dau의 table은 shop_kpi_daily.
- node type은 metric, table, entity, source, question, rule, sql(gold SQL 파일), term, variant다.
- graph id는 `<type>:<id>`다. 예: `metric:dau`, `variant:active_seller.usage`.

| edge | from → to | 적는 곳 |
|---|---|---|
| table | metric → table | metric `type_params.measure`가 속한 semantic_model |
| counts | metric → entity | metric meta `counts`(distinct_count면 필수) |
| source | metric → source | metric meta `docs` |
| question | metric·term·entity → question | metric meta `questions`, glossary `question`, relations `questions` |
| entity / sql / rule / inherits_codes | table → entity / sql / rule / table | semantic_model `entities` / meta.shop `defined_in` / `rules` / `long.inherits` |
| join | entity → entity(cardinality, via, keys) | `manifest/tables/relations/<via>.yml` |
| metric / term / used_by | variant → metric / term / source | glossary variant |
| default | term → variant | glossary `default` |

edge 종류는 13개다. 용어 둘의 variant는 아래와 같다.

| 용어 | variant(굵게 = default) | 가리키는 metric |
|---|---|---|
| `active_user`(활성 회원) | **login** / purchase / search / app_event | dau·wau·mau / buyers / search_users / gold에 없음 |
| `active_seller`(활성 판매자) | **usage** / plan / listing | su_active_sellers / seller_plan_active_eod / gold에 없음 |

gold에 없는 variant는 `metrics: []`와 `not_in_gold`에 이유를 적는다. default는 agent가 답할 때 쓰는 기본값일 뿐 공식 정의가 아니다.
