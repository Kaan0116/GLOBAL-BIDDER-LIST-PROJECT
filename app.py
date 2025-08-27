import os
import re
import json
import pandas as pd
import streamlit as st
import plotly.express as px
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from dotenv import load_dotenv
import bcrypt
from openai import OpenAI
import streamlit.components.v1 as components
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests, re
from bs4 import BeautifulSoup
import imaplib, email, re
# if "username" not in st.session_state:
#     st.session_state["username"] = "Guest"
#     st.session_state["role"] = "user"

def local_css(file_name):
    with open(file_name) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

local_css("style.css")
# ---------------- CONFIG ----------------
st.set_page_config(
    page_title="Tender Management Dashboard",
    page_icon="📑",
    layout="wide",
    initial_sidebar_state="expanded"
)
def fetch_recent_emails(limit=5):
    user = os.getenv("SENDER_EMAIL")
    password = os.getenv("SENDER_PASSWORD")

    try:
        # Gmail için
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(user, password)
        mail.select("inbox")

        status, data = mail.search(None, "ALL")  # sadece "UNSEEN" de yapılabilir
        email_ids = data[0].split()
        messages = []

        for eid in email_ids[-limit:]:
            status, msg_data = mail.fetch(eid, "(RFC822)")
            raw_msg = email.message_from_bytes(msg_data[0][1])

            subject = raw_msg["subject"]
            sender = raw_msg["from"]
            body = ""

            if raw_msg.is_multipart():
                for part in raw_msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            body = part.get_payload(decode=True).decode()
                        except:
                            pass
            else:
                body = raw_msg.get_payload(decode=True).decode()

            messages.append({"from": sender, "subject": subject, "body": body})
        mail.logout()
        return messages

    except Exception as e:
        return [{"error": str(e)}]
load_dotenv()

# ---------------- DB SETTINGS ----------------
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

# ---------------- OPENAI SETTINGS ----------------
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def ai_extract_filters(query_text):
    prompt = f"""
    Analyze the user's supplier search request and output JSON with:
    - buyer_country: 2-letter ISO code or null
    - bidder_country: 2-letter ISO code or null
    - year_min: integer or null
    - year_max: integer or null
    - max_price: number in USD or null
    - product_keywords: keywords for tender_title

    Only output valid JSON. No explanations.

    Query: "{query_text}"
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        raw_text = response.choices[0].message.content.strip()
        json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if not json_match:
            st.error("No JSON found in AI output")
            return None
        return json.loads(json_match.group(0))
    except Exception as e:
        st.error(f"AI parsing failed: {e}")
        return None

def find_suppliers(filters):
    def run_query(use_keywords=True, use_maxprice=True, use_bidder_country=True, use_years=True):
        where_clauses, params = [], {}

        if filters.get("buyer_country"):
            where_clauses.append("buyer_country = :buyer_country")
            params["buyer_country"] = filters["buyer_country"]

        if use_bidder_country and filters.get("bidder_country"):
            where_clauses.append("bidder_country = :bidder_country")
            params["bidder_country"] = filters["bidder_country"]

        if use_years and filters.get("year_min"):
            where_clauses.append("tender_year >= :ymin")
            params["ymin"] = filters["year_min"]
        if use_years and filters.get("year_max"):
            where_clauses.append("tender_year <= :ymax")
            params["ymax"] = filters["year_max"]

        if use_maxprice and filters.get("max_price"):
            where_clauses.append('"tender_finalpriceUsd" <= :max_price')
            params["max_price"] = filters["max_price"]

        if use_keywords and filters.get("product_keywords"):
            where_clauses.append("tender_title ILIKE :keywords")
            params["keywords"] = f"%{filters['product_keywords']}%"

        where_sql = " AND ".join(where_clauses)
        if where_sql:
            where_sql = "WHERE " + where_sql

        query = f"""
            SELECT
                bidder_name,
                bidder_country,
                bidder_email,
                bidder_phone,
                bidder_url,
                "bidder_contactName",
                COUNT(*) AS tender_count,
                AVG("tender_finalpriceUsd") AS avg_price
            FROM {TENDER_TABLE}
            {where_sql}
            GROUP BY bidder_name, bidder_country, bidder_email, bidder_phone, bidder_url, "bidder_contactName"
            ORDER BY tender_count DESC
            LIMIT 10;
        """
        with engine.connect() as conn:
            return pd.read_sql(text(query), conn, params=params)

    # 🔹 Fallback zinciri (kaybolmuştu, geri ekleniyor)
    df = run_query(True, True, True, True)
    if not df.empty:
        return df
    st.info("No exact match. Relaxing keyword filter...")
    df = run_query(False, True, True, True)
    if not df.empty:
        return df
    st.info("Still no match. Ignoring max price...")
    df = run_query(False, False, True, True)
    if not df.empty:
        return df
    st.info("Still no match. Allowing foreign suppliers...")
    df = run_query(False, False, False, True)
    if not df.empty:
        return df
    st.info("Still no match. Removing year restriction...")
    return run_query(False, False, False, False)

def summarize_industry(bidder_name, bidder_url=None):
    """AI ile şirketin sektörünü / faaliyetini özetler"""
    query_text = f"Company name: {bidder_name}. "
    if bidder_url:
        query_text += f"Website: {bidder_url}. "
    query_text += "Please summarize briefly which industry this company operates in and what it does."

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": query_text}],
            temperature=0.2
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return "Industry information not available."
def send_email_smtp(to_emails, subject, body):
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = ",".join(to_emails)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)  # Outlook için: smtp.office365.com
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_emails, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        return str(e)

def fetch_recent_emails(limit=5):
    user = os.getenv("SENDER_EMAIL")
    password = os.getenv("SENDER_PASSWORD")

    try:
        # Gmail için
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(user, password)
        mail.select("inbox")

        status, data = mail.search(None, "ALL")  # sadece okunmamış için: "UNSEEN"
        email_ids = data[0].split()
        messages = []

        for eid in email_ids[-limit:]:
            status, msg_data = mail.fetch(eid, "(RFC822)")
            raw_msg = email.message_from_bytes(msg_data[0][1])

            subject = raw_msg["subject"]
            sender = raw_msg["from"]

            # sadece düz metin body
            body = ""
            if raw_msg.is_multipart():
                for part in raw_msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            body = part.get_payload(decode=True).decode()
                        except:
                            pass
            else:
                try:
                    body = raw_msg.get_payload(decode=True).decode()
                except:
                    body = ""

            messages.append({
                "from": sender,
                "subject": subject,
                "body": body
            })
        mail.logout()
        return messages

    except Exception as e:
        return [{"error": str(e)}]

def analyze_tender_about(text):
    """
    Kullanıcı tarafından girilen ürün/hizmet bilgisini özetleyip
    e-mail konusu için kısa bir ifade üretir.
    """
    prompt = f"""
    You are preparing text for an email about a tender.
    Rules:
    - Translate to English if needed (e.g., if Turkish).
    - Give a short phrase (max 10 words).
    - Include quantity if mentioned (e.g., "100 units of Parol medicine").
    - Do NOT explain, only return the phrase to be used directly in the email.
    
    Tender about: "{text}"
    """
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return text


def market_research(product_info, quantity=None):
    """
    AI destekli piyasa araştırması yapar.
    - product_info: ürün açıklaması
    - quantity: adet bilgisi (opsiyonel)
    Çıktı: fiyat aralığı metin olarak
    """
    prompt = f"""
    You are a market research assistant.
    Estimate the typical wholesale price range in USD for the following product.
    Consider international suppliers and bulk purchase scenarios.
    If quantity is provided, scale the estimation accordingly.
    Provide result as: "Estimated price range: X - Y USD per unit"
    Product: {product_info}
    Quantity: {quantity if quantity else "N/A"}
    """
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Market research failed: {e}"


    df = run_query(True, True, True, True)
    if not df.empty:
        return df
    st.info("No exact match. Relaxing keyword filter...")
    df = run_query(False, True, True, True)
    if not df.empty:
        return df
    st.info("Still no match. Ignoring max price...")
    df = run_query(False, False, True, True)
    if not df.empty:
        return df
    st.info("Still no match. Allowing foreign suppliers...")
    df = run_query(False, False, False, True)
    if not df.empty:
        return df
    st.info("Still no match. Removing year restriction...")
    return run_query(False, False, False, False)

# ---------------- AUTH ----------------
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

def create_user(username, password, role="user"):
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    with engine.connect() as conn:
        conn.execute(
            text("INSERT INTO users (username, password_hash, role) VALUES (:u, :p, :r)"),
            {"u": username, "p": hashed, "r": role}
        )
        conn.commit()
def save_offer(username, name, email, status="Bekleniyor", price=None, delivery=None, terms=None):
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO offers (username, supplier_name, supplier_email, status, price, delivery, terms)
                VALUES (:u, :n, :e, :s, :p, :d, :t)
            """),
            {"u": username, "n": name, "e": email, "s": status, "p": price, "d": delivery, "t": terms}
        )
        conn.commit()

def load_offers(username):
    with engine.connect() as conn:
        return pd.read_sql(
            text("SELECT * FROM offers WHERE username = :u ORDER BY created_at DESC"),
            conn,
            params={"u": username}
        )

# ---------------- LOGIN & REGISTER ----------------
if "username" not in st.session_state:
    st.title("🔐 Account")

    auth_choice = st.radio("Select Action", ["Login", "Register"])

    if auth_choice == "Login":
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

    elif auth_choice == "Register":
        new_username = st.text_input("Choose Username")
        new_password = st.text_input("Choose Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        if st.button("Create Account"):
            if new_password != confirm_password:
                st.error("Passwords do not match.")
            elif not new_username or not new_password:
                st.error("Username and password cannot be empty.")
            else:
                try:
                    create_user(new_username, new_password)
                    st.success("Account created successfully! You can now login.")
                except Exception as e:
                    st.error(f"Failed to create account: {e}")

    st.stop()

# ---------------- LOGOUT ----------------
st.sidebar.write(f"👤 {st.session_state['username']} ({st.session_state['role']})")
if st.sidebar.button("Logout"):
    st.session_state.clear()
    st.rerun()

# ---------------- SIDEBAR ----------------
# st.sidebar.image("logo.png", width=160)
st.sidebar.markdown("## 🏛️ Tender Dashboard")
st.sidebar.write("Manage bidders, analytics, and AI-powered supplier search.")
st.sidebar.markdown("---")

page = st.sidebar.radio("📂 Pages", ["📋 Bidder List", "📊 Analytics", "🤖 AI Supplier Finder"])

# ---------------- PAGE 1: Bidder List ----------------
if page == "📋 Bidder List":
    st.title("📋 Bidder List")
    st.caption("Explore and manage registered bidders.")

    limit = 20
    page_no = st.sidebar.number_input("Page Number", min_value=1, value=1, step=1)
    offset = (page_no - 1) * limit

    def load_bidders(limit, offset):
        with engine.connect() as conn:
            return pd.read_sql(
                text(f"SELECT bidder_name FROM {BIDDER_TABLE} ORDER BY bidder_name LIMIT :limit OFFSET :offset"),
                conn,
                params={"limit": limit, "offset": offset}
            )

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
            return pd.read_sql(
                text(f"""
                    SELECT * FROM {TENDER_TABLE}
                    WHERE bidder_name = :bname
                    {order_sql}
                """),
                conn,
                params={"bname": bidder}
            )

    bidder_df = load_bidders(limit, offset)
    selected_bidder = st.session_state.get("selected_bidder", None)

    for bidder in bidder_df["bidder_name"]:
        with st.container():
            st.markdown(f"#### 🏷️ {bidder}")
            if st.button("View Details", key=f"view_{bidder}"):
                st.session_state["selected_bidder"] = bidder
                selected_bidder = bidder
        st.markdown("---")

    if selected_bidder:
        st.subheader(f"Tenders Related To {selected_bidder}")
        details_df = load_tender_details(selected_bidder)
        if details_df.empty:
            st.warning("No records found for this bidder.")
        else:
            st.dataframe(details_df, use_container_width=True)

# ---------------- PAGE 2: Analytics ----------------
elif page == "📊 Analytics":
    st.title("📊 Tender Analytics")
    st.caption("Analyze tender data with interactive charts.")

    analysis_type = st.sidebar.selectbox(
        "Analysis Type",
        ["Country Comparison (Buyer Country)", "Top Spending Bidders", "Bidder Prices By Country"]
    )

    metric = st.sidebar.selectbox("Metric", ["Tender Count", "Total Price (USD)"])

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

        if analysis_type == "Country Comparison (Buyer Country)":
            fig = px.line(df, x="tender_year", y=metric_col, color="buyer_country", markers=True)
        elif analysis_type == "Top Spending Bidders":
            top10 = df.groupby("bidder_name")[metric_col].sum().nlargest(10).index
            df_top = df[df["bidder_name"].isin(top10)]
            fig = px.line(df_top, x="tender_year", y=metric_col, color="bidder_name", markers=True)
        elif analysis_type == "Bidder Prices By Country":
            fig = px.line(df, x="tender_year", y=metric_col, color="bidder_name", markers=True)

        fig.update_layout(template="plotly_white", font=dict(size=14), margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Please select the analysis type and metric, then click 'Run Analysis'.")




# ---------------- PAGE 3: AI Supplier Finder ----------------
elif page == "🤖 AI Supplier Finder":
    st.title("🤖 AI Supplier Finder")
    st.caption("Find suppliers, request offers, and negotiate automatically.")

    user_query = st.text_area("Describe what kind of supplier you are looking for:")

    contact_type = st.radio("Would you like to send as:", ["Individual (Name)", "Company"])
    if contact_type == "Individual (Name)":
        contact_identity = st.text_input("Your Name", value=st.session_state.get("username", "Guest"))
    else:
        contact_identity = st.text_input("Your Company Name", "")

    product_info = st.text_input("What product/service is this tender about?")
    def generate_mailto_link(to_email, subject, body):
        subject_enc = subject.replace(" ", "%20")
        body_enc = body.replace("\n", "%0D%0A").replace(" ", "%20")
        return f"mailto:{to_email}?subject={subject_enc}&body={body_enc}"

    # 🔹 Market research parse fonksiyonu
    def parse_price_band(summary_text):
        match = re.search(r"(\d+\.?\d*)\s*-\s*(\d+\.?\d*)", summary_text)
        if match:
            return float(match.group(1)), float(match.group(2))
        return None, None

    # 🔹 Gelen e-postaları analiz et
    def analyze_offer_email(email_text, product_info):
        prompt = f"""
        The following email may not be in English.
        First, translate the content into English if necessary.
        Then extract structured offer details.

        Product of interest: {product_info}
        Email: {email_text}

        Output valid JSON with fields:
        - price_usd (float)
        - delivery_time (string)
        - payment_terms (string or null)
        """
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            return json.loads(resp.choices[0].message.content.strip())
        except Exception as e:
            return {"error": str(e)}
    def lookup_company_email(company_name, website=None):
        """
        Şirket adı veya web sitesiyle internetten resmi iletişim e-postasını bulur.
        Öncelik: sales@, info@, contact@ gibi adresler.
        """
        query = f"{company_name} contact email"
        if website:
            query += f" site:{website}"

        try:
            resp = requests.get(f"https://www.google.com/search?q={query}", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text()

            emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
            if emails:
                for pref in ["sales@", "info@", "contact@", "office@", "support@"]:
                    for e in emails:
                        if pref in e.lower():
                            return e
                return emails[0]
            else:
                return None
        except Exception:
            return None
    # ---------- RFQ Gönder ----------
    if st.button("🔎 Find Suppliers and Send RFQ"):
        if not user_query.strip() or not product_info.strip():
            st.warning("Please enter a query and product info.")
        else:
            with st.spinner("Finding suppliers and sending RFQs..."):
                market_summary = market_research(product_info)
                st.subheader("📊 AI Market Research")
                st.info(market_summary)
                min_price, max_price = parse_price_band(market_summary)

                filters = ai_extract_filters(user_query)
                if filters:
                    results_df = find_suppliers(filters)
                    if results_df is not None and not results_df.empty:
                        st.success(f"✅ Found {len(results_df)} suppliers.")

                        tender_summary = analyze_tender_about(product_info)
                        supplier_emails = [row["bidder_email"] for _, row in results_df.iterrows() if row["bidder_email"]]

                        if supplier_emails:
                            subject = f"Request for Quotation - {tender_summary}"
                            body = (
                                f"Dear Supplier,\n\n"
                                f"We are currently evaluating suppliers for {tender_summary}.\n"
                                f"Could you please provide us with your best offer including:\n"
                                f"- Price per unit\n"
                                f"- Delivery time\n"
                                f"- Payment terms\n\n"
                                f"Best regards,\n{contact_identity}"
                            )

                            result = send_email_smtp(supplier_emails, subject, body)
                            if result is True:
                                st.success("📨 RFQ emails sent successfully to all suppliers.")
                            else:
                                st.error(f"Failed to send emails: {result}")
# RFQ gönderilen şirketleri veritabanına kaydet
                        for _, row in results_df.iterrows():
                            found_email = lookup_company_email(row["bidder_name"], row["bidder_url"])
                            email_to_use = found_email or row["bidder_email"]

                            save_offer(
                                username=st.session_state["username"],
                                name=row["bidder_name"],
                                email=email_to_use,
                                status="Bekleniyor"
                            )


                        

                        # Bilgi amaçlı liste
                        for i, row in results_df.iterrows():
                            with st.expander(f"🏢 {row['bidder_name']}"):
                                st.write(f"📍 Country: **{row['bidder_country']}**")
                                st.write(f"📧 {row['bidder_email'] or 'N/A'}")
                                st.write(f"🌐 {row['bidder_url'] or 'N/A'}")
                                st.write(f"🏭 Industry: {summarize_industry(row['bidder_name'], row['bidder_url'])}")

                        fig = px.bar(results_df, x="bidder_name", y="tender_count", color="bidder_country")
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("No suppliers matched your criteria.")
                else:
                    st.error("❌ Failed to parse filters from your query.")

    # ---------- Inbox Analizi ----------
    if st.button("📥 Check Inbox for Offers"):
        st.subheader("📥 Supplier Email Analysis")

        # TODO: Gmail/Outlook API entegrasyonu
        emails = fetch_recent_emails()
        for mail in emails:
            if "error" in mail:
                st.error(mail["error"])
                continue
            st.markdown(f"### ✉️ From: {mail['from']}")
            st.write(f"**Subject:** {mail['subject']}")
            st.write(f"**Body:** {mail['body'][:300]}...")

            details = analyze_offer_email(mail['body'], product_info)
            st.json(details)
            sender = re.search(r'[\w\.-]+@[\w\.-]+', mail["from"])
            sender_email = sender.group(0).lower() if sender else mail["from"].lower()

       #min_price, max_price = parse_price_band(market_research(product_info))
        # Gelen mailleri teklif tablosuna işle


        

            details = analyze_offer_email(mail['body'], product_info)
            st.json(details)
            with engine.connect() as conn:
                conn.execute(
                    text("""
                        UPDATE offers
                        SET price = :p, delivery = :d, terms = :t, status = 'Teklif Geldi'
                        WHERE username = :u AND supplier_email = :e
                    """),
                    {
                        "p": details.get("price_usd"),
                        "d": details.get("delivery_time"),
                        "t": details.get("payment_terms"),
                        "u": st.session_state["username"],
                        "e": mail["from"]
                    }
                )
                conn.commit()

            if "price_usd" in details and details["price_usd"]:
                price = details["price_usd"]
                if min_price and max_price and price > max_price:
                    st.warning(f"⚠️ Offer {price} USD is above market.")
                else:
                    st.success(f"✅ Offer {price} USD is acceptable (within/below market).")
          # ---------- Teklif Tablosu ----------

# Teklifleri veritabanından çek ve göster
offers_df = load_offers(st.session_state["username"])
if not offers_df.empty:
    st.subheader("📑 Supplier Offers")
    st.dataframe(offers_df, use_container_width=True)

    for i, row in offers_df.iterrows():
        if row["status"] == "Teklif Geldi":
            if st.button(f"✅ Accept {row['supplier_name']}", key=f"accept_{i}"):
                with engine.connect() as conn:
                    conn.execute(
                        text("UPDATE offers SET status = 'Kabul Edildi ✅' WHERE id = :id"),
                        {"id": row["id"]}
                    )
                    conn.commit()
                st.success(f"Offer from {row['supplier_name']} accepted.")
                st.rerun()
