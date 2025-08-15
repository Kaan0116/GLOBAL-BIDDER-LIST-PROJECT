import os
import pandas as pd
import streamlit as st
import plotly.express as px
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from dotenv import load_dotenv
import bcrypt

st.set_page_config(page_title="Tender UI", layout="wide")
load_dotenv()

# ---------------- DB Settings ----------------
DB_USER = os.getenv("DB_USER", "postgres").strip()
DB_PASS = os.getenv("DB_PASS", "").strip()
DB_HOST = os.getenv("DB_HOST", "127.0.0.1").strip()
DB_PORT = os.getenv("DB_PORT", "5432").strip()
DB_NAME = os.getenv("DB_NAME", "postgres").strip()
BIDDER_TABLE = os.getenv("TABLE_NAME_BIDDER", "bidder_list").strip()
TENDER_TABLE = os.getenv("TABLE_NAME_TENDER", "tender_data").strip()

DB_URL = URL.create(
    drivername="postgresql+psycopg2",
    username=DB_USER,
    password=DB_PASS,
    host=DB_HOST,
    port=int(DB_PORT),
    database=DB_NAME
)

@st.cache_resource
def get_engine():
    return create_engine(DB_URL, pool_pre_ping=True)

engine = get_engine()

# ---------------- User Authentication ----------------
def load_users():
    with engine.connect() as conn:
        df = pd.read_sql("SELECT username, password_hash, role FROM users", conn)
    return df

def check_login(username, password):
    users_df = load_users()
    if username in users_df['username'].values:
        stored_hash = users_df.loc[users_df['username'] == username, 'password_hash'].iloc[0].encode('utf-8')
        if bcrypt.checkpw(password.encode('utf-8'), stored_hash):
            role = users_df.loc[users_df['username'] == username, 'role'].iloc[0]
            return True, role
    return False, None

# ---------------- Login Screen ----------------
if "username" not in st.session_state:
    st.title("🔐 Login")
    login_username = st.text_input("Username")
    login_password = st.text_input("Password", type="password")
    if st.button("Login"):
        ok, role = check_login(login_username, login_password)
        if ok:
            st.session_state["username"] = login_username
            st.session_state["role"] = role
            st.rerun()
        else:
            st.error("Invalid username or password.")
    st.stop()

# ---------------- Logout Button ----------------
st.sidebar.write(f"👤 {st.session_state['username']} ({st.session_state['role']})")
if st.sidebar.button("Logout"):
    st.session_state.clear()
    st.rerun()

# ---------------- Page Selection ----------------
page = st.sidebar.radio("Select Page", ["Bidder List", "Analytics"])

# ---------------- Page 1: Bidder List ----------------
if page == "Bidder List":
    limit = 20
    page_no = st.sidebar.number_input("Page Number", min_value=1, value=1, step=1)
    offset = (page_no - 1) * limit

    @st.cache_data(ttl=300)
    def load_bidders(limit, offset, username, role):
        with engine.connect() as conn:
            if role == "admin":
                query = f"SELECT bidder_name FROM {BIDDER_TABLE} ORDER BY bidder_name LIMIT :limit OFFSET :offset"
                return pd.read_sql(text(query), conn, params={"limit": limit, "offset": offset})
            else:
                query = f"""
                    SELECT bidder_name FROM {BIDDER_TABLE}
                    WHERE bidder_name IN (
                        SELECT bidder_name FROM user_bidders WHERE username = :username
                    )
                    ORDER BY bidder_name LIMIT :limit OFFSET :offset
                """
                return pd.read_sql(text(query), conn, params={"username": username, "limit": limit, "offset": offset})

    @st.cache_data(ttl=300)
    def load_tender_details(bidder):
        with engine.connect() as conn:
            cols = pd.read_sql(
                text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = :tname
                """),
                conn,
                params={"tname": TENDER_TABLE}
            )["column_name"].tolist()
            order_sql = "ORDER BY tender_year DESC" if "tender_year" in cols else ""
            df = pd.read_sql(
                text(f"""
                    SELECT * FROM {TENDER_TABLE}
                    WHERE bidder_name = :bname
                    {order_sql}
                """),
                conn,
                params={"bname": bidder}
            )
            df.columns = [col.replace("_", " ").title() for col in df.columns]
            return df

    bidder_df = load_bidders(limit, offset, st.session_state["username"], st.session_state["role"])
    selected_bidder = st.session_state.get("selected_bidder", None)

    for bidder in bidder_df["bidder_name"]:
        if st.button(bidder):
            st.session_state["selected_bidder"] = bidder
            selected_bidder = bidder

    if selected_bidder:
        st.subheader(f"Tenders Related To {selected_bidder}")
        details_df = load_tender_details(selected_bidder)
        if details_df.empty:
            st.warning("No records found for this bidder.")
        else:
            st.dataframe(details_df, use_container_width=True)

# ---------------- Page 2: Analytics ----------------
else:
    st.header("📊 Tender Analytics")

    analysis_type = st.sidebar.selectbox(
        "Analysis Type",
        [
            "Country Comparison (Buyer Country)",
            "Top Spending Bidders",
            "Bidder Prices By Country"
        ]
    )

    metric = st.sidebar.selectbox(
        "Metric",
        ["Tender Count", "Total Price (USD)"]
    )

    metric_sql = 'COUNT(*) AS tender_count' if metric == "Tender Count" else 'SUM("tender_finalpriceUsd") AS total_price'
    metric_col = "tender_count" if metric == "Tender Count" else "total_price"

    selected_country = None
    if analysis_type == "Bidder Prices By Country":
        with engine.connect() as conn:
            country_list = pd.read_sql(
                text(f"SELECT DISTINCT bidder_country FROM {TENDER_TABLE} WHERE bidder_country IS NOT NULL ORDER BY bidder_country"),
                conn
            )["bidder_country"].tolist()
        selected_country = st.sidebar.selectbox("Select Country", country_list)

    if st.sidebar.button("Run Analysis"):
        if analysis_type == "Country Comparison (Buyer Country)":
            sql = f"""
                SELECT tender_year, buyer_country, {metric_sql}
                FROM {TENDER_TABLE}
                WHERE buyer_country IS NOT NULL
                GROUP BY tender_year, buyer_country
                ORDER BY tender_year;
            """
        elif analysis_type == "Top Spending Bidders":
            sql = f"""
                SELECT tender_year, bidder_name, {metric_sql}
                FROM {TENDER_TABLE}
                WHERE bidder_name IS NOT NULL
                GROUP BY tender_year, bidder_name
                ORDER BY tender_year;
            """
        elif analysis_type == "Bidder Prices By Country":
            sql = f"""
                SELECT tender_year, bidder_country, bidder_name, {metric_sql}
                FROM {TENDER_TABLE}
                WHERE bidder_country = :selected_country
                GROUP BY tender_year, bidder_country, bidder_name
                ORDER BY tender_year;
            """

        with engine.connect() as conn:
            if selected_country:
                df = pd.read_sql(text(sql), conn, params={"selected_country": selected_country})
            else:
                df = pd.read_sql(text(sql), conn)

        # Format column names
        df.columns = [col.replace("_", " ").title() for col in df.columns]

        if analysis_type == "Country Comparison (Buyer Country)":
            fig = px.line(df, x="Tender Year", y=metric_col.title().replace("_", " "), color="Buyer Country", markers=True)
            st.plotly_chart(fig, use_container_width=True)
        elif analysis_type == "Top Spending Bidders":
            top10 = df.groupby("Bidder Name")[metric_col].sum().nlargest(10).index
            df_top = df[df["Bidder Name"].isin(top10)]
            fig = px.line(df_top, x="Tender Year", y=metric_col.title().replace("_", " "), color="Bidder Name", markers=True)
            st.plotly_chart(fig, use_container_width=True)
        elif analysis_type == "Bidder Prices By Country":
            fig = px.line(df, x="Tender Year", y=metric_col.title().replace("_", " "), color="Bidder Name", markers=True)
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Please select the analysis type and metric, then click 'Run Analysis'.")
