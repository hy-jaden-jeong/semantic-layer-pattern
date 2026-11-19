"""물리 catalog: 저장소의 SQL만 읽어 table·column·long table의 지표 code를 뽑는다(오프라인).

쓰는 쪽은 tables(), long_codes(), seed_codes(), view_columns()만 안다. SQL을 regex로 읽는 방법은 숨긴다.
"""
from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass, field

CATALOG = "`dev-shop-bi-catalog`"
_CREATE = re.compile(
    r"CREATE\s+(?:OR\s+(?:REPLACE|REFRESH)\s+)?(?:TEMPORARY\s+)?(?:MATERIALIZED\s+|STREAMING\s+)?(TABLE|VIEW)\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?" + re.escape(CATALOG) + r"\.`?(\w+)`?\.`?(\w+)`?\s*(\(|AS\b|COMMENT\b|USING\b)?",
    re.IGNORECASE,
)


@dataclass
class Table:
    name: str            # schema.table (catalog 뺀 이름)
    kind: str            # TABLE | VIEW
    file: str
    line: int
    columns: list = field(default_factory=list)   # 선언된 column 목록. 없으면 []
    declared: bool = False                         # column 목록이 DDL에 선언돼 있나
    body: str = ""                                 # CREATE 문 전체(선언 없는 view의 약한 검사용)


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


def tables(repo: str) -> dict:
    """schema.table → Table. src/의 SQL과, Python 안에 문자열로 쓴 CREATE(spark.sql 등)까지 본다."""
    found = {}
    paths = glob.glob(os.path.join(repo, "src", "**", "*.sql"), recursive=True)
    paths += [p for p in glob.glob(os.path.join(repo, "src", "**", "*.py"), recursive=True)
              if os.sep + os.path.join("bi", "semantic") + os.sep not in p]
    for path in sorted(paths):
        raw = open(path, encoding="utf-8").read()
        sql = _strip_comments(raw)
        ms = list(_CREATE.finditer(sql))
        for idx, m in enumerate(ms):
            kind, schema, tbl, nxt = m.group(1).upper(), m.group(2), m.group(3), m.group(4)
            end = sql.find(";", m.end())
            body = sql[m.start(): end if end != -1 else len(sql)]
            t = Table(f"{schema}.{tbl}", kind, os.path.relpath(path, repo),
                      sql.count("\n", 0, m.start()) + 1, body=body)
            if nxt == "(":
                block = _paren_block(sql, m.end() - 1)
                t.columns = [p.strip().split()[0] for p in _split_top(block) if p.strip()]
                t.declared = True
            found.setdefault(t.name, t)   # 같은 table을 두 파일이 만들면 첫 번째
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


def long_codes(repo: str, relpath: str, table: str, key: str):
    """(code 집합, prefix 집합, 읽지 못한 갈래 수). key column 자리의 식에서 지표 code를 뽑는다.

    column이 선언된 table은 저장소의 모든 SQL에서 그 table로 들어가는 INSERT를 읽고, 선언이 없는 view는 AS 뒤 본문을 읽는다.
    REPLACE WHERE 뒤의 WITH와 CTE는 따라 들어간다. literal·CASE·앞 literal 이어 붙이기로 풀리지 않는 식은 읽지 못한 갈래로 센다.
    """
    t = tables(repo)[table]
    if t.declared:
        cols, bodies = t.columns, _insert_bodies(repo, table)
    else:
        cols, bodies = view_columns(t) or [], [t.body[re.search(r"\bAS\b", t.body, re.I).end():]]
    codes, pres, unread = set(), set(), 0
    for body in bodies:
        ctes, main = _split_with(_skip_replace_where(body))
        c, p, u = _branch_codes(main, cols.index(key), None, ctes)
        codes |= c
        pres |= p
        unread += u
    return codes, pres, unread


def _insert_bodies(repo: str, table: str) -> list:
    """저장소 src/의 모든 SQL에서 table로 들어가는 INSERT 본문(table 이름 뒤부터 ;까지)."""
    pattern = re.compile(r"INSERT\s+(?:INTO|OVERWRITE)\s+(?:TABLE\s+)?" + re.escape(CATALOG) + r"\." + re.escape(table)
                         + r"\b", re.I)
    out = []
    for path in sorted(glob.glob(os.path.join(repo, "src", "**", "*.sql"), recursive=True)):
        sql = _strip_comments(open(path, encoding="utf-8").read())
        for m in pattern.finditer(sql):
            end = sql.find(";", m.end())
            out.append(sql[m.end(): end if end != -1 else len(sql)])
    return out


def _skip_replace_where(body: str) -> str:
    """INSERT ... REPLACE WHERE <조건> 뒤의 본 query(WITH 또는 SELECT)부터."""
    if not re.match(r"\s*REPLACE\s+WHERE\b", body, re.I):
        return body
    starts = [i for w in ("WITH", "SELECT") for i in _top_find(body, w)]
    return body[min(starts):] if starts else body


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
    """seed SQL(INSERT ... VALUES)의 각 row 첫 값. 한 줄에 row가 여럿이어도 읽는다."""
    sql = _strip_comments(open(os.path.join(repo, relpath), encoding="utf-8").read())
    values = sql[re.search(r"\bVALUES\b", sql, re.I).end():] if re.search(r"\bVALUES\b", sql, re.I) else ""
    return set(re.findall(r"(?:^|,)\s*\(\s*'(\w+)'", values, re.M))


def view_columns(t: Table):
    """column 선언이 없는 view: 첫 depth 0 SELECT의 출력 이름. *가 있으면 None."""
    body = t.body[re.search(r"\bAS\b", t.body, re.I).end():]
    sels, froms = _top_find(body, "SELECT"), _top_find(body, "FROM")
    if not sels:
        return None
    f = next(x for x in froms if x > sels[0])
    lst = re.sub(r"^\s*DISTINCT\b", "", body[sels[0] + 6:f], flags=re.I)
    cols = []
    for p in _split_top(lst):
        if p.strip().endswith("*"):
            return None
        cols.append(_alias(p))
    return cols
