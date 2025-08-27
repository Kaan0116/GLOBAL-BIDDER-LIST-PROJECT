# 📑 Tender Management Dashboard

Bu proje, **tedarikçi yönetimi**, **ihale analizi** ve **AI destekli teklif süreci** için geliştirilmiş bir **Streamlit tabanlı web uygulamasıdır**.  

## 🔧 Özellikler

### 👤 Kullanıcı Yönetimi
- Kullanıcı kayıt ve giriş sistemi (`bcrypt` ile şifreleme).
- Rollerle (user/admin) giriş desteği.

### 🗄️ Veritabanı Entegrasyonu
- PostgreSQL üzerinden `bidders`, `tenders` ve `offers` tabloları.
- SQLAlchemy ile veritabanı bağlantısı ve sorgular.

### 📋 Tedarikçi Yönetimi
- Kayıtlı tedarikçilerin listelenmesi.
- Her tedarikçi için detaylı ihale bilgileri görüntüleme.

### 📊 Analitik Modül
- Ülke bazlı karşılaştırmalar.
- En çok harcama yapan tedarikçiler.
- Ülke bazında fiyat dağılımları.
- Plotly ile etkileşimli grafikler.

### 🤖 AI Destekli Tedarikçi Bulma
- Kullanıcı sorgusunu AI ile filtrelere dönüştürme (`buyer_country`, `max_price`, `keywords` vb.).
- AI destekli piyasa araştırması (fiyat aralıkları).
- Tedarikçilere otomatik **RFQ (Request for Quotation)** gönderme.
- Şirket sektörünü AI ile özetleme.
- Google araması ile iletişim e-postası bulma.

### 📬 E-posta Entegrasyonu
- Gmail IMAP üzerinden gelen mailleri okuma.
- SMTP ile tedarikçilere e-posta gönderme.
- Gelen teklifleri AI ile analiz etme:
  - Fiyat (USD)
  - Teslim süresi
  - Ödeme şartları
- Çok dilli mailler (Türkçe/İngilizce fark etmez, AI önce çevirir sonra analiz eder).

### 📑 Teklif Yönetimi
- Gönderilen RFQ’lar veritabanına kaydedilir.
- Gelen teklifler otomatik olarak `offers` tablosunda güncellenir.
- Teklifler görüntülenebilir, kabul edilebilir veya beklemeye alınabilir.
- Piyasa fiyat aralıkları ile karşılaştırma yapılarak uyarı verir.

---

## ⚙️ Teknolojiler
- **Frontend**: Streamlit  
- **Veritabanı**: PostgreSQL (SQLAlchemy)  
- **AI**: OpenAI GPT-4o-mini  
- **Visualization**: Plotly  
- **E-posta**: IMAP + SMTP  
- **Web scraping**: BeautifulSoup, Regex  

---

## 🚀 Gelecek Geliştirmeler
- Arka planda otomatik çalışan servis (cron job / task scheduler) ile sürekli mail kontrolü.  
- Daha gelişmiş çoklu dil desteği.  
- Teklif kabul/red sonrası otomatik bildirim e-postaları.  












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
