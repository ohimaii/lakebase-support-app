# Lakebase Support Desk

A small Databricks App backed by **Lakebase** (Postgres). Users can view tickets,
read a ticket's messages, create tickets, add messages, update status, filter by
status, see statistics, and delete tickets (with confirmation). All data lives in
Lakebase — nothing is hard-coded.

```
lakebase-support-app/
├── app.py            # Streamlit app: OAuth token rotation + full CRUD
├── schema.sql        # tables, permissions, and sample data (run once)
├── app.yaml          # Databricks Apps config (connection params, not secrets)
├── requirements.txt  # dependencies
├── .env.sample       # local-testing env template (never commit a filled copy)
└── .gitignore
```

## What you still have to do

Everything below is click/copy-paste. You do **not** need to write code.

### 1. Create the app and the Lakebase project
- Create a Databricks App from the **Flask/Streamlit Hello world** template (any Python
  template is fine — you'll replace the files).
- On the app's **Environment** tab, copy the `DATABRICKS_CLIENT_ID` (a UUID). This is
  your app's Postgres username.
- In the app switcher, open **Lakebase Postgres** and create a project (accept Postgres 17).
  Wait ~1 min for compute to become active.

### 2. Run the schema
- Open the Lakebase **SQL Editor**.
- Open `schema.sql`, replace **every** `<DATABRICKS_CLIENT_ID>` with the UUID from step 1,
  and run it. The final `SELECT` should show 3 tickets with message counts (2–3 each).

### 3. Fill in `app.yaml`
From the Lakebase **Connect** modal (choose **Parameters only**) and your branch's
**Computes** tab (**Get ID → Copy resource name**), replace in `app.yaml`:
- `PGHOST` → endpoint hostname
- `PGUSER` → the same `DATABRICKS_CLIENT_ID`
- `ENDPOINT_NAME` → `projects/<project-id>/branches/<branch-id>/endpoints/<endpoint-id>`

### 4. (Optional) test locally first
```bash
databricks auth login
source .env.sample          # after editing it; set PGUSER to YOUR email locally
pip install -r requirements.txt
python -m streamlit run app.py
```

### 5. Deploy
```bash
databricks sync . /Workspace/Users/<your-email>/lakebase-support-app
databricks apps deploy <app-name> --source-code-path /Workspace/Users/<your-email>/lakebase-support-app
```
Open the app URL and confirm: tickets load, you can create a ticket, add a message,
update status, filter, and that changes survive a refresh.

## Assignment coverage

| Requirement | Where |
|---|---|
| Two related tables + FK | `schema.sql` (`ticket_messages.ticket_id → tickets`) |
| 3+ tickets, 2+ messages each, 2+ statuses | `schema.sql` sample data |
| View tickets / view messages / create / add message / update status | `app.py` |
| Reads and writes go to Lakebase | `app.py` data-access layer |
| **Bonus:** priority + category | `schema.sql`, `app.py` |
| **Bonus:** filter by status | `app.py` (status radio) |
| **Bonus:** input validation + error messages | `app.py` |
| **Bonus:** statistics | `app.py` sidebar |
| **Bonus:** delete with confirmation | `app.py` (checkbox gate) |

## Security
`app.yaml` and `.env.sample` contain only connection **parameters** (host, username,
endpoint), not secrets. The database password is a short-lived OAuth token generated at
runtime by `WorkspaceClient`. Never commit a real password, token, or key.

## Submission checklist
1. [ ] Databricks App URL
2. [ ] Zipped source code (this folder)
3. [ ] Screenshot of the deployed app
4. [ ] Screenshot of the Lakebase tables + sample records (the verification `SELECT` works)
5. [ ] 3–5 sentence reflection:
   - Hardest part?
   - How is Lakebase different from a traditional analytics table? *(Hint: it's an OLTP
     Postgres store built for low-latency single-row reads/writes and transactions —
     ideal for app state — versus an analytical/columnar table optimized for large scans.)*
   - What feature would you add next?
