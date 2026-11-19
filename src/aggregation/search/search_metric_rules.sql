CREATE SCHEMA IF NOT EXISTS `dev-shop-bi-catalog`.ref;

-- 상점 내 검색 로그를 지표 code로 가르는 규칙(seed). silver.search_events가 이 규칙으로 로그를 분류한다.
--   지표 code는 여기서만 정한다. gold.search_metric_monthly는 code를 그대로 넘겨받는다.
CREATE TABLE IF NOT EXISTS `dev-shop-bi-catalog`.ref.search_metric_rules (
  metric STRING, metric_label STRING, paths ARRAY<STRING>, needs_review BOOLEAN
) USING delta;

INSERT OVERWRITE `dev-shop-bi-catalog`.ref.search_metric_rules VALUES
 ('keyword_search', '키워드 검색', array('/search'), false),
 ('category_browse', '카테고리 탐색', array('/category', '/category/list'), false),
 ('filter_search', '필터 검색', array('/search/filter'), false);
