# 결정과 이유

[design.md](design.md)의 모양을 왜 그렇게 정했는지 적는다. 결정은 주제별 절로 묶었다. "원본 번호"는 원래 설계 문서의 결정 번호이고, 여러 번호를 하나로 합친 줄도 있다. "정한 쪽"의 설계자는 이 설계를 맡은 사람, agent는 함께 설계한 LLM agent다. 같이 읽을 문서: [llm-entry.md](llm-entry.md), [verification.md](verification.md).

## 범위와 소비자

| 원본 번호 | 무엇을 | 답 | 정한 쪽 | 이유 |
|---|---|---|---|---|
| D3 | 주 소비자 | LLM 우선, 사람도 읽는다 | 설계자 | YAML을 git에 두고 LLM이 읽게 하는 방향이 가장 싸다. warehouse 전용 자연어 질의 도구나 metric view 단독은 비용과 배포 부담이 크다 |
| D4·D14 | 범위 | 지금 mart에 있는 지표만. 대시보드·운영 작업이 읽는 mart model 전부를 정의하고, mart의 나머지 model은 `not_modeled.yml`에 사유를 적는다 | 설계자 | 아직 뼈대뿐인 도메인까지 정의하면 빈 정의가 쌓인다. 대시보드 숫자는 모두 설명할 수 있어야 한다 |
| D6 | 배포 | git 파일만. dbt Semantic Layer나 warehouse metric view는 소비자가 정해진 뒤 이 정의에서 생성물로 만든다 | 설계자 | 소비자가 정해지기 전에 서빙할 곳을 만들면 배포와 동기화 부담만 생긴다. LLM은 git 파일을 바로 읽는다(D3) |

## 형식

| 원본 번호 | 무엇을 | 답 | 정한 쪽 | 이유 |
|---|---|---|---|---|
| D30 | 정본 형식 | standalone MetricFlow semantic manifest YAML(문서 하나에 `semantic_model:` 또는 `metric:` 하나) + `config.meta.shop` + 옆 파일 | 설계자 요구 + agent | 업계 schema를 쓴다. 두 모델에게 따로 설계를 받았고 두 안이 이 모양으로 모였다. dbt project YAML(`semantic_models:`·`metrics:`)이 아니라 standalone manifest로 둔 이유는 셋이다. 파일 하나에 정의 하나, 파일 이름 = 이름이라는 배치를 그대로 쓴다(LLM이 읽는 양, diff). metricflow의 standalone parser·validator가 dbt profile·adapter·`dbt parse` 없이 오프라인 test에서 읽는다. 표준에 없는 뜻은 어차피 `config.meta`와 옆 파일에 있고 이 저장소의 검사가 본다. 다른 형식(dbt Semantic Layer, Ossie, metric view)은 필요하면 이 정의에서 생성물로 만든다 |
| D17·D64 | YAML key | MetricFlow 표준 그대로(`semantic_model`, `measures`, `type_params`, `label`, `description`). 옆 파일도 label·description·synonyms | 설계자 | metricflow를 fork하거나(약 120파일) 검사 직전에 key를 번역하는 대신 "우리가 표준에 맞춘다" |
| D31 | 표준 validator | metricflow 0.214.x를 test 의존성으로만 쓴다. 개발 Python은 3.10 이상 | 설계자 | 0.209부터 Apache-2.0이다(0.208.1 이하는 BSL). 런타임 의존을 늘리지 않는다 |
| D42 | seed가 code를 정하는 long table | `long.seed`에 dbt seed(CSV) 경로, code를 넘겨받는 table은 `long.inherits` | agent | `search_metric_monthly`의 code는 model SQL이 아니라 dbt seed `seeds/ref/search_metric_rules.csv`에 있고, `seller_usage_monthly`가 그 code를 물려받는다. 경로를 적어야 빠짐 검사가 code를 읽는다(seed는 CSV 첫 column) |
| D43·D75 | kind | `meta.shop.kind`를 두고 percentile을 더한다 | agent | `delivery_days_p90` 같은 분위수 지표가 있다. distinct_count면 `counts`가 필수라는 검사가 kind에 기댄다 |
| D44 | latest_snapshot | as_of_date가 오늘 하나뿐인 view는 `applied`, 날마다 쌓이는 table만 `caller` | agent | SQL로 확인했다. 하나뿐인 view에 caller를 적으면 LLM이 쓸데없는 MAX 조건을 붙인다 |
| D49 | dimension 설명 | dimension description은 필수, entity·measure description은 필수가 아니다 | 설계자 | measure의 뜻은 metric이, entity의 뜻은 `entities.yml`이 담는다. dimension은 담는 곳이 따로 없다 |

## 파일 나누기

| 원본 번호 | 무엇을 | 답 | 정한 쪽 | 이유 |
|---|---|---|---|---|
| D10 | 정의 위치 | `semantic/` 한 곳. dbt의 model-paths 밖 | agent | semantic layer는 dbt pipeline의 한 단계가 아니라 mart 위에 얹는 정의다. dbt는 model-paths 안의 YAML을 모두 property 파일로 읽는다. 정의 파일을 models/ 안에 넣어 `dbt parse`를 돌려 보니 오류도 경고도 없이 넘어갔다(dbt 1.12). 조용히 무시되는 파일이 dbt 파일 사이에 섞이면, 사람은 dbt가 그 정의를 쓴다고 오해한다. 정의는 dbt project YAML이 아니다(D30). 도메인마다 흩으면 진입점이 여럿이 된다 |
| D47·D48 | 나누는 이유 | 풀 문제는 넷: LLM의 읽기 비용, 사람의 찾기·diff·충돌, dbt 프로젝트와 같은 배치, 옆 파일의 크기 | 설계자 | 파일 하나에 모두 두면 지표 하나를 물어도 전부 읽고, 지표 하나를 더해도 큰 파일에 충돌이 난다 |
| D51·D54·D55 | 나누는 단위 | table 정의 파일에 semantic_model 하나, metric 파일 `<metric>.yml`에 metric 하나. 어기면 실패 | 설계자(검사는 agent) | dau를 물으면 table 정의 하나와 dau 파일 하나만 읽는다. 주제별 파일이나 table별 metric 파일은 metric이 늘수록 길어져 읽기 비용이 남는다 |
| D59·D63 | 폴더 | `manifest/tables/`와 `manifest/metrics/` 두 tree. 사람·LLM에게는 "table 정의"라 부른다 | 설계자 | dbt처럼 두 tree로 둔다. `semantic_models`라는 폴더 이름은 도구가 만든 낱말이라 읽는 사람에게 낯설다 |
| D61 | metric 폴더와 table | metric의 measure가 그 폴더 이름의 table에 있어야 한다 | agent | 폴더로 table을 짐작해도 틀리지 않게 한다 |
| D52·D56 | 옆 파일 | glossary·questions는 항목마다 `<id>.yml`, 나머지 넷(entities, rules, sources, not_modeled)은 한 파일 | 설계자(이름 규칙은 agent) | 용어·질문은 항목마다 길고 따로 바뀐다. 나머지까지 모두 나누면 한 줄짜리 파일이 수십 개 생긴다 |

## 모호한 용어 다루기

| 원본 번호 | 무엇을 | 답 | 정한 쪽 | 이유 |
|---|---|---|---|---|
| D5·D12 | 뜻이 다른 같은 이름 | 이름을 나눠 모두 두고 owner 확인 목록에 올린다. 답은 기본 variant로 하고, 다른 뜻과 "공식 정의 아님"을 밝힌다 | 설계자 | 정본 선택은 owner 합의가 필요하다. 되물으면 간단한 질문도 두 번 오간다 |
| D13·D33·D46 | 질의 때 계산하는 지표 | status `query_time`. glossary variant가 가리킬 mart 값이 없을 때만 두고 question이 필수다 | 설계자(이름·filter는 agent) | 넣지 않으면 LLM이 매번 식을 지어내고, 마음대로 넣으면 새 집계가 된다. `derived`라는 이름은 MetricFlow의 metric type과 겹쳐서 쓰지 않는다 |
| D18·D19 | 줄 번호, 원본 작성자 | 생성물에 줄 번호를 넣지 않는다. `sources.yml`에는 팀·역할만 적고 사람 이름은 적지 않는다 | agent | 줄 번호는 model SQL을 고칠 때마다 낡는다. PII를 줄인다 |
| D20·D73 | 원본 등급 | 원본 조사의 A~D 판정을 `sources.yml`로 옮긴다. D는 인용 금지. 어디서도 인용하지 않는 원본은 두지 않는다 | agent | 인용할 때 다시 넣으면 된다. 판정 근거는 조사 문서에 남긴다 |

## 검사

| 원본 번호 | 무엇을 | 답 | 정한 쪽 | 이유 |
|---|---|---|---|---|
| D7·D16·D25·D26 | 확인 방법 | 오프라인 test + 손으로 돌리는 질문 eval. 한 run에서 모든 질문이 맞아야(10/10) 통과. eval에서 skill은 이름으로 부르고, 자동 발동은 따로 확인한다. 모든 run을 기록한다 | 설계자 | 참조 무결성은 매번 test로, 정답률은 eval로 본다. 이름으로 불러야 정의 문제와 발동 문제가 갈린다 |
| D15·D58 | 정의 없는 새 mart 지표 | 무조건 실패(우회 표기 없음). 메시지가 만들 파일 경로와 붙여 넣을 최소 metric 문서를 보여 준다. 정의나 mart model을 고친 사람이 merge 전에 `make ci-local`로 돌린다. pre-push hook은 켜지 않는다 | 설계자(메시지는 agent) | 우회 표기를 허락하면 빠진 지표가 쌓인다. 대가는 mart model을 쓰는 사람이 매번 정의를 쓰는 것이다. 모든 push를 막는 hook은 과하다 |
| D24 | data가 만드는 code | family 정의 하나로 덮는다. 새 prefix는 실패, 아는 prefix 안의 새 code는 통과 | 설계자 | 오프라인에서는 data가 만들 code를 알 수 없다. D15의 유일한 예외다 |
| D29 | staging·intermediate를 거치는 관계 검사 | 하지 않는다 | agent | 관계 table(`dim_store`, `dim_member_seller`)도 mart model이다. 생기면 다시 정한다 |
| D72 | ci-local의 semantic test | 실제 정의 검사는 늘 돈다. 정의를 망가뜨려 보는 test(느리다)는 semantic 경로가 main 대비 바뀐 branch에서만 돈다. 전부는 `make test` | agent | 느린 test가 `make ci-local`마다 붙으면 사람이 검사를 건너뛴다. mart model이나 `macros/exclude_internal.sql`만 바뀐 변경도 실제 정의 검사가 D15를 잡는다 |

## LLM 진입과 skill

| 원본 번호 | 무엇을 | 답 | 정한 쪽 | 이유 |
|---|---|---|---|---|
| D11·D23 | LLM 진입 | skill 저장소의 얇은 skill로 들어오고, 절차는 정의 저장소 README에 둔다 | 설계자 | 절차를 YAML 형식과 같은 변경에서 고친다. 옛 skill과 새 YAML이 만나 조용히 틀린 SQL을 만들지 않는다 |
| D35 | SQL을 누가 쓰나 | LLM이 YAML을 읽고 직접 쓴다 | 설계자 | 정의 밖 질문(새 join)에도 답한다. metricflow의 SQL 생성은 정의 밖 질문에 하나도 답하지 못했고, 공통 규칙을 빠뜨리고, SQL이 길었다 |
| D32 | 기준 block key | `metrics` | agent | 표준에서 LLM이 고르는 단위가 metric이다 |
| D36 | skill을 돌리는 모델 | 모델 계열 alias를 쓴다(frontmatter `model: opus`). `/`로 부르면 그 turn이 그 모델로 돌고, 질문만으로 자동 발동하면 세션 모델로 돈다(실측). 자동 발동은 그대로 두고 SKILL.md·설치 안내에 적는다 | 설계자 | SQL을 LLM이 쓰는 대가로 모델 하한을 둔다. 버전을 고정하면 모델이 바뀔 때마다 skill을 고쳐야 한다. 강제하는 길은 `/`로만 부르게 하는 것뿐이었다([llm-entry.md](llm-entry.md#skill을-돌리는-모델)) |
| D37·D40 | skill 최신 유지 | `locate.sh`가 매 실행 자기 clone을 확인하고 자동 갱신한다. index.md의 `skill_min`이 skill `VERSION`보다 높으면 갱신하고, 그래도 낮으면 멈춘다 | 설계자(VERSION 파일은 agent) | 아무도 pull을 하지 않는다. SessionStart hook은 사람마다 등록해야 해서 빠진다. frontmatter에 version key를 두면 도구가 모르는 key로 무시할 수 있다 |
| D38·D39 | 답할 때 정의 버전 | 항상 origin/main. 정의를 고칠 때만 로컬 working tree. 최신 확인이 안 되면 로컬의 가장 최근 정의로 답하고 ref에 밝힌다. 정의가 아예 없으면 멈춘다 | 설계자 | 오래된 branch의 낡은 정의로 답하지 않는다. 멈추기만 하면 VPN 밖이나 오프라인에서 쓸 수 없다 |
| D28·D41 | checkout 밖에서 정의 받기 | git sparse clone | agent | gh CLI는 여러 계정이 걸린 환경에서 API가 404로 실패했다. git은 가짜 remote로 test할 수 있다 |
| D70·D71 | skill이 하는 일의 경계 | skill은 warehouse에 SELECT만 돌린다(사용자가 요청하고 권한이 있을 때). 정의 쓰기의 근거 찾기 차례는 mart model SQL → model yml(description·contract) → 대시보드 SQL → 저장소 docs → wiki → 메신저 thread → `dbt_project.yml`과 job 설정 | agent | 분석은 읽기 일이다. 코드가 정본이고 문서는 등급을 붙여 쓴다 |
| D79 | skill 이름과 개수 | skill은 `shop-data-analytics` 하나. 정의 쓰기용 dev skill과 `locate.sh`의 write 모드는 두지 않고, 정의 쓰기·근거 찾기·형식 version 차례는 README "정의 쓰기"에 둔다. "opus가 아니면 안내" 규칙도 두지 않는다 | 설계자 | 이름이 하는 일(데이터 분석)을 말해야 한다. dev skill은 README를 다시 말할 뿐이었다. sonnet 세션 3번에서 모델 안내는 한 번도 나오지 않았고, 한 번은 자기를 opus라고 했다 |
| D80 | 대화 답의 모양 | 대화로 답할 때 기준 block(YAML)과 semantic layer 안의 이름(metric 이름, variant, status 값, question id)은 보이지 않고 지표의 뜻으로 쓴다. 돌린 SQL은 보인다. block의 주의할 것만 "주의" 한두 줄에 사람 말로 적는다. 파일로 답하라는 지시(eval)나 근거를 물을 때만 block을 쓴다. 답마다 다음 분석 선택지 2~4개를 글 번호 목록으로 준다 | 설계자 | 데이터를 보는 사람에게 YAML은 도움이 안 된다. eval은 block 파일로 채점하므로 파일 답에는 남긴다 |

## 이름

| 원본 번호 | 무엇을 | 답 | 정한 쪽 | 이유 |
|---|---|---|---|---|
| D65 | metric 이름(D34·D45를 바꿈) | table마다 접두어 하나 + mart column(long은 code). [design.md의 "이름 규칙"](design.md#이름-규칙) | 설계자 | 이름이 겹칠 때만 접두어를 붙이면 한 table 안에서 붙은 것과 안 붙은 것이 섞이고, table이 늘 때마다 옛 이름이 바뀐다. 접두어 낱말은 mart column에 이미 쓰는 낱말에 맞춘다 |
| D76·D78 | 나머지 이름, 규칙 지키기 | measure `<table>_<column>`, primary_entity `<table>_row`. `meta.shop.metric_prefix`로 metric 이름을 검사하고, 실패 메시지의 제안 이름도 접두어를 붙인다 | agent | 규칙 하나로 맞춘다. 검사가 없으면 다시 섞인다 |
| D62 | graph 이름 | edge는 "출발 node의 무엇"으로 읽히는 명사. node type은 model 대신 table, code 대신 sql | 설계자 | 이름 규칙 하나로 새 edge도 짓는다. SKOS·PROV 같은 표준 낱말은 이 graph에 비해 무겁다 |

## 생성물

| 원본 번호 | 무엇을 | 답 | 정한 쪽 | 이유 |
|---|---|---|---|---|
| D21·D66 | 지식 graph | semantic layer + 명시적 관계(entity 관계, metric → entity·원본·용어 edge). `render.graph()`가 만들고 test가 본다. graph JSON은 commit하지 않고 `render --graph`로 필요할 때 만든다 | 설계자 | 범용 nodes/edges 저장소나 RDF/OWL은 과하다. graph JSON은 변경 diff를 크게 부풀리는데 읽는 곳은 test와 시각화뿐이다 |
| D57·D67 | index.md | table마다 "읽을 파일" 한 줄(table 정의 경로 + metric 경로 규칙, metric이 없으면 "(metric 없음)"), 끝에 owner 확인 목록. 지표 사전·graph 문서는 따로 두지 않는다 | agent(D67은 설계자) | metric마다 경로를 적으면 metric 수만큼 줄이 늘어 읽기 비용이 커진다. 지표 사전은 index.md와 내용이 같았다 |

## 버린 후보

- 정본 형식
  - warehouse metric view YAML + 원본을 담는 별도 파일: 정의가 두 곳으로 갈리고, long table의 distinct 값을 거짓으로 더한다.
  - 표준 위에 `x_` 확장 key를 얹는 안: 사실상 자체 형식이다. 빠짐(coverage) 검사 아이디어만 가져왔다.
  - 자체 형식: 업계 schema를 쓰기로 했다.
  - Ossie: release가 0.1.x뿐이고 additivity 칸이 없다.
  - warehouse metric view 단독: meta 칸도 오프라인 validator도 없다.
  - dbt project YAML(`semantic_models:`·`metrics:`) 그대로: metricflow로 읽으려면 dbt profile·adapter와 `dbt parse`를 거쳐야 해 오프라인 test가 dbt에 묶인다. standalone manifest는 파일 하나에 정의 하나 배치를 그대로 쓰고 parser·validator가 바로 읽는다. 표준에 없는 뜻은 어느 쪽이든 `config.meta`와 옆 파일에 있다. dbt Semantic Layer로 서빙해야 하면 생성물로 만든다(D30).
  - Cube·Snowflake: 서버나 계정이 필요하다.
  - Markdown·Python dict: 참조 검사를 할 수 없다.
- 검사
  - 표준 검사기 없이 손 검사만: 공식 도구에 맡기는 이점이 준다.
  - dbt-semantic-interfaces 단독: deprecated이고 개발이 멈췄다.
- 배치
  - `models/marts/<domain>/` 옆에 도메인마다 분산: 진입점이 도메인 수만큼 생기고, 정의가 dbt의 model-paths 안에 섞인다(D10).
  - 주제별 metric 파일, table별 metric 파일: 읽기 비용이 남는다(D51).
  - index.md에 metric마다 경로: 줄이 metric 수만큼 는다(D57).
  - graph JSON·지표 사전 commit: diff가 커지고 index.md와 겹친다(D66·D67).
- skill
  - 절차 전체를 skill에: 형식이 바뀌면 두 저장소를 동시에 맞춰야 한다.
  - 생성물(index.md)을 skill에 사본으로: 지표마다 두 저장소가 갈린다.
  - 분석용 skill과 정의 쓰기용 dev skill 둘: dev skill은 README를 다시 말할 뿐이었다(D79).
  - 모델 버전 고정: 새 모델마다 skill을 고친다(D36).
- 같은 사실을 두 곳에: 관계를 양쪽 entity에 적기, measure에 term 역참조 두기. 둘 다 어긋난다.
- metricflow로 SQL 생성(D35), metricflow fork나 검사 직전 key 번역(D64), 겹칠 때만 metric 접두어(D65).

## 치르는 값

- 이미 집계된 distinct 값에 `agg: sum`을 적는 어색함이 남는다. non_additive_dimension, `rollup: none`, README 규칙으로 막는다.
- Jinja filter(`{{ Dimension('...') }} = 'dau'`)는 사람과 LLM에게 덜 읽힌다. index.md가 풀어 쓴다.
- 개발용 Python을 3.10 이상으로 올려야 한다.
- mart model을 쓰는 사람이 지표를 더할 때마다 metric 파일을 쓰고 render를 돌린다(D15). 검사는 hook이 아니라 사람이 `make ci-local`로 돌리므로, 돌리지 않고 merge하면 막히지 않는다.
- table 하나를 고칠 때 `tables/`와 `metrics/` 두 폴더를 오간다.
- dbt project 안에 dbt가 읽지 않는 정의 폴더(`semantic/`)가 하나 더 생긴다. dbt Semantic Layer의 도구(예: 공식 SQL 생성)를 그대로 쓰지 못한다.
