# Fivetran Value Dashboard - dbt Charts starter

A four-board adaptation of `Fivetran_Streamlit_App_Guide.md`, using the same source database and schema: `NAAG_POSTGRES.NAAG_FIVETRAN_LOG`.

**Build status:** The files have been checked for YAML syntax, duplicate keys, internal query/chart references, Jinja template expansion and calculator arithmetic. They have **not** been validated by the dbt Charts CLI, rendered in its browser UI or executed against your Snowflake account. Treat this as a prepared starter, not a deployed or production-validated application. Complete the checks below before presenting it.

## The two implementation stages

Start with the direct-source version provided here:

```text
Fivetran Platform Connector -> Snowflake source tables -> dbt Charts SQL + YAML -> local browser
```

No Python application rewrite, Snowflake app object, new views, dbt build, Semantic Layer setup or Fivetran API credentials are required for this stage. Unlike Streamlit in Snowflake, the local dbt Charts process opens its own Snowflake connection and receives query results outside Snowflake. Use an approved workstation and network path.

After the first working demo, move shared transformations into tested dbt models:

```text
Fivetran Platform Connector -> Snowflake -> dbt staging/marts -> dbt Charts
```

Do not change the metric definitions during that move. dbt Charts does not build models for you; run your existing dbt build workflow separately.

## Included files

| File | Purpose |
| --- | --- |
| `dbt_charts.yml` | Direct Snowflake connection using your browser-based SSO |
| `local_env.example.sh` | Four account-specific settings to fill in locally |
| `charts/operations.yml` | Recorded-event KPIs, daily trend, connection summary, latest 200 matching events, selected payload |
| `charts/mar_usage.yml` | Month selector, paid/other/unclassified MAR, daily trend, top 20 table contributors and categories |
| `charts/changes_audit.yml` | Destination changes and account-level user actions in separate tabs |
| `charts/value_calculator.yml` | Six assumption inputs and the original capacity-value formulas |
| `sql/schema_check.sql` | Required-column visibility and type check |
| `sql/source_check.sql` | LOG, MAR and audit coverage |
| `sql/join_key_check.sql` | Metadata key uniqueness before joining |
| `sql/event_id_check.sql` | LOG.ID uniqueness for event selection |
| `sql/calculator_check.sql` | Independent default-value calculation |
| `config_examples/` | Alternatives for an existing dbt profile or approved key-pair authentication |
| `scripts/check_local.py` | Limited offline checks; not a substitute for `dct validate` |
| `REFERENCES.md` | Original-guide sections and current vendor documentation |

## Step 1 - Prepare the project folder

Unzip the project. In a terminal, change to its directory. For example, if you extracted it in Downloads:

```bash
cd ~/Downloads/fivetran_dbt_charts
python3 --version
```

Use Python **3.11 or later**, following the current dedicated dbt Charts installation documentation. Some older dbt quickstarts mention an earlier Python minimum. Follow your organisation's approved installation process if Python needs updating.

## Step 2 - Install into a NEW isolated environment

Use a new virtual environment inside this folder. Do not install into an environment that already contains dbt v2 or your existing dbt/Fusion tooling.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "dbt-charts[snowflake]"
dct --version
```

The Snowflake extra supplies the warehouse adapter. Record the installed version with your demo materials after testing it.

An alternative, when `uv` is already installed, is `uv tool install "dbt-charts[snowflake]"`; this also isolates the CLI. Use one installation method, not both.

## Step 3 - Configure your Snowflake connection

```bash
cp local_env.example.sh local_env.sh
```

Open `local_env.sh` in your text editor and replace the four placeholders:

```bash
export SF_ACCOUNT='YOUR_ORG-YOUR_ACCOUNT'
export SF_USER='YOUR_SNOWFLAKE_LOGIN'
export SF_ROLE='YOUR_APPROVED_READ_ONLY_ROLE'
export SF_WAREHOUSE='YOUR_DEVELOPMENT_WAREHOUSE'
```

Use the account identifier from your working Snowflake connection, not a full browser URL. Then load the variables in the same terminal:

```bash
source local_env.sh
```

The default `dbt_charts.yml` uses `authenticator: externalbrowser`. This assumes your account supports browser-based SSO. Complete the browser sign-in when the first warehouse query runs. A one-worker configuration reduces parallel authentication prompts. Account policy can still require repeated authentication.

No password or private key is included in the project. Do not send credentials to a chat or commit them to Git. `local_env.sh`, key files and local caches are ignored by the supplied `.gitignore`.

The selected role needs warehouse USAGE, database/schema USAGE, and SELECT on the required source tables. It does not need CREATE privileges for this direct-source version. Have your administrator verify a suitably restricted role rather than using ACCOUNTADMIN.

**Already have a local dbt profile?** Copy `config_examples/dbt_charts.profile.yml` over `dbt_charts.yml`, replace the profile name and target, and use the existing local `profiles.yml`. The profile name means its top-level YAML key, not necessarily the project name. A connection saved only in a hosted dbt workspace is not automatically a local profile. Preserve the source name `fivetran`, which the boards reference.

**Using key-pair authentication?** Use `config_examples/dbt_charts.keypair.yml` with an existing administrator-approved key. Supply `SF_PRIVATE_KEY_PATH` and, when required, `SF_PRIVATE_KEY_PASSPHRASE` through your approved secret mechanism. This guide does not generate or register keys.

## Step 4 - Check the warehouse and sources

First prove the account, user and role are correct:

```bash
dct query fivetran "SELECT CURRENT_ACCOUNT(), CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE()"
```

Then check the source schema and recorded coverage:

```bash
dct query fivetran --file sql/schema_check.sql
dct query fivetran --file sql/source_check.sql
dct query fivetran --file sql/join_key_check.sql
dct query fivetran --file sql/event_id_check.sql
```

Expected results: required columns are `OK`; LOG/MAR have records for the periods you plan to demo; both key checks return zero rows. Coverage scans and the LOG key check can be substantial on a large estate, so review warehouse/query cost first.

`MISSING / NOT VISIBLE TO THIS ROLE` can mean an absent table, a disabled table in the connector, different identifiers, or insufficient permissions. Verify the cause rather than creating guessed tables or fields. The guide is the supplied schema contract; your actual account remains authoritative. A disabled audit/change source can leave that board unavailable even when Operations works. Resolve or exclude an unavailable board before a demo.

## Step 5 - Validate the boards in two layers

```bash
dct validate charts/
dct validate charts/ --warehouse
```

The first checks the dbt Charts schema and references without executing data queries. The second checks warehouse SQL; Snowflake uses EXPLAIN for this check. Neither replaces a live run and visual review.

The starter intentionally combines several one-row bounds/summary queries with CROSS JOIN. Review any fan-out warnings: these particular joins are intended to combine one scalar row, while joins to connection and destination metadata still require the uniqueness checks above. Do not broadly ignore other warnings or declare the application validated merely because the YAML parses.

To isolate a problem:

```bash
dct query charts/operations.yml summary
dct query charts/mar_usage.yml summary
dct query charts/value_calculator.yml scenario
```

## Step 6 - Start the dashboard

```bash
dct serve --host 127.0.0.1 --port 3000 --no-cache
```

Open the actual URL printed in your terminal. Usually it is `http://127.0.0.1:3000/`; the CLI can select the next port when the requested one is busy. The home page lists the four boards.

The `--no-cache` option disables dbt Charts' query-result cache for this run. Its normal local cache is on disk and is not equivalent to the original app's per-viewer, two-minute memory cache. Disabling it avoids retaining a persistent query-result cache in this demo, but can increase warehouse work. It is not a claim that no other browser, OS, authentication or warehouse records exist.

Changing variables re-runs dependent queries. Reloading the page refreshes the board under this no-cache setup; neither operation starts a Fivetran sync. No custom refresh button or polling loop is implemented here.

Keep the server bound to loopback. The local preview is not a replacement for an authenticated multi-user deployment. Press Ctrl+C to stop it.

## Step 7 - Walk through Operations

Leave Connection unset to include all connections. Leave both date fields blank to use seven UTC dates ending on the latest observed LOG date. The end date is inclusive. Entering only an end date gives seven dates ending there. Entering only a start date retains the latest observed LOG date as the end.

The visible period-check table identifies reversed dates and periods longer than 93 days. These invalid periods return no event/change rows until corrected; zero values under an invalid period are not evidence of no incidents.

Read the three cards, then the connection summary. Select a connection and inspect the event detail. The default detail scope is Warnings and errors; switch to All events if needed. Select an event in the payload control to see its recorded text. Changing date/connection/detail scope may invalidate an earlier event selection; clear and reselect it.

Check that the summary is unchanged when only the detail-scope selector changes. The original separation between summary counts and detail filtering is intentional.

The additional daily-event trend describes recorded rows. Missing dates are not filled with invented zero events. The implementation does not produce active/broken/healthy status, success rate, last successful sync or incident deduplication.

## Step 8 - Walk through MAR usage

An unset month means the latest available MAR month. The selector offers up to 24 recorded months. Choose a populated month, then a connection.

Paid = sum of INCREMENTAL_ROWS with FREE_TYPE exactly PAID. Other classified = non-null FREE_TYPE different from PAID. Unclassified = null FREE_TYPE. All sync types are included. Unclassified MAR is displayed explicitly, including in the new trend's third category.

Connection filtering uses EXISTS over current connection name plus destination ID; it does not multiply consumption rows by joining to the connection inventory. Renamed connections can leave old MAR unmatched. Keep that caveat visible when filtering historical usage.

The top 20 table contributors and original FREE_TYPE/SYNC_TYPE categories retain the guide's purpose. Do not describe high usage as waste, MAR as a priced invoice, or reductions as achieved savings.

## Step 9 - Walk through Changes and audit

Destination schema changes uses connection and date filters. It combines schema/table/column records and displays the latest 200, with names from current destination metadata.

The User actions tab uses the date filters only. Changing the connection selector must not change account-level audit scope. Emails and old/new audit payloads remain omitted.

This board inherits the guide's date default based on LOG coverage. An empty audit view can require a different date period even when audit records exist elsewhere. Recorded changes are not a complete deletion history, and current entity names are not historical names at the time of the event.

## Step 10 - Test the value calculator

The six inputs are independent of operational filters and records. With the original defaults:

| Output | Expected |
| --- | --- |
| Monthly hours released | 15 |
| Monthly capacity value | AUD 2,250 |
| First-year net value with both cost inputs zero | AUD 27,000 |

Set monthly running cost to AUD 100 and implementation cost to AUD 500: first-year net value should be AUD 25,300. Set hours after above hours before: results should become negative, not clamp to zero. Zero investigations gives zero released capacity; entered running/implementation costs still reduce net value.

Zero default costs mean costs have not yet been estimated, not that running the application is free. Released capacity is not automatically a cash saving. Subscription savings and outage avoidance are excluded.

## Interface differences from the Streamlit original

These are four separate board pages, not one Python app with shared sidebar state. Filters are per board; reselect them when changing pages. Changes and audit uses tabs. Payload inspection is a text table rather than Streamlit's expandable JSON tree. The event trend and explicit unclassified-MAR trend are additions. Date validation uses a visible result table plus SQL guardrails rather than Streamlit alerts. Refresh/caching and authentication are different as described above.

These changes are deliberate adaptations, not a claim of pixel-for-pixel or runtime-equivalent reproduction.

## Optional next stage - Introduce dbt models

Suggested models, to create only after checking the actual source schema:

| Model | Grain / purpose |
| --- | --- |
| `stg_fivetran_log` | One source LOG row; typed UTC event time and original EVENT preserved |
| `stg_fivetran_connection` | One current CONNECTION_ID; uniqueness tested |
| `fct_fivetran_events_daily` | UTC date x connection ID x original event category |
| `fct_fivetran_mar_daily` | Measurement date x destination x recorded connection name x schema x table x FREE_TYPE x SYNC_TYPE |
| `fct_fivetran_destination_changes` | One recorded source change event, with source identity preserved |
| `fct_fivetran_audit_actions` | One account-level recorded audit action |

Do not replace raw event detail with daily aggregates. Keep the original fields required for drill-down. Do not sum daily distinct-connection counts to create a period-wide distinct count; calculate that at the chosen reporting grain. Preserve the original MAR classifications and explicit null category.

Use your existing dbt project to define sources, add models/tests and build them. Then use a dbt-profile source and `{{ ref('model_name') }}` in chart SQL. Check manifest resolution, profile and target before switching boards. Fully qualified built relation names are an alternative. This starter does not include an untested dbt mart layer or require the dbt Semantic Layer.

## Sharing beyond your laptop

For a shared dashboard, use an approved hosting route with authentication. dbt Charts Cloud supports a Git-backed project, configured warehouse connection, source mapping and access controls. The source name to map in this project is `fivetran`. Review its current network requirements and credential model; your local SSO configuration is not an unattended Cloud connection.

The default project config sets `cloud.allow_public: false`. Keep it private. Customer connection names and log payloads can be sensitive; review or remove them before sharing any board or static export. Do not upload real payloads to a public playground.

## Troubleshooting

| Symptom | First check |
| --- | --- |
| dct command not found | Activate this project's .venv; confirm the install succeeded |
| Snowflake adapter missing | Install the quoted `dbt-charts[snowflake]` package into the same environment as dct |
| SSO does not work | Confirm account identifier and approved auth method; do not invent credentials |
| Object not found | Run schema_check with the same role as the app; confirm connector sync scope |
| Query fails | Run that named board query with dct query; check actual column types and identifiers |
| No events or changes | Read the period-check table; choose a period with source coverage |
| No payload | Select an event from the current latest-200 list; clear stale selection |
| MAR lower after filtering | Check recorded connection name/destination matching and historical renames |
| AUDIT does not respond to connection selection | Intended: account-level scope |
| Metadata joins inflate results | Resolve duplicated join keys; do not apply DISTINCT as a blind fix |
| Results are old | Inspect source landing coverage and the Platform Connector; board reload does not sync Fivetran |
| Browser prompts repeat | Account SSO policy applies per connection; use approved token caching or key-pair configuration |

## Short demo narrative

"Fivetran brings its operational metadata into Snowflake. We use the same evidence to investigate recorded events, review consumption drivers and trace changes. dbt Charts presents those questions as version-controlled dashboards. The last page is a transparent assumption-based example of the engineering capacity that faster investigation could release."

Only add "dbt models define and test the metrics" after you have actually implemented and built the optional dbt model layer.
