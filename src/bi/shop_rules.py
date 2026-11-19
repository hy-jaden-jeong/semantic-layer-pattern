"""판매자 관련 공통 SQL 규칙(mart·대시보드 dataset이 함께 쓴다). 가상 예제다."""
from __future__ import annotations

# 내부·테스트 판매자 seller_id 참조 table. 이름이 아니라 id로 뺀다.
INTERNAL_REF = "`dev-shop-bi-catalog`.ref.internal_seller_id"


def exclude_internal(id_col: str) -> str:
    """내부·테스트 판매자를 빼는 predicate. id_col은 seller_id column 참조식(예: "h.seller_id")."""
    return f"{id_col} NOT IN (SELECT seller_id FROM {INTERNAL_REF})"
