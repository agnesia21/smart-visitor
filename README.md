# 🏢 Smart Visitor AI Agent

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Flask-3.0+-000000?style=for-the-badge&logo=flask&logoColor=white" alt="Flask">
  <img src="https://img.shields.io/badge/Google%20Gemini-2.5--Flash-4285F4?style=for-the-badge&logo=google&logoColor=white" alt="Gemini">
  <img src="https://img.shields.io/badge/PostgreSQL-Supabase-336791?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Deploy-Vercel-000000?style=for-the-badge&logo=vercel&logoColor=white" alt="Vercel">
  <img src="https://img.shields.io/badge/License-MIT-82B440?style=for-the-badge" alt="License">
</p>

<p align="center">
  <strong>Sistem Manajemen Buku Tamu Cerdas Berbasis Web dengan Integrasi Google Gemini AI Agent</strong>
</p>

<p align="center">
  <a href="#-tentang-proyek">Tentang Proyek</a> •
  <a href="#-fitur-utama">Fitur Utama</a> •
  <a href="#-alur-logika--arsitektur">Alur Logika</a> •
  <a href="#-struktur-repositori">Struktur Repositori</a> •
  <a href="#-panduan-instalasi-lokal">Instalasi Lokal</a> •
  <a href="#-panduan-deploy-ke-vercel">Deploy ke Vercel</a> •
  <a href="#-penggunaan-langsung-via-python-sdk">Python SDK</a> •
  <a href="#-batasan-dan-catatan-teknis">Catatan Teknis</a> •
  <a href="#-lisensi">Lisensi</a>
</p>

---

## 📌 Tentang Proyek

**Smart Visitor AI Agent** adalah aplikasi manajemen pengunjung (*visitor management system*) modern berbasis web yang mengintegrasikan kecerdasan buatan (**Google Gemini 2.5 Flash**) untuk mengotomatiskan proses penerimaan dan pencatatan data tamu secara interaktif, natural, dan terstruktur.

Aplikasi ini menggantikan buku tamu konvensional manual menjadi sistem digital yang aman dan otomatis:
- Tamu dapat mendaftarkan diri secara mandiri melalui asisten percakapan AI (*conversational check-in*) yang memvalidasi identitas secara *real-time*.
- Petugas (*staff/receptionist*) mendapatkan visibilitas penuh terhadap siapa saja yang sedang berada di dalam gedung, status penitipan kartu identitas, riwayat kunjungan, serta analitik komprehensif.

---

## ✨ Fitur Utama

| Modul | Deskripsi Fitur |
|---|---|
| 🤖 **AI-Powered Check-in** | Percakapan interaktif menggunakan Google Gemini untuk mengekstrak data tamu secara bertahap (Nama, Identitas, No HP, Instansi, Tujuan, Keperluan, Titip Kartu). |
| 🛡️ **Validasi Data Cerdas** | Validasi format identitas otomatis (KTP: 16 digit angka, SIM: 12 digit angka, NIM: 6–20 karakter alfanumerik) serta validasi nomor telepon. |
| 🔄 **Sistem Fallback Deterministik** | Jika kuota API Gemini habis atau terjadi gangguan jaringan, sistem otomatis beralih ke form bertahap terpadu tanpa mengganggu proses check-in. |
| 🚪 **Sistem Check-out Instan** | Pencarian data kunjungan aktif berdasarkan nomor identitas, pratinjau status penitipan kartu fisik, dan pencatatan waktu keluar secara otomatis. |
| 📊 **Dashboard Staff Terintegrasi** | Statistik *real-time* jumlah pengunjung hari ini, tamu yang sedang berada di gedung (*checked-in*), riwayat keluar (*checked-out*), serta rekapitulasi kartu yang dititipkan. |
| 🔔 **Notifikasi Kunjungan Baru** | Pemantauan kedatangan tamu baru secara *live* dengan polling berkala pada dashboard staff. |
| 📈 **Laporan & Ekspor CSV** | Filter riwayat kunjungan berdasarkan rentang tanggal dan status, serta fitur ekspor laporan ke format file `.csv`. |
| 🔐 **Manajemen Akun & Profil Staff** | Autentikasi aman berbasis sesi, pembaruan profil staff, dan penggantian kata sandi petugas. |

---

## 🧠 Alur Logika & Arsitektur

### 1. Alur Check-in Pengunjung (Conversational Flow)

```mermaid
flowchart TD
    A[Pengunjung Buka Halaman Check-in] --> B{Pilih Metode}
    B -->|AI Agent Chat| C[Input Percakapan Natural]
    B -->|Form Input| D[Pengisian Manual Bertahap]
    
    C --> E[Backend Flask + Gemini 2.5 Flash]
    E --> F[AI Function Calling / State Machine]
    F --> G{Semua Field Terisi & Valid?}
    
    G -->|Belum| H[AI Meminta Data yang Kurang]
    H --> C
    
    G -->|Lengkap| I[Tampilkan Ringkasan Data & Konfirmasi]
    I --> J[Simpan ke PostgreSQL Database]
    J --> K[Check-in Berhasil + Muncul Kartu Kunjungan Digital]
    K --> L[Notifikasi Masuk ke Dashboard Staff]
```

### 2. Alur Check-out & Manajemen Kartu

```mermaid
flowchart LR
    A[Pengunjung Masuk Menu Check-out] --> B[Masukkan Nomor Identitas]
    B --> C[Query Database: Status 'checked_in']
    C --> D{Data Ditemukan?}
    D -->|Tidak| E[Pesan: Tidak Ada Kunjungan Aktif]
    D -->|Ya| F[Tampilkan Data & Peringatan Status Kartu Dititipkan]
    F --> G[Konfirmasi Check-out]
    G --> H[Update DB: status='checked_out', check_out=NOW()]
    H --> I[Petugas Mengembalikan Kartu Fisik Tamu]
```

---

## 📂 Struktur Repositori

```text
smart-visitor/
├── api/                        # Direktori entry point Vercel Serverless
├── static/
│   └── style.css               # Styling global & komponen antarmuka modern
├── templates/
│   ├── checkin.html            # Halaman pendaftaran & chat AI check-in
│   ├── checkout.html           # Halaman check-out tamu mandiri
│   ├── index.html              # Landing page utama
│   ├── laporan.html            # Halaman rekapitulasi & ekspor laporan
│   ├── login.html              # Halaman login portal staff
│   ├── staff.html              # Dashboard utama monitoring staff
│   ├── staff_change_password.html # Form ubah password akun staff
│   ├── staff_notifications.html   # Riwayat notifikasi tamu masuk
│   ├── staff_profile.html      # Tampilan profil petugas
│   └── staff_profile_edit.html # Edit data nama & username staff
├── .env                        # Variabel lingkungan lokal (diabaikan git)
├── .gitignore                  # Berkas pengabaian Git
├── .vercelignore               # Berkas pengabaian build Vercel
├── app.py                      # Aplikasi inti Flask (Routing, AI Engine, DB logic)
├── requirements.txt            # Daftar dependensi Python
├── schema.sql                  # Skema DDL & DML inisialisasi database PostgreSQL
├── test_gemini.py              # Script pengujian koneksi langsung ke Gemini SDK
└── vercel.json                 # Konfigurasi routing & runtime deploy Vercel
```

---

## 💻 Panduan Instalasi Lokal

### 1. Prasyarat Sistem
- **Python** 3.10 atau versi lebih baru
- **PostgreSQL** (bisa menggunakan PostgreSQL lokal, Laragon PostgreSQL, atau instance cloud seperti Supabase/Neon)
- **Google Gemini API Key** (dapat dibuat melalui [Google AI Studio](https://aistudio.google.com/))
- **Git**

### 2. Kloning Repositori
```bash
git clone https://github.com/username/smart-visitor.git
cd smart-visitor
```

### 3. Buat dan Aktifkan Virtual Environment
- **Windows (PowerShell/CMD):**
  ```powershell
  python -m venv venv
  .\venv\Scripts\activate
  ```
- **macOS / Linux:**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```

### 4. Instalasi Dependensi
```bash
pip install -r requirements.txt
```

### 5. Konfigurasi Variabel Lingkungan (`.env`)
Buat file bernama `.env` pada root project, lalu isi dengan konfigurasi berikut:

```env
# Google Gemini API
GEMINI_API_KEY=AIzaSyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Database PostgreSQL (Gunakan salah satu format berikut)
# Opsi 1: URI PostgreSQL Cloud (Contoh: Supabase / Neon)
DATABASE_URL=postgresql://postgres.xxx:password@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres

# Opsi 2: Konfigurasi Lokal Terpisah (Jika tidak memakai DATABASE_URL)
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=visitor_management
DB_USER=postgres
DB_PASSWORD=your_local_password

# Flask Secret Key
SECRET_KEY=smart-visitor-rahasia-2026
```

### 6. Inisialisasi Database
Jalankan file `schema.sql` pada PostgreSQL Anda (menggunakan `psql`, pgAdmin, DBeaver, atau Supabase SQL Editor):

```bash
psql -h 127.0.0.1 -U postgres -d visitor_management -f schema.sql
```
> **Akun Bawaan Petugas:**
> - **Username:** `admin`
> - **Password:** `admin123`

### 7. Jalankan Aplikasi
```bash
python app.py
```
Buka browser Anda dan akses aplikasi di: `http://127.0.0.1:5000`

---

## 🚀 Panduan Deploy ke Vercel

Proyek ini telah dikonfigurasi agar siap dideploy ke **Vercel Serverless Functions** menggunakan `@vercel/python`.

### 1. Siapkan Database Cloud (Supabase / Neon)
1. Buat proyek baru di [Supabase](https://supabase.com).
2. Buka menu **SQL Editor**, salin seluruh isi [schema.sql](file:///d:/laragon/www/smart-visitor/schema.sql), lalu klik **Run**.
3. Buka menu **Project Settings > Database**, salin **Connection String (URI)** mode *Session* atau *Transaction Pooler* (Port 5432 / 6543).

### 2. Deploy Melalui Vercel Dashboard (Rekomendasi)
1. Push kode Anda ke repositori GitHub.
2. Buka [Vercel Dashboard](https://vercel.com/dashboard) dan klik **Add New Project**.
3. Impor repositori GitHub `smart-visitor`.
4. Pada bagian **Environment Variables**, tambahkan:
   - `GEMINI_API_KEY`: API Key dari Google AI Studio.
   - `DATABASE_URL`: Connection string PostgreSQL dari Supabase (contoh: `postgresql://postgres.[ref]:[pass]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres`).
   - `SECRET_KEY`: String acak aman untuk sesi Flask.
5. Klik **Deploy**.

### 3. Deploy Melalui Vercel CLI (Alternatif)
```bash
# Instal Vercel CLI jika belum ada
npm install -g vercel

# Login dan deploy
vercel

# Deploy ke production
vercel --prod
```

---

## 🐍 Penggunaan Langsung via Python SDK

Anda dapat menguji dan berinteraksi langsung dengan model AI Google Gemini menggunakan library resmi `google-genai` melalui script Python mandiri:

```python
import os
from google import genai
from dotenv import load_dotenv

# Muat environment variable dari .env
load_dotenv()

# Inisialisasi Gemini Client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def uji_gemini_smart_visitor():
    prompt = (
        "Kamu adalah Smart Visitor Assistant. Sambut tamu yang datang "
        "ke kantor dengan ramah dan tanyakan nama lengkapnya."
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        print("🤖 Respon AI:")
        print(response.text)
    except Exception as e:
        print(f"❌ Error saat memanggil Gemini API: {e}")

if __name__ == "__main__":
    uji_gemini_smart_visitor()
```

Jalankan script pengujian:
```bash
python test_gemini.py
```

---

## ⚙️ Batasan dan Catatan Teknis

1. **Timeout Serverless Function (Vercel)**
   - Vercel Serverless Free Tier memiliki batas eksekusi maksimum **10–15 detik** per request.
   - Panggilan ke Gemini AI dioptimalkan menggunakan model `gemini-2.5-flash` yang memiliki latensi rendah (*low latency*) agar tidak memicu *timeout*.
2. **Koneksi Database Cloud (PostgreSQL Connection Pooling)**
   - Pada lingkungan serverless, setiap request dapat membuat instance baru. Sangat disarankan menggunakan **Connection Pooler** Supabase (port 5432 / 6543) agar batas koneksi database tidak cepat penuh (*exhausted*).
   - Pastikan URL diawali dengan `postgresql://` (sistem `app.py` sudah menangani otomatis konversi `postgres://` ke `postgresql://`).
3. **Penanganan Batas Kuota (*Rate Limiting*) Gemini API**
   - Free Tier Google AI Studio memiliki batasan Request Per Minute (RPM).
   - Apabila kuota API terlampaui atau terjadi galat jaringan (HTTP 429/500), backend mengaktifkan mode **Fallback Deterministik** sehingga alur pendaftaran pengunjung tetap berjalan lancar tanpa *crash*.
4. **Keamanan Kredensial**
   - File `.env` telah dimasukkan ke dalam `.gitignore` dan `.vercelignore`. Jangan pernah mempublikasikan API Key atau password database ke repositori publik.

---

## 📄 Lisensi

Proyek ini dilisensikan di bawah lisensi **[MIT License](https://opensource.org/licenses/MIT)**. Anda bebas menggunakan, memodifikasi, dan mendistribusikan kode ini untuk keperluan pribadi maupun komersial.
