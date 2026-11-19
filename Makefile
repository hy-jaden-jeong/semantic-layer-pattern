# 로컬 검사. `make ci-local`은 오프라인에서 돈다(네트워크·인증·warehouse가 필요 없다).
# hook으로 걸지 않는다. 정의나 mart model을 고친 사람이 PR 전에 직접 돌린다.
#
# python은 .venv를 쓴다. 시스템 python에는 yaml·metricflow가 없어 pytest가 수집 단계에서 깨진다.

PY := ./.venv/bin/python
DBT := ./.venv/bin/dbt

.PHONY: ci-local test build render

# 실제 정의 검사(tests/semantic/test_repo_definitions.py)는 늘 돈다. mart model·seed·macro만 바뀌어도
# 정의 없는 지표와 빠진 model을 잡는다. 정의를 망가뜨려 보는 검사 test(test_semantic_layer.py, 느림)는
# 검사 코드·정의가 main 대비 바뀐 branch에서만 돈다. 전부: make test.
SEMANTIC_PATHS := semantic tests/semantic requirements.txt

ci-local:
	@base=$$(git merge-base HEAD origin/main 2>/dev/null); \
	if [ -z "$$base" ] || [ -n "$$(git diff --name-only $$base -- $(SEMANTIC_PATHS))" ]; then \
		$(MAKE) -s test; \
	else \
		echo "[make] semantic layer 검사 코드가 그대로라 test_semantic_layer.py를 건너뛴다(전부: make test)"; \
		$(MAKE) -s test PYTEST_ARGS=--ignore=tests/semantic/test_semantic_layer.py; \
	fi

test:
	@test -x $(PY) || { echo "[make] .venv가 없다. Python 3.10 이상으로 만들고 다시: python3.12 -m venv .venv && ./.venv/bin/pip install -r requirements.txt"; exit 1; }
	$(PY) -m pytest -q $(PYTEST_ARGS)

# 예제 mart를 DuckDB 파일(shop_bi.duckdb)에 만든다. model contract가 mart column을 강제한다.
build:
	$(DBT) build --profiles-dir .

# 정의를 고친 뒤 생성물(semantic/index.md)을 다시 만든다.
render:
	$(PY) -m semantic.render
