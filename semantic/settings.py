"""옮겨 쓸 때 바꾸는 값. 검사·생성 코드는 project 이름이나 경로를 여기서만 읽는다."""

NAMESPACE = "shop"        # 표준에 없는 뜻을 담는 곳: config.meta.<NAMESPACE>
PROJECT = "shop-bi"       # index.md 제목에 쓰는 이름

SEM_DIR = "semantic"      # 정의 폴더(저장소 루트 기준). skill의 locate.sh도 같은 경로를 쓴다
MODELS_DIR = "models"     # dbt model-paths
SEEDS_DIR = "seeds"       # dbt seed-paths
MACROS_DIR = "macros"     # dbt macro-paths

# models/<layer>/와 seeds/<group>/이 어느 schema로 가는가. dbt_project.yml의 +schema와 같게 둔다.
LAYER_SCHEMA = {"staging": "staging", "intermediate": "intermediate", "marts": "mart"}
SEED_SCHEMA = {"raw": "raw", "ref": "ref"}

# semantic layer가 덮는 schema. 이 schema의 model은 모두 정의하거나 not_modeled.yml에 이유를 적는다.
MART_SCHEMA = "mart"
