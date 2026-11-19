"""실제 정의 폴더 검사(빠름). 늘 돈다(Makefile ci-local).

정의를 일부러 망가뜨려 보는 검사 test(느림)는 test_semantic_layer.py에 있고, 검사 코드가 바뀔 때만 돈다.
"""
from pathlib import Path


from src.bi.semantic import checks, render

REPO = Path(__file__).resolve().parents[3]
SEM = REPO / "src" / "bi" / "semantic"
DIM_MEMBER = "manifest/tables/relations/dim_member_seller.yml"


def test_repo_manifest_passes_standard_validator():
    manifest, problems = checks.standard(SEM / "manifest")
    assert problems == []
    assert manifest is not None and manifest.metrics


def test_repo_definitions_have_no_problems():
    assert checks.problems(REPO) == []


def test_s4_generated_files_match_definitions():
    for path, text in render.render_all(REPO).items():
        assert (REPO / path).read_text(encoding="utf-8") == text, f"{path}가 낡았다. render를 돌린다"


def test_s4_graph_has_explicit_relation_edges():
    graph = render.graph(render.load(SEM))      # graph.json은 commit하지 않는다
    edges = {(e["from"], e["type"], e["to"]): e for e in graph["edges"]}
    rel = edges[("entity:member", "join", "entity:seller")]
    assert rel["attrs"] == {"cardinality": "many_to_many", "via": "silver.dim_member_seller",
                            "from_key": "member_id", "to_key": "seller_id"}
    assert rel["owner"] == DIM_MEMBER
    assert ("metric:dau", "counts", "entity:member") in edges
    assert ("variant:active_user.login", "metric", "metric:dau") in edges
    # edge 이름은 "출발 node의 무엇"으로 읽히는 명사
    assert ("metric:dau", "table", "table:shop_kpi_daily") in edges
    assert ("metric:dau", "source", "source:wiki.metric-criteria") in edges
    assert ("table:shop_kpi_daily", "sql", "sql:src/aggregation/commerce/gold_shop_kpi_daily.sql") in edges
    assert {e["type"] for e in graph["edges"]} == {"table", "counts", "source", "question", "entity", "sql", "rule",
                                                  "inherits_codes", "join", "metric", "term", "default", "used_by"}
    assert {n["type"] for n in graph["nodes"]} == {"metric", "table", "entity", "source", "question", "rule", "sql",
                                                  "term", "variant"}
    assert graph["format"] == 1


def test_s7_eval_questions_point_to_existing_definitions():
    import yaml

    graph = render.graph(render.load(SEM))
    ids = {n["id"] for n in graph["nodes"]}
    qs = yaml.safe_load((REPO / "tests/bi/semantic/eval/questions.yml").read_text(encoding="utf-8"))["questions"]
    assert len(qs) == 10
    for q in qs:
        want = q["expect"]
        for m in want.get("metrics") or []:
            assert f"metric:{m}" in ids, (q["id"], m)
        if want.get("variant"):
            assert f"variant:{want['variant']}" in ids, (q["id"], want["variant"])
        for qid in want.get("questions") or []:
            assert f"question:{qid}" in ids, (q["id"], qid)
        for v in want.get("other_variants") or []:
            assert f"variant:{v}" in ids, (q["id"], v)
        assert bool(q.get("sql")) == bool(want.get("metrics")), q["id"]   # 거절 문항만 sql이 없다


def test_split_index_shows_files_to_read():
    index = (SEM / "index.md").read_text(encoding="utf-8")
    assert ("- 읽을 파일: table 정의 `manifest/tables/commerce/shop_kpi_daily.yml` + "
            "metric `manifest/metrics/commerce/shop_kpi_daily/<metric>.yml`") in index
    assert index.splitlines()[:2] == ["format: 1", "skill_min: 1"]
