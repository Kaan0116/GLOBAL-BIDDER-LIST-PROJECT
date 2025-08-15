# Tender UI (Streamlit + PostgreSQL)

## Kurulum
1) Python 3.10+ kurulu olduğundan emin olun.
2) (Önerilir) Sanal ortam oluşturun:
   ```bash
   python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```
3) Bağımlılıkları yükleyin:
   ```bash
   pip install -r requirements.txt
   ```
4) `.env` dosyasını oluşturun ( `.env.example`'ı kopyalayabilirsiniz ) ve değerleri doldurun.
5) Çalıştırın:
   ```bash
   streamlit run app.py
   ```

## Notlar
- `tender_data` tablonuzda `bidder_name`, `tender_title`, `tender_description`, `tender_date` kolonları varsayılmıştır. İsimler farklıysa `app.py` içinde güncelleyin.
- Performans için index önerileri:
  ```sql
  CREATE INDEX IF NOT EXISTS idx_tender_bidder ON tender_data (bidder_name);
  CREATE INDEX IF NOT EXISTS idx_tender_date ON tender_data (tender_date);
  -- Serbest arama için (Postgres 12+):
  CREATE EXTENSION IF NOT EXISTS pg_trgm;
  CREATE INDEX IF NOT EXISTS idx_tender_title_trgm ON tender_data USING gin (tender_title gin_trgm_ops);
  CREATE INDEX IF NOT EXISTS idx_tender_desc_trgm ON tender_data USING gin (tender_description gin_trgm_ops);
  ```
