"""locate.sh 시험. 가짜 remote(로컬 bare 저장소)로 뒤처짐·고친 파일·네트워크 끊김·형식 약속을 재현한다.

실행: PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider skill/shop-data-analytics/scripts/test_locate.py
(bytecode·pytest cache를 남기지 않아 skill clone이 dirty가 되지 않는다)
"""
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
SEM = "semantic"
NEXT = str(int((SKILL / "VERSION").read_text().strip()) + 1)   # 지금 skill보다 한 단계 새 version


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def commit_all(repo, msg):
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", msg)


def make_bare(tmp, name, files):
    """files를 담은 commit 하나짜리 bare 저장소와 그 작업본을 만든다."""
    work = tmp / f"{name}-seed"
    work.mkdir()
    git(work, "init", "-q", "-b", "main")
    for rel, text in files.items():
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text(text)
    commit_all(work, "init")
    bare = tmp / f"{name}.git"
    git(tmp, "clone", "-q", "--bare", str(work), str(bare))
    git(work, "remote", "add", "origin", str(bare))
    git(work, "fetch", "-q", "origin")
    git(work, "branch", "-q", "--set-upstream-to=origin/main", "main")
    return bare, work


def index(marker, skill_min=1):
    return {f"{SEM}/index.md": f"format: 1\nskill_min: {skill_min}\n\n{marker}\n", f"{SEM}/README.md": "# r\n"}


@pytest.fixture
def env(tmp_path):
    """skill이 든 저장소 clone과 정의 저장소(shop-bi) bare. run(cwd)로 locate.sh를 돌린다."""
    skill_files = {f"skill/{d.name}/{p.relative_to(d)}": p.read_text()
                   for d in (SKILL,) for p in d.rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    skill_bare, skill_seed = make_bare(tmp_path, "skills", skill_files)
    skill_clone = tmp_path / "skills"
    git(tmp_path, "clone", "-q", str(skill_bare), str(skill_clone))
    shop_bare, shop_seed = make_bare(tmp_path, "shop-bi", index("v1"))
    cache = tmp_path / "cache"
    script = skill_clone / "skill/shop-data-analytics/scripts/locate.sh"

    def run(cwd, url=None, skills_url=None, script_path=None, extra_env=None, bash="bash"):
        e = {**os.environ, "SHOP_BI_URL": str(url or shop_bare), "SHOP_BI_CACHE": str(cache),
             "SHOP_SKILLS_URL": str(skills_url or skill_bare), **(extra_env or {})}
        p = subprocess.run([bash, str(script_path or script)], cwd=cwd, env=e, capture_output=True, text=True)
        return p.returncode, p.stdout.strip(), p.stderr
    return {"run": run, "tmp": tmp_path, "shop_bare": shop_bare, "shop_seed": shop_seed,
            "skill_bare": skill_bare, "skill_seed": skill_seed, "skill_clone": skill_clone, "cache": cache,
            "script": script}


def checkout(env, name="checkout"):
    path = env["tmp"] / name
    git(env["tmp"], "clone", "-q", str(env["shop_bare"]), str(path))
    return path


def push_change(seed, files, msg="change"):
    for rel, text in files.items():
        (seed / rel).parent.mkdir(parents=True, exist_ok=True)
        (seed / rel).write_text(text)
    commit_all(seed, msg)
    git(seed, "push", "-q", "origin", "main")


def test_answer_in_old_checkout_reads_main(env):
    co = checkout(env)
    push_change(env["shop_seed"], index("v2"))          # main이 앞서 나감. checkout은 v1 그대로
    code, out, err = env["run"](co)
    assert code == 0, err
    assert "v2" in (Path(out) / "index.md").read_text()
    assert "source=main ref=main@" in err


def test_outside_checkout_clones_main(env):
    outside = env["tmp"] / "elsewhere"
    outside.mkdir()
    code, out, err = env["run"](outside)
    assert code == 0, err
    assert "via=clone" in err and "v1" in (Path(out) / "index.md").read_text()


def test_network_down_uses_cache_with_warning(env):
    outside = env["tmp"] / "elsewhere"
    outside.mkdir()
    assert env["run"](outside)[0] == 0                  # 한 번 받아 cache가 생김
    code, out, err = env["run"](outside, url=env["tmp"] / "no-such.git")
    assert code == 0, err
    assert "freshness=unknown" in err and "last_checked=" in err


def test_network_down_without_anything_stops(env):
    outside = env["tmp"] / "elsewhere"
    outside.mkdir()
    code, out, err = env["run"](outside, url=env["tmp"] / "no-such.git")
    assert code == 4 and out == ""


def test_main_without_semantic_layer_stops(env):
    bare, _ = make_bare(env["tmp"], "empty", {"README.md": "x"})
    outside = env["tmp"] / "elsewhere"
    outside.mkdir()
    code, out, err = env["run"](outside, url=bare)
    assert code == 3, err


def test_skill_updates_itself_when_behind_and_clean(env):
    push_change(env["skill_seed"], {"skill/shop-data-analytics/VERSION": NEXT + "\n"})
    outside = env["tmp"] / "elsewhere"
    outside.mkdir()
    code, out, err = env["run"](outside)
    assert code == 0, err
    assert "skill_updated=1" in err
    assert (env["skill_clone"] / "skill/shop-data-analytics/VERSION").read_text().strip() == NEXT


def test_skill_behind_with_local_edits_stops(env):
    push_change(env["skill_seed"], {"skill/shop-data-analytics/VERSION": NEXT + "\n"})
    (env["skill_clone"] / "skill/shop-data-analytics/SKILL.md").write_text("local edit")
    outside = env["tmp"] / "elsewhere"
    outside.mkdir()
    code, out, err = env["run"](outside)
    assert code == 6 and "pull --ff-only" in err


def test_definitions_newer_than_skill_stop(env):
    push_change(env["shop_seed"], index("v3", skill_min=9))
    outside = env["tmp"] / "elsewhere"
    outside.mkdir()
    code, out, err = env["run"](outside)
    assert code == 5 and "skill version 9" in err


# ── 아래는 깨뜨리기 검증과 설계 대조에서 나온 장면 ────────────

def outside(env):
    o = env["tmp"] / "elsewhere"
    o.mkdir(exist_ok=True)
    return o


def marker(out):
    return (Path(out) / "index.md").read_text().split("\n")[3]


def alias(repo, fake_url, real):
    """origin을 fake_url로 적고, git이 실제로는 real로 가게 한다(insteadOf)."""
    git(repo, "remote", "set-url", "origin", fake_url)
    git(repo, "config", f"url.{real}.insteadOf", fake_url)


def go_offline(env):
    """정의 저장소 bare를 치워 fetch·ls-remote·clone이 모두 실패하게 한다."""
    env["shop_bare"].rename(env["tmp"] / "shop-bi.git.away")


# 1. 자기 갱신은 skill 저장소 clone일 때만

def test_copy_install_in_other_repo_is_not_pulled(env):
    mine_bare, mine_seed = make_bare(env["tmp"], "my-skills", {"README.md": "mine\n"})
    mine = env["tmp"] / "my-skills"
    git(env["tmp"], "clone", "-q", str(mine_bare), str(mine))
    shutil.copytree(env["skill_clone"] / "skill/shop-data-analytics", mine / "shop-data-analytics")
    commit_all(mine, "copy skill")
    git(mine, "push", "-q", "origin", "main")
    git(mine_seed, "pull", "-q", "origin", "main")
    push_change(mine_seed, {"other.txt": "다른 기기\n"})
    before = git(mine, "rev-parse", "HEAD")
    code, out, err = env["run"](outside(env), script_path=mine / "shop-data-analytics/scripts/locate.sh")
    assert code == 0, err
    assert "skill_freshness=unmanaged" in err and "skill_updated" not in err
    assert git(mine, "rev-parse", "HEAD") == before and not (mine / "other.txt").exists()


def test_copy_install_with_dirty_other_repo_does_not_stop(env):
    mine_bare, mine_seed = make_bare(env["tmp"], "my-skills", {"README.md": "mine\n"})
    mine = env["tmp"] / "my-skills"
    git(env["tmp"], "clone", "-q", str(mine_bare), str(mine))
    shutil.copytree(env["skill_clone"] / "skill/shop-data-analytics", mine / "shop-data-analytics")
    commit_all(mine, "copy skill")
    git(mine, "push", "-q", "origin", "main")
    git(mine_seed, "pull", "-q", "origin", "main")
    push_change(mine_seed, {"other.txt": "다른 기기\n"})
    (mine / "notes.md").write_text("작업 중\n")
    code, out, err = env["run"](outside(env), script_path=mine / "shop-data-analytics/scripts/locate.sh")
    assert code == 0, err
    assert "skill_freshness=unmanaged" in err


@pytest.mark.parametrize("url", ["https://github.com/hy-jaden-jeong/semantic-layer-pattern.git",
                                 "git@github.com:hy-jaden-jeong/semantic-layer-pattern"])
def test_skills_repo_recognised_by_origin_url(env, url):
    alias(env["skill_clone"], url, str(env["skill_bare"]))
    push_change(env["skill_seed"], {"skill/shop-data-analytics/VERSION": NEXT + "\n"})
    code, out, err = env["run"](outside(env), skills_url="/no/such/skills.git")
    assert code == 0, err
    assert "skill_updated=1" in err


def test_bytecode_does_not_make_skill_repo_dirty(env):
    push_change(env["skill_seed"], {"skill/shop-data-analytics/VERSION": NEXT + "\n"})
    pyc = env["skill_clone"] / "skill/shop-data-analytics/scripts/__pycache__"
    pyc.mkdir()
    (pyc / "test_locate.cpython-312.pyc").write_bytes(b"x")
    (env["skill_clone"] / "skill/shop-data-analytics/scripts/stray.pyc").write_bytes(b"x")
    code, out, err = env["run"](outside(env))
    assert code == 0, err
    assert "skill_updated=1" in err


def test_skill_on_other_branch_says_branch_not_edits(env):
    push_change(env["skill_seed"], {"skill/shop-data-analytics/VERSION": NEXT + "\n"})
    git(env["skill_clone"], "checkout", "-q", "-b", "mine")
    code, out, err = env["run"](outside(env))
    assert code == 6 and "지금 mine" in err and "고친 파일" not in err


# 2. 정의 저장소 판별

@pytest.mark.parametrize("url", ["https://github.com/hy-jaden-jeong/semantic-layer-pattern.git",
                                 "https://github.com/hy-jaden-jeong/semantic-layer-pattern",
                                 "git@github.com:hy-jaden-jeong/semantic-layer-pattern.git",
                                 "ssh://git@github.com/hy-jaden-jeong/semantic-layer-pattern.git"])
def test_defs_checkout_recognised_by_origin_url(env, url):
    co = checkout(env)
    alias(co, url, str(env["shop_bare"]))
    push_change(env["shop_seed"], index("v2"))
    code, out, err = env["run"](co, url="/no/such/shop-bi.git")
    assert code == 0, err
    assert "via=checkout" in err and marker(out) == "v2"


@pytest.mark.parametrize("url", ["https://github.com/hy-jaden-jeong/semantic-layer-pattern-dashboards.git",
                                 "https://github.com/someone/hy-jaden-jeong/semantic-layer-pattern.git"])
def test_similar_named_repo_is_not_defs_repo(env, url):
    other_bare, _ = make_bare(env["tmp"], "dash", {"README.md": "x"})
    co = env["tmp"] / "dash-co"
    git(env["tmp"], "clone", "-q", str(other_bare), str(co))
    alias(co, url, str(other_bare))
    code, out, err = env["run"](co)
    assert code == 0, err
    assert "via=checkout" not in err and marker(out) == "v1"


# 3. checkout 안: main을 명시해 받는다

def test_shallow_feature_only_checkout_reads_main_and_keeps_cache(env):
    assert env["run"](outside(env))[0] == 0                       # cache v1
    git(env["shop_seed"], "checkout", "-q", "-b", "feature")
    push_change(env["shop_seed"], {"feature.txt": "f\n"}, msg="feature")
    git(env["shop_seed"], "push", "-q", "origin", "feature")
    git(env["shop_seed"], "checkout", "-q", "main")
    push_change(env["shop_seed"], index("v2"))
    url = f"file://{env['shop_bare']}"
    co = env["tmp"] / "shallow"
    git(env["tmp"], "clone", "-q", "--depth", "1", "--branch", "feature", url, str(co))
    code, out, err = env["run"](co, url=url)
    assert code == 0, err
    assert "via=checkout" in err and marker(out) == "v2"
    assert re.search(r"ref=main@[0-9a-f]{7}", err)
    go_offline(env)
    code, out, err = env["run"](outside(env))
    assert code == 0, err


def test_main_without_semantic_in_checkout_stops_and_keeps_cache(env):
    assert env["run"](outside(env))[0] == 0                       # cache v1
    empty, _ = make_bare(env["tmp"], "empty", {"README.md": "x"})
    co = env["tmp"] / "empty-co"
    git(env["tmp"], "clone", "-q", str(empty), str(co))
    code, out, err = env["run"](co, url=empty)
    assert code == 3, err
    go_offline(env)
    code, out, err = env["run"](outside(env))
    assert code == 0 and marker(out) == "v1", err


# 4. 오프라인: 로컬에서 가장 최근 정의

def test_offline_checkout_prefers_newer_origin_main_over_cache(env):
    assert env["run"](outside(env))[0] == 0                       # cache v1
    push_change(env["shop_seed"], index("v2"))
    co = checkout(env)                                            # origin/main = v2
    go_offline(env)
    code, out, err = env["run"](co)
    assert code == 0, err
    assert marker(out) == "v2"
    assert "source=main" in err and "freshness=unknown" in err and "last_checked=" in err


def test_offline_checkout_prefers_newer_cache_over_origin_main(env):
    co = checkout(env)                                            # origin/main = v1
    push_change(env["shop_seed"], index("v2"))
    assert env["run"](outside(env))[0] == 0                       # cache v2
    go_offline(env)
    code, out, err = env["run"](co)
    assert code == 0, err
    assert marker(out) == "v2"
    assert "source=cache" in err and "freshness=unknown" in err and "last_checked=20" in err


def test_offline_checkout_without_cache_uses_origin_main(env):
    co = checkout(env)
    go_offline(env)
    code, out, err = env["run"](co)
    assert code == 0, err
    assert marker(out) == "v1" and "freshness=unknown" in err


def test_offline_checkout_reports_when_main_was_last_fetched(env):
    co = checkout(env)
    git(co, "fetch", "-q", "origin")                              # 사용자가 예전에 받아 둠
    go_offline(env)
    code, out, err = env["run"](co)
    assert code == 0, err
    assert re.search(r"last_checked=20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ", err), err


# 5. checkout 밖: 받은 사본을 다시 쓰고, 낡았으면 main을 받는다

def test_outside_reuses_cache_when_main_unchanged(env):
    o = outside(env)
    assert "via=clone" in env["run"](o)[2]
    code, out, err = env["run"](o)
    assert code == 0, err
    assert "source=main" in err and "via=cache-current" in err and marker(out) == "v1"
    push_change(env["shop_seed"], index("v2"))
    code, out, err = env["run"](o)
    assert code == 0, err
    assert "via=clone" in err and marker(out) == "v2"


def test_outside_takes_main_even_if_default_branch_differs(env):
    git(env["shop_seed"], "checkout", "-q", "-b", "develop")
    push_change(env["shop_seed"], index("v-develop"), msg="develop")
    git(env["shop_seed"], "push", "-q", "origin", "develop")
    git(env["shop_bare"], "symbolic-ref", "HEAD", "refs/heads/develop")
    code, out, err = env["run"](outside(env))
    assert code == 0, err
    assert marker(out) == "v1"


# 6. skill_min

@pytest.mark.parametrize("line", ["skill_min: 2.0", "skill_min: x", "min: 1"])
def test_bad_skill_min_is_format_error(env, line):
    push_change(env["shop_seed"], {f"{SEM}/index.md": f"format: 1\n{line}\n\nv2\n"})
    code, out, err = env["run"](outside(env))
    assert code == 5 and out == "" and "형식" in err


def test_crlf_skill_min_is_compared(env):
    push_change(env["shop_seed"], {f"{SEM}/index.md": "format: 1\r\nskill_min: 9\r\n\r\nv2\r\n"})
    code, out, err = env["run"](outside(env))
    assert code == 5 and "skill version 9" in err


def test_skill_min_met_after_self_update(env):
    """정의가 지금보다 새 skill(NEXT)을 요구하고 skill 저장소에 NEXT가 있으면, 갱신 뒤 비교해 통과한다."""
    push_change(env["skill_seed"], {"skill/shop-data-analytics/VERSION": NEXT + "\n"})
    push_change(env["shop_seed"], index("v2", skill_min=int(NEXT)))
    code, out, err = env["run"](outside(env))
    assert code == 0, err
    assert "skill_updated=1" in err and marker(out) == "v2"


def test_skill_min_still_high_after_self_update_stops(env):
    push_change(env["skill_seed"], {"skill/shop-data-analytics/VERSION": NEXT + "\n"})
    push_change(env["shop_seed"], index("v2", skill_min=9))
    code, out, err = env["run"](outside(env))
    assert code == 5 and out == ""
    assert "skill_updated=1" in err and "skill version 9" in err and f"지금 {NEXT}" in err


# 7. 종료 코드

def test_no_git_exits_2(env, tmp_path):
    empty_bin = tmp_path / "bin"
    empty_bin.mkdir()
    code, out, err = env["run"](outside(env), extra_env={"PATH": str(empty_bin)}, bash="/bin/bash")
    assert code == 2 and "git" in err


def test_exit_codes_documented_the_same_everywhere():
    sh = (SKILL / "scripts/locate.sh").read_text()
    used = {int(n) for n in re.findall(r"\bexit ([0-9])\b", sh)}
    assert used == {0, 2, 3, 4, 5, 6}
    header = "\n".join(l for l in sh.splitlines()[:20] if l.startswith("#"))
    doc = (SKILL / "SKILL.md").read_text()
    want = {2: ["git"], 3: ["semantic layer"], 4: ["가진 정의"], 5: ["형식"], 6: ["자동 갱신"]}
    for code, words in want.items():
        for text in (header, doc):
            line = re.search(rf"(?<![0-9]){code}[ :][^/\n]*", text)
            assert line, (code, text[:200])
            assert all(w in line.group(0) for w in words), (code, line.group(0))


# 8. 동시 실행

def test_concurrent_runs_never_fail(env):
    o = outside(env)
    assert env["run"](o)[0] == 0
    bad = []
    for rnd in range(4):
        push_change(env["shop_seed"], index(f"r{rnd}"))         # 매 번 모두 새로 받게 한다
        with ThreadPoolExecutor(6) as ex:
            res = list(ex.map(lambda _: env["run"](o), range(6)))
        bad += [r for r in res if r[0] != 0 or marker(r[1]) != f"r{rnd}"]
    assert not bad, bad[:2]
    left = [p.name for p in env["cache"].iterdir() if p.name.startswith(".")]
    assert left == [], left                                       # 임시 폴더·파일이 남지 않는다
    assert not list(env["cache"].glob("sha-*/semantic/semantic")) and not list(env["cache"].glob("sha-*/.tmp*"))
