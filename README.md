# Tender UI (Streamlit + PostgreSQL)

## Setup
1) Make sure you have **Python 3.10+** installed.
2) (Recommended) Create a virtual environment:
   ```bash
   python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```
3) Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4) Create a `.env` file (you can copy from `.env.example`) and fill in the values.

## Database Setup
1) Start PostgreSQL.
2) Create a database named `tedarik`:
   ```bash
   createdb -U postgres tedarik
   ```
3) Download the SQL dump from Google Drive:  
   **[Download dump.sql](PASTE_YOUR_GOOGLE_DRIVE_LINK_HERE)**  
4) Import the dump file into PostgreSQL:
   ```bash
   psql -U postgres -d tedarik -f dump.sql
   ```
5) Update your `.env` file with your own PostgreSQL credentials:
   ```
   DB_USER=postgres
   DB_PASS=your_password
   DB_HOST=127.0.0.1
   DB_PORT=5432
   DB_NAME=tedarik
   TABLE_NAME_BIDDER=bidder_list
   TABLE_NAME_TENDER=tender_data
   ```

## Running the App
```bash
streamlit run app.py
```

## Notes
- Your `tender_data` table is expected to contain the columns `bidder_name`, `tender_title`, `tender_description`, `tender_date`.  
  If column names are different, update them in `app.py`.
- Recommended indexes for performance:
   ```sql
   CREATE INDEX IF NOT EXISTS idx_tender_bidder ON tender_data (bidder_name);
   CREATE INDEX IF NOT EXISTS idx_tender_date ON tender_data (tender_date);
   -- For full-text search (Postgres 12+):
   CREATE EXTENSION IF NOT EXISTS pg_trgm;
   CREATE INDEX IF NOT EXISTS idx_tender_title_trgm ON tender_data USING gin (tender_title gin_trgm_ops);
   CREATE INDEX IF NOT EXISTS idx_tender_desc_trgm ON tender_data USING gin (tender_description gin_trgm_ops);
   ```
