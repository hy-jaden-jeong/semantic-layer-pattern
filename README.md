# semantic-layer-pattern

dbt project의 mart layer 위에 얹는 semantic layer 템플릿이다. LLM agent가 정의 파일만 읽고 지표를 맞게 골라 SQL을 쓰게 한다. 정의는 git에 둔 YAML이고, 읽는 데 dbt도 warehouse도 필요 없다.

회사 업무에서 설계한 semantic layer를, dbt project의 mart layer 위에 얹는다고 가정하고 가상 쇼핑몰 도메인(`shop-bi`)으로 다시 썼다. 지표와 data는 모두 지어낸 예제이고, 예제는 DuckDB에서 끝까지 돈다. 가져다 쓰기 쉽게 MIT license로 둔다.

![LLM은 skill로 들어와 정의 파일만 읽고 SQL을 쓴다](docs/img/overview.png)

## 푸는 문제

mart와 대시보드는 돌아가는데 지표의 뜻이 SQL 안과 wiki 여러 곳에 흩어져 있다. "활성 회원"처럼 같은 이름이 서너 가지 뜻으로 쓰이고, 사람이든 LLM이든 새 질문마다 table·column·공통 filter를 다시 찾다가 틀린다.

## 설계의 핵심

1. **정본은 업계 표준 형식이다.** MetricFlow semantic manifest YAML을 그대로 쓰고, 표준에 없는 뜻은 `config.meta.<namespace>`에, 어느 표준에도 자리가 없는 것은 옆 파일에 둔다. → [docs/design.md](docs/design.md)
2. **파일 하나에 정의 하나다.** table 정의 파일과 metric 파일을 나누고, 생성물 `index.md`를 진입점으로 삼는다. LLM은 지표 하나에 답할 때 파일 둘만 읽고, 사람이 지표 하나를 더하면 diff가 그 파일에만 생긴다.
3. **모호함을 지우지 않고 적는다.** 뜻이 여럿인 용어는 term → variant → metric으로 나눠 모두 두고, metric마다 status(`confirmed` · `code_only` · `conflict` · `query_time`)와 원본 등급(A~D)을 붙이고, 정본을 정할 owner에게 물을 질문을 목록으로 남긴다.
4. **합산 규칙을 정의에 적는다.** measure마다 rollup `sum` · `last` · `none`을 적어, 이미 중복을 뺀 값을 날짜를 넘어 더하는 실수를 막는다.
5. **정의 없는 지표는 검사가 막는다.** mart model의 SQL에서 지표 code를 뽑아 정의와 견주고, 빠진 것이 있으면 만들 파일 경로와 붙여 넣을 최소 문서를 보여 주며 실패한다. 읽지 못한 SQL 갈래도 실패다. → [docs/verification.md](docs/verification.md)
6. **검사를 검사한다.** 정의를 하나씩 망가뜨린 사본에서 검사가 그 문제를 잡는지 test로 본다.
7. **LLM은 얇은 skill로 들어온다.** skill에는 지표의 뜻이 한 줄도 없다. skill은 정의 폴더를 최신 main으로 찾아 그곳 README를 따르게 할 뿐이고, 읽는 법은 YAML 형식과 같은 변경에서 고친다. → [docs/llm-entry.md](docs/llm-entry.md)
8. **정답률은 질문 eval로 본다.** 새 agent가 질문에 SQL과 기준 block으로 답하고, 정답 SQL과 결과를 견준다.

결정마다 이유와 버린 후보는 [docs/decisions.md](docs/decisions.md)에 있다.

## dbt와의 관계

- pipeline은 dbt가 맡는다: `models/staging` → `models/intermediate` → `models/marts`. semantic layer는 mart만 덮는다.
- 정의 폴더 `semantic/`은 dbt의 model-paths 밖에 있다. dbt project YAML(`semantic_models:`)이 아니라 standalone manifest라서, 파일 하나에 정의 하나를 두고 dbt profile 없이 오프라인 test로 검사한다.
- 정의와 mart를 잇는 것은 `node_relation`(schema.alias)과 `defined_in`(model 파일 경로)이다. 검사가 둘이 맞는지 본다.
- mart model의 column은 dbt contract로 선언한다. dbt가 build 때 SQL과 맞는지 강제하고, 검사는 그 yml을 읽는다.
- 지표 code를 정하는 규칙은 dbt seed이고, 내부 판매자를 빼는 조각의 정본은 dbt macro다. 정의의 SQL 조각은 그 macro를 render한 것과 같아야 한다.

## 폴더

| 경로 | 담는 것 |
|---|---|
| `semantic/` | 정의 폴더. README(읽는 법·쓰는 법), `index.md`(생성물), `manifest/`(table 5개, 관계 2개, metric 32개), `glossary/`, `questions/`, 옆 파일 넷, 그리고 `settings.py` · `catalog.py` · `checks.py` · `render.py` |
| `skill/shop-data-analytics/` | data analytics skill. 지표 고르기 → SQL → EDA를 대화로 잇기 → 차트·장표. `SKILL.md`, `VERSION`, `scripts/locate.sh`와 그 test |
| `models/`, `seeds/`, `macros/` | 예제 dbt project. 정의가 가리키는 mart와 그 아래 layer, 가상 raw data |
| `tests/semantic/` | 실제 정의 검사, 정의를 망가뜨려 보는 test, eval 질문 10개 |
| `scripts/` | 질문 eval(`semantic_eval.py`), 가상 raw data 만들기(`gen_raw_seeds.py`) |
| `docs/` | 설계([design](docs/design.md)), 결정과 이유([decisions](docs/decisions.md)), LLM이 들어오는 길([llm-entry](docs/llm-entry.md)), 검사와 검증([verification](docs/verification.md)) |

원래 설계는 정의 저장소와 skill 저장소가 서로 다른 repo다. 여기서는 한 repo에 담았다.

## 돌려 보기

Python 3.10 이상이 필요하다.

```bash
python3.12 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
```

정의 검사와 망가뜨려 보는 test 68개를 돌린다. dbt도 warehouse도 필요 없다(DuckDB 파일이 있으면 catalog가 읽은 column이 실제 mart와 같은지도 본다).

```bash
make test
```

예제 mart를 DuckDB 파일(`shop_bi.duckdb`)에 만든다.

```bash
make build
```

skill의 `locate.sh` test 37개는 따로 돌린다.

```bash
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m pytest -q -p no:cacheprovider skill/shop-data-analytics/scripts/test_locate.py
```

검사가 일하는 모습을 보려면 `semantic/manifest/metrics/commerce/shop_kpi_daily/wau.yml`을 다른 곳으로 옮기고 `make test`를 돌린다. "mart에 있는 지표 'wau'가 정의에 없다"와 함께 만들 파일 경로, 붙여 넣을 metric 문서가 나온다.

## data analytics skill 써 보기

skill을 symlink로 걸면 Claude Code에서 "지난달 활성 판매자 수", "MAU 추이 차트로" 같은 질문에 켜진다.

```bash
ln -s "$(pwd)/skill/shop-data-analytics" ~/.claude/skills/shop-data-analytics
```

skill은 돌 때마다 이 repo의 main에서 `semantic/`을 받아 그곳 README대로 지표를 고르고 SQL을 쓴다. 답마다 다음 분석 선택지를 붙여 EDA를 대화로 이어 간다. SQL을 돌릴 곳은 `make build`가 만든 `shop_bi.duckdb`다.

## 자기 dbt project에 옮기기

1. `semantic/`(Python 넷과 README), `tests/semantic/`, `skill/`을 가져간다. 예제 정의(`manifest/`, `glossary/`, `questions/`, 옆 파일의 내용)는 비운다.
2. `semantic/settings.py`를 고친다: namespace(`config.meta.<이름>`), project 이름, layer 폴더와 schema의 대응, semantic layer가 덮을 schema.
3. mart model에 column을 선언한다(model yml의 `columns`, 되도록 contract). long table의 지표 code는 literal · `CASE` · 앞 literal 이어 붙이기로 쓴다. `catalog.py`는 dbt model의 SELECT를 regex로 읽는다. SQL을 쓰는 방식이 많이 다르면 여기를 고친다. 쓰는 쪽은 `tables()` · `long_codes()` · `seed_codes()` · `view_columns()` · `macro_sql()`만 안다.
4. `rules.yml`에 공통 규칙을 적는다. SQL 조각을 macro와 견주는 검사(`checks._side_files`)는 자기 macro 이름에 맞춘다.
5. 정의를 쓴다. 정의 폴더 README의 "정의 쓰기"가 차례를 알려 주고, `make test`의 실패 메시지가 빠진 파일과 붙여 넣을 문서를 알려 준다.
6. skill은 `locate.sh` 첫머리의 `DEFS_REPO` · `SKILLS_REPO` 두 줄과 `SKILL.md`의 이름·description을 바꾼다.
7. test의 문자열(예제 metric 이름, SQL 조각)은 자기 정의에 맞게 바꾼다. 무엇을 망가뜨려 보는지는 그대로 쓴다.

## 알아 둘 것

- 예제는 DuckDB(dbt-duckdb)에서 돈다. 다른 warehouse에서는 model의 날짜 함수와 `scripts/semantic_eval.py`의 `_connect` · `_run_sql`을 바꾼다.
- 실제 적용에서는 table 18개, metric 약 300개 규모였다. 이 예제는 설계의 갈래(long·wide table, family, seed가 정하는 code, 물려받는 code, 스냅샷, ratio, query_time)가 하나씩 보이도록 줄였다.
- 검사는 hook이 아니다. 정의나 mart model을 고친 사람이 `make ci-local`을 직접 돌린다.

## License

[MIT](LICENSE)
