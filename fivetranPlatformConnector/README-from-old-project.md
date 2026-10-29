# Fivetran Platform Connector Value Dashboard

This repository helps teams explore the operational and usage data that the Fivetran Platform Connector lands in Snowflake. It includes four dbt Charts dashboards and a set of read-only SQL checks to help you assess the data and see where it can be useful.

## Video preview

[▶ Watch the video preview on Google Drive](https://drive.google.com/file/d/1YO1ApgH-kznuuBC4KQVUM_S5JSqRXO1Y/view?usp=drive_link)

## What value can you get from this repo?

- **Investigate recorded operational events:** review event volumes over time, narrow them by connection and date, and inspect recorded event details and payloads.
- **Understand MAR usage:** see paid, other-classified and unclassified usage; compare trends; and identify the tables and categories contributing to consumption.
- **Trace recorded changes and user actions:** review destination schema changes and account-level audit activity in separate views.
- **Explore a transparent capacity-value scenario:** adjust investigation time, time reduction, hourly value and cost assumptions to estimate potential capacity released and first-year net value.
- **Validate your starting data:** use the included SQL checks to verify expected columns, source coverage and join-key uniqueness before relying on dashboard results.

The calculator is an assumption-based scenario, not a promise of savings. Released engineering capacity is not automatically a cash saving, and the dashboards do not claim to determine connector health or prevent incidents.

## What is included

| Dashboard | What you can explore |
| --- | --- |
| Operations | Recorded-event KPIs, daily trend, connection summary, event details and selected payload |
| MAR usage | Paid, other-classified and unclassified MAR; daily trend; top table contributors and categories |
| Changes and audit | Destination schema changes and account-level user actions in separate tabs |
| Value calculator | Adjustable assumptions for released time, capacity value and first-year net value |

Dashboards query the existing Snowflake source tables directly. The starter does not require a new Python application, Snowflake app object, dbt model build or Fivetran API credentials. Queries run from the local dbt Charts process, so use an approved workstation and network path.

## SQL checks

Run these checks with the same Snowflake role you plan to use for the dashboards. They are read-only; review warehouse/query cost before running scans on a large data estate.

| SQL file | What it checks | Expected result |
| --- | --- | --- |
| [`schema_check.sql`](sql/schema_check.sql) | Required source tables and columns are visible to your role | Required columns report `OK` |
| [`source_check.sql`](sql/source_check.sql) | Row counts and date coverage for LOG, MAR and audit data | Confirm records and date ranges cover your intended review |
| [`join_key_check.sql`](sql/join_key_check.sql) | Duplicate or null metadata keys that could inflate joined results | Zero rows |
| [`event_id_check.sql`](sql/event_id_check.sql) | Duplicate or null LOG IDs used to select event details | Zero rows |
| [`calculator_check.sql`](sql/calculator_check.sql) | Default value-calculator arithmetic | 15 hours/month, AUD 2,250/month capacity value, AUD 27,000 first-year net value |

Example commands:

```bash
dct query fivetran --file sql/schema_check.sql
dct query fivetran --file sql/source_check.sql
dct query fivetran --file sql/join_key_check.sql
dct query fivetran --file sql/event_id_check.sql
dct query fivetran --file sql/calculator_check.sql
```

An empty result from a data-coverage check can mean there is no data for that source or period; it does not indicate healthy pipelines. A missing column can reflect connector configuration, identifiers or permissions. Check the actual Snowflake schema and access with your administrator.

## Get started

1. Install Python 3.11 or later and `dbt-charts[snowflake]` in a new virtual environment, following your organization's approved installation process.
2. Copy `local_env.example.sh` to `local_env.sh`; set your Snowflake account, user, approved read-only role and warehouse. Keep credentials and local environment files out of Git.
3. Load the environment and check the connection:

   ```bash
   source local_env.sh
   dct query fivetran "SELECT CURRENT_ACCOUNT(), CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE()"
   ```

4. Run the SQL checks above, then validate and preview the dashboards:

   ```bash
   dct validate charts/
   dct validate charts/ --warehouse
   dct serve --host 127.0.0.1 --port 3000 --no-cache
   ```

Open the local URL printed by `dct serve`. These files are a prepared starter, not a deployed or production-validated application. Validate the queries and dashboards against your Snowflake account before presenting or relying on results. Keep the local server bound to loopback; use an approved authenticated hosting route for sharing.

For questions or help, please reach out to [naag.balakrish@fivetran.com](mailto:naag.balakrish@fivetran.com).
