# LLM이 들어오는 길

원본에서는 정의와 skill이 두 저장소에 있었다. 정의는 정의 저장소(`shop-bi`, dbt project)의 `semantic/`에, skill은 팀이 함께 쓰는 skill 저장소에 있었다. 이 아카이브는 보기 쉽게 한 repo에 담고 skill을 `skill/shop-data-analytics/`에 둔다. 아래 설계는 두 저장소를 전제로 쓴다. `locate.sh` 첫머리의 `DEFS_REPO`와 `SKILLS_REPO` 두 줄이 두 저장소의 주소이고, 이 아카이브에서는 둘이 같은 값이다.

같이 읽을 문서: [design.md](design.md)(형식과 파일 구성), [decisions.md](decisions.md)(결정과 이유), [verification.md](verification.md)(검사와 eval).

## 두 저장소에 나누는 기준

기준은 "무엇이 바뀔 때 고치는가"다. 정의 형식이 바뀔 때 함께 바뀌는 글은 정의 저장소에 두고, 분석하는 방식이 바뀔 때 바뀌는 글은 skill에 둔다. 이렇게 나누면 형식을 바꾸는 변경 하나가 읽는 법까지 함께 고치고, 옛 skill이 새 YAML을 잘못 읽어 조용히 틀린 SQL을 만들 틈이 줄어든다.

| 내용 | 두는 곳 |
|---|---|
| skill `shop-data-analytics`: 질문 → SQL → EDA·차트 → 장표. warehouse에는 SELECT만. `scripts/locate.sh`, `VERSION`, test | skill 저장소(아카이브: `skill/shop-data-analytics/`) |
| 정의 쓰기: 근거 찾기 차례, 형식 version 올리는 차례, 검증. 정의 쓰기용 dev skill은 두지 않는다 | 정의 저장소 `semantic/README.md`의 "정의 쓰기" |
| 언제 쓰는지, 실행 모델, 최신 강제, 실패하면 멈춤, 어디서나 지킬 것(정의 밖 추측 금지, PII, 답에 ref) | SKILL.md |
| 읽는 순서, MetricFlow 칸과 `meta.shop`의 뜻, SQL 규칙, 답 끝 기준 block, 정의 쓰는 법 | 정의 저장소 `semantic/README.md`. YAML 형식과 같은 변경에서 고친다 |

skill에는 지표의 뜻을 한 줄도 적지 않는다. skill이 하는 일은 정의 폴더를 최신 main으로 찾아 그곳 README의 "질문에 답하기"를 따르게 하는 것, 그리고 분석 대화를 이어 가는 것뿐이다.

## 두 저장소 약속 셋

skill이 정의 저장소에 기대는 것은 셋뿐이다. 정의 저장소의 test가 셋을 검사한다([verification.md](verification.md)).

1. 경로: 정의 폴더는 저장소 root의 `semantic/`이다(`semantic/settings.py`의 `SEM_DIR`, `locate.sh`의 `SEM`).
2. README 절 이름 둘: "질문에 답하기", "정의 쓰기". skill은 이 이름으로 절을 찾는다.
3. index.md 첫 두 줄: `format: 1`과 `skill_min: 1`. `format`은 정의 형식 version이고, `skill_min`은 이 정의를 읽을 수 있는 가장 낮은 skill `VERSION`이다.

정의 형식(파일 배치, YAML 칸, index.md 약속)을 바꿔 옛 skill이 읽지 못하게 되면 차례가 중요하다. 먼저 skill의 `VERSION`을 올려 skill 저장소 기본 branch에 반영하고, 그다음 `render.py`의 `SKILL_MIN`을 그 값으로 올린다. 순서가 바뀌면 모든 사람의 skill이 종료 코드 5로 멈춘다.

## 최신 강제

`locate.sh`가 skill이 돌 때마다 먼저 실행된다. stdout 한 줄은 정의 폴더의 절대 경로이고, 알림은 stderr의 `key=value` 줄이다. 아무도 손으로 pull하지 않는다는 전제에서 만들었다.

### 답할 때는 항상 origin/main

- 작업 디렉터리가 정의 저장소 checkout이어도 working tree가 아니라 origin/main을 쓴다. fetch한 뒤 `git archive origin/main semantic`으로 꺼낸다(`source=main ref=main@<sha> via=checkout`).
- checkout 밖이면 `git ls-remote`로 main의 sha를 보고, 받아 둔 cache와 같으면 다시 쓴다(`via=cache-current`). 다르면 git sparse clone(`--depth 1 --filter=blob:none --sparse`)으로 `semantic/`만 받는다(`via=clone`). dbt project의 나머지(models, seeds)는 받지 않는다.
- cache는 sha마다 폴더를 따로 둔다. 실행마다 고유한 임시 폴더에 받은 뒤 rename으로 들이고, 현재 sha를 적는 파일도 임시 파일을 rename해 바꾼다. 동시에 돌아도 이미 알려 준 경로가 사라지지 않게, 옛 sha 폴더는 하루 넘게 안 쓴 것만 치운다.
- 정의를 고칠 때만 로컬 working tree를 쓴다. 그때는 skill이 아니라 README "정의 쓰기"를 따른다.
- 한 대화에서는 처음 찾은 정의 폴더와 ref를 끝까지 쓴다. turn마다 정의가 다르면 앞 답과 견줄 수 없다. 날이 바뀌었거나 사용자가 정의를 고쳤다고 하면 다시 실행하고, ref가 달라졌으면 답에 적는다.

### skill 자기 갱신

- skill이 든 clone의 origin URL이 skill 저장소 주소와 정확히 같을 때만 갱신한다. 다른 저장소에 복사한 skill은 갱신하지 않고 `skill_freshness=unmanaged`를 알린다. 그러면 agent는 그대로 진행하되 symlink 설치를 권한다.
- clone이 기본 branch에 있고 깨끗하면 fetch 뒤 `pull --ff-only`를 한다. 갱신했으면 `skill_updated=1`을 알리고, agent는 SKILL.md를 다시 읽고 처음부터 따른다.
- 다른 branch에 있거나, 고친 파일이 있거나, fast-forward가 안 되면 고칠 명령을 알리고 종료 코드 6으로 멈춘다. 아무 저장소나 pull하지 않는다.
- 정의의 `skill_min`이 skill `VERSION`보다 높으면 갱신을 시도하고, 그래도 낮으면 종료 코드 5로 멈춘다.

### 확인 실패 때 동작

- 네트워크나 권한 때문에 최신인지 확인하지 못하면 로컬의 가장 최근 정의(checkout의 origin/main 또는 받아 둔 cache)로 답한다. stderr에 `freshness=unknown last_checked=<시각>`이 나오고, 답의 주의 줄에 "최신 확인 못 한 정의(마지막 확인 <시각>)"를 적는다. 멈추기만 하면 VPN 밖이나 오프라인에서 쓸 수 없다.
- 가진 정의가 없으면 멈춘다. agent는 stderr의 `error=` 줄을 사용자에게 그대로 전하고, 기억이나 mart model SQL을 직접 읽어 지어낸 정의로 답하지 않는다.

| 종료 코드 | 뜻 |
|---|---|
| 0 | 성공 |
| 2 | git이 없다 |
| 3 | main에 semantic layer가 없다 |
| 4 | 정의를 받지 못했고(네트워크·권한) 가진 정의도 없다 |
| 5 | skill이 정의 형식보다 낡았거나(갱신한 뒤에도 낮다) index.md 형식 오류다 |
| 6 | skill 저장소를 자동 갱신할 수 없다(안내된 명령을 사용자가 실행한다) |

`locate.sh`는 시험용 환경 변수로 정의 저장소 주소, cache 폴더, skill 저장소 주소를 바꿀 수 있다. `scripts/test_locate.py`가 가짜 remote로 위 갈래를 모두 돌린다.

## 질문에 답하는 절차

README "질문에 답하기"의 요약이다. 정본은 README다.

1. index.md를 읽는다. 질문의 말이 "뜻이 여럿인 용어"에 있으면 glossary에서 variant를 고른다. 기준을 말하지 않으면 default variant를 쓴다. synonyms(예: DAU)에 있으면 그 용어로 보고, 어느 용어에도 없는 지표 이름을 바로 물으면 variant는 `없음`이다.
2. index.md가 그 table 절의 "읽을 파일"에 적은 두 파일(table 정의, metric 파일)을 연다. long table은 metric filter의 code로 `WHERE <key> = '<code>'`를 쓰고, family는 prefix로 고른 뒤 code별로 묶어 보인다. wide table은 measure의 `expr` column을 쓴다. query_time metric은 measure의 식을 질의 때 계산한다.
3. rollup을 지킨다([design.md의 rollup 표](design.md#rollup-sum--last--none)).
4. 공통 규칙을 본다. `caller`면 `rules.yml`의 SQL 조각을 건다. `not_applied`면 "내부·테스트 판매자의 주문이 섞여 있다"처럼 밝힌다. 스냅샷 table은 as_of_date 하나를 고른다(기본 MAX). long table은 값이 0인 날의 row가 빠질 수 있다. row가 없는 날은 0으로 보고, 데이터가 어디까지 들어왔는지는 그 metric의 마지막 row가 아니라 table의 마지막 날짜로 정한다. 단, metric의 caveats가 측정이 안 되는 기간을 적었으면 그 기간은 "측정 안 됨"이다.
5. 다른 table과 이어야 하면 index.md의 "entity와 관계"에서 via table과 key를 찾는다. 관계 표에 없는 join은 하지 말고 없다고 답한다.
6. 답에 보인 column은 모두 쓴 metric이다. 보조로 보인 column(예: 점수 순위와 함께 낸 tier)도 기준 block의 metrics에 넣는다. conflict인 metric은 뜻을 사실처럼 쓰지 않고 "코드 기준"이라고 붙인다.
7. status가 confirmed가 아니면 그 뜻을 사람 말로 적는다. 열린 question은 묻는 내용을 한 줄로 적는다.
8. 정의에 없는 지표는 없다고 답하고 SQL을 짓지 않는다.
9. SQL은 질문이 묻는 값만 select한다. 설명은 답 글에 쓴다.
10. 기준 block을 만든다. 대화 답에는 보이지 않는다(아래).

기준 block의 모양은 이렇다.

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

## 대화 답의 모양

데이터를 보는 사람에게 YAML은 도움이 안 된다. 그래서 대화로 답할 때는 기준 block을 숨기고, 그 안에서 사람이 알아야 할 것만 끝의 "주의" 한두 줄에 사람 말로 적는다.

- 답의 차례: 결론 한 줄(숫자 포함) → `조건:` 한 줄(기간, variant, 건 규칙, 뺀 날) → 장표(만들었으면) → 표 하나(10 row 안팎) → 발견 3개까지 → 돌린 SQL → 주의 한두 줄 → 다음 분석 선택지.
- 답 글에는 semantic layer 안의 이름(metric 이름, variant, status 값, question id, YAML, 정의 파일 경로)을 쓰지 않고 지표의 뜻으로 쓴다. 예: `su_active_sellers` → "그달 쓴 판매자 수". SQL 안의 table·column·code 값은 그대로 둔다. 무엇을 돌렸는지는 SQL이 보여 준다.
- 주의 줄에 올리는 것: 확정되지 않은 정의(conflict, code_only), 걸지 못한 규칙, 측정 안 된 기간, 최신 확인 못 한 정의.
- 발견마다 표지를 붙인다. `확인`(query 결과로 봤다), `정의`(정의 파일에 적혀 있다), `추정`(둘 다 아니다). 추정에는 무엇을 보면 확정되는지 한 줄을 적고 그 확인을 다음 선택지에 넣는다.
- 다음 분석 선택지는 2~4개를 글 번호 목록으로 준다. 종류(검증, 쪼개기, 넓히기, 견주기, 정리)가 겹치지 않게 고르고, 추천 하나를 맨 위에 둔다. 정의에 있는 metric·dimension·join으로 바로 답할 수 있는 것만 넣는다. 선택 화면 도구는 쓰지 않는다.
- block을 그대로 쓰는 때: 답을 파일로 쓰라는 지시가 있을 때(eval은 block 파일로 채점한다), 사용자가 기준·근거를 물을 때.
- 실행은 warehouse에 SELECT만 돌린다. 집계한 결과만 가져오고 원본 row를 통째로 가져오지 않는다. 결과에 PII가 나오면 id나 집계로 바꿔 보인다.

## skill을 돌리는 모델

SQL을 LLM이 쓰므로 skill에는 모델 하한이 필요하다. 버전 대신 계열 alias(`model: opus`)를 frontmatter에 적었다. 버전을 고정하면 모델이 바뀔 때마다 skill을 고쳐야 한다.

Claude Code에서 직접 돌려 본 결과(2.1.323 기준, 문서 설명과 달랐다)는 이렇다.

| 부르는 법 | 도는 모델 |
|---|---|
| 사용자가 `/shop-data-analytics`로 부름 | frontmatter의 `model`(sonnet 세션에서도 opus) |
| 질문만으로 자동 발동 | 세션 모델(frontmatter `model` 무시) |

- 일반화하면: skill frontmatter의 `model`은 사람이 `/`로 부를 때만 적용된다. 자동 발동에 모델 하한을 걸 방법은 없었다.
- skill 본문에 "opus가 아니면 멈춰라", "opus subagent에 넘겨라"라고 적어도 sonnet 세션은 따르지 않았다(3번). 모델 안내 문구는 한 번도 나오지 않았고, 한 번은 자기를 opus라고 답했다. 모델이 자기 모델을 알아서 판단하게 하는 규칙은 믿을 수 없어 지웠다.
- `context: fork`로 다른 모델 subagent에서 돌게 하는 설정은 발동하지 않았다.
- 강제하려면 `/`로만 부르게 하는 길뿐이다. 그 대가로 자동 발동을 잃는다. 이 설계는 자동 발동을 남기고, 그 사실을 SKILL.md와 설치 안내에 적었다.
- 자동 발동 자체는 잘 됐다. 당시 skill은 분석용과 정의 쓰기용 둘이었고, skill 이름을 말하지 않고 표현을 바꾼 질문 21번에서 모두 맞는 skill이 발동했다.
