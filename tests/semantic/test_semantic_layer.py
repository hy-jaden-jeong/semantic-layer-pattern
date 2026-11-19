"""semantic layer 정의 검사(docs/verification.md).

정의를 하나씩 망가뜨린 사본에서 검사가 그 문제를 잡는지 본다. 실제 정의가 문제 0인지는 test_repo_definitions.py가 본다.
"""
import shutil
from pathlib import Path

import pytest

from semantic import checks

REPO = Path(__file__).resolve().parents[2]
SEM = REPO / "semantic"
KPI = "manifest/tables/commerce/shop_kpi_daily.yml"
FUNNEL = "manifest/tables/commerce/checkout_funnel_daily.yml"
HEALTH = "manifest/tables/seller/seller_health_score.yml"
DAU = "manifest/metrics/commerce/shop_kpi_daily/dau.yml"
EOD = "manifest/metrics/commerce/shop_kpi_daily/seller_plan_active_eod.yml"
ACTIVE_USER = "glossary/active_user.yml"
ACTIVE_SELLER = "glossary/active_seller.yml"


@pytest.fixture
def broken(tmp_path):
    """정의 폴더 사본에서 rel 파일의 a를 b로 바꾸고 문제 목록을 돌려준다."""
    def _broken(rel, a, b, **kw):
        sem = tmp_path / "semantic"
        shutil.copytree(SEM, sem, ignore=shutil.ignore_patterns("__pycache__", "*.py"))
        path = sem / rel
        text = path.read_text(encoding="utf-8")
        assert a in text, f"{rel}에 바꿀 문자열이 없다: {a}"
        path.write_text(text.replace(a, b, 1), encoding="utf-8")
        return checks.problems(REPO, sem=sem, **{"coverage": False, **kw})
    return _broken


S1_CASES = [
    ("표준: metric의 모르는 key", DAU, "  type: simple\n  type_params:\n    measure: shop_kpi_daily_value_distinct",
     "  type: simple\n  rollup: none\n  type_params:\n    measure: shop_kpi_daily_value_distinct", "[표준]"),
    ("표준: 없는 measure", EOD, "measure: shop_kpi_daily_value_eod\n", "measure: shop_kpi_daily_value_eodd\n", "[표준]"),
    ("filter가 없는 dimension을 가리킴", DAU, "shop_kpi_daily_row__metric') }} = 'dau'",
     "shop_kpi_daily_row__nope') }} = 'dau'", "filter가"),
    ("meta.shop key 오타", EOD, "status: conflict", "statuss: conflict", "모르는 key"),
    ("status enum 오타", DAU, "status: confirmed", "status: confirmd", "status="),
    ("rollup과 non_additive_dimension 어긋남", KPI, "rollup: last", "rollup: sum", "어긋난다"),
]


@pytest.mark.parametrize("name,rel,a,b,needle", S1_CASES, ids=[c[0] for c in S1_CASES])
def test_s1_broken_definition_is_caught(broken, name, rel, a, b, needle):
    problems = broken(rel, a, b)
    assert any(needle in p for p in problems), problems


# ── S2: mart model의 지표가 정의에 다 있는가 ───────────────────────────────────────
KPI_SQL = "models/marts/commerce/shop_kpi_daily.sql"
DAU_BRANCH = "select login_date as event_date, 'overview' as category, 'dau' as metric, count(distinct member_id) as value"
DAU_FROM = "\n    from logins group by login_date\n    union all\n    "


@pytest.fixture
def fake_repo(tmp_path):
    """dbt project(models·seeds·macros)와 정의 폴더를 사본으로 뜬 저장소. sql_edit(a, b)로 mart model을 고친다."""
    repo = tmp_path / "repo"
    for folder in ("models", "seeds", "macros", "semantic"):
        shutil.copytree(REPO / folder, repo / folder, ignore=shutil.ignore_patterns("__pycache__", "*.py"))

    def sql_edit(a, b):
        path = repo / KPI_SQL
        text = path.read_text(encoding="utf-8")
        assert a in text, a
        path.write_text(text.replace(a, b, 1), encoding="utf-8")
        return [p for p in checks.problems(repo, sem=repo / "semantic") if "shop_kpi_daily" in p]
    return repo, sql_edit


def test_s2_undefined_mart_metric_is_reported_with_minimal_definition(fake_repo):
    repo, _ = fake_repo
    wau = "manifest/metrics/commerce/shop_kpi_daily/wau.yml"
    (repo / "semantic" / wau).unlink()
    found = checks.problems(repo, sem=repo / "semantic")
    missing = [p for p in found if "mart에 있는 지표 'wau'가 정의에 없다" in p]
    assert len(missing) == 1
    # 만들 파일 경로를 알려 준다
    assert f"{wau} 파일을 만들어" in missing[0]
    assert "{measure: shop_kpi_daily_value_distinct}" in missing[0]   # rollup none인 measure 중 먼저 적힌 것
    # 붙여 넣을 최소 metric 문서가 메시지에 들어 있다
    assert "metric:" in missing[0] and "name: wau" in missing[0]
    assert "{{ Dimension('shop_kpi_daily_row__metric') }} = 'wau'" in missing[0]


def test_s2_new_literal_code_without_definition_fails(fake_repo):
    _, sql_edit = fake_repo
    found = sql_edit(DAU_BRANCH, DAU_BRANCH.replace("'dau' as metric", "'brand_new_metric' as metric") + DAU_FROM + DAU_BRANCH)
    assert any("'brand_new_metric'가 정의에 없다" in p for p in found), found


def test_s2_new_prefix_without_family_fails(fake_repo):
    _, sql_edit = fake_repo
    found = sql_edit("'order_pay_' ||", "'order_paid_' ||")
    assert any("새 prefix 'order_paid_'" in p for p in found), found


def test_s2_new_code_inside_known_prefix_passes(fake_repo):
    _, sql_edit = fake_repo
    before = sql_edit("'dau' as metric", "'dau' as metric")
    after = sql_edit(DAU_BRANCH, DAU_BRANCH.replace("'dau' as metric", "'order_pay_newmethod_count' as metric") + DAU_FROM + DAU_BRANCH)
    assert after == before


def test_s2_placeholder_left_in_pasted_definition_fails(broken):
    found = broken(DAU, "label: DAU(로그인 회원 수)", "label: <사람이 읽는 이름>")
    assert any("자리표시" in p for p in found), found


# ── S3: 옆 파일과 원본·status·규칙·PII ──────────────────────────────────────────
S3_CASES = [
    ("D 등급 원본 인용", "sources.yml", "주요 지표 집계 기준, kind: wiki, ref: data/metric-criteria, owner: 데이터팀(리드), grade: A",
     "주요 지표 집계 기준, kind: wiki, ref: data/metric-criteria, owner: 데이터팀(리드), grade: D", "D 등급"),
    ("confirmed인데 A·B 원본 없음", DAU, "status: confirmed\n        docs:\n        - wiki.metric-criteria\n",
     "status: confirmed\n        docs:\n        - wiki.quarterly-report\n", "A·B 등급"),
    ("conflict인데 question 없음", EOD, "        questions:\n        - Q-active-seller\n        - Q-plan-scope\n",
     "", "question이 없다"),
    ("원본 등급 오타", "sources.yml", "grade: A, checked_on", "grade: AA, checked_on", "grade"),
    ("model이 모르는 공통 규칙", KPI, "          latest_snapshot: na\n",
     "          latest_snapshot: na\n          weekend_only: applied\n", "모르는 규칙"),
    ("내부 판매자 제외 SQL이 macro와 다름", "rules.yml", "NOT IN (SELECT seller_id",
     "NOT IN (SELECT DISTINCT seller_id", "exclude_internal()"),
    ("정의에 이메일", DAU, "description: 그날(KST) 로그인 기록이", "description: someone@example.com 그날(KST) 로그인 기록이",
     "PII"),
    ("정의에 법인 표기", ACTIVE_SELLER, "label: 활성 판매자", "label: 활성 판매자(주식회사 가나다)", "PII"),
]


@pytest.mark.parametrize("name,rel,a,b,needle", S3_CASES, ids=[c[0] for c in S3_CASES])
def test_s3_broken_side_file_is_caught(broken, name, rel, a, b, needle):
    problems = broken(rel, a, b)
    assert any(needle in p for p in problems), problems


# ── S4: 관계(edge)와 생성물, skill과 정의 사이의 약속 ────────────────────────────
DIM_STORE = "manifest/tables/relations/dim_store.yml"
DIM_MEMBER = "manifest/tables/relations/dim_member_seller.yml"


S4_CASES = [
    ("YAML만 고치고 render 안 함", DAU, "label: DAU(로그인 회원 수)", "label: DAU(로그인 기준 회원 수)", "낡았다"),
    ("관계를 두 곳에 적음", DIM_STORE, "          - {from: store, to: seller, cardinality: many_to_one}",
     "          - {from: store, to: seller, cardinality: many_to_one}\n"
     "          - {from: seller, to: store, cardinality: many_to_many}", "적는 곳은 하나"),
    ("via table에 없는 join key", DIM_MEMBER, "{name: seller, type: foreign, expr: seller_id}",
     "{name: seller, type: foreign, expr: seller_idd}", "column"),
    ("cardinality가 entity type과 어긋남", DIM_MEMBER, "cardinality: many_to_many", "cardinality: many_to_one", "어긋난다"),
    ("README 약속 절이 없음", "README.md", "## 질문에 답하기", "## 질문 답하기", "README"),
    ("index.md 형식 표시가 없음", "index.md", "format: 1", "format: 2", "index.md"),
]


@pytest.mark.parametrize("name,rel,a,b,needle", S4_CASES, ids=[c[0] for c in S4_CASES])
def test_s4_broken_relation_or_generated_file_is_caught(broken, name, rel, a, b, needle):
    problems = broken(rel, a, b)
    assert any(needle in p for p in problems), problems


# ── S5: mart model 전부에 정의나 제외 사유가 있는가 ─────────────────────────────
def test_s5_mart_model_without_definition_or_reason_fails(broken):
    found = broken("not_modeled.yml", "  - table: mart.seller_health_score_legacy",
                   "  - table: mart.seller_health_score_legacy_x", coverage=True)
    assert any("mart.seller_health_score_legacy: table 정의도 not_modeled 사유도 없다" in p for p in found), found


def test_s5_wide_column_without_definition_fails(broken):
    found = broken(FUNNEL, "          store_name: 옛 대시보드 호환 column. 이름을 수집하지 않아 늘 NULL이다.\n",
                   "          event_date: 시험용 자리\n", coverage=True)
    missing = [p for p in found if "mart column 'store_name'가 정의에 없다" in p]
    assert missing and "metric:" in missing[0] and "expr: store_name" in missing[0], found
    assert "name: funnel_store_name" in missing[0]                 # metric_prefix를 붙여 제안
    assert "manifest/metrics/commerce/checkout_funnel_daily/funnel_store_name.yml 파일을 만들어" in missing[0]


# ── 빠짐 검사의 구멍(검증에서 찾아 막은 것) ──────────────────────────────────────
KPI_TAIL = "     and not m.is_deleted\n    group by sp.d\n"       # unioned CTE의 마지막 갈래


def _append_branch(sql_edit, branch):
    return sql_edit(KPI_TAIL, KPI_TAIL + "    union all\n    " + branch + "\n")


def test_fix_unreadable_branch_fails(fake_repo):
    _, sql_edit = fake_repo
    found = _append_branch(sql_edit, "select sp.d, 'snapshot', if(sp.d > date '2020-01-01', 'zz_a', 'zz_b'), "
                                     "count(*) from spine sp group by sp.d")
    assert any("지표 code를 읽지 못했다" in p for p in found), found


def test_fix_code_inside_another_cte_is_read(fake_repo):
    _, sql_edit = fake_repo
    sql_edit("with logins as (", "with zz_cte as (select date '2026-01-01' as d, 'zz_in_cte' as metric), logins as (")
    found = _append_branch(sql_edit, "select z.d, 'snapshot', z.metric, count(*) from zz_cte z group by z.d, z.metric")
    assert any("'zz_in_cte'가 정의에 없다" in p for p in found), found


def test_fix_column_passed_from_another_model_fails(fake_repo):
    _, sql_edit = fake_repo
    found = _append_branch(sql_edit, "select o.order_date, 'order', o.pay_method, count(*) "
                                     "from {{ ref('int_orders') }} o group by o.order_date, o.pay_method")
    assert any("지표 code를 읽지 못했다" in p for p in found), found


def test_fix_comments_and_quoted_dashes_do_not_confuse_extractor(fake_repo):
    _, sql_edit = fake_repo
    before = sql_edit("'dau' as metric", "'dau' as metric")
    after = _append_branch(sql_edit, "/* 옛 갈래: don't\n    select sp.d, 'snapshot', 'zz_in_block_comment', 1 from spine sp */\n"
                                     "    {# select sp.d, 'snapshot', 'zz_in_jinja_comment', 1 from spine sp #}\n"
                                     "    select sp.d, 'snapshot', 'dau', count(case when '--' = '--' then 1 end) from spine sp group by sp.d")
    assert after == before


# ── 정의 검사의 빈틈(검증에서 찾아 막은 것) ──────────────────────────────────────
USAGE = "manifest/tables/seller/seller_usage_monthly.yml"
SELLERS = "manifest/metrics/seller/seller_usage_monthly/su_active_sellers.yml"
FIX_DEF_CASES = [
    ("counts가 없는 entity", DAU, "        counts: member\n", "        counts: nobody\n", "counts"),
    ("glossary used_by가 없는 원본", ACTIVE_USER, "used_by: [wiki.metric-criteria]", "used_by: [wiki.nope]", "원본 wiki.nope"),
    ("long.inherits가 없는 model", USAGE, "          - search_metric_monthly\n", "          - search_metric_monthlyx\n", "inherits"),
    ("measure expr가 없는 column", KPI, "    expr: value\n", "    expr: value_typo\n", "value_typo"),
    ("last measure의 window_choice min", KPI, "      window_choice: max\n", "      window_choice: min\n", "window_choice"),
    ("model rules에서 규칙 하나 빠짐", KPI, "          exclude_internal: not_applied\n", "", "rules.exclude_internal"),
    ("PII ㈜", ACTIVE_SELLER, "label: 활성 판매자", "label: 활성 판매자(㈜가나다)", "PII"),
    ("PII 국제 전화", DAU, "description: 그날(KST) 로그인 기록이", "description: 문의 +82-10-1234-5678 그날(KST) 로그인 기록이", "PII"),
    ("PII 점·붙여 쓴 전화", DAU, "description: 그날(KST) 로그인 기록이", "description: 문의 01012345678 그날(KST) 로그인 기록이", "PII"),
    ("PII YAML escape", ACTIVE_SELLER, "label: 활성 판매자", 'label: "활성 판매자 \\uC8FC\\uC2DD\\uD68C\\uC0AC"', "PII"),
    ("표준 경고(모르는 granularity)", SELLERS,
     "filter: \"{{ Dimension('seller_usage_monthly_row__metric_source') }} != 'cs'\"",
     "filter: \"{{ Dimension('seller_usage_monthly_row__metric_source') }} != 'cs' AND "
     "{{ TimeDimension('seller_usage_monthly_row__event_month', 'fortnight') }} >= '2026-01'\"", "[표준"),
]


@pytest.mark.parametrize("name,rel,a,b,needle", FIX_DEF_CASES, ids=[c[0] for c in FIX_DEF_CASES])
def test_fix_broken_definition_is_caught(broken, name, rel, a, b, needle):
    problems = broken(rel, a, b)
    assert any(needle in p for p in problems), problems


def test_fix_yaml_extension_in_manifest_fails(broken, tmp_path):
    broken(DAU, "label: DAU(로그인 회원 수)", "label: DAU(로그인 회원 수)")
    sem = tmp_path / "semantic"
    (sem / DAU).rename(sem / DAU.replace(".yml", ".yaml"))
    found = checks.problems(REPO, sem=sem, coverage=False)
    assert any(".yaml" in p for p in found), found


# ── 파일 배치: 파일 하나에 정의 하나 ────────────────────────────────────────────
@pytest.fixture
def edited(tmp_path):
    """정의 폴더 사본에서 edit(sem)으로 파일을 옮기거나 더한 뒤 문제 목록을 돌려준다."""
    def _edited(edit):
        sem = tmp_path / "semantic"
        shutil.copytree(SEM, sem, ignore=shutil.ignore_patterns("__pycache__", "*.py"))
        edit(sem)
        return checks.problems(REPO, sem=sem, coverage=False)
    return _edited


def _append(rel, text):
    def edit(sem):
        path = sem / rel
        path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")
    return edit


def _write(rel, text):
    def edit(sem):
        (sem / rel).write_text(text, encoding="utf-8")
    return edit


def _rename(rel, new):
    def edit(sem):
        (sem / new).parent.mkdir(parents=True, exist_ok=True)
        (sem / rel).rename(sem / new)
    return edit


HS_SCORE = "manifest/metrics/seller/seller_health_score/hs_score.yml"
LAYOUT_CASES = [
    ("metric 파일에 문서 둘", _append(DAU, "---\n" + (SEM / EOD).read_text(encoding="utf-8")), "metric 문서 하나만"),
    ("model 파일에 metric을 붙임", _append(KPI, "---\n" + (SEM / DAU).read_text(encoding="utf-8")), "semantic_model 문서 하나만"),
    ("metric 파일 이름이 name과 다름", _rename(DAU, DAU.replace("dau.yml", "daily_active.yml")), "파일 이름이 metric name"),
    ("model 파일 이름이 name과 다름", _rename(KPI, KPI.replace("shop_kpi_daily.yml", "kpi.yml")), "파일 이름이 semantic_model name"),
    ("metric을 다른 table 폴더에 둠", _rename(DAU, "manifest/metrics/commerce/checkout_funnel_daily/dau.yml"),
     "measure shop_kpi_daily_value_distinct는 shop_kpi_daily에 있다"),
    ("옛 배치(table 하나에 파일 하나)", _rename(KPI, "manifest/commerce/shop_kpi_daily.yml"), "정의 파일은"),
    ("용어 파일 이름이 id와 다름", _rename(ACTIVE_USER, "glossary/active_users.yml"), "파일 이름이 id(active_user)"),
    ("질문 파일 이름이 id와 다름", _rename("questions/Q-tier-direction.yml", "questions/Q-tier.yml"),
     "파일 이름이 id(Q-tier-direction)"),
    ("용어 파일에 항목을 list로", _write("glossary/extra.yml", "- id: extra\n- id: extra2\n"), "항목 하나"),
    ("project.yml에 metric을 붙임", _append("manifest/project.yml", "---\n" + (SEM / DAU).read_text(encoding="utf-8")
                                         .replace("name: dau\n", "name: dau_in_project\n")), "project_configuration 문서 하나만"),
    ("빈 metric 문서", _write("manifest/metrics/commerce/shop_kpi_daily/zz.yml", "metric:\n"), "metric 문서 하나만"),
    ("metric 이름이 table 접두어와 다름", _write("manifest/metrics/seller/seller_health_score/score.yml",
            (SEM / HS_SCORE).read_text(encoding="utf-8").replace("name: hs_score", "name: score")),
     "metric_prefix 'hs_'로 시작하지 않는다"),
    ("용어 파일을 하위 폴더에", _rename(ACTIVE_USER, "glossary/sub/active_user.yml"), "하위 폴더 없이"),
]


@pytest.mark.parametrize("name,edit,needle", LAYOUT_CASES, ids=[c[0] for c in LAYOUT_CASES])
def test_split_layout_is_enforced(edited, name, edit, needle):
    found = edited(edit)
    assert any(needle in p for p in found), found


# ── dimension 설명 필수 ─────────────────────────────────────────────────────────
def test_split_dimension_without_description_fails(broken):
    found = broken(FUNNEL, "    description: 단계 이름. step_no와 1:1이다.\n", "")
    assert any("dimension step_label에 description이 없다" in p for p in found), found


# ── metric 이름 = table 접두어 + column ─────────────────────────────────────────
def test_suggest_name_does_not_double_prefix():
    assert checks.suggest_name("su_", "su_new_metric") == "su_new_metric"
    assert checks.suggest_name("hs_", "order_growth") == "hs_order_growth"
    assert checks.suggest_name("", "dau") == "dau"
    assert checks.suggest_name(None, "foo_cnt") == "<metric_prefix>foo_cnt"   # 자리표시라 채우기 전엔 검사가 막는다


def test_table_without_metric_prefix_is_reported_once(broken):
    found = broken(HEALTH, "        metric_prefix: 'hs_'\n", "")
    hits = [p for p in found if "table seller_health_score: metric이 있는데 meta.shop.metric_prefix" in p]
    assert len(hits) == 1, found


def test_non_string_metric_prefix_is_reported(broken):
    found = broken(HEALTH, "        metric_prefix: 'hs_'\n", "        metric_prefix: 7\n")
    assert any("metric_prefix(문자열" in p for p in found), found
