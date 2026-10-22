# Fivetran_Streamlit_App_Guide

# Fivetran Platform Connector —> Streamlit Value Dashboard

## Purpose

Turn Fivetran operational logs and metadata in Snowflake into a dashboard that helps customers investigate issues, understand consumption and trace changes. An adjustable calculator illustrates the potential value of engineering time released.

This guide includes the complete Python application at the end. It reflects the original app supplied for this demo; successful execution against the Snowflake account has not yet been confirmed.

## Architecture

Fivetran Platform Connector → Snowflake tables → Streamlit in Snowflake.

The app queries the source tables directly using Snowpark SQL. It does not require SQL views, dbt models, external hosting or API credentials. The queries are read-only.

| Setting | Value |
| --- | --- |
| Source database | `NAAG_POSTGRES` |
| Source schema | `NAAG_FIVETRAN_LOG` |
| Suggested application schema | `NAAG_POSTGRES.FIVETRAN_DEMO` |
| Application name | `FIVETRAN_VALUE_DASHBOARD` |
| Runtime | Warehouse |
| Python packages | `streamlit`, `pandas`, `snowflake-snowpark-python` |

## Setup

1. In Snowsight, open **Projects → Streamlit → + Streamlit App**.
2. Name the app `FIVETRAN_VALUE_DASHBOARD`.
3. Select database `NAAG_POSTGRES` and schema `FIVETRAN_DEMO`.
4. Select **Run on warehouse** and an available development warehouse. Start with X-Small and review performance.
5. Select **Create**.
6. In **Packages**, ensure the three Python packages listed above are available.
7. Replace the entire starter file, normally `streamlit_app.py`, with the Python code at the end of this guide. Copy only the contents of the Python code block, excluding the Markdown fences.
8. Click **Run**.

The role creating the application needs permission to create the app in its schema, use the selected warehouse, and read the source database, schema and tables. If access is missing, ask the Snowflake administrator to grant the required permissions to that role.

The code uses `get_active_session()` and is intended for the warehouse runtime. Adapting to a container runtime requires changes to connection handling.

## Dashboard views

| View | Functions | Customer value |
| --- | --- | --- |
| Operations | Connection-level event counts; warning/severe events; event drill-down and JSON payload inspection | Reduce time gathering troubleshooting evidence |
| MAR usage | Monthly selection; daily MAR trend; top 20 table contributors; usage categories | Identify consumption drivers for review |
| Changes & audit | Destination schema, table and column changes; recorded user actions | Investigate what changed and when |
| Value calculator | Adjustable investigation effort, hourly cost, running cost and implementation cost | Illustrate the financial value of released engineering capacity |

### Source tables used

- `LOG` and `CONNECTION` for event investigation and connection labels.
- `INCREMENTAL_MAR` for recorded consumption.
- `DESTINATION_SCHEMA_CHANGE_EVENT`, `DESTINATION_TABLE_CHANGE_EVENT` and `DESTINATION_COLUMN_CHANGE_EVENT` for destination changes.
- `DESTINATION_SCHEMA`, `DESTINATION_TABLE` and `DESTINATION_COLUMN` for current entity names.
- `AUDIT_TRAIL` for recorded user actions.

The app uses `LOG.TIME_STAMP`, matching the supplied schema export.

## Filters and freshness

- The connection selector applies to Operations, MAR usage and destination schema changes.
- User actions remain an account-level view of available audit records; the connection selector does not filter them.
- The calculator uses independent assumptions and does not use the connection selector.
- Operations and Changes use UTC dates with an inclusive end date. The default period is seven days ending on the latest observed log date. The maximum allowed period is 93 days.
- MAR usage has its own month selector, showing up to 24 available months.
- Query results are cached in the viewer’s session for two minutes. They are refreshed on a subsequent interaction after expiry; there is no automatic polling.
- **Refresh data** clears that session’s cache and re-queries Snowflake. It does not start a Fivetran sync.
- The newest observed landing timestamp is not a completed-sync watermark or proof of current pipeline health.

## Metric definitions

| Metric | Calculation or interpretation |
| --- | --- |
| Connections with log events | Distinct non-null connection IDs with events in the chosen period |
| Warning events | Events whose uppercased severity is `WARNING` |
| Severe/error events | Events whose uppercased severity is `SEVERE`, `ERROR` or `FATAL` |
| Paid MAR recorded | Sum of `INCREMENTAL_ROWS` where `FREE_TYPE = 'PAID'`, in the chosen month |
| Other classified MAR | Sum where `FREE_TYPE` is non-null and differs from `PAID` |
| Unclassified MAR | Sum where `FREE_TYPE` is null; shown as a warning when non-zero |
| Latest measurement date | Latest available MAR measurement date under the current filters |

MAR totals include all sync types, with the original categories available for inspection. Partial-month or incomplete-history totals are not a final invoice. The app does not calculate subscription costs from MAR.

MAR filtering matches the connection’s current name and destination ID. Historical connection renames can leave usage unmatched. High usage alone is not evidence of waste.

Warning/error events are not deduplicated into incidents. Operations does not calculate a success rate, last successful sync or a live healthy/unhealthy status. Change records do not provide a complete deletion history. Entity names come from current metadata.

## Value calculator

All inputs are illustrative assumptions; none is inferred from event counts.

```
Monthly hours released = investigations per month × (hours before − hours after)
Monthly capacity value = monthly hours released × loaded hourly cost
First-year net value = 12 × (monthly capacity value − monthly running cost)
                       − one-off implementation cost
```

Default example:

| Assumption or result | Value |
| --- | --- |
| Investigations per month | 20 |
| Hours before, per investigation | 1.00 |
| Hours after, per investigation | 0.25 |
| Loaded engineering cost | A$150/hour |
| Monthly hours released | 15 |
| Monthly capacity value | A$2,250 |
| First-year value before running/implementation costs | A$27,000 |

Running and implementation costs default to zero because they have not been estimated. Enter customer-specific estimates before presenting a net-value scenario. Released capacity is not automatically a cash saving. The calculator excludes subscription savings and outage avoidance.

## First-run checks

1. Open **Operations → All connections** and confirm event summaries appear.
2. Select a connection and inspect an event. If no warning/error detail appears, choose **All events**.
3. Open **MAR usage**, select a populated month, and confirm the trend and contributors.
4. Open **Changes & audit** and try both evidence views. Change the dates if necessary.
5. Open **Value calculator** and confirm changing assumptions changes the result.

Python syntax was checked locally. Live Snowflake SQL, account permissions and visual rendering still need validation in the target account.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| No records | Change connection, dates or usage month; confirm the relevant source table is populated |
| Insufficient privileges | Check the app owner’s role has source-table read access and warehouse access |
| Missing package | Add the required package in the editor’s Packages panel |
| Active session error | Confirm **Run on warehouse** was selected |
| Slow initial load | Allow for warehouse startup; use a narrower date range or one connection |
| Values look old | Check the Platform Connector’s last sync, then refresh the app |
| Other query error | Expand **Query / application error** and inspect the technical message |

The app limits event and change details to 200 records and table contributors to 20. SQL performs aggregations in Snowflake. The initial log-coverage query still reads across the LOG table, and the connection selector loads the connection inventory; review performance for a larger estate.

## Five-minute recording flow

| Time | Screen | Message |
| --- | --- | --- |
| 0:00–1:00 | Introductory slide | Explain operational visibility, consumption insight and traceability |
| 1:00–1:50 | Fivetran configuration | Show destination schema, scope selection, Save & Test, and sync schedule |
| 1:50–2:15 | Snowflake | Show the landed metadata schema and key tables |
| 2:15–3:10 | Operations | Select a connection and inspect a recorded event |
| 3:10–3:55 | MAR usage | Highlight a top table contributor and explain the review opportunity |
| 3:55–4:25 | Changes & audit | Show a recorded change or user action |
| 4:25–5:00 | Value calculator | Explain the adjustable A$2,250/month engineering-capacity scenario |

Complete the initial connector sync before recording. Prepare one useful event, a populated usage month and a change record. Review connection names and event payloads before sharing the recording externally. This is a custom dashboard built over Fivetran metadata.

## Complete application code

Paste this code into the Snowflake Streamlit editor.

```jsx
"""Streamlit in Snowflake • warehouse runtime.

Source: NAAG_POSTGRES.NAAG_FIVETRAN_LOG. Read-only, no external services.
Requires streamlit, pandas and snowflake-snowpark-python.
"""
from datetime import date, datetime, timedelta, timezone
import json
import time

import pandas as pd
import streamlit as st
from snowflake.snowpark.context import get_active_session

st.set_page_config(page_title="Fivetran Value Dashboard", page_icon="📊", layout="wide")
S = "NAAG_POSTGRES.NAAG_FIVETRAN_LOG"
session = get_active_session()

def query(sql, params=()):
    """Session-local cache. Never shares query results between app viewers."""
    cache = st.session_state.setdefault("query_cache", {})
    key = (sql, tuple(params))
    now = time.monotonic()
    if key not in cache or now - cache[key][0] > 120:
        frame = session.sql(sql, params=list(params)).to_pandas()
        if len(cache) > 60:
            cache.clear()
        cache[key] = (now, frame)
    return cache[key][1].copy()

def grid(frame):
    if frame.empty:
        st.info("No records for these filters. Try another connection or period.")
    else:
        st.dataframe(frame, use_container_width=True, hide_index=True)

def as_date(value):
    return None if pd.isna(value) else pd.Timestamp(value).date()

def stamp(value):
    if pd.isna(value):
        return "No timestamp available"
    return pd.Timestamp(value).tz_convert("UTC").strftime("%d %b %Y, %H:%M UTC")

def run():
    st.title("Fivetran Value Dashboard")
    st.caption("Find operational issues • Understand consumption • Trace changes")
    st.sidebar.header("Explore your Fivetran estate")
    if st.sidebar.button("Refresh data"):
        st.session_state["query_cache"] = {}

    coverage = query(f"""
        SELECT MIN(TIME_STAMP) AS FIRST_EVENT, MAX(TIME_STAMP) AS LAST_EVENT,
               MAX(_FIVETRAN_SYNCED) AS NEWEST_LOG_ROW_LANDED
        FROM {S}.LOG
    """).iloc[0]
    connections = query(f"""
        SELECT CONNECTION_ID, CONNECTION_NAME, DESTINATION_ID, PAUSED,
               COALESCE(_FIVETRAN_DELETED, FALSE) AS DELETED
        FROM {S}.CONNECTION ORDER BY CONNECTION_NAME, CONNECTION_ID
    """)
    labels = {
        r.CONNECTION_ID: f"{r.CONNECTION_NAME or r.CONNECTION_ID} · {r.CONNECTION_ID}"
        + (" [deleted]" if r.DELETED else "")
        for r in connections.itertuples()
    }
    chosen = st.sidebar.selectbox(
        "Connection", [None] + list(labels),
        format_func=lambda x: "All connections" if x is None else labels[x],
    )
    page = st.sidebar.radio("View", ["Operations", "MAR usage", "Changes & audit", "Value calculator"])
    st.sidebar.caption("Scope is limited to what this Platform Connector has synced.")
    st.sidebar.caption("Query results cached per viewer for 2 minutes. Refresh re-queries Snowflake; it does not trigger a Fivetran sync.")
    st.caption(f"Source: {S} · Newest observed LOG row landed: {stamp(coverage['NEWEST_LOG_ROW_LANDED'])}")
    if not pd.isna(coverage["LAST_EVENT"]):
        st.caption(f"Available log events: {stamp(coverage['FIRST_EVENT'])} → {stamp(coverage['LAST_EVENT'])}. This is observed coverage, not a pipeline health indicator.")

    if page == "Value calculator":
        value_calculator()
        return
    if page == "MAR usage":
        usage(chosen)
        return

    # Default to the latest observed log date, so older demo datasets are usable.
    end_default = as_date(coverage["LAST_EVENT"]) or date.today()
    left, right = st.columns(2)
    start = left.date_input("Start date (UTC)", end_default - timedelta(days=6))
    end = right.date_input("End date (UTC, inclusive)", end_default)
    if start > end:
        st.error("Start date must be on or before end date.")
        return
    if (end - start).days > 92:
        st.warning("Choose a period of 93 days or less for a responsive demo.")
        return
    bounds = [f"{start} 00:00:00 +00:00", f"{end + timedelta(days=1)} 00:00:00 +00:00"]
    if page == "Operations":
        operations(chosen, bounds)
    else:
        changes(chosen, bounds)

def operations(chosen, bounds):
    st.subheader("Where should the team investigate?")
    st.caption("Observed log events, not live connection status. Warning/severe event counts are not incident counts.")
    where = "l.TIME_STAMP >= TO_TIMESTAMP_TZ(?) AND l.TIME_STAMP < TO_TIMESTAMP_TZ(?)"
    params = list(bounds)
    if chosen is not None:
        where += " AND l.CONNECTION_ID = ?"
        params.append(chosen)
    summary = query(f"""
        SELECT l.CONNECTION_ID,
               COALESCE(c.CONNECTION_NAME, l.CONNECTION_ID, 'Account / unknown') AS CONNECTION_NAME,
               MAX(l.TIME_STAMP) AS LAST_OBSERVED_EVENT,
               COUNT(*) AS LOG_EVENTS,
               COUNT_IF(UPPER(l.EVENT) = 'WARNING') AS WARNING_EVENTS,
               COUNT_IF(UPPER(l.EVENT) IN ('SEVERE','ERROR','FATAL')) AS SEVERE_EVENTS
        FROM {S}.LOG l LEFT JOIN {S}.CONNECTION c
          ON l.CONNECTION_ID = c.CONNECTION_ID
        WHERE {where}
        GROUP BY l.CONNECTION_ID, c.CONNECTION_NAME
        ORDER BY SEVERE_EVENTS DESC, WARNING_EVENTS DESC, LOG_EVENTS DESC
    """, params)
    a, b, c = st.columns(3)
    a.metric("Connections with log events", f"{summary['CONNECTION_ID'].nunique():,}")
    b.metric("Warning events", f"{int(summary['WARNING_EVENTS'].sum()):,}")
    c.metric("Severe / error events", f"{int(summary['SEVERE_EVENTS'].sum()):,}")
    grid(summary)
    if summary.empty:
        return
    # A drill-down keeps event detail bounded even when All connections is selected.
    ids = summary["CONNECTION_ID"].dropna().tolist()
    drill = st.selectbox("Investigate a connection", [None] + ids,
                         format_func=lambda x: "All selected connections" if x is None else str(x))
    level = st.selectbox("Event severity", ["Warnings and errors", "All events"])
    detail_where, detail_params = where, params.copy()
    if drill is not None:
        detail_where += " AND l.CONNECTION_ID = ?"
        detail_params.append(drill)
    if level == "Warnings and errors":
        detail_where += " AND UPPER(l.EVENT) IN ('WARNING','SEVERE','ERROR','FATAL')"
    details = query(f"""
        SELECT l.TIME_STAMP, l.CONNECTION_ID, l.EVENT, l.MESSAGE_EVENT,
               l.SYNC_ID, l.MESSAGE_DATA
        FROM {S}.LOG l WHERE {detail_where}
        ORDER BY l.TIME_STAMP DESC, l.ID DESC LIMIT 200
    """, detail_params)
    st.markdown("**Latest matching events — up to 200**")
    grid(details.drop(columns=["MESSAGE_DATA"]))
    if not details.empty:
        i = st.selectbox("Inspect event payload", list(range(len(details))),
                         format_func=lambda x: f"{details.iloc[x]['TIME_STAMP']} · {details.iloc[x]['MESSAGE_EVENT']} · row {x + 1}")
        raw = details.iloc[i]["MESSAGE_DATA"]
        with st.expander("Event details", expanded=True):
            try:
                st.json(json.loads(raw))
            except (ValueError, TypeError):
                st.code(str(raw), language="text")

def usage(chosen):
    st.subheader("What is driving consumption?")
    months = query(f"""
        SELECT DISTINCT DATE_TRUNC('MONTH', MEASURED_DATE)::DATE AS MONTH
        FROM {S}.INCREMENTAL_MAR ORDER BY MONTH DESC LIMIT 24
    """)["MONTH"].dropna().tolist()
    if not months:
        st.info("No MAR measurements are available yet.")
        return
    month = st.selectbox("Usage month (UTC)", months, format_func=lambda x: pd.Timestamp(x).strftime("%B %Y"))
    where = "m.MEASURED_DATE >= TO_DATE(?) AND m.MEASURED_DATE < DATEADD('MONTH', 1, TO_DATE(?))"
    params = [str(as_date(month)), str(as_date(month))]
    if chosen is not None:
        # MAR stores connection name + destination, not connection ID. EXISTS avoids multiplication.
        where += f""" AND EXISTS (SELECT 1 FROM {S}.CONNECTION c
            WHERE c.CONNECTION_ID = ? AND c.CONNECTION_NAME = m.CONNECTION_NAME
            AND c.DESTINATION_ID = m.DESTINATION_ID)"""
        params.append(chosen)
        st.caption("MAR is matched using the connection's current name and destination. Historical renames may leave unmatched usage.")
    daily = query(f"""
        SELECT m.MEASURED_DATE,
          SUM(CASE WHEN m.FREE_TYPE = 'PAID' THEN m.INCREMENTAL_ROWS ELSE 0 END) AS PAID_MAR,
          SUM(CASE WHEN m.FREE_TYPE <> 'PAID' THEN m.INCREMENTAL_ROWS ELSE 0 END) AS OTHER_CLASSIFIED_MAR,
          SUM(CASE WHEN m.FREE_TYPE IS NULL THEN m.INCREMENTAL_ROWS ELSE 0 END) AS UNCLASSIFIED_MAR,
          MAX(m._FIVETRAN_SYNCED) AS NEWEST_ROW_LANDED
        FROM {S}.INCREMENTAL_MAR m WHERE {where}
        GROUP BY m.MEASURED_DATE ORDER BY m.MEASURED_DATE
    """, params)
    if daily.empty:
        st.info("No MAR records for this connection and month.")
        return
    a, b, c = st.columns(3)
    a.metric("Paid MAR recorded", f"{int(daily['PAID_MAR'].sum()):,}")
    b.metric("Other classified MAR", f"{int(daily['OTHER_CLASSIFIED_MAR'].sum()):,}")
    c.metric("Latest measurement date", str(as_date(daily['MEASURED_DATE'].max())))
    st.caption("Sums of daily MAR increments in the selected month, including all sync types. PAID follows FREE_TYPE; other categories retain their original labels below. Partial-month / partial-history totals are not a final invoice.")
    st.caption(f"Newest observed MAR row landed: {stamp(daily['NEWEST_ROW_LANDED'].max())}")
    if daily["UNCLASSIFIED_MAR"].sum():
        st.warning(f"Unclassified MAR (null FREE_TYPE): {int(daily['UNCLASSIFIED_MAR'].sum()):,}")
    st.line_chart(daily.set_index("MEASURED_DATE")[["PAID_MAR", "OTHER_CLASSIFIED_MAR"]])
    top = query(f"""
        SELECT m.DESTINATION_ID, m.CONNECTION_NAME, m.SCHEMA_NAME, m.TABLE_NAME,
          SUM(CASE WHEN m.FREE_TYPE = 'PAID' THEN m.INCREMENTAL_ROWS ELSE 0 END) AS PAID_MAR,
          SUM(m.INCREMENTAL_ROWS) AS ALL_RECORDED_MAR
        FROM {S}.INCREMENTAL_MAR m WHERE {where}
        GROUP BY m.DESTINATION_ID, m.CONNECTION_NAME, m.SCHEMA_NAME, m.TABLE_NAME
        ORDER BY PAID_MAR DESC, ALL_RECORDED_MAR DESC LIMIT 20
    """, params)
    st.markdown("**Top 20 table contributors**")
    grid(top)
    categories = query(f"""
        SELECT m.FREE_TYPE, m.SYNC_TYPE, SUM(m.INCREMENTAL_ROWS) AS RECORDED_MAR
        FROM {S}.INCREMENTAL_MAR m WHERE {where}
        GROUP BY m.FREE_TYPE, m.SYNC_TYPE ORDER BY RECORDED_MAR DESC
    """, params)
    with st.expander("Usage categories and sync types"):
        grid(categories)
    st.info("High usage is a review opportunity, not proof of waste. Confirm business requirements before changing replication scope. No Fivetran bill or savings is calculated from MAR here.")

def changes(chosen, bounds):
    st.subheader("What changed, and when?")
    kind = st.radio("Evidence", ["Destination schema changes", "User actions"], horizontal=True)
    if kind == "User actions":
        where = "CAPTURED_AT >= TO_TIMESTAMP_TZ(?) AND CAPTURED_AT < TO_TIMESTAMP_TZ(?)"
        params = list(bounds)
        # Resource IDs can refer to destinations, users or accounts: do not guess a connection mapping.
        st.caption("Account-level audit view. The connection selector does not filter user actions; inspect resource IDs for context.")
        frame = query(f"""
            SELECT CAPTURED_AT, ACTION, USER_ID, INTERACTION_METHOD,
                   PRIMARY_RESOURCE_TYPE, PRIMARY_RESOURCE_ID,
                   SECONDARY_RESOURCE_TYPE, SECONDARY_RESOURCE_ID
            FROM {S}.AUDIT_TRAIL WHERE {where}
            ORDER BY CAPTURED_AT DESC, ID DESC LIMIT 200
        """, params)
        grid(frame)
        st.caption("Latest 200 matching recorded actions. User emails and old/new payload values are omitted from this view.")
        return
    branches = []
    params = []
    # Names are looked up only for the latest 200 matching events, not every column in the estate.
    for table, entity, id_col in [
        ("DESTINATION_SCHEMA_CHANGE_EVENT", "Schema", "SCHEMA_ID"),
        ("DESTINATION_TABLE_CHANGE_EVENT", "Table", "TABLE_ID"),
        ("DESTINATION_COLUMN_CHANGE_EVENT", "Column", "COLUMN_ID"),
    ]:
        filt = "DETECTED_AT >= TO_TIMESTAMP_TZ(?) AND DETECTED_AT < TO_TIMESTAMP_TZ(?)"
        p = list(bounds)
        if chosen is not None:
            filt += " AND CONNECTION_ID = ?"
            p.append(chosen)
        attribute = "ATTRIBUTE_NAME" if entity == "Column" else "NULL::VARCHAR"
        value = "NEW_VALUE" if entity == "Column" else "NULL::VARCHAR"
        branches.append(f"""SELECT DETECTED_AT, CONNECTION_ID, DESTINATION_ID,
            '{entity}' AS ENTITY, {id_col} AS ENTITY_ID, CHANGE_TYPE,
            {attribute} AS ATTRIBUTE_NAME, {value} AS NEW_VALUE
            FROM {S}.{table} WHERE {filt}""")
        params.extend(p)
    union = " UNION ALL ".join(branches)
    frame = query(f"""
        WITH recent AS (
            SELECT * FROM ({union})
            ORDER BY DETECTED_AT DESC, ENTITY, ENTITY_ID LIMIT 200
        )
        SELECT r.*, COALESCE(ds.NAME, dt.NAME, dc.NAME) AS CURRENT_ENTITY_NAME
        FROM recent r
        LEFT JOIN {S}.DESTINATION_SCHEMA ds ON r.ENTITY = 'Schema'
          AND r.ENTITY_ID = ds.ID AND r.CONNECTION_ID = ds.CONNECTION_ID
          AND r.DESTINATION_ID = ds.DESTINATION_ID
        LEFT JOIN {S}.DESTINATION_TABLE dt ON r.ENTITY = 'Table'
          AND r.ENTITY_ID = dt.ID AND r.CONNECTION_ID = dt.CONNECTION_ID
          AND r.DESTINATION_ID = dt.DESTINATION_ID
        LEFT JOIN {S}.DESTINATION_COLUMN dc ON r.ENTITY = 'Column'
          AND r.ENTITY_ID = dc.ID AND r.CONNECTION_ID = dc.CONNECTION_ID
          AND r.DESTINATION_ID = dc.DESTINATION_ID
        ORDER BY r.DETECTED_AT DESC, r.ENTITY, r.ENTITY_ID
    """, params)
    st.caption("Latest 200 matching schema/table/column change records. Names are current metadata. Creation/modification records are not a complete deletion history.")
    grid(frame)

def value_calculator():
    st.subheader("What could faster investigations be worth?")
    st.info("Illustrative scenario only. Every input below is an assumption, not inferred from log events. No realised savings are measured.")
    a, b = st.columns(2)
    investigations = a.number_input("Investigations per month", min_value=0, max_value=10000, value=20, step=1)
    before = a.number_input("Hours per investigation — before", min_value=0.0, value=1.0, step=0.25)
    after = a.number_input("Hours per investigation — with dashboard", min_value=0.0, value=0.25, step=0.25)
    rate = b.number_input("Loaded engineering cost (AUD / hour)", min_value=0.0, value=150.0, step=10.0)
    run_cost = b.number_input("Estimated app / warehouse cost (AUD / month)", min_value=0.0, value=0.0, step=10.0)
    build_cost = b.number_input("One-off implementation cost (AUD)", min_value=0.0, value=0.0, step=100.0)
    hours = investigations * (before - after)
    gross = hours * rate
    net = gross - run_cost
    x, y, z = st.columns(3)
    x.metric("Monthly hours released (scenario)", f"{hours:,.1f}")
    y.metric("Monthly capacity value (scenario)", f"A${gross:,.0f}")
    z.metric("First-year net value (scenario)", f"A${12 * net - build_cost:,.0f}")
    st.caption("Hours = investigations × (before − after). Capacity value = hours × loaded hourly cost. First-year net value = 12 × (monthly capacity value − monthly running cost) − implementation cost.")
    st.caption("Released capacity is not automatically a cash saving. This scenario excludes subscription savings and outage avoidance. Zero cost defaults mean costs have not been estimated yet.")
    if hours < 0:
        st.warning("These assumptions increase investigation effort. The scenario correctly shows negative value.")

try:
    run()
except Exception as exc:
    st.error("A dashboard query could not complete. Check the app role's SELECT permissions, warehouse access, and the source schema.")
    st.caption("Technical details are available below for troubleshooting.")
    with st.expander("Query / application error"):
        st.code(str(exc), language="text")
    st.stop()
```