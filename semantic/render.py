"""정의 → 생성물. index.md(LLM 목차, commit함)와 graph(node·edge JSON, 필요할 때 --graph로 만듦).

생성물은 commit하고, 검사가 다시 만든 결과와 byte로 견준다. 손으로 고치지 않는다.
실행: python -m semantic.render  (저장소 루트에서)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

from semantic import settings

_Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)   # libyaml이 있으면 빠른 쪽

FORMAT = 1       # 두 저장소 약속: skill은 index.md 첫머리의 format을 읽는다
SKILL_MIN = 1    # 이 정의를 읽으려면 skill version이 이 값 이상이어야 한다(spec D40)


def _docs(path: Path):
    return [d for d in yaml.load_all(path.read_text(encoding="utf-8"), Loader=_Loader) if d]


def load(sem: Path) -> dict:
    """manifest를 표준 parser 없이 원문 그대로 읽는다(생성물은 원문 순서를 따른다)."""
    models, metrics = [], []
    for path in sorted((sem / "manifest").rglob("*.yml")):
        rel = str(path.relative_to(sem))
        for d in _docs(path):
            if isinstance(d, dict) and isinstance(d.get("semantic_model"), dict):     # 모양이 틀린 문서는 검사(_layout)가 따로 알린다
                models.append({**d["semantic_model"], "_file": rel})
            elif isinstance(d, dict) and isinstance(d.get("metric"), dict):
                metrics.append({**d["metric"], "_file": rel})
    side = {name: yaml.load((sem / f"{name}.yml").read_text(encoding="utf-8"), Loader=_Loader)
            for name in ("sources", "entities", "rules")}
    side["glossary"] = {"terms": side_items(sem, "glossary")}
    side["questions"] = {"questions": side_items(sem, "questions")}
    return {"models": models, "metrics": metrics, **side}


SIDE_DIRS = ("glossary", "questions")   # 항목 하나에 파일 하나인 옆 폴더(spec D52·D56): <폴더>/<id>.yml


def side_items(sem: Path, folder: str) -> list:
    """<folder>/<id>.yml을 파일 이름순으로 읽는다. 파일 하나가 항목 하나(mapping)다."""
    items = [yaml.load(p.read_text(encoding="utf-8"), Loader=_Loader) for p in sorted((sem / folder).glob("*.yml"))]
    return [x for x in items if isinstance(x, dict) and "id" in x]   # 모양이 틀린 파일은 검사가 따로 알린다


def _ext(obj) -> dict:
    """config.meta.<namespace>: 표준에 없는 뜻을 담는 곳."""
    return ((obj.get("config") or {}).get("meta") or {}).get(settings.NAMESPACE) or {}


def _measure_index(d) -> dict:
    return {x["name"]: (m, x) for m in d["models"] for x in m.get("measures") or []}


def graph(d) -> dict:
    nodes, edges = {}, []

    def node(typ, nid, label, file, **attrs):
        nodes[f"{typ}:{nid}"] = {"id": f"{typ}:{nid}", "type": typ, "label": label, "file": file, "attrs": attrs}

    def edge(frm, typ, to, owner, **attrs):
        edges.append({"from": frm, "type": typ, "to": to, "owner": owner, "attrs": attrs})

    grade = {s["id"]: s["grade"] for s in d["sources"]["sources"]}
    for s in d["sources"]["sources"]:
        node("source", s["id"], s["label"], "sources.yml", grade=s["grade"], kind=s["kind"])
    for q in d["questions"]["questions"]:
        node("question", q["id"], q["question"], f"questions/{q['id']}.yml", ask=q["ask"], state=q["state"])
    for r in d["rules"]["rules"]:
        node("rule", r["id"], r["label"], "rules.yml")
    for e in d["entities"]["entities"]:
        node("entity", e["id"], e["label"], "entities.yml", keys=e["keys"])
    for m in d["models"]:
        w, f = _ext(m), m["_file"]
        expr = {e["name"]: e.get("expr", e["name"]) for e in m.get("entities") or []}
        via = f"{m['node_relation']['schema_name']}.{m['node_relation']['alias']}"
        if w.get("role") == "relation":
            for r in w.get("relations") or []:
                edge(f"entity:{r['from']}", "join", f"entity:{r['to']}", f, cardinality=r["cardinality"],
                     via=via, from_key=expr[r["from"]], to_key=expr[r["to"]])
                for q in r.get("questions") or []:
                    edge(f"entity:{r['from']}", "question", f"question:{q}", f, about=f"join {r['to']}")
            continue
        node("table", m["name"], m.get("description", ""), f, table=via, shape=w.get("shape"), grain=w.get("grain"))
        node("sql", w["defined_in"], w["defined_in"], w["defined_in"])
        edge(f"table:{m['name']}", "sql", f"sql:{w['defined_in']}", f)
        for name, col in expr.items():
            edge(f"table:{m['name']}", "entity", f"entity:{name}", f, column=col)
        for rid, state in (w.get("rules") or {}).items():
            edge(f"table:{m['name']}", "rule", f"rule:{rid}", f, state=state)
        for other in (w.get("long") or {}).get("inherits") or []:
            edge(f"table:{m['name']}", "inherits_codes", f"table:{other}", f)
    measures = _measure_index(d)
    by_name = {x["name"]: x for x in d["metrics"]}
    for x in d["metrics"]:
        w, f, mid = _ext(x), x["_file"], f"metric:{x['name']}"
        model, meas = measures.get(_base_measure(x, by_name), ({}, {}))
        node("metric", x["name"], x.get("label", ""), f, kind=w.get("kind"), status=w.get("status"),
             rollup=_ext(meas).get("rollup"))
        if model:
            edge(mid, "table", f"table:{model['name']}", f)
        if w.get("counts"):
            edge(mid, "counts", f"entity:{w['counts']}", f)
        for sid in w.get("docs") or []:
            edge(mid, "source", f"source:{sid}", f, grade=grade.get(sid))
        for q in w.get("questions") or []:
            edge(mid, "question", f"question:{q}", f)
    for t in d["glossary"]["terms"] or []:
        gf = f"glossary/{t['id']}.yml"
        node("term", t["id"], t["label"], gf, synonyms=t.get("synonyms") or [])
        if t.get("question"):
            edge(f"term:{t['id']}", "question", f"question:{t['question']}", gf)
        edge(f"term:{t['id']}", "default", f"variant:{t['id']}.{t['default']}", gf)
        for v in t["variants"]:
            vid = f"variant:{t['id']}.{v['id']}"
            node("variant", f"{t['id']}.{v['id']}", v["label"], gf, not_in_mart=v.get("not_in_mart"))
            edge(vid, "term", f"term:{t['id']}", gf)
            for n in v.get("metrics") or []:
                edge(vid, "metric", f"metric:{n}", gf)
            for sid in v.get("used_by") or []:
                edge(vid, "used_by", f"source:{sid}", gf)
    return {"format": FORMAT, "nodes": sorted(nodes.values(), key=lambda n: n["id"]), "edges": edges}


_FILTER = re.compile(r"\{\{ Dimension\('[a-z0-9_]+__([a-z0-9_]+)'\) \}\} (=|!=|<>|LIKE) ('[^']*'|[0-9]+)")


def _base_measure(x, by_name: dict, seen=()):
    """metric이 기대는 measure 이름. ratio는 분자 metric을 따라간다(table을 찾고 index 표에 올리려고)."""
    tp = x.get("type_params") or {}
    if tp.get("measure"):
        return tp["measure"]
    num = (tp.get("numerator") or {}).get("name")
    if num in by_name and num not in seen:
        return _base_measure(by_name[num], by_name, seen + (num,))
    return None


def _code(x) -> str:
    """metric filter를 사람이 읽는 조건으로. 예: metric = 'dau', metric_source != 'cust_serv'."""
    hit = _FILTER.search(x.get("filter") or "")
    if hit:
        return f"{hit.group(1)} {hit.group(2)} {hit.group(3)}"
    return "(filter 없음)" if not x.get("filter") else x["filter"]


def metric_path(domain: str, model: str, name: str | None = None) -> str:
    """metric 폴더 manifest/metrics/<domain>/<table>, name을 주면 그 metric 파일(정의 폴더 기준, spec D54·D59)."""
    base = f"manifest/metrics/{domain}/{model}"
    return base if name is None else f"{base}/{name}.yml"


def _metric_dir(m) -> str:
    """model 파일 manifest/tables/<domain>/<table>.yml의 metric 폴더."""
    return metric_path(Path(m["_file"]).parent.name, m["name"])


def index_md(d) -> str:
    measures = _measure_index(d)
    L = [f"format: {FORMAT}", f"skill_min: {SKILL_MIN}", "",
         f"# {settings.PROJECT} semantic layer 목차 (생성물, 손으로 고치지 않는다)", "",
         "읽는 순서는 README.md의 \"질문에 답하기\"를 따른다.", "", "## 뜻이 여럿인 용어", ""]
    for t in d["glossary"]["terms"] or []:
        syn = ", ".join(t.get("synonyms") or []) or "-"
        L.append(f"- **{t['label']}** (`{t['id']}`, 기본 `{t['default']}`, 확인 질문 {t.get('question', '-')}, 같은 말: {syn})")
        for v in t["variants"]:
            target = ", ".join(v.get("metrics") or []) or f"mart에 없음: {v.get('not_in_mart')}"
            L.append(f"  - `{v['id']}` {v['label']} → {target}")
    L += ["", "## entity와 관계(join 경로)", "", "| from | to | cardinality | via table | 이 table의 key(같은 row에 함께 있음) |", "|---|---|---|---|---|"]
    for m in d["models"]:
        w = _ext(m)
        if w.get("role") != "relation":
            continue
        expr = {e["name"]: e.get("expr", e["name"]) for e in m.get("entities") or []}
        via = f"{m['node_relation']['schema_name']}.{m['node_relation']['alias']}"
        for r in w.get("relations") or []:
            L.append(f"| {r['from']} | {r['to']} | {r['cardinality']} | {via} | "
                     f"{expr[r['from']]}, {expr[r['to']]} |")
    L += ["", "## table과 metric", ""]
    by_model = {}
    by_name = {x["name"]: x for x in d["metrics"]}
    for x in d["metrics"]:
        model, _ = measures.get(_base_measure(x, by_name), ({"name": "-"}, {}))
        by_model.setdefault(model["name"], []).append(x)
    for m in d["models"]:
        w = _ext(m)
        if w.get("role") == "relation":
            continue
        rules = ", ".join(f"{k}={v}" for k, v in (w.get("rules") or {}).items() if v in ("caller", "not_applied"))
        L += [f"### {m['name']}", "",
              f"- table `{m['node_relation']['schema_name']}.{m['node_relation']['alias']}` · "
              f"shape {w.get('shape')} · grain {w.get('grain')}",
              f"- 읽을 파일: table 정의 `{m['_file']}`"
              + (f" + metric `{_metric_dir(m)}/<metric>.yml`" if by_model.get(m["name"]) else " (metric 없음)"),
              f"- 주의할 규칙: {rules or '없음'}", "",
              "| metric | 뜻 | 고르는 법 | kind | rollup | status | 세는 것 | 질문 |", "|---|---|---|---|---|---|---|---|"]
        for x in by_model.get(m["name"], []):
            xw = _ext(x)
            tp = x.get("type_params") or {}
            if tp.get("measure"):
                code, rollup = f"`{_code(x)}`", _ext(measures[tp["measure"]][1]).get("rollup")
            else:   # ratio: 분자·분모 metric을 기간으로 각각 더한 뒤 나눈다
                side = lambda k: (f"{(tp.get(k) or {}).get('name')}"
                                  + (f" where {_code(tp[k])}" if (tp.get(k) or {}).get("filter") else ""))
                code = f"`{side('numerator')}` ÷ `{side('denominator')}`"
                rollup = "ratio"
            L.append(f"| {x['name']} | {x.get('label', '')} | {code} | {xw.get('kind')} | "
                     f"{rollup} | {xw.get('status')} | {xw.get('counts', '-')} | "
                     f"{', '.join(xw.get('questions') or []) or '-'} |")
        L.append("")
    L += ["## owner 확인 목록", "", "| id | 물어볼 곳 | 질문 | 상태 |", "|---|---|---|---|"]
    for q in d["questions"]["questions"]:
        L.append(f"| {q['id']} | {', '.join(q['ask'])} | {q['question']} | {q['state']} |")
    return "\n".join(L).rstrip() + "\n"


def render_sem(sem: Path, d=None) -> dict:
    """commit하는 생성물(정의 폴더 기준 경로 → 내용). graph.json은 commit하지 않는다(spec D66)."""
    d = d or load(Path(sem))
    return {"index.md": index_md(d)}


def render_all(repo) -> dict:
    """저장소 루트 기준 경로 → 내용."""
    sem = Path(repo) / settings.SEM_DIR
    return {f"{settings.SEM_DIR}/{k}": v for k, v in render_sem(sem).items()}


USAGE = ("사용(저장소 루트에서): python -m semantic.render            index.md를 다시 만든다\n"
         "                         python -m semantic.render --graph F  graph(node·edge JSON)를 F에 쓴다(commit하지 않는다)")


def main(argv=()) -> int:
    argv = list(argv)
    sem = Path(settings.SEM_DIR)
    if not (sem / "manifest").is_dir():
        print(f"정의 폴더 {sem}/manifest가 없다. 저장소 루트에서 돌린다.\n{USAGE}", file=sys.stderr)
        return 2
    if len(argv) == 2 and argv[0] == "--graph":
        Path(argv[1]).write_text(json.dumps(graph(load(sem)), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {argv[1]}")
        return 0
    if argv:
        print(USAGE, file=sys.stderr)
        return 2
    for path, text in render_all(".").items():
        Path(path).write_text(text, encoding="utf-8")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
