"""물리 catalog: dbt project의 파일만 읽어 model·seed의 relation, column, long table의 지표 code를 뽑는다(오프라인).

warehouse에도 dbt에도 붙지 않는다. models/**/*.sql, models/**/*.yml, seeds/**/*.csv, macros/**/*.sql을 읽는다.
쓰는 쪽은 tables(), long_codes(), seed_codes(), view_columns(), macro_sql()만 안다. SQL을 regex로 읽는 방법은 숨긴다.
"""
from __future__ import annotations

import csv
import glob
import os
import re
from dataclasses import dataclass, field

import yaml

from semantic import settings

_JINJA_NOISE = re.compile(r"\{#.*?#\}|\{\{-?\s*config\(.*?\)\s*-?\}\}", re.S)   # Jinja 주석과 config() 호출


@dataclass
class Table:
    name: str            # schema.table
    kind: str            # model | seed
    file: str            # 저장소 루트 기준 경로
    columns: list = field(default_factory=list)   # 선언된 column 목록. 없으면 []
    declared: bool = False                         # model yml(또는 seed header)에 column이 선언돼 있나
    body: str = ""                                 # model SQL(주석·config를 뺀 것)


def _strip_comments(sql: str) -> str:
    """-- 줄 주석과 /* */ 주석을 지운다. 문자열('...') 안의 --·/*는 건드리지 않는다. 줄 수는 그대로 둔다."""
    out, i, n, in_str = [], 0, len(sql), False
    while i < n:
        c = sql[i]
        if in_str:
            out.append(c)
            if c == "'":
                if i + 1 < n and sql[i + 1] == "'":   # '' 는 문자열 안의 따옴표
                    out.append("'")
                    i += 1
                else:
                    in_str = False
        elif c == "'":
            in_str = True
            out.append(c)
        elif sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j == -1 else j
            continue
        elif sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            block = sql[i:n if j == -1 else j + 2]
            out.append("\n" * block.count("\n"))
            i = n if j == -1 else j + 2
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)


def _paren_block(text: str, start: int) -> str:
    depth, i, in_str = 0, start, False
    while i < len(text):
        c = text[i]
        if c == "'":
            in_str = not in_str
        elif not in_str:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return text[start + 1:i]
        i += 1
    raise ValueError("괄호가 닫히지 않음")


def _split_top(block: str) -> list:
    out, depth, cur, in_str = [], 0, "", False
    for c in block:
        if c == "'":
            in_str = not in_str
        if not in_str:
            if c in "(<":
                depth += 1
            elif c in ")>":
                depth -= 1
            elif c == "," and depth == 0:
                out.append(cur)
                cur = ""
                continue
        cur += c
    if cur.strip():
        out.append(cur)
    return out


def _declared_columns(repo: str) -> dict:
    """model 이름 → model yml(models/**/*.yml)의 columns 이름 목록."""
    out = {}
    for path in sorted(glob.glob(os.path.join(repo, settings.MODELS_DIR, "**", "*.yml"), recursive=True)):
        doc = yaml.safe_load(open(path, encoding="utf-8")) or {}
        for m in doc.get("models") or []:
            cols = [c["name"] for c in m.get("columns") or [] if isinstance(c, dict) and "name" in c]
            if cols:
                out[m.get("name")] = cols
    return out


def tables(repo: str) -> dict:
    """schema.table → Table. dbt model(models/<layer>/**/<name>.sql)과 seed(seeds/<group>/<name>.csv)를 본다.

    schema는 layer·group 폴더 이름으로 정한다(settings.LAYER_SCHEMA·SEED_SCHEMA, dbt_project.yml의 +schema와 같게 둔다).
    """
    found, declared = {}, _declared_columns(repo)
    root = os.path.join(repo, settings.MODELS_DIR)
    for path in sorted(glob.glob(os.path.join(root, "**", "*.sql"), recursive=True)):
        layer = os.path.relpath(path, root).split(os.sep)[0]
        name = os.path.splitext(os.path.basename(path))[0]
        body = _strip_comments(_JINJA_NOISE.sub("", open(path, encoding="utf-8").read()))
        t = Table(f"{settings.LAYER_SCHEMA.get(layer, layer)}.{name}", "model", os.path.relpath(path, repo), body=body)
        if name in declared:
            t.columns, t.declared = declared[name], True
        found.setdefault(t.name, t)
    root = os.path.join(repo, settings.SEEDS_DIR)
    for path in sorted(glob.glob(os.path.join(root, "**", "*.csv"), recursive=True)):
        group = os.path.relpath(path, root).split(os.sep)[0]
        name = os.path.splitext(os.path.basename(path))[0]
        with open(path, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f), [])
        found.setdefault(f"{settings.SEED_SCHEMA.get(group, group)}.{name}",
                         Table(f"{settings.SEED_SCHEMA.get(group, group)}.{name}", "seed", os.path.relpath(path, repo),
                               columns=header, declared=True))
    return found


def _top_find(text: str, word: str, start: int = 0):
    """괄호·문자열·CASE 밖(depth 0)에서 word(대소문자 무시, 단어 경계)가 나오는 위치들."""
    out, depth, in_str, i, W = [], 0, False, start, word.upper()
    U = text.upper()
    while i < len(text):
        c = text[i]
        if c == "'":
            in_str = not in_str
        elif not in_str:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            elif depth == 0 and U.startswith(W, i) and (i == 0 or not (U[i - 1].isalnum() or U[i - 1] == "_")) \
                    and (i + len(W) == len(U) or not (U[i + len(W)].isalnum() or U[i + len(W)] == "_")):
                out.append(i)
        i += 1
    return out


def _case_results(expr: str) -> list:
    """CASE ... END 한 겹의 THEN/ELSE 결과 식들(안쪽 CASE는 건드리지 않는다)."""
    U, res, depth, i, in_str, mark = expr.upper(), [], 0, 0, False, None
    def kw(k):
        return U.startswith(k, i) and not (U[i - 1].isalnum() or U[i - 1] == "_") and \
            (i + len(k) >= len(U) or not (U[i + len(k)].isalnum() or U[i + len(k)] == "_"))
    while i < len(expr):
        c = expr[i]
        if c == "'":
            in_str = not in_str
        elif not in_str and i > 0:
            if kw("CASE"):
                depth += 1
            elif kw("END"):
                if depth == 0:
                    if mark is not None:
                        res.append(expr[mark:i])
                    break
                depth -= 1
            elif depth == 0 and (kw("THEN") or kw("ELSE")):
                if mark is not None:
                    res.append(expr[mark:i])
                mark = i + 4
            elif depth == 0 and kw("WHEN") and mark is not None:
                res.append(expr[mark:i]); mark = None
        i += 1
    return res


def _codes(expr: str):
    """식 하나 → (code 집합, prefix 집합, 종류). 종류: literal | column | unknown.

    literal이면 code, CASE면 결과마다, 앞이 literal인 이어 붙이기(CONCAT, ||)면 그 literal이 prefix다.
    column 참조면 출처(subquery·CTE)를 따라가야 하고, 그 밖의 식(IF, coalesce, 뒤만 literal 등)은 읽지 못한다.
    """
    e = re.sub(r"\s+AS\s+\w+\s*$", "", expr.strip(), flags=re.I).strip()
    e = re.sub(r"\s+\w+\s*$", "", e) if re.fullmatch(r"'[^']*'\s+\w+", e) else e      # 'dau' metric
    if re.fullmatch(r"'[^']*'", e):
        return {e[1:-1]}, set(), "literal"
    if e.upper().startswith("CASE"):
        codes, pres, kinds = set(), set(), set()
        for r in _case_results(e[4:]):
            c, p, k = _codes(r)
            codes |= c
            pres |= p
            kinds.add(k)
        return codes, pres, "literal" if kinds <= {"literal"} else "unknown"
    m = re.match(r"(?:CONCAT\s*\(\s*)?'([^']*)'\s*(?:,|\|\|)", e, re.I)
    if m:
        return set(), {m.group(1)}, "literal"
    if re.fullmatch(r"(?:\w+\.)?\w+", e):
        return set(), set(), "column"
    return set(), set(), "unknown"


def long_codes(repo: str, table: str, key: str):
    """(code 집합, prefix 집합, 읽지 못한 갈래 수). model SQL에서 key column 자리의 식을 따라가 지표 code를 뽑는다.

    마지막 SELECT가 column을 그대로 넘기면 같은 WITH의 CTE로 들어간다. literal·CASE·앞 literal 이어 붙이기로
    풀리지 않는 식과, 다른 model의 column을 그대로 넘기는 갈래는 읽지 못한 갈래로 센다.
    """
    t = tables(repo)[table]
    cols = t.columns if t.declared else (view_columns(t) or [])
    ctes, main = _split_with(t.body)
    return _branch_codes(main, cols.index(key), None, ctes)


def _split_with(body: str):
    """WITH a AS (...), b AS (...) <본 query> → ({이름: 본문}, 본 query)."""
    ctes, rest = {}, body.lstrip()
    if not re.match(r"WITH\b", rest, re.I):
        return ctes, body
    rest = rest[4:]
    while True:
        m = re.match(r"\s*,?\s*(\w+)\s+AS\s*\(", rest, re.I)
        if not m:
            return ctes, rest
        start = m.end() - 1
        ctes[m.group(1)] = _paren_block(rest, start)
        depth, i, in_str = 0, start, False
        while i < len(rest):          # 닫는 괄호 뒤로
            c = rest[i]
            if c == "'":
                in_str = not in_str
            elif not in_str and c == "(":
                depth += 1
            elif not in_str and c == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        rest = rest[i + 1:]


def _alias(item: str) -> str:
    m = re.search(r"\bAS\s+(\w+)\s*$", item.strip(), re.I)
    return m.group(1) if m else re.split(r"[.\s]", item.strip())[-1]


def _branch_codes(body: str, pos, name, ctes=None):
    """body의 depth 0 SELECT 갈래마다 pos번째(또는 alias가 name인) 식에서 code를 뽑는다.
    식이 column 참조이면 FROM의 subquery나 같은 WITH의 CTE로 한 번 더 들어간다. (code, prefix, 읽지 못한 갈래 수)"""
    ctes = ctes or {}
    codes, pres, unread = set(), set(), 0
    sels, froms, unions = _top_find(body, "SELECT"), _top_find(body, "FROM"), _top_find(body, "UNION")
    for s in sels:
        nxt = min([x for x in sels + unions if x > s], default=len(body))
        f = next((x for x in froms if s < x < nxt), None)     # FROM 없는 SELECT도 있다
        items = _split_top(re.sub(r"^\s*DISTINCT\b", "", body[s + 6:f if f is not None else nxt], flags=re.I))
        if name is not None:
            idx = next((k for k, it in enumerate(items) if _alias(it) == name), None)
            if idx is None and pos is not None and pos < len(items):
                idx = pos                      # UNION 뒤 갈래는 alias 없이 자리로 맞춘다
        else:
            idx = pos if pos < len(items) else None
        if idx is None or items[idx].strip().endswith("*"):
            unread += 1                        # SELECT * 이거나 자리를 찾지 못했다
            continue
        c, p, kind = _codes(items[idx])
        if kind == "column":
            rest = body[f + 4:].lstrip() if f is not None else ""
            src = re.match(r"(\w+)\b", rest)
            if rest.startswith("("):
                c, p, u = _branch_codes(_paren_block(rest, 0), None, _alias(items[idx]), ctes)
            elif src and src.group(1) in ctes:
                c, p, u = _branch_codes(ctes[src.group(1)], None, _alias(items[idx]), ctes)
            else:
                c, p, u = set(), set(), 1      # 다른 table의 column을 그대로 넘긴다(inherits·seed로 밝힌다)
            unread += u
        elif kind == "unknown":
            unread += 1
        codes |= c
        pres |= p
        if name is not None and pos is None:
            pos = idx                          # 첫 갈래에서 찾은 자리를 다음 갈래에 쓴다
    return codes, pres, unread


def seed_codes(repo: str, relpath: str) -> set:
    """dbt seed(CSV)의 첫 column 값들. code를 seed가 정하는 long table에 쓴다."""
    with open(os.path.join(repo, relpath), newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return {r[0] for r in rows[1:] if r and r[0]}


def view_columns(t: Table):
    """column 선언이 없는 model: 마지막 query의 첫 depth 0 SELECT가 내는 이름. *가 있으면 None."""
    _, body = _split_with(t.body)
    sels, froms = _top_find(body, "SELECT"), _top_find(body, "FROM")
    if not sels:
        return None
    f = next((x for x in froms if x > sels[0]), len(body))
    lst = re.sub(r"^\s*DISTINCT\b", "", body[sels[0] + 6:f], flags=re.I)
    cols = []
    for p in _split_top(lst):
        if p.strip().endswith("*"):
            return None
        cols.append(_alias(p))
    return cols


def macro_sql(repo: str, macro: str, *args):
    """macros/의 macro를 dbt 없이 render한 SQL 조각. ref()는 catalog의 relation 이름(schema.table)으로 바꾼다. 없으면 None."""
    import jinja2

    rel = {t.name.split(".", 1)[1]: t.name for t in tables(repo).values()}
    for path in sorted(glob.glob(os.path.join(repo, settings.MACROS_DIR, "**", "*.sql"), recursive=True)):
        text = open(path, encoding="utf-8").read()
        if re.search(r"\{%-?\s*macro\s+" + re.escape(macro) + r"\s*\(", text):
            env = jinja2.Environment()
            env.globals["ref"] = lambda name: rel[name]
            return str(getattr(env.from_string(text).module, macro)(*args)).strip()
    return None
