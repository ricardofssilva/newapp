import os
import uuid
import sqlite3
from pathlib import Path
from datetime import datetime
import hashlib
import hmac

import pandas as pd
import streamlit as st

# -------------------------
# Config
# -------------------------
DB_PATH = "crowdfunding_v2.db"   # DB file
IMAGE_DIR = Path("project_images")
IMAGE_DIR.mkdir(exist_ok=True)


# -------------------------
# Password hashing helpers
# -------------------------
def _hash_password(password: str) -> str:
    """Return a SHA-256 hash of the password."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# -------------------------
# Database helpers
# -------------------------
@st.cache_resource
def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # Users table for registration / login
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            display_name TEXT,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            value_needed REAL NOT NULL,
            interest_rate REAL NOT NULL,
            image_path TEXT,
            total_raised REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS investments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            investor_name TEXT,
            investor_username TEXT,
            amount REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
        """
    )

    conn.commit()


def get_user_by_email(email: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email,))
    return cur.fetchone()


def create_user(email: str, password_plain: str, display_name: str | None = None):
    conn = get_connection()
    cur = conn.cursor()
    password_hash = _hash_password(password_plain)
    cur.execute(
        """
        INSERT INTO users (email, display_name, password_hash, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (email, display_name, password_hash, datetime.utcnow().isoformat()),
    )
    conn.commit()


def create_project(name, description, value_needed, interest_rate, image_path=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO projects (name, description, value_needed, interest_rate, image_path, total_raised, created_at)
        VALUES (?, ?, ?, ?, ?, 0, ?)
        """,
        (name, description, value_needed, interest_rate, image_path, datetime.utcnow().isoformat()),
    )
    conn.commit()


def list_projects():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM projects
        ORDER BY created_at DESC
        """
    )
    return cur.fetchall()


def get_project(project_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    return cur.fetchone()


def add_investment(project_id, amount, investor_name=None, investor_username=None):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO investments (project_id, investor_name, investor_username, amount, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (project_id, investor_name, investor_username, amount, datetime.utcnow().isoformat()),
    )

    cur.execute(
        """
        UPDATE projects
        SET total_raised = total_raised + ?
        WHERE id = ?
        """,
        (amount, project_id),
    )

    conn.commit()


def list_investments_for_project(project_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM investments
        WHERE project_id = ?
        ORDER BY created_at DESC
        """,
        (project_id,),
    )
    return cur.fetchall()


def list_investments_for_user(investor_name: str, investor_username: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            i.*,
            p.name AS project_name,
            p.interest_rate AS project_interest_rate,
            p.value_needed AS project_value_needed,
            p.total_raised AS project_total_raised
        FROM investments i
        JOIN projects p ON i.project_id = p.id
        WHERE i.investor_username = ?
           OR (i.investor_username IS NULL AND i.investor_name = ?)
        ORDER BY i.created_at
        """,
        (investor_username, investor_name),
    )
    return cur.fetchall()


# -------------------------
# Authentication helpers
# -------------------------
def login_or_register():
    """
    Show a page with Login and Register tabs.
    Returns (display_name, authenticated_bool, email_username_str)
    """
    if "auth" not in st.session_state:
        st.session_state.auth = {
            "logged_in": False,
            "username": None,
            "name": None,
        }

    auth = st.session_state.auth

    if auth["logged_in"]:
        return auth["name"], True, auth["username"]

    st.title("Mini Crowdfunding Platform")

    tab_login, tab_register = st.tabs(["Login", "Register"])

    # -------- Login tab --------
    with tab_login:
        st.subheader("🔐 Login")
        with st.form("login_form"):
            email_login = st.text_input("Email")
            password_login = st.text_input("Password", type="password")
            submitted_login = st.form_submit_button("Login")

        if submitted_login:
            user = get_user_by_email(email_login.strip().lower())
            if user is None:
                st.error("Incorrect email or password.")
            else:
                expected_hash = user["password_hash"]
                pwd_hash = _hash_password(password_login)
                if hmac.compare_digest(expected_hash, pwd_hash):
                    display_name = user["display_name"] or user["email"]
                    st.session_state.auth = {
                        "logged_in": True,
                        "username": user["email"],
                        "name": display_name,
                    }
                    st.success("Login successful. Loading your app...")
                    st.rerun()
                else:
                    st.error("Incorrect email or password.")

    # -------- Register tab --------
    with tab_register:
        st.subheader("📝 Register")
        with st.form("register_form"):
            email_reg = st.text_input("Email (this will be your login)")
            name_reg = st.text_input("Name (how we’ll display you)")
            password_reg = st.text_input("Password", type="password")
            password_confirm = st.text_input("Confirm password", type="password")
            submitted_register = st.form_submit_button("Create account")

        if submitted_register:
            email_reg = email_reg.strip().lower()
            if not email_reg or not password_reg:
                st.error("Email and password are required.")
            elif "@" not in email_reg:
                st.error("Please enter a valid email.")
            elif password_reg != password_confirm:
                st.error("Passwords do not match.")
            else:
                try:
                    create_user(email_reg, password_reg, name_reg.strip() or None)
                    st.success("Account created! You can now log in with your credentials.")
                except sqlite3.IntegrityError:
                    st.error("This email is already registered. Try logging in instead.")

    return None, False, None


def logout():
    if "auth" in st.session_state:
        st.session_state.auth = {
            "logged_in": False,
            "username": None,
            "name": None,
        }
    st.rerun()


# -------------------------
# UI: Project creation
# -------------------------
def page_submit_project():
    st.subheader("📌 Submit a new project")

    with st.form("project_form"):
        name = st.text_input("Project name")
        description = st.text_area("Project description")
        value_needed = st.number_input(
            "Total amount needed (€)",
            min_value=0.0,
            step=100.0,
            format="%.2f",
        )
        interest_rate = st.number_input(
            "Interest rate offered to investors (%)",
            min_value=0.0,
            step=0.1,
            format="%.2f",
        )

        uploaded_image = st.file_uploader(
            "Upload a project image (optional)",
            type=["png", "jpg", "jpeg"],
        )

        submitted = st.form_submit_button("Create project")

    if submitted:
        if not name or not description or value_needed <= 0:
            st.error("Please fill in the name, description and a positive amount needed.")
            return

        image_path = None
        if uploaded_image is not None:
            extension = os.path.splitext(uploaded_image.name)[1]
            filename = f"{uuid.uuid4().hex}{extension}"
            filepath = IMAGE_DIR / filename
            with open(filepath, "wb") as f:
                f.write(uploaded_image.getvalue())
            image_path = str(filepath)

        create_project(name, description, value_needed, interest_rate, image_path)
        st.success("Project created successfully! ✅")


# -------------------------
# UI: Invest in projects
# -------------------------
def page_invest(current_name: str, current_username: str):
    st.subheader("💰 Invest in projects")

    projects = list_projects()
    if not projects:
        st.info("There are no projects yet. Check back later or submit one yourself!")
        return

    st.markdown("### Available projects")

    if "selected_project_id" not in st.session_state and projects:
        st.session_state["selected_project_id"] = projects[0]["id"]

    # 3-column grid
    for i in range(0, len(projects), 3):
        cols = st.columns(3)
        for col, p in zip(cols, projects[i: i + 3]):
            with col:
                remaining = max(p["value_needed"] - p["total_raised"], 0)
                with st.container(border=True):
                    st.markdown(f"**{p['name']}**")
                    if p["image_path"] and Path(p["image_path"]).exists():
                        st.image(p["image_path"], use_column_width=True)
                    st.caption(
                        p["description"][:120]
                        + ("..." if len(p["description"]) > 120 else "")
                    )
                    st.write(f"Needed: €{p['value_needed']:.2f}")
                    st.write(f"Raised: €{p['total_raised']:.2f}")
                    st.write(f"Remaining: €{remaining:.2f}")
                    st.write(f"Interest: {p['interest_rate']:.2f}%")

                    if p["value_needed"] > 0:
                        progress = p["total_raised"] / p["value_needed"]
                        progress = min(max(progress, 0), 1)
                        st.progress(progress)

                    if st.button("Select this project", key=f"select_{p['id']}"):
                        st.session_state["selected_project_id"] = p["id"]

    st.markdown("---")

    selected_id = st.session_state.get("selected_project_id")
    project = get_project(selected_id) if selected_id else None

    if project:
        remaining = max(project["value_needed"] - project["total_raised"], 0)

        st.markdown(f"### Selected project: **{project['name']}**")
        cols = st.columns([2, 1])

        with cols[0]:
            st.markdown(f"**Description**: {project['description']}")
            st.markdown(f"**Value needed**: €{project['value_needed']:.2f}")
            st.markdown(f"**Interest rate**: {project['interest_rate']:.2f}%")
            st.markdown(f"**Raised so far**: €{project['total_raised']:.2f}")
            st.markdown(f"**Remaining**: €{remaining:.2f}")

            if project["value_needed"] > 0:
                progress = project["total_raised"] / project["value_needed"]
                progress = min(max(progress, 0), 1)
                st.progress(progress)

        with cols[1]:
            if project["image_path"] and Path(project["image_path"]).exists():
                st.image(project["image_path"], use_column_width=True)
            else:
                st.caption("No image available.")

        st.markdown("#### Make an investment")

        invest_amount = st.number_input(
            "Amount to invest (€)",
            min_value=0.0,
            max_value=remaining if remaining > 0 else 0.0,
            step=10.0,
            format="%.2f",
            key=f"invest_amount_{project['id']}",
        )

        if st.button("Invest now", key=f"invest_button_{project['id']}"):
            if invest_amount <= 0:
                st.error("Please enter a positive amount.")
            elif invest_amount > remaining:
                st.error("Amount exceeds the remaining amount needed for this project.")
            else:
                add_investment(
                    project["id"],
                    invest_amount,
                    investor_name=current_name,
                    investor_username=current_username,
                )
                st.success("Thank you for your investment! 🎉")
                st.rerun()

        st.markdown("#### Recent investments for this project")
        investments = list_investments_for_project(project["id"])
        if investments:
            for inv in investments:
                name = inv["investor_name"] or "Anonymous investor"
                st.write(
                    f"- {name} invested €{inv['amount']:.2f} on {inv['created_at']}"
                )
        else:
            st.caption("No investments yet for this project.")


# -------------------------
# UI: Overview page
# -------------------------
def page_overview():
    st.subheader("📊 Project overview")

    projects = list_projects()
    if not projects:
        st.info("No projects yet.")
        return

    for p in projects:
        remaining = max(p["value_needed"] - p["total_raised"], 0)
        with st.expander(f"{p['name']} – remaining: €{remaining:.2f}"):
            cols = st.columns([2, 1])

            with cols[0]:
                st.markdown(f"**Description**: {p['description']}")
                st.markdown(f"**Total needed**: €{p['value_needed']:.2f}")
                st.markdown(f"**Interest rate**: {p['interest_rate']:.2f}%")
                st.markdown(f"**Raised**: €{p['total_raised']:.2f}")
                st.markdown(f"**Remaining**: €{remaining:.2f}")

                if p["value_needed"] > 0:
                    progress = p["total_raised"] / p["value_needed"]
                    progress = min(max(progress, 0), 1)
                    st.progress(progress)

            with cols[1]:
                if p["image_path"] and Path(p["image_path"]).exists():
                    st.image(p["image_path"], use_column_width=True)
                else:
                    st.caption("No image available.")


# -------------------------
# UI: Personal page
# -------------------------
def page_personal_page(current_name: str, current_username: str):
    st.subheader("👤 My Page")

    investments = list_investments_for_user(current_name, current_username)

    if not investments:
        st.info("You haven't invested in any projects yet.")
        return

    df = pd.DataFrame(investments)

    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"])
    else:
        df["created_at"] = pd.to_datetime(df.index, unit="D", origin="unix")

    df["expected_gain"] = df["amount"] * df["project_interest_rate"] / 100.0
    df = df.sort_values("created_at")
    df["cum_invested"] = df["amount"].cumsum()
    df["cum_expected_gain"] = df["expected_gain"].cumsum()

    st.markdown("### Investment history")
    st.line_chart(
        df.set_index("created_at")[["cum_invested", "cum_expected_gain"]],
        height=350,
    )

    st.markdown("### Investment summary by project")
    summary = (
        df.groupby("project_name")
        .agg(
            total_invested=("amount", "sum"),
            avg_interest=("project_interest_rate", "mean"),
            expected_gain=("expected_gain", "sum"),
            num_investments=("id", "count"),
        )
        .reset_index()
    )

    st.dataframe(
        summary.style.format(
            {
                "total_invested": "€{:.2f}",
                "avg_interest": "{:.2f}%",
                "expected_gain": "€{:.2f}",
            }
        ),
        use_container_width=True,
    )

    st.markdown("### Raw transaction list")
    st.dataframe(
        df[
            [
                "created_at",
                "project_name",
                "amount",
                "project_interest_rate",
                "expected_gain",
            ]
        ]
        .rename(
            columns={
                "created_at": "Date",
                "project_name": "Project",
                "amount": "Amount (€)",
                "project_interest_rate": "Interest (%)",
                "expected_gain": "Expected gain (€)",
            }
        )
        .sort_values("Date", ascending=False),
        use_container_width=True,
    )


# -------------------------
# Main app
# -------------------------
def main():
    st.set_page_config(
        page_title="Mini Crowdfunding Platform",
        page_icon="💶",
        layout="wide",
    )
    init_db()

    # ---- Login / Register ----
    name, authenticated, username = login_or_register()
    if not authenticated:
        return  # login_or_register already rendered the view

    # ---- After login ----
    st.sidebar.button("Logout", on_click=logout)
    st.sidebar.caption(f"Logged in as **{name}** ({username})")

    st.title("Mini Crowdfunding Platform")

    tab_submit, tab_invest, tab_my_page, tab_overview = st.tabs(
        ["Submit a project", "Invest in projects", "My Page", "Projects overview"]
    )

    with tab_submit:
        page_submit_project()
    with tab_invest:
        page_invest(name, username)
    with tab_my_page:
        page_personal_page(name, username)
    with tab_overview:
        page_overview()


if __name__ == "__main__":
    main()
