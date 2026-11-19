# 검사와 검증

정의가 맞는지는 두 겹으로 본다. 매번 도는 오프라인 검사가 참조 무결성을 보고, 손으로 돌리는 질문 eval이 LLM이 그 정의로 맞게 답하는지 본다. 같이 읽을 문서: [design.md](design.md), [decisions.md](decisions.md), [llm-entry.md](llm-entry.md).

## 검사 두 겹

### 1. 표준 validator

metricflow 0.214.x의 parser와 validator가 `manifest/`를 읽는다. 모르는 key, 없는 measure, 이름 중복, enum 오타, 없는 time dimension, Jinja 문법 오류를 잡는다. 경고도 문제로 본다. 표준 도구에 맡길 수 있는 것은 맡기고, 직접 짠 검사는 표준이 못 잡는 것만 본다.

### 2. 표준이 못 잡는 것을 잡는 검사

`semantic/checks.py`가 본다. dbt를 부르지 않고 dbt project 파일만 읽는다.

- 파일 배치: table 정의 파일에 semantic_model 하나, metric 파일에 metric 하나, 파일 이름 = name, metric 폴더의 table = measure의 table, `project.yml`에는 문서 하나, glossary·questions는 `<id>.yml`에 하나씩(하위 폴더·list 항목 금지)
- filter가 가리키는 dimension과 prefix가 있는가
- 정의 없는 mart 지표(아래 "빠짐 검사")
- `meta.shop` 형식과 enum(status, rollup, kind, 규칙 상태)
- status와 원본 규칙: confirmed는 A·B 원본 필수, conflict·query_time은 question 필수, query_time은 가리키는 variant 필수, D 등급 인용은 실패
- rollup과 non_additive_dimension이 맞는가
- table과 mart: `node_relation`(`schema_name` + `alias`)이 가리키는 dbt model이 있는가, `defined_in`이 그 model 파일 경로인가, entity·dimension·measure의 column이 model yml contract에 선언돼 있는가
- 관계: cardinality가 entity type과 맞는가, 같은 관계를 두 곳에 적지 않았는가, via table과 join key column이 있는가
- distinct_count metric에 `counts`가 있는가
- glossary가 가리키는 metric·원본·question이 있는가
- dimension에 description이 있는가
- metric 이름이 자기 table의 `metric_prefix`로 시작하는가. `metric_prefix`가 없거나 문자열이 아니면 table마다 한 번 알린다
- `rules.yml`의 내부 판매자 제외 SQL이 dbt macro `macros/exclude_internal.sql`의 `exclude_internal`을 render한 것과 같은가(`catalog.macro_sql`이 dbt 없이 Jinja로 render한다)
- commit된 index.md가 지금 정의로 만든 것과 byte까지 같은가
- PII: 정의 파일과 README에 이메일, 전화번호(붙여 쓴 것 포함), 법인 표기(㈜ 포함, YAML escape로 숨긴 것 포함)가 있으면 실패
- 두 저장소 약속: 경로, README 절 이름 둘, index.md 첫 두 줄([llm-entry.md](llm-entry.md#두-저장소-약속-셋))

## 빠짐 검사: 정의 없는 mart 지표는 무조건 실패

`semantic/catalog.py`가 dbt project 파일에서 지표를 뽑는다. dbt도 warehouse도 부르지 않는다.

- long table: mart model SQL(`models/marts/<domain>/<model>.sql`)의 SELECT에서 key column 자리의 식을 따라가 code literal, CASE 결과, prefix(`'order_pay_' || ...` 같은 앞 literal 이어 붙이기)를 뽑는다. 그 자리가 column 참조이면 FROM의 subquery나 같은 WITH의 CTE로 들어간다. Jinja 주석(`{# #}`), `config()` 호출, SQL 주석은 먼저 지운다.
- wide table: column 목록을 model yml(`_<domain>__models.yml`)의 contract에서 읽는다. dbt가 build 때 SQL과 contract가 맞는지 강제하므로 선언된 column을 믿을 수 있다.
- seed가 code를 정하는 table(`long.seed`): dbt seed CSV(`seeds/ref/search_metric_rules.csv`)의 첫 column 값을 code로 읽는다.

뽑은 것마다 정의가 있어야 한다.

- 정의가 없으면 무조건 실패한다. "일부러 뺐다"는 우회 표기는 두지 않는다. 허락하면 빠진 지표가 쌓인다. 메시지는 "mart에 있는 지표 'x'가 정의에 없다"다.
- 실패 메시지는 만들 파일 경로(`manifest/metrics/<domain>/<table>/<metric>.yml`)와 그 파일에 붙여 넣을 최소 metric 문서를 보여 준다. 제안 이름에는 table의 접두어가 붙어 있고, measure도 원래 쓰던 것을 제안한다. kind·rollup은 이름으로 짐작한 값이라 SQL을 보고 고친다.
- 붙여 넣은 뒤 자리표시(`<...>`, TODO)가 남으면 실패한다.
- 유일한 예외는 data가 만드는 code다. 오프라인에서는 data가 만들 code를 알 수 없으므로 family 정의 하나로 덮는다. 아는 prefix 안의 새 code는 통과하고, 새 prefix는 실패한다.
- SQL에서 읽지 못한 갈래(IF, coalesce, `SELECT *` 등으로 code를 만드는 갈래)는 통과가 아니라 실패다. "지표 code를 읽지 못했다"고 알린다.
- 다른 model의 column을 그대로 넘기는 갈래(예: `{{ ref('int_orders') }}`의 column을 key 자리에 그대로 둠)도 읽지 못한 갈래다. table 정의가 `long.inherits`(code를 넘겨주는 table)와 `long.seed`(code를 정하는 seed)로 출처를 밝힌 만큼만 허락한다. `seller_usage_monthly`는 `search_metric_monthly`를 `long.inherits`에 적어 그 갈래 하나를 허락받고, 넘겨받은 code는 넘겨주는 쪽의 seed로 확인한다.
- mart schema의 model마다 table 정의가 있거나 `not_modeled.yml`에 사유가 있어야 한다. wide table은 모든 column을 dimension·measure로 두거나 `skip_columns`에 이유를 적는다.

## 정의를 망가뜨려 보는 test

`tests/semantic/test_semantic_layer.py`는 실제 정의 폴더(빠짐 검사 test는 `models`·`seeds`·`macros`까지)를 임시 폴더에 복사하고, 파일 하나의 문자열 하나를 바꾼 뒤 검사가 그 문제를 잡는지 본다. 검사가 실제 정의에서 문제 0건을 내는 것만으로는 검사가 일하는지 알 수 없어서다.

| 묶음 | 망가뜨리는 것(예) |
|---|---|
| S1 정의 | metric에 모르는 key, 없는 measure, filter가 없는 dimension을 가리킴, `meta.shop` key 오타, status enum 오타, rollup과 non_additive_dimension 어긋남 |
| S2 빠짐 | metric 파일 하나 지움(최소 문서가 나오는지), mart model SQL에 새 literal code, 새 prefix, 아는 prefix 안의 새 code(통과해야 함), 붙여 넣은 문서에 자리표시가 남음 |
| S3 옆 파일 | D 등급 원본 인용, confirmed인데 A·B 원본 없음, conflict인데 question 없음, 등급 오타, table이 모르는 공통 규칙, 내부 판매자 제외 SQL이 macro `exclude_internal`과 다름, 정의에 이메일·법인 표기 |
| S4 관계·생성물·약속 | YAML만 고치고 render를 안 돌림, 관계를 두 곳에 적음, via table에 없는 join key, cardinality가 entity type과 어긋남, README 약속 절 이름 바꿈, index.md `format` 바꿈 |
| S5 table 범위 | not_modeled에서 table 하나를 지움, wide column 정의를 지움(접두어 붙은 제안 이름이 나오는지) |
| 고친 구멍 | 읽지 못한 갈래, 다른 CTE 안의 code, 다른 model의 column을 그대로 넘기는 갈래, 블록 주석·Jinja 주석 안의 code와 따옴표 안의 `--` |
| 배치 | 파일 이름 ≠ name, metric 폴더의 table ≠ measure의 table, 하위 폴더, 한 파일에 문서 둘, dimension description 없음, 접두어 겹침 제안 |

`tests/semantic/test_repo_definitions.py`는 실제 정의와 실제 dbt project 파일을 본다. 표준 validator 오류·경고 0, 검사 문제 0, 생성물 일치, graph의 명시적 관계 edge, eval 질문이 있는 정의를 가리키는지, index.md의 "읽을 파일" 줄을 확인한다.

## 언제 무엇이 도는가

| 언제 | 도는 것 | 이유 |
|---|---|---|
| `dbt build --profiles-dir .`, mart model을 고친 뒤 | seed·model build와 contract 검사 | dbt가 mart model의 SQL이 model yml contract(column 이름·type)와 맞는지 강제한다. 검사는 contract를 읽으므로 build가 통과해야 검사가 믿는 column이 맞다 |
| `make ci-local`, 늘 | 표준 validator + 실제 정의 검사(`test_repo_definitions.py`) | mart model이나 `macros/exclude_internal.sql`만 바뀐 변경에서도 빠짐 검사가 돌아야 한다 |
| `make ci-local`, semantic 경로(`semantic`, `tests/semantic`, `requirements.txt`)가 main 대비 바뀐 branch | 위 + 망가뜨려 보는 test(실제 적용에서 약 60초, 이 예제는 약 10초) | 검사 코드가 그대로면 같은 결과다. 약 60초가 매번 붙으면 사람이 검사를 건너뛴다 |
| `make test` | 전부 | |
| 손으로, 정의나 skill을 크게 바꾼 뒤 | 질문 eval | LLM이 답을 쓰는 단계가 있어 오프라인 검사에 넣을 수 없다. score 자체는 DuckDB에서 계정 없이 돈다 |

검사는 hook이 아니다. 정의나 mart model을 고친 사람이 merge 전에 `make ci-local`을 직접 돌린다. 돌리지 않고 merge하면 막히지 않는다([decisions.md의 치르는 값](decisions.md#치르는-값)).

## 질문 eval

`scripts/semantic_eval.py`가 두 단계로 돈다. 순서는 `dbt build --profiles-dir .` → `pack` → agent가 답 → `score`다.

- `dbt build --profiles-dir .`: seed와 model을 DuckDB 파일 `shop_bi.duckdb`에 만든다. score가 이 파일을 읽는다.
- `pack`: 임시 폴더에 정의 저장소 모양 checkout(`semantic/`만, `.py` 제외)과 skill 사본을 만든다. bare 저장소를 가짜 remote로 두어 `locate.sh`가 그곳의 main을 받게 한다. 질문 목록(`QUESTIONS.md`)을 쓴다.
- 새 agent가 그 checkout 안에서 skill을 이름으로 불러, 질문마다 `answers/<id>.sql`(SQL 한 문장, 거절이면 빈 파일)과 `answers/<id>.yml`(기준 block)을 쓴다. 이름으로 불러야 정의 문제와 발동 문제가 갈린다.
- `score`: 정답 SQL과 답 SQL을 같은 DuckDB 파일(`--db`, 기본 `shop_bi.duckdb`)에서 돌려 결과 표 전체를 견준다(계정 불필요. 숫자는 소수 6자리로 맞추고 row 순서는 무시한다). 기준 block은 id로 견준다.

| block 칸 | 채점 |
|---|---|
| `metrics` | 정답과 집합이 같아야 한다. 거절 문항은 `[]` |
| `variant` | 정답에 있으면 같아야 한다 |
| `questions`, `rules_applied_by_me`, `other_variants` | 정답의 항목이 모두 있어야 한다(더 있어도 된다) |
| block 파일 | 없으면 실패 |
| SQL | 거절해야 하는데 SQL을 지으면 실패 |

한 run에서 모든 질문이 맞아야 통과다. 원본 설계 때 질문은 10개였고 기준은 10/10이었다. 모든 run을 보고서로 남긴다. 한 번 통과한 run만 남기면 정답률이 부풀어 보인다. 이 예제에서는 `dbt build`가 통과하고(node 38개), 정답 SQL 9개가 DuckDB에서 값을 낸다(q09는 거절 문항이라 정답 SQL이 없다). run 기록은 `--record`로 `docs/eval-runs/`에 남는다. 이 예제로 두 번 돌렸다. [run 1](eval-runs/2026-11-19T070111Z.md)과 [run 2](eval-runs/2026-11-19T070340Z.md) 모두 10/10이다. run 1에서 답한 agent가 짚은 README의 빈틈 셋을 고친 뒤 run 2를 돌렸다(아래 "eval은 통과해도 README의 빈틈을 알려 준다").

## 동작 표

설계가 지키겠다고 한 동작과 그것을 지키는 test다.

| # | 동작 | 지키는 것 |
|---|---|---|
| B1 | 질문에 답할 때 `locate.sh`는 origin/main 정의를 꺼내 쓰고 `source=main ref=<sha>`를 알린다 | `skill/shop-data-analytics/scripts/test_locate.py` |
| B2 | checkout 밖이면 git으로 main의 `semantic/`만 받고 cache를 다시 쓴다. git 없음 2, main에 없음 3, 받기 실패 4로 멈추고 정의를 지어내지 않는다 | test_locate.py |
| B3 | 답은 SQL과 끝의 기준 block(metrics, variant, status, questions, rules_applied_by_me, other_variants, ref)이다 | eval score |
| B4 | 뜻이 여럿인 용어는 기본 variant로 답하고 다른 variant와 "공식 정의 아님"을 밝힌다 | eval q01·q06 |
| B5 | mart에 없는 지표는 SQL을 짓지 않고 거절한다(`metrics: []`) | eval q09 |
| B6 | rollup none(dau)은 날짜를 넘어 더하지 않고, last(member_eod)는 기간 마지막 날 값을 쓴다 | eval q03·q04 |
| B7 | mart schema의 model마다 table 정의가 있거나 not_modeled 사유가 있다 | test_s5_mart_model_without_definition_or_reason_fails |
| B8 | 정의 없는 literal code나 wide column이 생기면 실패하고 붙여 넣을 최소 metric 문서가 나온다 | test_s2_undefined_mart_metric_is_reported_with_minimal_definition, test_s2_new_literal_code_without_definition_fails, test_s5_wide_column_without_definition_fails |
| B9 | 정의 없는 새 prefix는 실패, 정의된 prefix 안 새 code는 통과 | test_s2_new_prefix_without_family_fails, test_s2_new_code_inside_known_prefix_passes |
| B10 | 없는 table·column·code·원본·node를 가리키면 실패한다. 읽지 못한 갈래와 다른 model의 column을 그대로 넘기는 갈래는 실패한다 | test_s1_broken_definition_is_caught, test_fix_broken_definition_is_caught, test_fix_unreadable_branch_fails, test_fix_column_passed_from_another_model_fails |
| B11 | confirmed는 A·B 원본 필수, conflict·query_time은 question 필수, D 인용은 실패, query_time은 variant 필수 | test_s3_broken_side_file_is_caught |
| B12 | 관계는 한 곳에만, via table과 join key 필수, distinct_count는 counts 필수, rollup과 non_additive 일치 | test_s1_*, test_s4_broken_relation_or_generated_file_is_caught |
| B13 | `python -m semantic.render`가 index.md를 만들고, commit된 index.md가 정의와 다르면 실패한다. graph는 `--graph F`로만 쓴다 | test_s4_generated_files_match_definitions |
| B14·B15 | `rules.yml`의 내부 판매자 제외 SQL이 macro `exclude_internal`을 render한 것과 다르거나, 정의 파일·README에 이메일·전화번호·법인 표기가 있으면 실패 | test_s3_broken_side_file_is_caught |
| B16 | 두 저장소 약속(경로, README 절 이름 둘, index.md 첫 두 줄)을 검사한다 | test_s4_broken_relation_or_generated_file_is_caught |
| B17 | index.md 끝에 owner 확인 목록(question 5개: Q-active-user, Q-active-seller, Q-plan-scope, Q-tier-direction, Q-repeat-rate-denominator)이 있다 | test_s4_generated_files_match_definitions |
| B18 | `semantic_eval.py pack`·`score`로 한 run 전부 맞으면 통과, 모든 run을 보고서로 남긴다 | eval |
| B19·B22 | 표현을 바꾼 질문에서 skill이 이름 없이 켜진다. `/shop-data-analytics`로 부르면 frontmatter 모델로 돈다 | 실측([llm-entry.md](llm-entry.md#skill을-돌리는-모델)) |
| B20 | 기존 test는 그대로 통과하고 mart model·대시보드는 바뀌지 않는다. semantic layer는 dbt project 파일을 거의 건드리지 않는다(`dbt_project.yml`의 `test-paths` 한 줄, requirements 한 줄, Makefile 진입점) | `make ci-local`, main 대비 diff |
| B21 | metricflow parser + validator가 오류·경고 0이고, 실제 정의의 검사 문제가 0건이다 | test_repo_manifest_passes_standard_validator, test_repo_definitions_have_no_problems |
| B23 | rollup none 지표를 더 긴 기간으로 물으면 더하지 않고 다른 metric을 제안하거나 마지막 날 값임을 밝힌다 | eval q04 |
| B24·B25·B26 | skill clone이 skill 저장소·기본 branch·깨끗하면 스스로 갱신하고 아니면 6으로 멈춘다. 최신 확인이 안 되면 로컬의 가장 최근 정의로 답하고 ref에 밝힌다. `skill_min`이 VERSION보다 높으면 갱신을 시도하고 그래도 낮으면 5로 멈춘다 | test_locate.py |
| B27 | project.yml·table 정의·metric 파일은 문서 하나씩, 파일 이름 = name, metric 폴더의 table = measure의 table. 어기면 실패 | test_split_layout_is_enforced |
| B28 | 용어·질문은 `<id>.yml`에 하나씩. 파일 이름 ≠ id, 하위 폴더, list 항목이면 실패 | test_split_layout_is_enforced |
| B29 | index.md의 table마다 "읽을 파일" 한 줄, metric이 없으면 "(metric 없음)" | test_split_index_shows_files_to_read |
| B30·B34 | 정의 없는 code의 실패 메시지와 README "정의 쓰기"가 지표 하나에 파일 하나(`manifest/metrics/<domain>/<table>/<metric>.yml`)를 만들게 안내한다 | test_s2_undefined_mart_metric_is_reported_with_minimal_definition, README "정의 쓰기" |
| B31 | dimension에 description이 없으면 실패 | test_split_dimension_without_description_fails |
| B32 | 파일 나누기·이름 바꾸기 전후 graph는 파일 경로와 이름 대응 말고 같다. edge 종류는 설계 표의 13개다 | 바꾸기 전후 한 번 견줌, test_s4_graph_has_explicit_relation_edges |
| B36 | metric 이름이 table의 metric_prefix로 시작하지 않으면 실패. metric_prefix가 없거나 문자열이 아니면 table마다 한 번 알린다. 제안 이름에 접두어를 겹쳐 붙이지 않는다 | test_split_layout_is_enforced, test_table_without_metric_prefix_is_reported_once, test_non_string_metric_prefix_is_reported, test_suggest_name_does_not_double_prefix |
| B37 | ci-local은 실제 정의 검사를 늘 돌리고, 망가뜨려 보는 test는 semantic 경로가 main 대비 바뀐 branch에서만 돌린다 | Makefile `ci-local` |

## 검증에서 잡힌 구멍과 고친 것

큰 변경마다 만든 과정을 모르는 새 reviewer 셋에게 diff를 보였다. 하나는 spec과 대조하고, 하나는 저장소 규칙을 보고, 하나는 일부러 깨뜨려 본다. 셋이 낸 지적 중 고칠 것을 골라 고쳤다. 아래는 그때 잡힌 것을 교훈으로 묶은 것이다.

### 빠짐 검사는 읽지 못한 것을 통과로 치면 안 된다

첫 설계의 빠짐 검사는 SQL에서 code를 뽑다가 읽지 못한 갈래(IF, coalesce, `SELECT *` 등)를 조용히 버렸다. 그러면 새 지표가 그 갈래로 들어올 때 검사가 통과한다. "읽지 못한 갈래는 실패"로 바꿨고, 다른 CTE 안의 code, 주석과 따옴표 안의 `--`도 test로 막았다. dbt에서는 model 하나가 파일 하나라, 한 table에 여러 문장이 값을 넣는 갈래는 생기지 않는다. 대신 둘을 test로 본다. 다른 model의 column을 그대로 넘기는 갈래는 읽지 못한 갈래로 세고 `long.inherits`·`long.seed`로 출처를 밝힌 만큼만 허락한다. Jinja 주석(`{# #}`) 안의 code는 읽지 않는다. 검사가 모르는 것은 실패로 다뤄야 "검사가 통과했다"가 뜻을 갖는다.

### 최신을 가져오는 script는 경합과 낡은 cache부터 의심한다

첫 `locate.sh`에는 넷이 있었다. 낡은 cache를 먼저 쓰는 것, skill이 든 clone이면 아무 저장소나 pull하는 것, 얕은(shallow) checkout에서 깨지는 것, 동시에 두 번 돌 때 서로의 cache를 지우는 것. main sha를 늘 견주고, origin URL이 정확히 skill 저장소일 때만 갱신하고, sha마다 폴더를 두고 rename으로 바꾸게 고쳤다.

### 채점은 빠진 것도 본다

eval score가 처음에는 block 파일이 없거나 `other_variants`가 빠진 답을 통과시켰다. 둘 다 실패로 바꿨다. 표준 validator의 경고와 `window_choice: min`도 실패로 바꿨고, PII 검사는 변형(㈜, 붙여 쓴 전화번호, YAML escape)까지 잡게 했다.

### eval 실패가 정의가 아니라 README의 빈틈일 수 있다

첫 eval run은 9/10이었다. 틀린 문항은 정의가 아니라 답 SQL이 묻지 않은 column을 더 select해 결과 표가 달라진 것이었다. README에 "SQL은 질문이 묻는 값만 select한다"를 더했고 다음 run은 10/10이었다.

### 파일을 나누면 경로를 만드는 곳이 하나여야 한다

정의 파일을 나눌 때 문서·주석에 옛 경로가 남았고, README 표에서 `project.yml`이 빠졌고, metric 파일 경로를 만드는 코드가 두 곳에 있었다. 경로는 `render.metric_path` 하나로 모았다. 함께 잡힌 것: `project.yml`에 다른 문서를 붙이면 배치 검사를 건너뛰던 것, 하위 폴더의 파일이 조용히 무시되던 것, 빈 `metric:` 문서가 예외로 멈추던 것, 실패 메시지가 원래와 다른 measure를 제안하던 것. 실패 메시지가 제안하는 문서도 test가 봐야 한다. 사람은 그 문서를 그대로 붙여 넣는다.

### 검사를 빨리 하려고 건너뛰면 빈틈이 생긴다

망가뜨려 보는 test를 semantic 경로가 바뀔 때만 돌리게 하자, mart model이나 내부 판매자 규칙만 바뀐 변경에서 실제 정의 검사까지 빠졌다. 실제 정의 검사는 늘 돌게 나눴다. 건너뛰는 조건은 "결과가 같을 것이 확실한 test"에만 건다.

### 이름 규칙은 제안하는 쪽도 지켜야 한다

접두어 규칙을 넣은 뒤 실패 메시지가 column이 이미 접두어로 시작해도 다시 붙여 `su_su_` 같은 이름을 제안했다. `metric_prefix`가 없거나 문자열이 아닐 때 metric마다 같은 알림을 쏟던 것은 table마다 한 번으로 줄였다. 검사 메시지의 "model"은 사람이 부르는 말인 "table"로 바꿨고, render가 모르는 인자를 받으면 종료 코드 2로 멈추게 했다.

### eval은 통과해도 README의 빈틈을 알려 준다

이 예제의 run 1은 10/10이었지만, 답한 agent가 답을 정하기 어려웠던 곳을 셋 짚었다. 셋 다 README의 빈틈이었다.

- 합산 규칙 `last`의 "한 날을 물었는데 row가 없으면 값이 없다"와 long table의 "row가 없는 날은 0"이 부딪혔다. "그날이 table의 마지막 날짜보다 뒤면 값이 없다. 그 안이면 row 없는 날 규칙을 따른다"로 고쳤다.
- "일평균"을 무엇으로 나누는지 없었다. row가 없는 날이 0이라 row 수가 아니라 달력 일수로 나눈다고 적었다. 정답 SQL도 `AVG(value)`에서 `SUM(value) / 31`로 바꿨다. DAU는 날마다 row가 있어 두 식의 값이 같았고, 그래서 채점이 이 빈틈을 잡지 못했다.
- 같은 code(`keyword_search`)를 쓰는 metric이 두 table에 있는데 고르는 기준이 없었다. 두 metric 설명에 서로를 가리키는 한 줄을 넣었다.

통과한 run에서도 답한 agent에게 "답을 정하기 어려웠던 곳"을 묻는다. 정답과 값이 우연히 같아 통과한 문항은 채점으로는 보이지 않는다.

### 그대로 둔 것

- 기준 block에 `not_applied` 규칙(걸지 못한 규칙)을 적는 칸이 없다. run 2의 agent가 짚었다. 대화 답에서는 주의 줄에 적으므로 채점 칸만 없다.

- LLM이 읽는 선택 칸(caveats, synonyms, time_format)은 형식을 검사하지 않는다.
- 따옴표 scanner 같은 작은 코드 중복.
- 같은 manifest를 여러 번 읽는 것: 시간 영향이 작다.
- 여러 조건을 묶은 filter의 index 표시: 지금 정의에 없다.
- glossary 파일에 `---`로 문서를 여럿 두면 YAML 예외로 멈춘다. 실패는 하므로 두었다.
- 접두어 하나가 다른 접두어의 앞부분이면(예: `hs_`와 `hs_x_`) 이름만으로 table을 가르지 못한다. 검사는 자기 table 접두어로 시작하는지만 본다.
