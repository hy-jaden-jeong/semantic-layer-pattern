"""semantic layer 질문 eval(docs/verification.md). 손으로 돌린다.

  pack  : 임시 폴더에 정의 저장소 모양 checkout(semantic/만)과 skill 사본을 만든다.
          새 agent가 <out>/shop-bi 안에서 skill을 이름으로 불러, 질문마다
          answers/<id>.sql 과 answers/<id>.yml(답 끝 기준 block)을 쓴다.
  score : 정답 SQL과 답 SQL을 같은 DuckDB 파일(dbt build가 만든 것)에서 돌려 결과를 견주고, 기준 block을 id로 견준다.
          한 run에서 모든 질문이 맞아야 통과(종료 코드 0). 보고서를 <answers>/../report.md에 쓴다.

예:
  dbt build --profiles-dir .
  python scripts/semantic_eval.py pack --skill-dir skill/shop-data-analytics --out <임시 폴더>
  python scripts/semantic_eval.py score --answers <임시 폴더>/answers --record

다른 warehouse에서 쓰려면 _connect와 _run_sql 둘만 바꾼다.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
QUESTIONS = REPO / "tests" / "semantic" / "eval" / "questions.yml"


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def pack(skill_dir: Path, out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    seed = out / "seed"
    shutil.copytree(REPO / "semantic", seed / "semantic",
                    ignore=shutil.ignore_patterns("*.py", "__pycache__"))
    _git(seed, "init", "-q", "-b", "main")
    _git(seed, "add", "-A")
    _git(seed, "-c", "user.name=eval", "-c", "user.email=eval@example.invalid", "commit", "-q", "-m", "pack")
    bare = out / "shop-bi.git"
    _git(out, "clone", "-q", "--bare", str(seed), str(bare))
    work = out / "shop-bi"
    _git(out, "clone", "-q", str(bare), str(work))
    shutil.copytree(skill_dir, work / ".claude" / "skills" / "shop-data-analytics",
                    ignore=shutil.ignore_patterns("__pycache__", "test_*.py"))
    (out / "answers").mkdir()
    qs = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    lines = ["# eval 질문", "", "각 질문에 shop-data-analytics skill을 이름으로 불러 답한다.",
             f"환경 변수: SHOP_BI_URL={bare}  SHOP_BI_CACHE={out / 'cache'}",
             "답마다 answers/<id>.sql(SQL 한 문장, 거절이면 빈 파일)과 answers/<id>.yml(답 끝 기준 block)을 쓴다.",
             "SQL은 질문이 묻는 값만 select한다(설명용 column을 더하지 않는다). 채점은 결과 표 전체를 정답 SQL과 견준다.", ""]
    lines += [f"- {q['id']}: {q['question']}" for q in qs]
    (out / "QUESTIONS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    shutil.rmtree(seed)
    print(f"packed {out} (질문 {len(qs)}개). QUESTIONS.md를 새 agent에게 준다.")


def _connect(db: str):
    import duckdb

    return duckdb.connect(db, read_only=True)


def _run_sql(con, sql: str):
    return [tuple(row) for row in con.execute(sql).fetchall()]


def _norm(v):
    try:
        f = float(v)
        return round(f, 6) if not math.isnan(f) else None
    except (TypeError, ValueError):
        return v


def _same(a, b) -> bool:
    return sorted(tuple(_norm(x) for x in r) for r in a) == sorted(tuple(_norm(x) for x in r) for r in b)


def score(answers: Path, db: str, record: bool = False) -> int:
    w = _connect(db)
    qs = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    rows, passed = [], 0
    for q in qs:
        sql_path, block_path = answers / f"{q['id']}.sql", answers / f"{q['id']}.yml"
        notes = []
        if not block_path.exists():
            notes.append("기준 block 파일이 없다")
        block = (yaml.safe_load(block_path.read_text(encoding="utf-8")) or {}) if block_path.exists() else {}
        block = block.get("기준", block)
        want = q["expect"]
        if set(block.get("metrics") or []) != set(want.get("metrics") or []):
            notes.append(f"metrics {block.get('metrics')} != {want.get('metrics')}")
        for key in ("variant",):
            if key in want and block.get(key) != want[key]:
                notes.append(f"{key} {block.get(key)} != {want[key]}")
        for key in ("questions", "rules_applied_by_me", "other_variants"):
            missing = set(want.get(key) or []) - set(block.get(key) or [])
            if missing:
                notes.append(f"{key}에 {sorted(missing)}가 없다")
        answer_sql = sql_path.read_text(encoding="utf-8").strip() if sql_path.exists() else ""
        if q.get("sql"):
            try:
                ok = answer_sql and _same(_run_sql(w, q["sql"]), _run_sql(w, answer_sql))
                if not ok:
                    notes.append("결과가 정답 SQL과 다르다")
            except Exception as e:  # noqa: BLE001 - 보고서에 그대로 남긴다
                notes.append(f"실행 실패: {str(e)[:200]}")
        elif answer_sql:
            notes.append("거절해야 하는데 SQL을 지었다")
        good = not notes
        passed += good
        rows.append(f"| {q['id']} | {'통과' if good else '실패'} | {'; '.join(notes) or '-'} |")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = [f"# semantic layer eval {stamp}", "", f"{passed}/{len(qs)} 통과(기준: 모두 통과)", "",
              "| 질문 | 결과 | 사유 |", "|---|---|---|", *rows]
    (answers.parent / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    if record:   # 모든 run을 저장소에 남긴다(D26)
        out = REPO / "docs" / "eval-runs" / f"{stamp.replace(':', '')}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(report) + "\n", encoding="utf-8")
        print(f"recorded {out.relative_to(REPO)}")
    print("\n".join(report))
    return 0 if passed == len(qs) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack")
    p.add_argument("--skill-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("score")
    s.add_argument("--answers", type=Path, required=True)
    s.add_argument("--db", default=str(REPO / "shop_bi.duckdb"), help="dbt build가 만든 DuckDB 파일")
    s.add_argument("--record", action="store_true", help="보고서를 docs/eval-runs/에도 남긴다")
    ns = ap.parse_args(argv)
    if ns.cmd == "pack":
        pack(ns.skill_dir, ns.out)
        return 0
    return score(ns.answers, ns.db, ns.record)


if __name__ == "__main__":
    sys.exit(main())
