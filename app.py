"""
Lakebase Support Desk — a Databricks App backed by Lakebase (Postgres).

All ticket/message data lives in Lakebase; nothing is hard-coded.
Auth uses OAuth token rotation, so the same code runs deployed (as the app's
service principal) and locally (as your Databricks user).
"""

import os

import pandas as pd
import psycopg
import streamlit as st
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from databricks.sdk import WorkspaceClient

STATUSES = ["open", "in_progress", "resolved"]
PRIORITIES = ["low", "medium", "high"]

# ---------------------------------------------------------------------------
# Connection setup: fresh OAuth token per new connection (auto-rotating pool)
# ---------------------------------------------------------------------------
_w = WorkspaceClient()


class OAuthConnection(psycopg.Connection):
    """Injects a fresh Lakebase OAuth token as the password on each connect."""

    @classmethod
    def connect(cls, conninfo="", **kwargs):
        endpoint_name = os.environ["ENDPOINT_NAME"]
        credential = _w.postgres.generate_database_credential(endpoint=endpoint_name)
        kwargs["password"] = credential.token
        return super().connect(conninfo, **kwargs)


@st.cache_resource
def get_pool() -> ConnectionPool:
    """Create the connection pool once and reuse it across Streamlit reruns."""
    user = os.environ["PGUSER"]
    host = os.environ["PGHOST"]
    port = os.environ.get("PGPORT", "5432")
    database = os.environ.get("PGDATABASE", "databricks_postgres")
    sslmode = os.environ.get("PGSSLMODE", "require")
    return ConnectionPool(
        conninfo=f"dbname={database} user={user} host={host} port={port} sslmode={sslmode}",
        connection_class=OAuthConnection,
        min_size=1,
        max_size=5,
        open=True,
    )


# ---------------------------------------------------------------------------
# Data access layer — every read and write goes through Lakebase
# ---------------------------------------------------------------------------
def fetch_all(sql, params=None):
    with get_pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()


def execute(sql, params=None, returning=False):
    with get_pool().connection() as conn:  # commits on clean exit, rolls back on error
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchone() if returning else None


def get_tickets(status_filter="all"):
    if status_filter and status_filter != "all":
        return fetch_all(
            "SELECT * FROM tickets WHERE status = %s ORDER BY created_at DESC",
            (status_filter,),
        )
    return fetch_all("SELECT * FROM tickets ORDER BY created_at DESC")


def get_messages(ticket_id):
    return fetch_all(
        "SELECT * FROM ticket_messages WHERE ticket_id = %s ORDER BY created_at",
        (ticket_id,),
    )


def create_ticket(title, created_by, priority, category):
    row = execute(
        """INSERT INTO tickets (title, status, created_by, priority, category)
           VALUES (%s, 'open', %s, %s, %s)
           RETURNING ticket_id""",
        (title, created_by, priority, category),
        returning=True,
    )
    return row[0]


def add_message(ticket_id, message_text, author):
    execute(
        """INSERT INTO ticket_messages (ticket_id, message_text, author)
           VALUES (%s, %s, %s)""",
        (ticket_id, message_text, author),
    )


def update_status(ticket_id, status):
    execute("UPDATE tickets SET status = %s WHERE ticket_id = %s", (status, ticket_id))


def delete_ticket(ticket_id):
    # FK is ON DELETE CASCADE, so messages are removed automatically.
    execute("DELETE FROM tickets WHERE ticket_id = %s", (ticket_id,))


def get_stats():
    rows = fetch_all("SELECT status, COUNT(*) AS n FROM tickets GROUP BY status")
    return {r["status"]: r["n"] for r in rows}


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Lakebase Support Desk", page_icon="🎫", layout="wide")
st.title("🎫 Lakebase Support Desk")
st.caption("Support tickets and messages, stored in Databricks Lakebase (Postgres).")

# ---- Sidebar: statistics + create ticket --------------------------------
with st.sidebar:
    st.header("📊 Statistics")
    try:
        stats = get_stats()
        st.metric("Total tickets", sum(stats.values()))
        cols = st.columns(len(STATUSES))
        for col, s in zip(cols, STATUSES):
            col.metric(s.replace("_", " ").title(), stats.get(s, 0))
    except Exception as e:
        st.error("Could not load statistics.")
        st.exception(e)

    st.divider()
    st.header("➕ New ticket")
    with st.form("new_ticket", clear_on_submit=True):
        t_title = st.text_input("Title")
        t_author = st.text_input("Created by (email)")
        t_priority = st.selectbox("Priority", PRIORITIES, index=1)
        t_category = st.text_input("Category", value="general")
        submitted = st.form_submit_button("Create ticket", use_container_width=True)

    if submitted:
        if not t_title.strip() or not t_author.strip():
            st.error("Title and 'Created by' are both required.")
        else:
            try:
                new_id = create_ticket(
                    t_title.strip(),
                    t_author.strip(),
                    t_priority,
                    (t_category.strip() or "general"),
                )
                st.success(f"Created ticket #{new_id}.")
                st.rerun()
            except Exception as e:
                st.error("Failed to create the ticket.")
                st.exception(e)

# ---- Main area: filter + list + detail ----------------------------------
try:
    status_filter = st.radio(
        "Filter by status", ["all"] + STATUSES, horizontal=True
    )
    tickets = get_tickets(status_filter)
except Exception as e:
    st.error("Could not load tickets from Lakebase.")
    st.exception(e)
    st.stop()

if not tickets:
    st.info("No tickets match this filter. Create one from the sidebar.")
    st.stop()

df = pd.DataFrame(tickets)
st.dataframe(
    df[["ticket_id", "title", "status", "priority", "category", "created_by", "created_at"]],
    use_container_width=True,
    hide_index=True,
)

labels = {f'#{t["ticket_id"]} · {t["title"]}': t["ticket_id"] for t in tickets}
choice = st.selectbox("Select a ticket", list(labels.keys()))
ticket_id = labels[choice]
ticket = next(t for t in tickets if t["ticket_id"] == ticket_id)

st.divider()
left, right = st.columns([2, 1])

# ----- Messages + add message
with left:
    st.subheader(f"💬 Ticket #{ticket_id}: {ticket['title']}")
    try:
        for m in get_messages(ticket_id):
            with st.chat_message("user"):
                st.markdown(f"**{m['author']}** · {m['created_at']:%Y-%m-%d %H:%M}")
                st.write(m["message_text"])
    except Exception as e:
        st.error("Could not load messages.")
        st.exception(e)

    with st.form(f"add_message_{ticket_id}", clear_on_submit=True):
        m_author = st.text_input("Your name/email", key=f"author_{ticket_id}")
        m_text = st.text_area("Message", key=f"text_{ticket_id}")
        add_clicked = st.form_submit_button("Add message")
    if add_clicked:
        if not m_author.strip() or not m_text.strip():
            st.error("Both name and message are required.")
        else:
            try:
                add_message(ticket_id, m_text.strip(), m_author.strip())
                st.success("Message added.")
                st.rerun()
            except Exception as e:
                st.error("Failed to add the message.")
                st.exception(e)

# ----- Status update + delete
with right:
    st.subheader("⚙️ Actions")

    current_idx = STATUSES.index(ticket["status"]) if ticket["status"] in STATUSES else 0
    new_status = st.selectbox("Status", STATUSES, index=current_idx, key=f"status_{ticket_id}")
    if st.button("Update status", use_container_width=True):
        try:
            update_status(ticket_id, new_status)
            st.success(f"Status set to '{new_status}'.")
            st.rerun()
        except Exception as e:
            st.error("Failed to update status.")
            st.exception(e)

    st.divider()
    st.markdown("**Danger zone**")
    confirm = st.checkbox("Yes, delete this ticket and its messages", key=f"confirm_{ticket_id}")
    if st.button("🗑️ Delete ticket", type="primary", disabled=not confirm, use_container_width=True):
        try:
            delete_ticket(ticket_id)
            st.success(f"Deleted ticket #{ticket_id}.")
            st.rerun()
        except Exception as e:
            st.error("Failed to delete the ticket.")
            st.exception(e)
