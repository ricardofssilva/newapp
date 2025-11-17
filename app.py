import streamlit as st
import sqlite3
from pathlib import Path
from datetime import datetime
import uuid
import os

# -------------------------
# Config
# -------------------------
DB_PATH = "crowdfunding.db"
IMAGE_DIR = Path("project_images")
IMAGE_DIR.mkdir(exist_ok=True)


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
            amount REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
        """
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


def get_project(project_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    return cur.fetchone()


def add_investment(project_id, amount, investor_name=None):
    conn = get_connection()
    cur = conn.cursor()

    # Insert investment
    cur.execute(
        """
        INSERT INTO investments (project_id, investor_name, amount, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (project_id, investor_name, amount, datetime.utcnow().isoformat()),
    )

    # Update project's total_raised
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


# -------------------------
# UI: Project creation
# -------------------------
def page_submit_project():
    st.header("📌 Submit a new project")

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
            st.error("Please fill in the name, description and a positive value needed.")
            return

        image_path = None
        if uploaded_image is not None:
            # Save uploaded image to disk
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
def page_invest():
    st.header("💰 Invest in projects")

    projects = list_projects()
    if not projects:
        st.info("There are no projects yet. Check back later or submit one yourself!")
        return

    # For the selector, show name and remaining amount
    project_options = []
    option_to_id = {}
    for p in projects:
        remaining = max(p["value_needed"] - p["total_raised"], 0)
        label = f'{p["name"]} – needed: €{p["value_needed"]:.2f}, raised: €{p["total_raised"]:.2f}, remaining: €{remaining:.2f}'
        project_options.append(label)
        option_to_id[label] = p["id"]

    selected_label = st.selectbox("Select a project to invest in", project_options)
    selected_project_id = option_to_id[selected_label]
    project = get_project(selected_project_id)

    if project:
        remaining = max(project["value_needed"] - project["total_raised"], 0)

        st.subheader(project["name"])
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

        st.markdown("---")
        st.subheader("Make an investment")

        investor_name = st.text_input("Your name (optional)")
        max_invest = remaining if remaining > 0 else 0.0
        invest_amount = st.number_input(
            "Amount to invest (€)",
            min_value=0.0,
            max_value=max_invest,
            step=10.0,
            format="%.2f",
            key=f"invest_amount_{project['id']}",
        )

        if st.button("Invest now"):
            if invest_amount <= 0:
                st.error("Please enter a positive amount.")
            elif invest_amount > remaining:
                st.error("Amount exceeds remaining needed for this project.")
            else:
                add_investment(project["id"], invest_amount, investor_name or None)
                st.success("Thank you for your investment! 🎉")
                st.experimental_rerun()  # refresh page to show updated totals

        # Show recent investments
        st.markdown("### Recent investments for this project")
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
    st.header("📊 Project overview")

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
# Main app
# -------------------------
def main():
    st.set_page_config(page_title="Mini Crowdfunding Platform", page_icon="💶", layout="wide")
    init_db()

    st.sidebar.title("Mini Crowdfunding")
    page = st.sidebar.radio(
        "I want to…",
        (
            "Submit a project",
            "Invest in projects",
            "View projects overview",
        ),
    )

    if page == "Submit a project":
        page_submit_project()
    elif page == "Invest in projects":
        page_invest()
    else:
        page_overview()


if __name__ == "__main__":
    main()
