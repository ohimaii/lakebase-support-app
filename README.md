# Lakebase Support Desk

A small, transactional support-ticketing app built as a **Databricks App** backed by
**[Lakebase](https://docs.databricks.com/aws/en/oltp/projects/)** (managed Postgres).
Users can browse support tickets, read and add messages, open new tickets, change
ticket status, filter, and delete — with every read and write going through Lakebase.
No application data is hard-coded.

Built with Streamlit and a thin data-access layer over `psycopg`, using OAuth token
rotation so the same code runs deployed (as the app's service principal) and locally
(as your own Databricks identity).

## Features

- View all tickets and drill into a ticket's message thread
- Create tickets and add messages
- Update ticket status (`open` / `in_progress` / `resolved`)
- Filter tickets by status
- Ticket statistics (totals and counts per status)
- Input validation with clear error messages
- Delete a ticket (and its messages) behind a confirmation step
- Priority and category fields on each ticket

## Repository layout

| File | Purpose |
|------|---------|
| `app.py` | Streamlit app: OAuth-rotating connection pool, data-access layer, and UI |
| `schema.sql` | Tables, foreign key, service-principal grants, and sample data |
| `app.yaml` | Databricks Apps config — start command and connection parameters (no secrets) |
| `requirements.txt` | Python dependencies |

## Data model

Two related tables in Lakebase:

- **`tickets`** — `ticket_id` (PK), `title`, `status`, `created_by`, `created_at`, `priority`, `category`
- **`ticket_messages`** — `message_id` (PK), `ticket_id` (FK → `tickets.ticket_id`, `ON DELETE CASCADE`), `message_text`, `author`, `created_at`

Status and priority are constrained with `CHECK` constraints, and `ticket_messages.ticket_id`
is indexed for message lookups.

## Setup and deployment

### 1. Create the app and Lakebase project
- Create a Databricks App (any Python template works — you'll replace the files).
- From the app's **Environment** tab, copy the `DATABRICKS_CLIENT_ID` (a UUID). This is
  the app's Postgres username.
- Open **Lakebase Postgres** from the app switcher and create a project (Postgres 17).

### 2. Run the schema
In the Lakebase **SQL Editor**, open `schema.sql`, replace every `<DATABRICKS_CLIENT_ID>`
with the UUID from step 1, and run it. The final `SELECT` should show three tickets with
their message counts.

### 3. Configure `app.yaml`
Fill in the connection parameters from the Lakebase **Connect** modal (choose
**Parameters only**) and the branch's **Computes** tab:
- `PGHOST` — endpoint hostname
- `PGUSER` — the app's `DATABRICKS_CLIENT_ID`
- `ENDPOINT_NAME` — `projects/<project-id>/branches/<branch-id>/endpoints/<endpoint-id>`

`PGDATABASE` (`databricks_postgres`) and `PGPORT` (`5432`) are already set.

### 4. Deploy
Point the app's source at this repo/folder and deploy — via the app page's **Deploy**
button in the workspace, or the CLI:

```bash
databricks sync . /Workspace/Users/<your-email>/lakebase-support-app
databricks apps deploy <app-name> --source-code-path /Workspace/Users/<your-email>/lakebase-support-app
```

Open the app URL and confirm tickets load, you can create/update, and changes persist
across a refresh.

### Run locally (optional)
Authenticate as yourself and set `PGUSER` to your Databricks email (not the service
principal):

```bash
databricks auth login
export PGHOST="<endpoint-hostname>"
export PGDATABASE="databricks_postgres"
export PGUSER="you@example.com"
export PGPORT="5432"
export PGSSLMODE="require"
export ENDPOINT_NAME="projects/<project-id>/branches/<branch-id>/endpoints/<endpoint-id>"
pip install -r requirements.txt
python -m streamlit run app.py
```

## How authentication works

Databricks Apps authenticate to Lakebase with OAuth tokens that expire after one hour.
`app.py` defines a custom `psycopg` connection class that calls the Databricks SDK to
mint a fresh token every time a new connection is opened, so the pool stays valid without
any stored password. The only values in `app.yaml` are non-secret connection parameters.

## Security

No passwords, tokens, or keys are committed. `app.yaml` holds connection **parameters**
only; the database password is a short-lived OAuth token generated at runtime. Do not
commit real credentials — access them through the Databricks environment or another
secure configuration method.

## Tech stack

Databricks Apps · Lakebase (Postgres 17) · Python · Streamlit · psycopg · Databricks SDK
