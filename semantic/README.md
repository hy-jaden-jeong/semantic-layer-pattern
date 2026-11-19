# shop-bi semantic layer

shop-bi(dbt project)의 mart 지표가 무슨 뜻이고 어떻게 쓰는지 적은 정의 폴더다. 형식은 MetricFlow semantic manifest YAML이고, 표준에 없는 뜻은 `config.meta.shop`과 옆 파일에 있다. dbt는 이 폴더를 읽지 않는다(model-paths 밖이다).
지표로 분석하는 LLM은 `shop-data-analytics` skill로 들어와 아래 "질문에 답하기"를 따른다. 정의를 고칠 때는 사람이든 LLM이든 아래 "정의 쓰기"를 따른다. 설계와 결정: `docs/design.md`, `docs/decisions.md`.

| 파일 | 담는 것 |
|---|---|
| `index.md` | 목차(생성물). 용어, entity 관계, table별 metric 한 줄씩, owner 확인 목록 |
| `manifest/tables/<domain>/<table>.yml` | table 정의: mart model 하나(YAML key는 MetricFlow 표준 `semantic_model`). table 위치, entity, dimension, measure, `meta.shop.metric_prefix` |
| `manifest/metrics/<domain>/<table>/<metric>.yml` | metric 하나. 파일 이름이 metric 이름이고, 이름은 그 table의 `metric_prefix` + mart column(long table은 지표 code)이다 |
| `manifest/tables/relations/*.yml` | join 경로(entity 관계). measure 없음 |
| `manifest/project.yml` | MetricFlow project 설정(문서 하나). 다른 정의를 두지 않는다 |
| `glossary/<term id>.yml` | 뜻이 여럿인 용어 하나 → variant → metric. `default`는 agent 기본값이다(공식 정의 아님). mart에 없는 뜻은 `metrics: []`와 `not_in_mart`에 이유 |
| `entities.yml` | 세는 단위(member, seller …)와 key |
| `rules.yml` | 공통 규칙(KST, 내부 판매자 제외, 스냅샷 기준일)과 SQL 조각 |
| `sources.yml` | 정의 원본과 신뢰도 등급(A~D) |
| `questions/<question id>.yml` | owner에게 확인할 질문 하나. `state: open`, 답을 받으면 `answered`와 `answer`·`answered_on`을 적고 정의를 고친다 |
| `not_modeled.yml` | 정의를 두지 않은 mart model과 이유 |
| `settings.py` · `catalog.py` · `checks.py` · `render.py` | 옮겨 쓸 때 바꾸는 값 / dbt project 파일에서 relation·column·지표 code 뽑기 / 검사 / `index.md` 생성 |

## 질문에 답하기

1. `index.md`를 읽는다. 질문의 말이 "뜻이 여럿인 용어"에 있으면 `glossary/<term id>.yml`에서 variant를 고른다. 질문이 기준을 말하지 않으면 `default` variant를 쓴다. 질문의 말이 용어의 synonyms(예: DAU)에 있으면 그 용어로 보고 그 metric을 가리키는 variant를 적는다. 어느 용어에도 없는 지표 이름(예: "유효 유료 입점 플랜 수")을 바로 물으면 variant는 `없음`이다.
2. `index.md`가 그 table 절의 "읽을 파일"에 적은 두 파일을 연다: table 정의 파일(`manifest/tables/…`)과 metric 파일(`manifest/metrics/<domain>/<table>/<metric>.yml`). 아래를 읽는다.
   - table: `node_relation`의 `schema_name.alias`(예: `mart.shop_kpi_daily`)
   - long model(`meta.shop.shape: long`): 지표 이름이 row 값이다. metric의 `filter`가 고르는 code로 `WHERE <key> = '<code>'`를 쓴다. family(`LIKE`)는 prefix로 고르고 code별로 묶어 보인다.
   - wide model: measure의 `expr` column을 쓴다.
   - query_time metric: measure의 `agg`·`expr`(예: `COUNT(DISTINCT ...)`)을 질의 때 계산한다.
3. 합산 규칙(measure의 `meta.shop.rollup`)을 지킨다.
   - `sum`: 기간으로 더해도 된다.
   - `last`: 기간을 물으면 그 기간 마지막 날(또는 마지막 as_of_date)의 값을 쓴다. 그날 row가 없으면 기간 안의 가장 늦은 날 값을 쓰고 그 날짜를 밝힌다. 한 날을 물었는데 그날이 table의 마지막 날짜보다 뒤면 값이 없다고 답한다. 그 안의 날인데 row가 없으면 아래 4번의 "row가 없는 날" 규칙을 따른다.
   - `none`: 저장된 grain(하루, 한 달, 한 판매자)에서만 맞다. 날짜·판매자를 넘어 더하지 않는다. "월 DAU"처럼 더 긴 기간을 물으면 더하지 말고 MAU·일평균 같은 다른 metric을 제안하거나, 기간 마지막 날 값임을 밝힌다. 일평균은 기간 합을 기간의 달력 일수로 나눈다(row가 없는 날은 0이라 row 수로 나누지 않는다). 기간이 table의 마지막 날짜를 넘으면 그날까지의 일수로 나누고 밝힌다.
4. 공통 규칙(model의 `meta.shop.rules`)을 본다.
   - `caller`: 질의하는 쪽이 건다. SQL 조각은 `rules.yml`에 있다.
   - `not_applied`: 걸 수 없다. 답에 "내부·테스트 판매자의 주문이 섞여 있다"처럼 밝힌다.
   - `latest_snapshot: caller`: as_of_date 하나를 고른다(기본은 MAX).
   - long model은 값이 0인 날·달의 row가 빠질 수 있다(`shop_kpi_daily`는 빠진다). row가 없는 날은 0으로 본다. 데이터가 어디까지 들어왔는지는 그 metric의 마지막 row가 아니라 table의 마지막 날짜(`MAX(event_date)` 등)로 정한다. 그날까지 row가 없으면 0건이다. 예외: metric의 `caveats`가 측정이 안 되는 기간(원천 결측, 경로 변경 등)을 적었으면 그 기간의 row 없음을 0으로 보지 않고 "측정 안 됨"이라 답한다.
   - 날짜는 이미 KST다(staging model이 바꿨다). dimension의 `meta.shop.format`이 `yyyy-MM`인 month column은 문자열이라 `'2026-10'`처럼 문자열로 비교한다.
5. 다른 table과 이어야 하면 `index.md`의 "entity와 관계"에서 via table과 key를 찾는다. 관계 표에 없는 join은 하지 말고 없다고 답한다.
6. 답의 SQL·표·장표에 보인 column은 모두 쓴 metric이다(예: 점수 순위를 보이며 함께 낸 tier는 `hs_tier`). 보조로 보인 column도 기준 block의 metrics에 넣고 그 status를 밝힌다. `conflict`인 metric은 뜻(예: 재구매 회원 비율의 분모가 최근 30일인지 누적인지)을 사실처럼 쓰지 않고 "코드 기준"이라고 붙인다.
7. status를 보고 답에 밝힌다. `confirmed`가 아니면 그 뜻을 사람 말로 적는다: `code_only`는 "문서 정의 없이 코드로만 정한 지표", `conflict`는 "문서와 코드가 달라 코드 기준으로 셌다"(SQL은 코드(mart) 기준이다), `query_time`은 "저장된 값이 아니라 질의 때 계산했다". 열린 question은 묻는 내용을 한 줄로 적는다.
8. 정의에 없는 지표(예: MRR, 판매자 churn)는 없다고 답하고 SQL을 짓지 않는다. staging·intermediate model을 직접 읽어 새 집계를 만들지 않는다.
9. SQL은 질문이 묻는 값만 select한다. 설명은 SQL이 아니라 답 글에 쓴다.
10. 기준 block을 만든다. 대화로 답할 때는 block을 보이지 않는다. 답 글에는 semantic layer 안의 이름(metric 이름, variant, status 값, question id, 정의 파일 경로)을 쓰지 않고 지표의 뜻(label)으로 쓴다. SQL 안의 table·column·code 값은 그대로 둔다. block에서 사용자가 알아야 할 것(확정되지 않은 정의, 걸지 못한 규칙, 측정 안 된 기간, 최신 확인 못 한 정의)만 답 끝 "주의" 한두 줄에 사람 말로 적는다. 답을 파일로 쓰라는 지시가 있거나(eval 등) 사용자가 기준·근거를 물으면 아래 block을 그대로 쓴다.

```yaml
기준:
  metrics: [<쓴 metric 이름>]          # 거절이면 []
  variant: <term.variant 또는 없음>
  status: [<쓴 metric들의 status>]
  questions: [<쓴 metric과 고른 용어에 걸린 열린 question id>]
  rules_applied_by_me: [<caller 규칙 중 내가 건 것>]
  other_variants: [<고르지 않은 variant>]
  ref: <locate.sh가 알린 ref. 최신 확인 못 했으면 그 사실과 last_checked>
```

## 정의 쓰기

정의는 저장소 checkout 안에서 고친다. mart model에 지표를 더하거나 바꾸면 같은 PR에서 정의를 고친다. 정의가 없으면 `make ci-local`이 실패한다(우회 표기 없음).
검사는 `make ci-local`이다. 정의나 mart model을 고쳤으면 PR 전에 직접 돌린다. 검사는 dbt도 warehouse도 부르지 않고 파일만 읽는다.

1. 실패 메시지가 만들 파일 경로(`manifest/metrics/<domain>/<table>/<metric>.yml`)와 그 파일에 쓸 최소 metric 문서를 보여 준다. 그 파일을 만들어 붙여 넣고 `<...>` 자리표시를 채운다. kind·rollup은 이름으로 짐작한 값이니 SQL을 보고 고친다. 파일 하나에 metric 하나만 두고, 파일 이름은 metric 이름과 같게 한다. 이름은 그 table의 `meta.shop.metric_prefix` + mart column(long table은 지표 code)이고 실패 메시지가 이미 그렇게 제안한다. family는 `<prefix><code 앞부분>_by_<무엇별>`(예: `order_pay_count_by_method`).
2. status를 정한다. A·B 등급 원본(`sources.yml`)이 그 지표를 정의하고 코드와 맞으면 `confirmed`와 `docs`, 원본이 없으면 `code_only`, 원본과 코드가 다르면 `conflict`와 `questions`(필요하면 `questions/<question id>.yml`로 질문을 더한다). D 등급 원본은 인용하지 않는다. 근거는 이 차례로 찾는다. 코드가 정본이다.
   1. mart model의 SQL(`models/marts/`): 지표를 만드는 식, grain, filter. 필요하면 `ref()`를 따라 intermediate·staging model까지 본다
   2. model yml(`models/marts/**/_*.yml`): model·column 설명과 contract
   3. 대시보드 SQL: 실제로 읽는 방식
   4. 저장소 `docs/`
   5. wiki 문서. 정의에 쓴 문서는 `sources.yml`에 등급과 함께 등록한다
   6. 메신저 thread. 결정이 담긴 thread는 근거로만 쓰고 PII는 옮기지 않는다. 비공개 채널의 본문은 정의, `sources.yml`, PR 본문에 옮기지 않고 링크만 남긴다
   7. `dbt_project.yml`과 job 설정: materialization, 실행 주기, 의존 순서
3. long table의 지표 code는 mart model 안에서 literal, `CASE`, 앞 literal 이어 붙이기(`'prefix_' || 코드`)로만 쓴다. 검사가 그 식을 읽어 정의와 견준다. data가 만드는 code(이어 붙이기)는 metric 하나의 `filter: ... LIKE '<prefix>%<suffix>'`로 덮는다. code를 dbt seed가 정하면 `meta.shop.long.seed`에 seed 경로를, 다른 model의 code를 그대로 넘겨받으면 `long.inherits`에 그 table을 적는다.
4. mart에 새 model을 만들면 model yml에 column을 선언하고(contract), `manifest/tables/<domain>/<table>.yml`을 둔다(`meta.shop.metric_prefix`로 그 table의 metric 접두어를 정한다. 다른 table 접두어와 헷갈리지 않는 짧은 낱말). metric은 `manifest/metrics/<domain>/<table>/`에 하나씩 두거나, `not_modeled.yml`에 이유를 적는다. wide table은 모든 column을 dimension·measure로 두거나 `meta.shop.skip_columns`에 이유를 적는다.
5. 생성물을 다시 만들고 검사한다.

```bash
python -m semantic.render
make ci-local
```

정의 형식(파일 배치, YAML key, index.md 약속)을 바꿔 옛 skill이 읽지 못하게 되면, skill의 `VERSION`(`skill/shop-data-analytics/VERSION`)을 먼저 올려 기본 브랜치에 반영하고, 그다음 `render.py`의 `SKILL_MIN`을 그 값으로 올린다. 순서가 바뀌면 모든 사용자의 skill이 종료 코드 5로 멈춘다. 이 README의 절 이름 둘("질문에 답하기", "정의 쓰기")과 index.md 첫 두 줄은 skill과 정의 사이의 약속이라 함께 바꾼다.

회사명·사람 이름·이메일은 어떤 파일에도 쓰지 않는다. 검사는 이메일·전화번호·법인 표기를 막고, 사람 이름은 검토하는 사람이 본다.

## skill 설치

skill을 symlink로 건다. clone은 기본 브랜치에 둔다. skill은 돌 때마다 이 저장소의 최신 main 정의를 받아 쓰고, clone이 뒤처졌으면 스스로 `pull --ff-only` 한다.

```bash
ln -s "<이 저장소 clone>/skill/shop-data-analytics" ~/.claude/skills/shop-data-analytics
```
