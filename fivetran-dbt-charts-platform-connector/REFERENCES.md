# Source basis and documentation

Prepared 22 October 2026.

## User-provided source

`Fivetran_Streamlit_App_Guide.md`, uploaded with the request. Used as the source for database/schema/table/column names, four dashboard views, date and filter scope, MAR classification, current-name matching, audit scope, row caps, caveats and calculator formulas. The source guide itself says its live Snowflake execution was not confirmed. No unseen prior application state or actual warehouse data was inferred.

Relevant original headings: Purpose; Architecture; Dashboard views; Filters and freshness; Metric definitions; Value calculator; Complete application code.

## Current product documentation checked

- Overview: https://docs.dbtcharts.com/
- Installation, Python minimum and adapters: https://docs.dbtcharts.com/guides/installation/
- Source registry, dbt-profile connection and read-only posture: https://docs.dbtcharts.com/sources/
- SQL queries and parameter binding: https://docs.dbtcharts.com/queries/
- Variable options and query-powered labels: https://docs.dbtcharts.com/variables/
- Number/date/select controls: https://docs.dbtcharts.com/variables/ui-elements/
- SQL conditionals and filters: https://docs.dbtcharts.com/variables/expressions/
- Tables, KPI style and callouts: https://docs.dbtcharts.com/charts/tables/
- Rows, columns and tab layouts: https://docs.dbtcharts.com/boards/layouts/
- Validation: https://docs.dbtcharts.com/cli/validate/
- Query execution and named query testing: https://docs.dbtcharts.com/cli/query/
- Local serve, loopback and caching: https://docs.dbtcharts.com/cli/serve/
- Shared deployment: https://docs.dbtcharts.com/cloud/getting-started/
- Snowflake authentication fields: https://docs.getdbt.com/docs/local/connect-data-platform/snowflake-setup

The product documentation informs the implementation syntax. It does not verify the customer's source table contents, permissions or query outcomes. The proposed file organisation and optional dbt model architecture are new implementation choices, not claims from the original guide.
