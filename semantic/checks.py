"""semantic layer 정의 검사.

표준(MetricFlow parser + validator)이 형식을 보고, 여기서는 표준이 보지 않는 것을 본다:
config.meta.<namespace> 형식, filter가 가리키는 dimension, mart model과의 대응(빠진 지표), 원본·status 규칙, 관계, 용어.
쓰는 쪽은 problems()만 안다. 문제가 없으면 빈 목록이다.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

_Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)   # libyaml이 있으면 빠른 쪽
from metricflow_semantic_interfaces.parsing.dir_to_model import (
    parse_directory_of_yaml_files_to_semantic_manifest,
)
from metricflow_semantic_interfaces.validations.semantic_manifest_validator import (
    SemanticManifestValidator,
)

from semantic import catalog, render, settings

NS = settings.NAMESPACE   # config.meta.<NS>

STATUS = {"confirmed", "code_only", "conflict", "query_time"}
ROLLUP = {"sum", "last", "none"}
KIND = {"count", "sum", "distinct_count", "ratio", "avg", "percentile", "score", "grade", "date", "amount"}
RULE_STATE = {"applied", "caller", "not_applied", "na"}
CARDINALITY = {"one_to_one", "many_to_one", "many_to_many"}
GRADE = {"A", "B", "C", "D"}
# meta.<NS> 안에서 허용하는 key: (꼭 있어야 하는 것, 있어도 되는 것)
META_KEYS = {
    "model": ({"defined_in"}, {"shape", "long", "grain", "rules", "role", "relations", "time_format", "skip_columns",
                               "metric_prefix"}),
    "measure": ({"rollup"}, set()),
    "metric": ({"kind", "status", "docs"}, {"counts", "unit", "questions", "caveats", "synonyms"}),
    "dimension": (set(), {"values", "format"}),
}
_EQ = re.compile(r"^\{\{ Dimension\('([a-z0-9_]+)__([a-z0-9_]+)'\) \}\} = '([a-z0-9_]+)'$")
# PII 흔적: 이메일, 전화번호, 법인 표기. 사람 이름은 regex로 잡지 못한다(sources.yml에는 팀·역할만 적는다).
_PII = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "이메일"),
    (re.compile(r"(?<!\d)(?:\+82[-.\s]?1\d|01\d)[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)"), "휴대전화"),
    (re.compile(r"(?<!\d)0\d{1,2}-\d{3,4}-\d{4}(?!\d)"), "전화번호"),
    (re.compile(r"\(주\)|㈜|주식회사|유한회사"), "법인 표기"),
]
SOURCE_KEYS = {"id", "label", "kind", "ref", "owner", "grade", "checked_on", "use"}
QUESTION_KEYS = {"id", "ask", "question", "evidence", "state"}
_PLACEHOLDER = re.compile(r"<[^>]*>|\bTODO\b")
_LIKE = re.compile(r"^\{\{ Dimension\('([a-z0-9_]+)__([a-z0-9_]+)'\) \}\} LIKE '([a-z0-9_]+)%([a-z0-9_]*)'$")


def default_sem(repo) -> Path:
    return Path(repo) / settings.SEM_DIR


def standard(manifest_dir):
    """MetricFlow 표준 parse + validator. (manifest 또는 None, 문제 목록)"""
    try:
        parsed = parse_directory_of_yaml_files_to_semantic_manifest(str(manifest_dir))
    except Exception as e:  # schema 위반은 예외로 나온다
        return None, [f"[표준] {str(e)[:400]}"]
    errors = [f"[표준] {i.message}" for i in parsed.issues.errors]
    if errors:
        return None, errors
    result = SemanticManifestValidator().validate_semantic_manifest(parsed.semantic_manifest)
    found = [f"[표준] {e.message}" for e in result.errors]
    found += [f"[표준 경고] {w.message}" for w in result.warnings]   # 경고도 0이어야 한다(B21)
    return parsed.semantic_manifest, found


def problems(repo, sem=None, coverage: bool = True) -> list:
    """정의 폴더(sem, 기본 settings.SEM_DIR) 전체를 검사한다. coverage는 mart model의 지표가 다 정의됐는지(D15)."""
    repo, sem = Path(repo), Path(sem) if sem else default_sem(repo)
    manifest, found = standard(sem / "manifest")
    found += _side_files(repo, sem)
    found += _layout(sem)
    found += _generated(repo, sem)
    if manifest is None:
        return found
    return found + _definitions(manifest, sem, repo, coverage)


README_SECTIONS = ("## 질문에 답하기", "## 정의 쓰기")


def _model_domains(sem: Path) -> dict:
    """table name -> manifest/tables/ 아래의 domain 폴더 이름."""
    out = {}
    for path in sorted((sem / "manifest" / "tables").glob("*/*.yml")):
        for d in yaml.load_all(path.read_text(encoding="utf-8"), Loader=_Loader):
            if d and "semantic_model" in d:
                out[d["semantic_model"].get("name")] = path.parent.name
    return out


def _layout(sem: Path) -> list:
    """B27·D61: semantic_model 파일과 metric 파일은 하나에 문서 하나, 파일 이름 = name, metric은 자기 table 폴더에."""
    out, man = [], sem / "manifest"
    owner = {}                                   # measure name -> (model name, domain)
    files = []
    for path in sorted(man.rglob("*.yml")):
        rel = path.relative_to(man)
        docs = [d for d in yaml.load_all(path.read_text(encoding="utf-8"), Loader=_Loader) if d]
        files.append((path, rel, docs))
        if rel.parts[0] == "tables" and len(rel.parts) == 3 and len(docs) == 1 and "semantic_model" in docs[0]:
            sm = docs[0]["semantic_model"]
            for x in sm.get("measures") or []:
                owner[x.get("name")] = (sm.get("name"), rel.parts[1])
    for path, rel, docs in files:
        where = f"manifest/{rel.as_posix()}"
        kind = next(iter(docs[0]), None) if len(docs) == 1 and isinstance(docs[0], dict) else None
        if rel.as_posix() == "project.yml":          # parser가 읽으니 여기에 다른 문서를 붙이지 못하게 한다
            if kind != "project_configuration" or len(docs[0]) != 1:
                out.append(f"{where}: project.yml에는 project_configuration 문서 하나만 둔다")
            continue
        if rel.parts[0] == "tables" and len(rel.parts) == 3:
            if kind != "semantic_model" or len(docs[0]) != 1 or not isinstance(docs[0]["semantic_model"], dict):
                out.append(f"{where}: table 정의 파일에는 semantic_model 문서 하나만 둔다(metric은 manifest/metrics/ 아래)")
            elif docs[0]["semantic_model"].get("name") != path.stem:
                out.append(f"{where}: 파일 이름이 semantic_model name({docs[0]['semantic_model'].get('name')})과 다르다")
        elif rel.parts[0] == "metrics" and len(rel.parts) == 4:
            if kind != "metric" or len(docs[0]) != 1 or not isinstance(docs[0]["metric"], dict):
                out.append(f"{where}: metrics 파일에는 metric 문서 하나만 둔다")
                continue
            x = docs[0]["metric"]
            if x.get("name") != path.stem:
                out.append(f"{where}: 파일 이름이 metric name({x.get('name')})과 다르다")
            measure = (x.get("type_params") or {}).get("measure")
            if isinstance(measure, dict):
                measure = measure.get("name")
            if measure in owner and owner[measure] != (rel.parts[2], rel.parts[1]):
                model, domain = owner[measure]
                out.append(f"{where}: measure {measure}는 {model}에 있다. {render.metric_path(domain, model, x.get('name'))}로 옮긴다")
        else:
            out.append(f"{where}: 정의 파일은 manifest/tables/<domain>/<table>.yml이나 "
                       "manifest/metrics/<domain>/<table>/<metric>.yml에 둔다")
    return out


def _generated(repo: Path, sem: Path) -> list:
    """생성물이 정의와 같은지, 두 저장소 약속(README 절 이름, index.md 첫머리)이 지켜지는지(B13, B16)."""
    out = []
    d = render.load(sem)
    expected = [(name, sem / name, text) for name, text in render.render_sem(sem, d).items()]
    for name, path, text in expected:
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            out.append(f"{name}: 생성물이 낡았다. python -m semantic.render를 돌린다")
    readme = (sem / "README.md").read_text(encoding="utf-8") if (sem / "README.md").exists() else ""
    for section in README_SECTIONS:
        if section not in readme.splitlines():
            out.append(f"README.md: skill이 찾는 절 \"{section}\"이 없다(두 저장소 약속)")
    index = (sem / "index.md").read_text(encoding="utf-8").splitlines() if (sem / "index.md").exists() else []
    if index[:2] != [f"format: {render.FORMAT}", f"skill_min: {render.SKILL_MIN}"]:
        out.append(f"index.md: 첫머리가 format: {render.FORMAT} / skill_min: {render.SKILL_MIN}이 아니다(두 저장소 약속)")
    return out


def _side_files(repo: Path, sem: Path) -> list:
    """옆 파일 형식, 공통 규칙 SQL, 정의 전체의 PII 흔적."""
    out = []
    seen = set()
    for src in _load(sem, "sources.yml")["sources"]:
        where = f"source {src.get('id')}"
        for k in sorted(SOURCE_KEYS - set(src)):
            out.append(f"{where}: {k}가 없다")
        for k in sorted(set(src) - SOURCE_KEYS):
            out.append(f"{where}: {k}는 모르는 key다")
        if src.get("grade") not in GRADE:
            out.append(f"{where}: grade={src.get('grade')}는 A~D가 아니다")
        if src.get("id") in seen:
            out.append(f"{where}: id가 겹친다")
        seen.add(src.get("id"))
    for folder in render.SIDE_DIRS:              # B28: 항목 하나에 파일 하나, 파일 이름 = id
        for path in sorted((sem / folder).rglob("*.yml")):
            if path.parent != sem / folder:
                out.append(f"{path.relative_to(sem).as_posix()}: 하위 폴더 없이 {folder}/<id>.yml에 둔다")
                continue
            item = yaml.load(path.read_text(encoding="utf-8"), Loader=_Loader)
            if not isinstance(item, dict) or "id" not in item:
                out.append(f"{folder}/{path.name}: 파일 하나에 항목 하나(id가 있는 mapping)를 둔다")
            elif item["id"] != path.stem:
                out.append(f"{folder}/{path.name}: 파일 이름이 id({item['id']})와 다르다")
    for q in render.side_items(sem, "questions"):
        where = f"question {q.get('id')}"
        for k in sorted(QUESTION_KEYS - set(q)):
            out.append(f"{where}: {k}가 없다")
        if q.get("state") not in ("open", "answered"):
            out.append(f"{where}: state={q.get('state')}는 open·answered가 아니다")
    rules = {r["id"]: r for r in _load(sem, "rules.yml")["rules"]}
    seller_sql = (rules.get("exclude_internal", {}).get("sql") or {}).get("seller")
    if seller_sql != catalog.macro_sql(str(repo), "exclude_internal", "{id}"):
        out.append("rules.yml exclude_internal.sql.seller가 macro exclude_internal() 출력과 다르다")
    for path in sorted(sem.rglob("*.yaml")):
        out.append(f"{path.relative_to(sem)}: 정의 파일 확장자는 .yml이다(.yaml은 render·검사가 읽지 않는다)")
    for path in sorted([*sem.rglob("*.yml"), *sem.rglob("*.yaml"), sem / "README.md"]):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if path.suffix in (".yml", ".yaml"):   # YAML escape(\uC8FC…)로 쓴 글도 본다
            text += "\n" + "\n".join(_strings(list(yaml.load_all(text, Loader=_Loader))))
        for pattern, kind in _PII:
            if pattern.search(text):
                out.append(f"{path.relative_to(sem)}: PII 흔적({kind})이 있다")
    return out


def _strings(v):
    if isinstance(v, dict):
        return [x for k, val in v.items() for x in (_strings(k) + _strings(val))]
    if isinstance(v, list):
        return [x for val in v for x in _strings(val)]
    return [v] if isinstance(v, str) else []


def _load(sem: Path, name: str):
    return yaml.load((sem / name).read_text(encoding="utf-8"), Loader=_Loader)


def _clean(v):
    """표준 parser가 dict마다 끼우는 __parsing_context__를 뺀다."""
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items() if not k.startswith("__")}
    return [_clean(x) for x in v] if isinstance(v, list) else v


def _meta(obj, parent=None) -> dict:
    """meta.<NS>. 표준 parser는 model의 meta를 entity·dimension·measure에 내려 붙인다. 물려받은 것은 빈 것으로 본다."""
    cfg = getattr(obj, "config", None)
    w = _clean(((cfg.meta if cfg else None) or {}).get(NS, {}))
    return {} if parent is not None and w == _meta(parent) else w


def _keys(kind: str, w: dict, where: str, out: list):
    need, optional = META_KEYS[kind]
    for k in sorted(need - set(w)):
        out.append(f"{where}: meta.{NS}.{k}가 없다")
    for k in sorted(set(w) - need - optional):
        out.append(f"{where}: meta.{NS}.{k}는 모르는 key다")


def _definitions(m, sem: Path, repo: Path, coverage: bool) -> list:
    out = []
    sources = {s["id"]: s for s in _load(sem, "sources.yml")["sources"]}
    questions = {q["id"] for q in render.side_items(sem, "questions")}
    entity_ids = {e["id"] for e in _load(sem, "entities.yml")["entities"]}
    terms = render.side_items(sem, "glossary")
    rule_ids = {r["id"] for r in _load(sem, "rules.yml")["rules"]}
    tables = catalog.tables(str(repo))
    measure_of = {x.name: (s, x) for s in m.semantic_models for x in s.measures}
    metric_names = {x.name for x in m.metrics}
    used_entities, pairs, codes_by_model, families_by_model = set(), {}, {}, {}
    model_names = {x.name for x in m.semantic_models}
    source_ids = set(sources)

    for s in m.semantic_models:
        w, where = _meta(s), f"table {s.name}"
        _keys("model", w, where, out)
        tname = f"{s.node_relation.schema_name}.{s.node_relation.alias}"
        t = tables.get(tname)
        if not t:
            out.append(f"{where}: table {tname}이 dbt model에 없다")
            continue
        if w.get("defined_in") != t.file:
            out.append(f"{where}: defined_in이 {t.file}이 아니다")
        cols = set(t.columns) if t.declared else set(catalog.view_columns(t) or [])
        entity_expr = {}
        for e in s.entities:
            used_entities.add(e.name)
            entity_expr[e.name] = e.expr or e.name
            if cols and entity_expr[e.name] not in cols:
                out.append(f"{where}: entity {e.name}의 column {entity_expr[e.name]}이 없다")
        for d in s.dimensions:
            _keys("dimension", _meta(d, s), f"{where}.{d.name}", out)
            if cols and (d.expr or d.name) not in cols:
                out.append(f"{where}: dimension {d.name}의 column이 없다")
            if not (d.description or "").strip():          # B31: dimension은 뜻을 적는 곳이 여기뿐이다
                out.append(f"{where}: dimension {d.name}에 description이 없다")
        if w.get("role") != "relation":
            for k in sorted(rule_ids - set(w.get("rules") or {})):
                out.append(f"{where}: meta.{NS}.rules.{k}가 없다(applied·caller·not_applied·na 중 하나를 적는다)")
        for other in (w.get("long") or {}).get("inherits") or []:
            if other not in model_names:
                out.append(f"{where}: long.inherits {other}가 없는 model이다")
        for k, v in (w.get("rules") or {}).items():
            if k not in rule_ids:
                out.append(f"{where}: rules.{k}는 rules.yml에 없는 모르는 규칙이다")
            if v not in RULE_STATE:
                out.append(f"{where}: rules.{k}={v}는 모르는 값이다")
        for x in s.measures:
            mw, mwhere = _meta(x, s), f"measure {x.name}"
            _keys("measure", mw, mwhere, out)
            rollup = mw.get("rollup")
            if rollup not in ROLLUP:
                out.append(f"{mwhere}: rollup={rollup}는 모르는 값이다")
                continue
            if cols and re.fullmatch(r"\w+", x.expr or x.name) and (x.expr or x.name) not in cols:
                out.append(f"{mwhere}: expr column {x.expr or x.name}이 {tname}에 없다")
            has_nad = x.non_additive_dimension is not None
            if has_nad and x.non_additive_dimension.window_choice.value != "max":
                out.append(f"{mwhere}: non_additive_dimension.window_choice는 max여야 한다(기간 마지막 값)")
            if x.agg.value == "count_distinct":
                if rollup != "none":
                    out.append(f"{mwhere}: count_distinct는 rollup none이어야 한다")
            elif (rollup == "sum") == has_nad:
                out.append(f"{mwhere}: rollup {rollup}와 non_additive_dimension이 어긋난다"
                           "(sum이면 없어야 하고 last·none이면 있어야 한다)")
        types = {e.name: e.type.value for e in s.entities}
        for rel in w.get("relations") or []:
            a, b, card = rel.get("from"), rel.get("to"), rel.get("cardinality")
            if a not in entity_expr or b not in entity_expr:
                out.append(f"{where}: relation {a}->{b}의 entity가 이 model에 없다")
                continue
            if card not in CARDINALITY:
                out.append(f"{where}: cardinality={card}는 모르는 값이다")
                continue
            one = lambda n: types[n] in ("primary", "unique")  # noqa: E731
            # 이 table에서 from 쪽 key가 row마다 하나(primary·unique)면 to 쪽은 여러 from이 모이는 하나다.
            want = ("one_to_one" if one(a) and one(b) else "many_to_one" if one(a)
                    else "many_to_many" if not one(b) else "one_to_many")
            if card != want:
                out.append(f"{where}: relation {a}->{b} cardinality {card}가 entity type"
                           f"({types[a]}, {types[b]})과 어긋난다(기대 {want})")
            key = frozenset((a, b))
            if key in pairs:
                out.append(f"{where}: relation {a}-{b}는 {pairs[key]}에 이미 있다(적는 곳은 하나)")
            pairs[key] = s.name
            for q in rel.get("questions", []):
                if q not in questions:
                    out.append(f"{where}: question {q}가 questions/에 없다")

    for e in sorted(used_entities - entity_ids):
        out.append(f"entity {e}: entities.yml에 없다")
    counted = {_meta(x).get("counts") for x in m.metrics}
    for e in sorted(entity_ids - used_entities - counted):
        out.append(f"entity {e}: 어느 model·metric도 쓰지 않는다")

    prefix_reported = set()
    for x in m.metrics:
        w, where = _meta(x), f"metric {x.name}"
        _keys("metric", w, where, out)
        owner_model = measure_of.get(x.type_params.measure.name if x.type_params.measure else None, (None, None))[0]
        if owner_model is not None:              # D65·D78: metric 이름 = table의 metric_prefix + column(code)
            prefix = _meta(owner_model).get("metric_prefix")
            if not isinstance(prefix, str):
                if owner_model.name not in prefix_reported:
                    prefix_reported.add(owner_model.name)
                    out.append(f"table {owner_model.name}: metric이 있는데 meta.{NS}.metric_prefix(문자열, 다른 table과 "
                               "헷갈리지 않는 짧은 낱말)가 없다")
            elif not x.name.startswith(prefix):
                out.append(f"{where}: 이름이 table {owner_model.name}의 metric_prefix '{prefix}'로 시작하지 않는다")
        for field_name, text in (("label", x.label), ("description", x.description)):
            if not text or _PLACEHOLDER.search(text) or len(text.strip()) < 2:
                out.append(f"{where}: {field_name}가 비었거나 자리표시(<...>, TODO)가 남아 있다")
        status, docs = w.get("status"), w.get("docs") or []
        if status not in STATUS:
            out.append(f"{where}: status={status}는 모르는 값이다")
        if w.get("kind") not in KIND:
            out.append(f"{where}: kind={w.get('kind')}는 모르는 값이다")
        for d in docs:
            if d not in sources:
                out.append(f"{where}: 원본 {d}가 sources.yml에 없다")
            elif sources[d].get("grade") == "D":
                out.append(f"{where}: D 등급 원본 {d}는 인용할 수 없다")
        good = any(sources.get(d, {}).get("grade") in ("A", "B") for d in docs)
        if status == "confirmed" and not good:
            out.append(f"{where}: confirmed인데 A·B 등급 원본이 없다")
        if status in ("conflict", "query_time") and not w.get("questions"):
            out.append(f"{where}: {status}인데 question이 없다")
        for q in w.get("questions") or []:
            if q not in questions:
                out.append(f"{where}: question {q}가 questions/에 없다")
        if x.type.value != "simple" or not x.type_params.measure:
            continue
        if x.type_params.measure.name not in measure_of:
            continue
        s, meas = measure_of[x.type_params.measure.name]
        sw = _meta(s)
        if w.get("kind") == "distinct_count":
            counts = w.get("counts")
            if counts not in entity_ids:
                out.append(f"{where}: distinct_count인데 counts가 entity가 아니다({counts})")
            elif meas.agg.value == "count_distinct":
                key = {e.name: e.expr or e.name for e in s.entities}.get(counts)
                if not key or not re.search(rf"\b{re.escape(key)}\b", meas.expr or ""):
                    out.append(f"{where}: counts {counts}의 key가 measure expr에 없다")
        stored = meas.agg.value != "count_distinct"
        if (status == "query_time") == stored:
            out.append(f"{where}: query_time은 질의 때 세는 measure(count_distinct)만 가리킨다")
        if sw.get("shape") == "long" and stored:
            wf = x.filter.where_filters if x.filter else []
            sql = wf[0].where_sql_template if len(wf) == 1 else ""
            hit = _EQ.match(sql) or _LIKE.match(sql)
            key = (sw.get("long") or {}).get("key")
            if not hit:
                out.append(f"{where}: long model의 metric filter는 "
                           f"\"{{{{ Dimension('{s.primary_entity}__{key}') }}}} = '<code>'\" "
                           "또는 LIKE '<prefix>%<suffix>' 꼴이어야 한다")
                continue
            if hit.group(1) != s.primary_entity or hit.group(2) != key:
                out.append(f"{where}: filter가 {s.primary_entity}__{key}를 가리키지 않는다")
                continue
            if hit.re is _EQ:
                codes_by_model.setdefault(s.name, set()).add(hit.group(3))
            else:
                families_by_model.setdefault(s.name, set()).add((hit.group(3), hit.group(4)))

    if coverage:
        out += _coverage(m, repo, sem, codes_by_model, families_by_model)
        out += _table_coverage(m, sem, tables)

    pointed = set()
    for t in terms:
        ids = [v["id"] for v in t["variants"]]
        if t.get("default") not in ids:
            out.append(f"term {t['id']}: default가 variant에 없다")
        if t.get("question") and t["question"] not in questions:
            out.append(f"term {t['id']}: question {t['question']}이 questions/에 없다")
        for v in t["variants"]:
            if not v.get("metrics") and not v.get("not_in_mart"):
                out.append(f"term {t['id']}.{v['id']}: metrics가 비었으면 not_in_mart에 이유를 적는다")
            for sid in v.get("used_by") or []:
                if sid not in source_ids:
                    out.append(f"term {t['id']}.{v['id']}: used_by 원본 {sid}가 sources.yml에 없다")
            for n in v.get("metrics") or []:
                pointed.add(n)
                if n not in metric_names:
                    out.append(f"term {t['id']}.{v['id']}: metric {n}이 없다")
    for x in m.metrics:
        if _meta(x).get("status") == "query_time" and x.name not in pointed:
            out.append(f"metric {x.name}: query_time인데 가리키는 variant가 없다")
    return out


def _coverage(m, repo: Path, sem: Path, codes_by_model: dict, families_by_model: dict) -> list:
    """D15·D24: mart model이 만드는 지표 code·prefix가 정의에 다 있는가. 예외는 family(prefix)뿐이다."""
    out, domains = [], _model_domains(sem)
    for s in m.semantic_models:
        sw = _meta(s)
        if sw.get("shape") != "long" or "defined_in" not in sw:
            continue
        tname = f"{s.node_relation.schema_name}.{s.node_relation.alias}"
        key = (sw.get("long") or {}).get("key")
        if not key:
            out.append(f"table {s.name}: shape long인데 meta.{NS}.long.key가 없다")
            continue
        codes, prefixes, unread = catalog.long_codes(str(repo), tname, key)
        long = sw.get("long") or {}
        allowed = len(long.get("inherits") or []) + (1 if long.get("seed") else 0)
        if unread > allowed:
            out.append(f"table {s.name}: mart model의 갈래 {unread - allowed}개에서 지표 code를 읽지 못했다"
                       "(IF·coalesce·SELECT * 같은 식). code를 literal·CASE로 쓰거나, data가 만드는 code면 "
                       "앞 literal 이어 붙이기('prefix_' || ...)로 쓰고 family로 덮거나, 다른 table의 code를 넘기면 "
                       f"meta.{NS}.long.inherits·seed로 출처를 밝힌다")
        if long.get("seed"):                       # code를 dbt seed(CSV)가 정하는 table
            codes |= catalog.seed_codes(str(repo), long["seed"])
        inherited = set()                          # 다른 model의 code를 그대로 넘겨받는 갈래(정의는 그 model에 있다)
        for other in long.get("inherits") or []:
            src = next((x for x in m.semantic_models if x.name == other), None)
            seed = ((_meta(src).get("long") or {}).get("seed")) if src else None
            if seed:
                inherited |= catalog.seed_codes(str(repo), seed)
        have = codes_by_model.get(s.name, set())
        families = families_by_model.get(s.name, set())

        def covered(c):
            return c in have or any(c.startswith(p) and c.endswith(sfx) for p, sfx in families)

        for c in sorted(codes):
            if not covered(c):
                pre = sw.get("metric_prefix")
                path = render.metric_path(domains.get(s.name, "<domain>"), s.name, suggest_name(pre, c))
                out.append(f"table {s.name}: mart에 있는 지표 '{c}'가 정의에 없다. "
                           f"{path} 파일을 만들어 아래를 쓰고 render를 돌린다:\n{_minimal_metric(s, key, c, pre)}")
        for p in sorted(prefixes):
            if not any(p.startswith(fp) for fp, _ in families):
                out.append(f"table {s.name}: 새 prefix '{p}'의 family 정의가 없다"
                           f"(filter LIKE '{p}%<suffix>'인 metric 하나로 덮는다)")
        for c in sorted(have - codes - inherited):
            if not any(c.startswith(p) for p in prefixes):
                out.append(f"table {s.name}: metric code '{c}'가 mart model에 없다")
    return out


def _table_coverage(m, sem: Path, tables: dict) -> list:
    """B7: mart model마다 semantic_model이 있거나 not_modeled.yml에 이유가 있다. wide model은 모든 column을 쓴다."""
    out, domains = [], _model_domains(sem)
    modeled = {f"{s.node_relation.schema_name}.{s.node_relation.alias}": s for s in m.semantic_models}
    skipped = {}
    for row in _load(sem, "not_modeled.yml")["not_modeled"]:
        if not row.get("reason"):
            out.append(f"not_modeled {row.get('table')}: reason이 없다")
        if row.get("table") not in tables:
            out.append(f"not_modeled {row.get('table')}: dbt model에 없는 table이다")
        if row.get("table") in modeled:
            out.append(f"not_modeled {row.get('table')}: semantic_model이 있는데 제외 목록에도 있다")
        skipped[row.get("table")] = row
    for name in sorted(t for t in tables if t.startswith(settings.MART_SCHEMA + ".")):
        if name not in modeled and name not in skipped:
            out.append(f"{name}: table 정의도 not_modeled 사유도 없다")
    for name, s in modeled.items():
        sw = _meta(s)
        if sw.get("shape") != "wide" or name not in tables:
            continue
        t = tables[name]
        cols = t.columns if t.declared else (catalog.view_columns(t) or [])
        used = {e.expr or e.name for e in s.entities} | {d.expr or d.name for d in s.dimensions}
        used |= {x.expr or x.name for x in s.measures} | set((sw.get("skip_columns") or {}))
        for c in cols:
            if c not in used:
                domain, name = domains.get(s.name, "<domain>"), suggest_name(sw.get("metric_prefix"), c)
                out.append(f"table {s.name}: mart column '{c}'가 정의에 없다. dimension으로 두거나 meta.{NS}.skip_columns에 "
                           f"이유를 적거나, 지표면 manifest/tables/{domain}/{s.name}.yml의 measures에 "
                           f"아래 measure를 더하고:\n"
                           f"  - name: {s.name}_{c}\n    agg: sum\n    expr: {c}\n"
                           f"    config: {{meta: {{{NS}: {{rollup: sum}}}}}}\n"
                           f"{render.metric_path(domain, s.name, name)} 파일을 만들어 아래를 쓴다:\nmetric:\n"
                           f"  name: {name}\n  label: <사람이 읽는 이름>\n  description: <무엇을 세는지 한 문장>\n"
                           f"  type: simple\n  type_params: {{measure: {s.name}_{c}}}\n"
                           f"  config: {{meta: {{{NS}: {{kind: count, status: code_only, docs: []}}}}}}")
    return out


def suggest_name(prefix, base: str) -> str:
    """D65·D78: metric 이름 = metric_prefix + mart column(code). column이 이미 접두어로 시작하면 다시 붙이지 않는다
    (su_order_count → su_order_count). table에 metric_prefix가 없으면 자리표시를 넣어 채우게 한다."""
    if not isinstance(prefix, str):
        return f"<metric_prefix>{base}"
    return base if base.startswith(prefix) else prefix + base


def _minimal_metric(s, key: str, code: str, prefix="") -> str:
    """D15 실패 메시지에 붙일 최소 metric 문서. kind·rollup은 이름 끝으로 짐작해 채운다(사람이 고친다)."""
    if code in ("dau", "wau", "mau") or code.endswith(("_users", "_user_count")):
        kind, rollup = "distinct_count", "none"
    elif code.endswith("_eod"):
        kind, rollup = "count", "last"
    else:
        kind, rollup = "count", "sum"
    by_rollup = {}                        # rollup마다 model에 먼저 적힌 measure(예: none이면 _distinct가 _stat보다 먼저)
    for x in s.measures:
        by_rollup.setdefault(_meta(x, s).get("rollup"), x.name)
    counts = "counts: <entity>, " if kind == "distinct_count" else ""
    return (
        "metric:\n"
        f"  name: {suggest_name(prefix, code)}\n"
        f"  label: <사람이 읽는 이름>\n"
        f"  description: <무엇을 세는지 한 문장>\n"
        "  type: simple\n"
        f"  type_params: {{measure: {by_rollup.get(rollup, '<measure>')}}}\n"
        f"  filter: \"{{{{ Dimension('{s.primary_entity}__{key}') }}}} = '{code}'\"\n"
        f"  config: {{meta: {{{NS}: {{kind: {kind}, {counts}status: code_only, docs: []}}}}}}"
    )
