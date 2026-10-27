-- BI layer for Power BI: plain views over the Gold tables (no data copied, always current after a job run).
-- Run once in Databricks SQL Editor on a SQL warehouse (e.g. wh-novacart-bi), then publish schema
-- dpe_azure_poc.novacart_bi to Power BI (Catalog Explorer -> novacart_bi -> Use with BI tools).
CREATE SCHEMA IF NOT EXISTS dpe_azure_poc.novacart_bi
  COMMENT 'Business-ready views for Power BI (Gold layer only)';

CREATE OR REPLACE VIEW dpe_azure_poc.novacart_bi.dim_date            AS SELECT * FROM dpe_azure_poc.novacart_poc.gold_dim_date;
CREATE OR REPLACE VIEW dpe_azure_poc.novacart_bi.dim_channel         AS SELECT * FROM dpe_azure_poc.novacart_poc.gold_dim_channel;
CREATE OR REPLACE VIEW dpe_azure_poc.novacart_bi.dim_products        AS SELECT * FROM dpe_azure_poc.novacart_poc.gold_dim_products;
CREATE OR REPLACE VIEW dpe_azure_poc.novacart_bi.dim_customers       AS SELECT * FROM dpe_azure_poc.novacart_poc.gold_dim_customers;
CREATE OR REPLACE VIEW dpe_azure_poc.novacart_bi.dim_campaigns       AS SELECT * FROM dpe_azure_poc.novacart_poc.gold_dim_campaigns;
CREATE OR REPLACE VIEW dpe_azure_poc.novacart_bi.fact_orders         AS SELECT * FROM dpe_azure_poc.novacart_poc.gold_fact_orders;
CREATE OR REPLACE VIEW dpe_azure_poc.novacart_bi.fact_order_items    AS SELECT * FROM dpe_azure_poc.novacart_poc.gold_fact_order_items;
CREATE OR REPLACE VIEW dpe_azure_poc.novacart_bi.fact_payments       AS SELECT * FROM dpe_azure_poc.novacart_poc.gold_fact_payments;
CREATE OR REPLACE VIEW dpe_azure_poc.novacart_bi.fact_sessions       AS SELECT * FROM dpe_azure_poc.novacart_poc.gold_fact_sessions;
CREATE OR REPLACE VIEW dpe_azure_poc.novacart_bi.fact_website_events AS SELECT * FROM dpe_azure_poc.novacart_poc.gold_fact_website_events;
CREATE OR REPLACE VIEW dpe_azure_poc.novacart_bi.customer_summary    AS SELECT * FROM dpe_azure_poc.novacart_poc.gold_customer_summary;
