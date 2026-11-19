-- shop_kpi_daily를 일자 × 지표 column으로 펼친 view. 시트로 내보낼 때만 쓴다. 뜻은 shop_kpi_daily를 따른다.
CREATE OR REPLACE VIEW `dev-shop-bi-catalog`.gold.shop_kpi_wide AS
SELECT event_date,
       MAX(CASE WHEN metric = 'dau' THEN value END) AS dau,
       MAX(CASE WHEN metric = 'order_count' THEN value END) AS order_count,
       MAX(CASE WHEN metric = 'order_amount_krw' THEN value END) AS order_amount_krw
FROM `dev-shop-bi-catalog`.gold.shop_kpi_daily
GROUP BY event_date;
