from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response
import mysql.connector
from datetime import datetime
import os
import csv
import io
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)

app.secret_key = os.getenv("SECRET_KEY", "smart-visitor-secret-key")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    print("[OK] Gemini AI siap digunakan.")
else:
    gemini_client = None
    print("[WARN] GEMINI_API_KEY belum ditemukan.")


def get_db_connection():
    host = os.getenv("DB_HOST", "127.0.0.1")
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "")
    database = os.getenv("DB_NAME", "visitor_management")
    port = int(os.getenv("DB_PORT", "3306"))

    conn_params = {
        "host": host,
        "user": user,
        "password": password,
        "database": database,
        "port": port,
        "connection_timeout": 5,
    }

    ssl_ca = os.getenv("DB_SSL_CA")
    if ssl_ca:
        conn_params["ssl_ca"] = ssl_ca
    elif os.getenv("DB_SSL_DISABLED", "").lower() in ("true", "1"):
        conn_params["ssl_disabled"] = True
    else:
        # TiDB Cloud dan database cloud lainnya membutuhkan SSL namun seringkali tanpa CA khusus
        conn_params["ssl_verify_cert"] = os.getenv("DB_SSL_VERIFY_CERT", "false").lower() in ("true", "1")

    return mysql.connector.connect(**conn_params)

NAMA_HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
NAMA_BULAN = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember"
]


def format_tanggal_indonesia(dt):
    hari = NAMA_HARI[dt.weekday()]
    bulan = NAMA_BULAN[dt.month - 1]
    return f"{hari}, {dt.day} {bulan} {dt.year}"

FIELD_ORDER = [
    "nama",
    "jenis_identitas",
    "nomor_identitas",
    "no_hp",
    "instansi",
    "bertemu_dengan",
    "keperluan",
    "status_kartu",
]

FIELD_QUESTIONS = {
    "nama": "Siapa nama lengkap Anda?",
    "jenis_identitas": "Identitas apa yang Anda gunakan? (KTP/SIM/NIM)",
    "nomor_identitas": "Boleh disebutkan nomor identitasnya?",
    "no_hp": "Berapa nomor HP yang bisa dihubungi?",
    "instansi": "Anda berasal dari instansi atau perusahaan mana?",
    "bertemu_dengan": "Anda ingin bertemu dengan siapa?",
    "keperluan": "Apa keperluan kunjungan Anda?",
    "status_kartu": "Apakah Anda menitipkan kartu identitas kepada petugas? (YA/TIDAK)",
}

FIELD_LABELS = {
    "nama": "Nama",
    "jenis_identitas": "Jenis Identitas",
    "nomor_identitas": "Nomor Identitas",
    "no_hp": "No HP",
    "instansi": "Instansi",
    "bertemu_dengan": "Bertemu Dengan",
    "keperluan": "Keperluan",
    "status_kartu": "Status Kartu",
}


def get_next_field(visitor_data):
    """Menentukan field berikutnya yang harus diminta, secara deterministik
    (server yang mengontrol urutan, bukan AI)."""

    for field in FIELD_ORDER:
        if not str(visitor_data.get(field, "")).strip():
            return field

    return None


def _check_nomor_identitas_format(jenis_identitas, nomor_identitas):
    """Aturan format nomor identitas berdasarkan jenisnya. Dipakai bersama
    oleh tool cek_nomor_identitas_valid (real-time check oleh AI) dan
    validate_and_clean_field (safety net server-side saat data disimpan).
    Mengembalikan (valid: bool, alasan: str)."""

    jenis = str(jenis_identitas or "").strip().upper()
    nomor = str(nomor_identitas or "").strip()

    if jenis not in ("KTP", "SIM", "NIM"):
        return False, f"Jenis identitas '{jenis_identitas}' tidak dikenali. Harus KTP, SIM, atau NIM."

    if not nomor:
        return False, "Nomor identitas kosong."

    digits_only = "".join(ch for ch in nomor if ch.isdigit())

    if jenis == "KTP":
        if len(digits_only) == 16 and digits_only == nomor.replace(" ", ""):
            return True, "Format KTP valid (16 digit)."
        return False, "Nomor KTP harus terdiri dari 16 digit angka."

    if jenis == "SIM":
        if 8 <= len(digits_only) <= 14:
            return True, "Format SIM tampak valid."
        return False, "Nomor SIM tampak tidak valid (jumlah digit tidak sesuai)."

    if jenis == "NIM":
        cleaned = nomor.replace(" ", "").replace("-", "")
        if len(cleaned) >= 5 and cleaned.isalnum():
            return True, "Format NIM tampak valid."
        return False, "NIM tampak terlalu pendek atau mengandung karakter tidak wajar."

    return False, "Tidak dapat memvalidasi jenis identitas ini."


def validate_and_clean_field(field, value, context=None):
    """Validasi satu nilai field sebelum disimpan ke session.
    `context` adalah visitor_data yang sedang berjalan, dipakai untuk
    validasi lintas-field (nomor_identitas butuh tahu jenis_identitas).
    Mengembalikan (nilai_bersih, None) jika valid,
    atau (None, alasan_penolakan) jika tidak valid."""

    context = context or {}

    if value is None:
        return None, "Nilai kosong."

    value = str(value).strip()

    if not value:
        return None, "Nilai kosong."

    if field == "jenis_identitas":
        v = value.upper()
        if v not in ("KTP", "SIM", "NIM"):
            return None, f"Jenis identitas '{value}' tidak dikenali. Harus KTP, SIM, atau NIM."
        return v, None

    if field == "no_hp":
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) < 9 or len(digits) > 15:
            return None, f"Nomor HP '{value}' tampak tidak valid."
        return value, None

    if field == "status_kartu":
        v = value.upper()
        if v in ("YA", "Y", "DITITIPKAN", "TITIP"):
            return "dititipkan", None
        if v in ("TIDAK", "TIDAK DITITIPKAN", "TIDAKDITITIPKAN", "N"):
            return "tidak_dititipkan", None
        return None, "Jawaban kartu harus YA atau TIDAK."

    if field == "nomor_identitas":
        jenis = context.get("jenis_identitas")

        if jenis:
            valid, alasan = _check_nomor_identitas_format(jenis, value)
            if not valid:
                return None, alasan
            return value, None
        if len(value) < 4:
            return None, f"Nomor identitas '{value}' tampak terlalu pendek."
        return value, None
    if len(value) < 2:
        return None, f"Nilai '{value}' tampak terlalu pendek untuk field ini."

    return value, None


def apply_visitor_updates(visitor_data, updates):
    applied = {}
    rejected = {}

    candidate_fields = [
        f for f in FIELD_ORDER if f in updates and updates[f] not in (None, "")
    ]
    ordered_fields = sorted(
        candidate_fields,
        key=lambda f: 0 if f == "jenis_identitas" else 1
    )

    for field in ordered_fields:
        cleaned, error = validate_and_clean_field(field, updates[field], visitor_data)

        if error:
            rejected[field] = error
        else:
            visitor_data[field] = cleaned
            applied[field] = cleaned

    return applied, rejected

def tool_cek_nomor_identitas_valid(args):
    jenis_identitas = args.get("jenis_identitas", "")
    nomor_identitas = args.get("nomor_identitas", "")

    valid, alasan = _check_nomor_identitas_format(jenis_identitas, nomor_identitas)

    return {
        "valid": valid,
        "alasan": alasan,
    }

def tool_cari_staff(args):
    nama = str(args.get("nama", "")).strip()

    if not nama:
        return {
            "found": False,
            "matches": [],
            "message": "Nama kosong, tidak bisa dicari."
        }

    db = None
    cursor = None

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT nama FROM staff_accounts
            WHERE nama LIKE %s
            LIMIT 5
        """, (f"%{nama}%",))

        rows = cursor.fetchall()
        matches = [row["nama"] for row in rows]

        return {
            "found": len(matches) > 0,
            "matches": matches,
            "message": (
                "Ditemukan nama yang cocok di data internal."
                if matches else
                "Tidak ditemukan nama yang cocok di data internal. "
                "Tetap bisa dilanjutkan, tapi sebaiknya konfirmasikan "
                "ejaan namanya ke pengunjung."
            )
        }

    except Exception as e:
        print("ERROR CARI STAFF (TOOL):", e)
        return {
            "found": False,
            "matches": [],
            "message": "Data staff sedang tidak bisa diperiksa saat ini."
        }

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()

def tool_simpan_data_pengunjung(visitor_data):

    missing = [
        field for field in FIELD_ORDER
        if not str(visitor_data.get(field, "")).strip()
    ]

    if missing:
        return {
            "success": False,
            "message": "Data belum lengkap, belum bisa disimpan.",
            "missing_fields": missing,
        }

    final_data = {
        "nama": visitor_data["nama"],
        "jenis_identitas": visitor_data["jenis_identitas"],
        "nomor_identitas": visitor_data["nomor_identitas"],
        "no_hp": visitor_data["no_hp"],
        "instansi": visitor_data["instansi"],
        "bertemu_dengan": visitor_data["bertemu_dengan"],
        "keperluan": visitor_data["keperluan"],
        "status_kartu": visitor_data.get("status_kartu", "tidak_dititipkan"),
    }

    ai_result = analyze_visitor_with_ai(final_data)

    if ai_result["success"]:
        ai_analysis = ai_result["analysis"]
    else:
        ai_analysis = (
            "AI tidak dapat melakukan analisis. "
            "Petugas dapat melakukan pemeriksaan manual."
        )

    db = None
    cursor = None

    try:
        db = get_db_connection()
        cursor = db.cursor()

        sql = """
            INSERT INTO visitors
            (
                nama,
                jenis_identitas,
                nomor_identitas,
                no_hp,
                instansi,
                bertemu_dengan,
                keperluan,
                check_in,
                status,
                status_kartu
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                NOW(),
                %s,
                %s
            )
        """

        values = (
            final_data["nama"],
            final_data["jenis_identitas"],
            final_data["nomor_identitas"],
            final_data["no_hp"],
            final_data["instansi"],
            final_data["bertemu_dengan"],
            final_data["keperluan"],
            "checked_in",
            final_data["status_kartu"],
        )

        cursor.execute(sql, values)
        db.commit()

        visitor_id = cursor.lastrowid

        return {
            "success": True,
            "message": "Check-in berhasil disimpan.",
            "visitor_id": visitor_id,
            "ai_analysis": ai_analysis,
        }

    except Exception as e:
        if db:
            db.rollback()

        print("ERROR SIMPAN DATA PENGUNJUNG (TOOL):", e)

        return {
            "success": False,
            "message": str(e),
        }

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


def build_tools():
    """Deklarasi seluruh tool yang tersedia untuk AI Agent check-in."""

    return types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="update_visitor_data",
                description=(
                    "Simpan satu atau lebih data pengunjung yang BARU SAJA "
                    "diberikan secara eksplisit dan jelas oleh pengunjung pada "
                    "pesan terakhirnya. Boleh mengisi beberapa field sekaligus "
                    "kalau pengunjung memang menyebutkan beberapa data valid "
                    "dalam satu kalimat. Panggil hanya untuk field yang "
                    "benar-benar disebutkan dengan valid. Jangan memanggil "
                    "untuk field yang belum jelas, belum disebutkan, atau "
                    "masih berupa pertanyaan balik dari pengunjung. Jangan "
                    "mengarang nilai."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "nama": types.Schema(
                            type=types.Type.STRING,
                            description="Nama lengkap pengunjung."
                        ),
                        "jenis_identitas": types.Schema(
                            type=types.Type.STRING,
                            enum=["KTP", "SIM", "NIM"],
                            description="Jenis identitas yang digunakan pengunjung."
                        ),
                        "nomor_identitas": types.Schema(
                            type=types.Type.STRING,
                            description="Nomor identitas sesuai jenis identitas."
                        ),
                        "no_hp": types.Schema(
                            type=types.Type.STRING,
                            description="Nomor HP pengunjung yang bisa dihubungi."
                        ),
                        "instansi": types.Schema(
                            type=types.Type.STRING,
                            description="Instansi atau perusahaan asal pengunjung."
                        ),
                        "bertemu_dengan": types.Schema(
                            type=types.Type.STRING,
                            description="Nama orang/pihak yang ingin ditemui pengunjung."
                        ),
                        "keperluan": types.Schema(
                            type=types.Type.STRING,
                            description="Keperluan atau tujuan kunjungan."
                        ),
                        "status_kartu": types.Schema(
                            type=types.Type.STRING,
                            enum=["dititipkan", "tidak_dititipkan"],
                            description="Status penitipan kartu identitas. YA = dititipkan, TIDAK = tidak_dititipkan."
                        ),
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="cek_nomor_identitas_valid",
                description=(
                    "Cek format nomor identitas terhadap jenisnya (KTP harus "
                    "16 digit, dll) SEBELUM memanggil update_visitor_data untuk "
                    "field nomor_identitas. Gunakan setiap kali pengunjung "
                    "menyebutkan nomor identitas dan jenis identitasnya sudah "
                    "atau baru saja diketahui."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "jenis_identitas": types.Schema(
                            type=types.Type.STRING,
                            enum=["KTP", "SIM", "NIM"],
                        ),
                        "nomor_identitas": types.Schema(
                            type=types.Type.STRING,
                        ),
                    },
                    required=["jenis_identitas", "nomor_identitas"],
                ),
            ),
            types.FunctionDeclaration(
                name="cari_staff",
                description=(
                    "Cari apakah nama orang yang ingin ditemui pengunjung "
                    "(bertemu_dengan) terdaftar di data internal. Gunakan "
                    "setiap kali pengunjung menyebutkan siapa yang ingin "
                    "ditemui, untuk membantu memastikan ejaan nama benar. "
                    "Ini hanya pengecekan bantu (advisory) — kalau tidak "
                    "ditemukan, tetap boleh lanjut setelah mengonfirmasi "
                    "ejaan ke pengunjung, karena tidak semua orang yang "
                    "ditemui ada di data ini."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "nama": types.Schema(type=types.Type.STRING),
                    },
                    required=["nama"],
                ),
            ),
            types.FunctionDeclaration(
                name="simpan_data_pengunjung",
                description=(
                    "Simpan data check-in pengunjung secara PERMANEN ke "
                    "database. Tidak butuh parameter — tool ini otomatis "
                    "memakai data yang sudah tersimpan dan tervalidasi lewat "
                    "update_visitor_data sebelumnya. HANYA panggil tool ini "
                    "jika SEMUA field wajib sudah terisi DAN pengunjung sudah "
                    "memberi konfirmasi eksplisit (misal 'ya', 'benar', "
                    "'lanjutkan', 'sudah sesuai') setelah kamu menampilkan "
                    "ringkasan lengkap datanya. Jangan pernah memanggil ini "
                    "tanpa ringkasan + konfirmasi eksplisit itu."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={},
                ),
            ),
        ]
    )


def build_system_instruction():
    """Instruksi sistem untuk AI Agent check-in berbasis tool calling."""

    return """
Kamu adalah Smart Visitor Assistant, AI Agent yang bertugas MEMIMPIN
seluruh proses check-in pengunjung kantor secara ramah, natural, dan
cerdas — bukan sekadar mengikuti skrip pertanyaan tetap.

=========================================================
TOOL YANG TERSEDIA
=========================================================

1. update_visitor_data
   Simpan data pengunjung ke sistem begitu kamu yakin datanya valid.

2. cek_nomor_identitas_valid
   Cek format nomor identitas SEBELUM menyimpannya lewat
   update_visitor_data.

3. cari_staff
   Cek apakah nama yang ingin ditemui pengunjung dikenal di data
   internal.

4. simpan_data_pengunjung
   Commit final ke database. Sangat sensitif, ikuti aturan ketat di
   bawah.

=========================================================
KAMU YANG MEMUTUSKAN ALUR, BUKAN URUTAN TETAP
=========================================================

1. Sistem akan memberimu daftar field yang MASIH KOSONG beserta
   pertanyaan default untuk masing-masing, dan satu field yang
   DISARANKAN untuk ditanyakan berikutnya. Itu hanya saran default —
   kamu boleh menyesuaikan urutan mengikuti alur percakapan yang
   natural.

2. Kalau pengunjung menyebutkan beberapa data sekaligus dalam satu
   kalimat (misal "nama saya Budi, saya mau ketemu Pak Andi soal
   magang"), EKSTRAK SEMUANYA sekaligus lewat satu panggilan
   update_visitor_data dengan beberapa field terisi — jangan minta
   pengunjung mengulang satu per satu.

3. Setelah itu, tanyakan field yang MASIH kosong berikutnya, pilih
   yang paling natural berdasarkan konteks percakapan (boleh ikuti
   saran default kalau tidak ada alasan lain).

4. JANGAN memanggil update_visitor_data untuk data yang belum jelas,
   meragukan, atau hanya disebutkan sekilas. Jangan mengarang nilai.

5. Jika pengunjung menyebutkan nomor identitas, panggil dulu
   cek_nomor_identitas_valid (pakai jenis_identitas yang sudah/baru
   diketahui). Kalau valid, baru panggil update_visitor_data untuk
   menyimpannya. Kalau tidak valid, sampaikan alasannya dan minta
   nomor yang benar — jangan disimpan.

6. Jika pengunjung menyebutkan siapa yang ingin ditemui
   (bertemu_dengan), panggil cari_staff untuk mengecek ejaan/keberadaan
   nama tersebut di data internal. Kalau tidak ditemukan, itu BUKAN
   alasan untuk menolak — cukup konfirmasikan ejaan ke pengunjung,
   lalu tetap simpan lewat update_visitor_data begitu pengunjung
   memastikan.

7. Jika pengunjung mengoreksi data sebelumnya, panggil
   update_visitor_data lagi untuk field itu dengan nilai yang benar.

8. Jika pengunjung bertanya sesuatu yang masih berkaitan dengan proses
   check-in, jawab singkat lalu lanjutkan proses.

9. Jika pengunjung keluar dari topik, arahkan kembali dengan sopan.

=========================================================
KAPAN MENYIMPAN PERMANEN (simpan_data_pengunjung)
=========================================================

1. Begitu SEMUA field wajib sudah terisi, TAMPILKAN RINGKASAN lengkap
   datanya ke pengunjung dan tanyakan apakah sudah benar.

2. TUNGGU pengunjung memberi konfirmasi eksplisit (misal "ya", "benar",
   "lanjutkan", "sudah sesuai").

3. Baru setelah konfirmasi itu diberikan, panggil simpan_data_pengunjung.

4. JANGAN PERNAH memanggil simpan_data_pengunjung sebelum ada
   konfirmasi eksplisit tersebut, walaupun semua data sudah lengkap.

5. Kalau simpan_data_pengunjung mengembalikan success=false karena
   data ternyata belum lengkap, minta maaf singkat dan lanjutkan
   menanyakan field yang kurang.

6. Setelah simpan_data_pengunjung berhasil, sampaikan konfirmasi
   check-in berhasil dengan ramah. Jangan mengklaim data tersimpan
   sebelum tool ini benar-benar dipanggil dan berhasil.

=========================================================
JENIS IDENTITAS
=========================================================
Yang diterima: KTP, SIM, NIM

=========================================================
PENITIPAN KARTU
=========================================================
Pertanyaan ini WAJIB ada sebelum ringkasan:
"Apakah Anda menitipkan kartu identitas kepada petugas? (YA/TIDAK)"

Jika pengunjung menjawab YA, simpan status_kartu sebagai:
"dititipkan".

Jika pengunjung menjawab TIDAK, simpan status_kartu sebagai:
"tidak_dititipkan".

Jangan melewati pertanyaan ini.

=========================================================
GAYA BICARA
=========================================================
Gunakan bahasa Indonesia. Ramah, natural, singkat, profesional.
Emoji secukupnya. Jangan berubah menjadi chatbot umum.
Balasanmu hanya berupa teks yang akan ditampilkan ke pengunjung —
jangan sertakan penjelasan proses internal atau nama tool.
"""

def analyze_visitor_with_ai(visitor_data):
    """
    AI menganalisis data pengunjung untuk membantu petugas.
    """

    if gemini_client is None:
        return {
            "success": False,
            "message": "GEMINI_API_KEY belum tersedia."
        }

    prompt = f"""
Kamu adalah Smart Visitor Assistant, AI Agent untuk membantu
petugas mengelola pengunjung kantor.

Analisis data berikut berdasarkan informasi yang benar-benar diberikan:

Nama: {visitor_data.get("nama")}
Jenis Identitas: {visitor_data.get("jenis_identitas")}
Nomor Identitas: {visitor_data.get("nomor_identitas")}
No HP: {visitor_data.get("no_hp")}
Instansi: {visitor_data.get("instansi")}
Bertemu Dengan: {visitor_data.get("bertemu_dengan")}
Keperluan: {visitor_data.get("keperluan")}
Status Kartu: {visitor_data.get("status_kartu")}

Tugas:
1. Periksa kelengkapan informasi.
2. Identifikasi hal yang perlu diperhatikan petugas.
3. Tentukan kategori:
   - AMAN
   - PERLU DIPERHATIKAN
   - PRIORITAS
4. Berikan rekomendasi singkat.

Jangan membuat informasi yang tidak diberikan.
Jangan meminta informasi sensitif tambahan.

Format:
STATUS: [AMAN/PERLU DIPERHATIKAN/PRIORITAS]

RINGKASAN:
[ringkasan singkat]

PERHATIAN:
[hal yang perlu diperhatikan, jika ada]

REKOMENDASI:
[tindakan yang disarankan]

Gunakan bahasa Indonesia yang singkat dan mudah dipahami.
"""

    try:
        response = gemini_client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt
        )

        return {
            "success": True,
            "analysis": response.text
        }

    except Exception as e:
        print("ERROR GEMINI:", e)

        return {
            "success": False,
            "message": f"Gagal menghubungi AI: {str(e)}"
        }


@app.route("/")
def index():
    return render_template("index.html")



@app.route("/checkin")
def checkin():
    return render_template("checkin.html")



# FALLBACK CHECK-IN
# Dipakai hanya saat Gemini mengembalikan 429/rate limit.
# Proses tetap deterministik dan tidak mengarang data.

def fallback_checkin_response(message):
    visitor_data = session.get("visitor_data", {})
    message_clean = str(message or "").strip()

    missing = [
        f for f in FIELD_ORDER
        if not str(visitor_data.get(f, "")).strip()
    ]

    # Semua data sudah lengkap -> tunggu konfirmasi.
    if not missing and session.get("checkin_confirm_pending"):
        normalized = message_clean.lower()
        confirm_words = (
            "ya", "iya", "y", "benar", "betul",
            "lanjut", "lanjutkan", "konfirmasi",
            "sudah benar", "sudah sesuai"
        )

        if any(word in normalized for word in confirm_words):
            result = tool_simpan_data_pengunjung(visitor_data)

            if result.get("success"):
                name = visitor_data.get("nama", "")
                session.pop("visitor_data", None)
                session.pop("conversation", None)
                session.pop("checkin_confirm_pending", None)

                return {
                    "success": True,
                    "reply": (
                        "🎉 <b>Check-In Berhasil!</b><br><br>"
                        f"Selamat datang, <b>{name}</b>.<br><br>"
                        "Data kunjungan Anda telah dicatat.<br>"
                        "Silakan tunggu petugas untuk proses kartu identitas."
                    ),
                    "visitor_data": visitor_data,
                    "completed": True,
                    "finalized": True,
                    "visitor_id": result.get("visitor_id"),
                    "ai_analysis": result.get("ai_analysis"),
                    "applied_fields": visitor_data,
                    "rejected_fields": {},
                }

        return {
            "success": True,
            "reply": "Baik. Silakan pilih <b>Ya, Check-In</b> jika semua data sudah benar.",
            "visitor_data": visitor_data,
            "completed": True,
            "finalized": False,
            "applied_fields": {},
            "rejected_fields": {},
        }

    next_field = missing[0]
    cleaned, error = validate_and_clean_field(next_field, message_clean, visitor_data)

    if error:
        return {
            "success": True,
            "reply": (
                f"⚠️ {error}<br><br>"
                f"{FIELD_QUESTIONS.get(next_field, 'Silakan coba lagi.')}"
            ),
            "visitor_data": visitor_data,
            "next_field": next_field,
            "next_question": FIELD_QUESTIONS.get(next_field, ""),
            "completed": False,
            "finalized": False,
            "applied_fields": {},
            "rejected_fields": {next_field: error},
        }

    visitor_data[next_field] = cleaned
    session["visitor_data"] = visitor_data

    remaining = [
        f for f in FIELD_ORDER
        if not str(visitor_data.get(f, "")).strip()
    ]

    if remaining:
        next_field = remaining[0]
        return {
            "success": True,
            "reply": FIELD_QUESTIONS[next_field],
            "visitor_data": visitor_data,
            "next_field": next_field,
            "next_question": FIELD_QUESTIONS[next_field],
            "completed": False,
            "finalized": False,
            "applied_fields": {next_field: cleaned},
            "rejected_fields": {},
        }

    session["checkin_confirm_pending"] = True

    status_text = (
        "Dititipkan"
        if visitor_data.get("status_kartu") == "dititipkan"
        else "Tidak dititipkan"
    )

    reply = (
        "✅ Semua data sudah lengkap.<br><br>"
        "Silakan periksa ringkasan di bawah. "
        "Apakah semua data sudah benar?"
    )

    return {
        "success": True,
        "reply": reply,
        "visitor_data": visitor_data,
        "completed": True,
        "finalized": False,
        "applied_fields": {next_field: cleaned},
        "rejected_fields": {},
    }


@app.route("/ask_ai", methods=["POST"])
def ask_ai():

    try:
        data = request.get_json() or {}
        message = str(data.get("message", "")).strip()

        if gemini_client is None:
            print("[WARN] Gemini API tidak tersedia. Menggunakan fallback check-in.")
            return jsonify(fallback_checkin_response(message))

        if not message:
            return jsonify({
                "success": False,
                "message": "Pesan tidak boleh kosong."
            }), 400


        visitor_data = session.get("visitor_data", {})
        history = session.get("conversation", [])

        missing_fields = [
            f for f in FIELD_ORDER if not str(visitor_data.get(f, "")).strip()
        ]
        suggested_next_field = missing_fields[0] if missing_fields else None

        filled_lines = [
            f"{FIELD_LABELS.get(f, f)}: {visitor_data[f]}"
            for f in FIELD_ORDER
            if str(visitor_data.get(f, "")).strip()
        ]
        filled_data_text = "\n".join(filled_lines) if filled_lines else "Belum ada data yang tersimpan."

        if missing_fields:
            missing_lines = "\n".join(
                f"- {f}: {FIELD_QUESTIONS.get(f, '')}" for f in missing_fields
            )
        else:
            missing_lines = "(tidak ada, semua field wajib sudah terisi)"

        prompt_context = f"""
=========================================================
STATUS SISTEM SAAT INI
=========================================================

Data yang sudah diketahui:
{filled_data_text}

Field yang masih kosong (urutan default, boleh kamu sesuaikan):
{missing_lines}

Field yang disarankan untuk ditanyakan berikutnya: {suggested_next_field or "(tidak ada)"}
"""


        contents = []

        for turn in history[-12:]:
            role = "model" if turn.get("role") == "assistant" else "user"
            text = turn.get("content", "")

            if text:
                contents.append(
                    types.Content(role=role, parts=[types.Part(text=text)])
                )

        contents.append(
            types.Content(
                role="user",
                parts=[types.Part(text=f"{prompt_context}\n\nPesan pengunjung:\n{message}")]
            )
        )

        config = types.GenerateContentConfig(
            system_instruction=build_system_instruction(),
            tools=[build_tools()],
        )

        MAX_TOOL_ITERATIONS = 6

        applied_all = {}
        rejected_all = {}
        finalize_result = None
        reply = ""

        for _ in range(MAX_TOOL_ITERATIONS):

            response = gemini_client.models.generate_content(
                model="gemini-3.6-flash",
                contents=contents,
                config=config
            )

            candidate = response.candidates[0]
            parts = candidate.content.parts or []

            function_calls = [
                p.function_call for p in parts if getattr(p, "function_call", None)
            ]

            if not function_calls:
                reply = (response.text or "").strip()
                break

            contents.append(candidate.content)

            function_response_parts = []

            for fc in function_calls:
                try:
                    args = dict(fc.args) if fc.args else {}
                except Exception:
                    args = {}

                if fc.name == "update_visitor_data":
                    applied, rejected = apply_visitor_updates(visitor_data, args)
                    applied_all.update(applied)
                    rejected_all.update(rejected)
                    session["visitor_data"] = visitor_data
                    result = {"applied": applied, "rejected": rejected}

                elif fc.name == "cek_nomor_identitas_valid":
                    result = tool_cek_nomor_identitas_valid(args)

                elif fc.name == "cari_staff":
                    result = tool_cari_staff(args)

                elif fc.name == "simpan_data_pengunjung":
                    result = tool_simpan_data_pengunjung(visitor_data)
                    if result.get("success"):
                        finalize_result = result

                else:
                    result = {"error": f"Tool '{fc.name}' tidak dikenal."}

                function_response_parts.append(
                    types.Part.from_function_response(
                        name=fc.name,
                        response=result
                    )
                )

            contents.append(
                types.Content(role="user", parts=function_response_parts)
            )

        if not reply:
            reply = "Baik, mohon lanjutkan ya 😊"


        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": reply})

        if finalize_result:
            # Check-in sudah dikomit ke DB oleh AI sendiri lewat tool.
            # Sesi dibersihkan supaya percakapan berikutnya mulai dari nol.
            session.pop("visitor_data", None)
            session.pop("conversation", None)

            return jsonify({
                "success": True,
                "reply": reply,
                "visitor_data": visitor_data,
                "completed": True,
                "finalized": True,
                "visitor_id": finalize_result.get("visitor_id"),
                "ai_analysis": finalize_result.get("ai_analysis"),
                "applied_fields": applied_all,
                "rejected_fields": rejected_all,
            })

        session["conversation"] = history[-20:]

        new_missing = [
            f for f in FIELD_ORDER if not str(visitor_data.get(f, "")).strip()
        ]
        new_next_field = new_missing[0] if new_missing else None

        return jsonify({
            "success": True,
            "reply": reply,
            "visitor_data": visitor_data,
            "next_field": new_next_field,
            "next_question": FIELD_QUESTIONS.get(new_next_field, "") if new_next_field else "",
            "completed": new_next_field is None,
            "finalized": False,
            "applied_fields": applied_all,
            "rejected_fields": rejected_all,
        })

    except Exception as e:

        error_text = str(e)
        print("ERROR AI:", error_text)

        if (
            "429" in error_text
            or "RESOURCE_EXHAUSTED" in error_text
            or "quota" in error_text.lower()
            or "rate limit" in error_text.lower()
        ):
            print("[WARN] Gemini quota/rate limit. Menggunakan fallback check-in.")
            return jsonify(fallback_checkin_response(message))

        return jsonify({
            "success": False,
            "message": error_text
        }), 500


@app.route("/api/checkin/state", methods=["GET"])
def checkin_state():

    visitor_data = session.get("visitor_data", {})
    next_field = get_next_field(visitor_data)

    return jsonify({
        "success": True,
        "visitor_data": visitor_data,
        "next_field": next_field,
        "next_question": FIELD_QUESTIONS.get(next_field, "") if next_field else "",
        "completed": next_field is None,
    })


@app.route("/api/checkin/reset", methods=["POST"])
def checkin_reset():

    session.pop("visitor_data", None)
    session.pop("conversation", None)

    return jsonify({
        "success": True,
        "message": "Sesi check-in direset."
    })

@app.route("/save_checkin", methods=["POST"])
def save_checkin():

    db = None
    cursor = None

    try:
        data = request.get_json() or {}

        required_fields = [
            "nama",
            "jenis_identitas",
            "nomor_identitas",
            "no_hp",
            "instansi",
            "bertemu_dengan",
            "keperluan",
            "status_kartu"
        ]

        for field in required_fields:
            if not str(data.get(field, "")).strip():
                return jsonify({
                    "success": False,
                    "message": f"Data '{field}' belum lengkap."
                }), 400

        visitor_data = {
    "nama": data.get("nama"),
    "jenis_identitas": data.get("jenis_identitas"),
    "nomor_identitas": data.get("nomor_identitas"),
    "no_hp": data.get("no_hp"),
    "instansi": data.get("instansi"),
    "bertemu_dengan": data.get("bertemu_dengan"),
    "keperluan": data.get("keperluan"),
    "status_kartu": "dititipkan"
}

        # AI menganalisis sebelum data disimpan.
        ai_result = analyze_visitor_with_ai(visitor_data)

        if ai_result["success"]:
            ai_analysis = ai_result["analysis"]
        else:
            ai_analysis = (
                "AI tidak dapat melakukan analisis. "
                "Petugas dapat melakukan pemeriksaan manual."
            )

        db = get_db_connection()
        cursor = db.cursor()

        sql = """
            INSERT INTO visitors
            (
                nama,
                jenis_identitas,
                nomor_identitas,
                no_hp,
                instansi,
                bertemu_dengan,
                keperluan,
                check_in,
                status,
                status_kartu
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                NOW(),
                %s,
                %s
            )
        """

        values = (
            visitor_data["nama"],
            visitor_data["jenis_identitas"],
            visitor_data["nomor_identitas"],
            visitor_data["no_hp"],
            visitor_data["instansi"],
            visitor_data["bertemu_dengan"],
            visitor_data["keperluan"],
            "checked_in",
            visitor_data["status_kartu"]
        )

        cursor.execute(sql, values)
        db.commit()

        visitor_id = cursor.lastrowid

        return jsonify({
            "success": True,
            "message": "Check-in berhasil.",
            "visitor_id": visitor_id,
            "ai_analysis": ai_analysis
        })

    except Exception as e:
        if db:
            db.rollback()

        print("ERROR CHECK-IN:", e)

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


@app.route("/finalisasi_checkin", methods=["POST"])
def finalisasi_checkin():
    """Fallback manual: melakukan hal yang PERSIS SAMA dengan tool
    simpan_data_pengunjung yang biasanya dipanggil AI sendiri. Berguna
    sebagai jaring pengaman kalau frontend masih ingin menyediakan
    tombol konfirmasi eksplisit, atau AI gagal memanggil tool-nya."""

    try:
        visitor_data = session.get("visitor_data", {})

        result = tool_simpan_data_pengunjung(visitor_data)

        if not result.get("success"):
            status_code = 400 if "missing_fields" in result else 500
            return jsonify({
                "success": False,
                "message": result.get("message", "Gagal menyimpan data."),
                "missing_fields": result.get("missing_fields", []),
            }), status_code

        session.pop("visitor_data", None)
        session.pop("conversation", None)

        return jsonify({
            "success": True,
            "message": "Check-in berhasil difinalisasi.",
            "visitor_id": result.get("visitor_id"),
            "ai_analysis": result.get("ai_analysis"),
        })

    except Exception as e:
        print("ERROR FINALISASI CHECKIN:", e)

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@app.route("/ai/analyze", methods=["POST"])
def ai_analyze():

    try:
        data = request.get_json() or {}

        if not data:
            return jsonify({
                "success": False,
                "message": "Data tidak ditemukan."
            }), 400

        result = analyze_visitor_with_ai(data)

        return jsonify(result)

    except Exception as e:
        print("ERROR AI ANALYZE:", e)

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@app.route("/checkout")
def checkout_page():
    return render_template("checkout.html")



@app.route("/api/visitor/<nomor_identitas>")
def get_visitor_for_checkout(nomor_identitas):

    db = None
    cursor = None

    try:

        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                id,
                nama,
                nomor_identitas,
                instansi,
                bertemu_dengan,
                keperluan,
                check_in,
                status,
                status_kartu
            FROM visitors
            WHERE nomor_identitas = %s
            AND status = 'checked_in'
            LIMIT 1
        """, (nomor_identitas,))

        visitor = cursor.fetchone()

        if not visitor:

            return jsonify({
                "success": False,
                "message": "Pengunjung tidak ditemukan atau sudah melakukan check-out."
            }), 404

        if visitor["check_in"]:
            visitor["check_in"] = visitor["check_in"].strftime(
                "%d/%m/%Y %H:%M"
            )

        return jsonify({
            "success": True,
            "visitor": visitor
        })

    except Exception as e:

        print("ERROR CARI CHECKOUT:", e)

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()

@app.route("/checkout/<int:visitor_id>", methods=["POST"])
def checkout(visitor_id):

    db = None
    cursor = None

    try:
        db = get_db_connection()
        cursor = db.cursor()

        sql = """
            UPDATE visitors
            SET
                check_out = NOW(),
                status = 'checked_out',
                status_kartu = 'dikembalikan'
            WHERE id = %s
            AND status = 'checked_in'
        """

        cursor.execute(sql, (visitor_id,))
        db.commit()

        if cursor.rowcount == 0:
            return jsonify({
                "success": False,
                "message": "Pengunjung tidak ditemukan atau sudah check-out."
            }), 400

        return jsonify({
            "success": True,
            "message": "Check-out berhasil."
        })

    except Exception as e:
        if db:
            db.rollback()

        print("ERROR CHECKOUT:", e)

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "GET":
        return render_template("login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if not username or not password:
        return render_template(
            "login.html",
            error="Username dan password wajib diisi."
        )

    db = None
    cursor = None

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT id, nama, username, password, role
            FROM staff_accounts
            WHERE username = %s
        """, (username,))

        staff = cursor.fetchone()

        if not staff:
            return render_template(
                "login.html",
                error="Username atau password salah."
            )

        # Untuk sementara password masih plaintext
        if password != staff["password"]:
            return render_template(
                "login.html",
                error="Username atau password salah."
            )

        # Simpan data petugas ke session
        session["staff_id"] = staff["id"]
        session["staff_nama"] = staff["nama"]
        session["staff_username"] = staff["username"]
        session["staff_role"] = staff["role"]

        return redirect(url_for("staff"))

    except Exception as e:

        print("ERROR LOGIN:", e)

        return render_template(
            "login.html",
            error="Terjadi kesalahan saat login."
        ), 500

    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))

@app.route("/staff/notifications")
def staff_notifications():

    # Cek apakah petugas sudah login
    if "staff_id" not in session:
        return redirect(url_for("login"))

    db = None
    cursor = None
    notifications = []

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        # Ambil pengunjung yang masih berada di kantor
        cursor.execute("""
            SELECT
                id,
                nama,
                check_in,
                status,
                status_kartu
            FROM visitors
            WHERE status = 'checked_in'
            ORDER BY check_in ASC
        """)

        visitors = cursor.fetchall()

        sekarang = datetime.now()

        for visitor in visitors:

            # Pastikan ada waktu check-in
            if visitor["check_in"]:

                durasi = sekarang - visitor["check_in"]

                # Jika sudah 8 jam atau lebih
                if durasi.total_seconds() >= 8 * 60 * 60:

                    notifications.append({
                        "type": "warning",
                        "icon": "⚠️",
                        "title": "Pengunjung berada terlalu lama",
                        "message": (
                            f'{visitor["nama"]} sudah berada di kantor '
                            f'lebih dari 8 jam dan belum melakukan check-out.'
                        ),
                        "time": visitor["check_in"]
                    })

            # Jika kartu masih dititipkan
            if visitor["status_kartu"] == "dititipkan":

                notifications.append({
                    "type": "card",
                    "icon": "💳",
                    "title": "Kartu pengunjung masih dititipkan",
                    "message": (
                        f'Kartu milik {visitor["nama"]} '
                        f'masih tercatat sebagai dititipkan.'
                    ),
                    "time": visitor["check_in"]
                })

        return render_template(
            "staff_notifications.html",
            notifications=notifications,
            staff_nama=session.get("staff_nama"),
            staff_username=session.get("staff_username")
        )

    except Exception as e:

        print("ERROR STAFF NOTIFICATIONS:", e)

        return f"""
        <h2>Terjadi Error pada Notifikasi</h2>
        <p>{e}</p>
        """, 500

    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


@app.route("/api/notifications/count")
def notification_count():

    if "staff_id" not in session:
        return jsonify({
            "success": False,
            "count": 0
        }), 401

    db = None
    cursor = None

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM visitors
            WHERE status = 'checked_in'
            AND check_in <= DATE_SUB(NOW(), INTERVAL 8 HOUR)
        """)

        result = cursor.fetchone()

        return jsonify({
            "success": True,
            "count": result["total"]
        })

    except Exception as e:

        print("ERROR NOTIFICATION COUNT:", e)

        return jsonify({
            "success": False,
            "count": 0
        }), 500

    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


@app.route("/staff")
def staff():

    # Cek apakah petugas sudah login
    if "staff_id" not in session:
        return redirect(url_for("login"))

    db = None
    cursor = None

    try:

        db = get_db_connection()

        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                id,
                nama,
                jenis_identitas,
                nomor_identitas,
                no_hp,
                instansi,
                bertemu_dengan,
                keperluan,
                check_in,
                check_out,
                status,
                status_kartu
            FROM visitors
            ORDER BY check_in DESC, id DESC
        """)

        visitors = cursor.fetchall()

        sedang_di_kantor = 0
        kartu_dititipkan = 0
        perlu_diperhatikan = 0

        sekarang = datetime.now()

        for visitor in visitors:


            if visitor["status"] == "checked_in":

                sedang_di_kantor += 1

                if visitor["check_in"]:

                    durasi = sekarang - visitor["check_in"]

                    if durasi.total_seconds() >= 8 * 60 * 60:

                        visitor["peringatan_lama"] = True

                        perlu_diperhatikan += 1

                    else:

                        visitor["peringatan_lama"] = False

                else:

                    visitor["peringatan_lama"] = False

            else:

                visitor["peringatan_lama"] = False


            if visitor["status_kartu"] == "dititipkan":

                kartu_dititipkan += 1


            if visitor["check_in"]:
                visitor["tanggal_key"] = visitor["check_in"].strftime("%Y-%m-%d")
                visitor["tanggal_label"] = format_tanggal_indonesia(visitor["check_in"])
            else:
                visitor["tanggal_key"] = "tidak-diketahui"
                visitor["tanggal_label"] = "Tanggal tidak diketahui"

        return render_template(
            "staff.html",
            visitors=visitors,
            sedang_di_kantor=sedang_di_kantor,
            kartu_dititipkan=kartu_dititipkan,
            perlu_diperhatikan=perlu_diperhatikan,
            staff_nama=session.get("staff_nama"),
            staff_username=session.get("staff_username")
        )


    except Exception as e:

        print("ERROR STAFF:", e)

        return f"""
        <h2>Terjadi Error pada Dashboard</h2>
        <p>{e}</p>
        """, 500


    finally:

        if cursor:

            cursor.close()

        if db:

            db.close()


@app.route("/staff/profile")
def staff_profile():

    # Cek login
    if "staff_id" not in session:
        return redirect(url_for("login"))

    return render_template(
        "staff_profile.html",
        staff_nama=session.get("staff_nama"),
        staff_username=session.get("staff_username"),
        staff_role=session.get("staff_role", "petugas")
    )

@app.route("/staff/profile/edit", methods=["GET", "POST"])
def staff_profile_edit():

    if "staff_id" not in session:
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template(
            "staff_profile_edit.html",
            staff_nama=session.get("staff_nama"),
            staff_username=session.get("staff_username"),
            staff_role=session.get("staff_role", "petugas")
        )

    nama_baru = request.form.get("nama", "").strip()

    if not nama_baru:
        return render_template(
            "staff_profile_edit.html",
            staff_nama=session.get("staff_nama"),
            staff_username=session.get("staff_username"),
            staff_role=session.get("staff_role", "petugas"),
            error="Nama lengkap tidak boleh kosong."
        )

    db = None
    cursor = None

    try:
        db = get_db_connection()
        cursor = db.cursor()

        cursor.execute("""
            UPDATE staff_accounts
            SET nama = %s
            WHERE id = %s
        """, (nama_baru, session["staff_id"]))

        db.commit()

        # Perbarui session supaya langsung terlihat di seluruh halaman
        session["staff_nama"] = nama_baru

        return redirect(url_for("staff_profile"))

    except Exception as e:

        if db:
            db.rollback()

        print("ERROR EDIT PROFIL:", e)

        return render_template(
            "staff_profile_edit.html",
            staff_nama=session.get("staff_nama"),
            staff_username=session.get("staff_username"),
            staff_role=session.get("staff_role", "petugas"),
            error="Terjadi kesalahan saat menyimpan perubahan."
        ), 500

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


@app.route("/staff/profile/password", methods=["GET", "POST"])
def staff_profile_password():

    if "staff_id" not in session:
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template(
            "staff_change_password.html",
            staff_nama=session.get("staff_nama"),
            staff_username=session.get("staff_username")
        )

    password_lama = request.form.get("password_lama", "").strip()
    password_baru = request.form.get("password_baru", "").strip()
    konfirmasi_password = request.form.get("konfirmasi_password", "").strip()

    if not password_lama or not password_baru or not konfirmasi_password:
        return render_template(
            "staff_change_password.html",
            staff_nama=session.get("staff_nama"),
            staff_username=session.get("staff_username"),
            error="Semua kolom wajib diisi."
        )

    if password_baru != konfirmasi_password:
        return render_template(
            "staff_change_password.html",
            staff_nama=session.get("staff_nama"),
            staff_username=session.get("staff_username"),
            error="Konfirmasi password baru tidak cocok."
        )

    if len(password_baru) < 6:
        return render_template(
            "staff_change_password.html",
            staff_nama=session.get("staff_nama"),
            staff_username=session.get("staff_username"),
            error="Password baru minimal 6 karakter."
        )

    db = None
    cursor = None

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT password FROM staff_accounts WHERE id = %s
        """, (session["staff_id"],))

        staff = cursor.fetchone()

        if not staff or password_lama != staff["password"]:
            return render_template(
                "staff_change_password.html",
                staff_nama=session.get("staff_nama"),
                staff_username=session.get("staff_username"),
                error="Password lama tidak sesuai."
            )

        cursor.execute("""
            UPDATE staff_accounts
            SET password = %s
            WHERE id = %s
        """, (password_baru, session["staff_id"]))

        db.commit()

        return render_template(
            "staff_change_password.html",
            staff_nama=session.get("staff_nama"),
            staff_username=session.get("staff_username"),
            success="Password berhasil diubah."
        )

    except Exception as e:

        if db:
            db.rollback()

        print("ERROR GANTI PASSWORD:", e)

        return render_template(
            "staff_change_password.html",
            staff_nama=session.get("staff_nama"),
            staff_username=session.get("staff_username"),
            error="Terjadi kesalahan saat mengubah password."
        ), 500

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()

@app.route("/staff/laporan")
def staff_laporan():

    if "staff_id" not in session:
        return redirect(url_for("login"))

    db = None
    cursor = None

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS total FROM visitors")
        total_kunjungan = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total FROM visitors
            WHERE status = 'checked_out'
        """)
        sudah_checkout = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total FROM visitors
            WHERE status = 'checked_in'
        """)
        masih_di_kantor = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total FROM visitors
            WHERE status_kartu = 'dititipkan'
        """)
        kartu_dititipkan = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT
                DATE(check_in) AS tanggal,
                COUNT(*) AS jumlah
            FROM visitors
            WHERE check_in IS NOT NULL
            GROUP BY DATE(check_in)
            ORDER BY tanggal DESC
            LIMIT 30
        """)
        kunjungan_per_tanggal = cursor.fetchall()

        jumlah_max = max(
            [row["jumlah"] for row in kunjungan_per_tanggal],
            default=0
        )

        for row in kunjungan_per_tanggal:
            if jumlah_max > 0:
                row["persen"] = round(
                    (row["jumlah"] / jumlah_max) * 100
                )
            else:
                row["persen"] = 0

        return render_template(
            "laporan.html",
            total_kunjungan=total_kunjungan,
            sudah_checkout=sudah_checkout,
            masih_di_kantor=masih_di_kantor,
            kartu_dititipkan=kartu_dititipkan,
            kunjungan_per_tanggal=kunjungan_per_tanggal,
            staff_nama=session.get("staff_nama"),
            staff_username=session.get("staff_username")
        )

    except Exception as e:

        print("ERROR LAPORAN:", e)

        return f"""
        <h2>Terjadi Error pada Laporan</h2>
        <p>{e}</p>
        """, 500

    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


@app.route("/staff/laporan/download")
def staff_laporan_download():

    if "staff_id" not in session:
        return redirect(url_for("login"))

    db = None
    cursor = None

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS total FROM visitors")
        total_kunjungan = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total FROM visitors
            WHERE status = 'checked_out'
        """)
        sudah_checkout = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total FROM visitors
            WHERE status = 'checked_in'
        """)
        masih_di_kantor = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total FROM visitors
            WHERE status_kartu = 'dititipkan'
        """)
        kartu_dititipkan = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT
                DATE(check_in) AS tanggal,
                COUNT(*) AS jumlah
            FROM visitors
            WHERE check_in IS NOT NULL
            GROUP BY DATE(check_in)
            ORDER BY tanggal DESC
        """)
        kunjungan_per_tanggal = cursor.fetchall()

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(["LAPORAN KUNJUNGAN - SMART VISITOR"])
        writer.writerow([
            "Dicetak pada",
            datetime.now().strftime("%d/%m/%Y %H:%M")
        ])
        writer.writerow([])

        writer.writerow(["RINGKASAN"])
        writer.writerow(["Total Kunjungan", total_kunjungan])
        writer.writerow(["Sudah Check-Out", sudah_checkout])
        writer.writerow(["Masih di Kantor", masih_di_kantor])
        writer.writerow(["Kartu Dititipkan", kartu_dititipkan])
        writer.writerow([])

        writer.writerow(["KUNJUNGAN PER TANGGAL"])
        writer.writerow(["Tanggal", "Jumlah Kunjungan"])

        for row in kunjungan_per_tanggal:
            writer.writerow([
                row["tanggal"].strftime("%d/%m/%Y"),
                row["jumlah"]
            ])

        csv_data = "\ufeff" + output.getvalue()

        filename = (
            "laporan-kunjungan-"
            + datetime.now().strftime("%Y-%m-%d")
            + ".csv"
        )

        return Response(
            csv_data,
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except Exception as e:

        print("ERROR DOWNLOAD LAPORAN:", e)

        return f"""
        <h2>Gagal membuat file laporan</h2>
        <p>{e}</p>
        """, 500

    finally:

        if cursor:
            cursor.close()

        if db:
            db.close()


@app.errorhandler(mysql.connector.Error)
def handle_db_error(e):
    return (
        f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 650px; margin: 50px auto; padding: 24px; border: 1px solid #fed7d7; border-radius: 12px; background: #fff5f5; color: #2d3748; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
            <h2 style="color: #e53e3e; margin-top: 0;">⚠️ Koneksi Database Gagal</h2>
            <p>Aplikasi Smart Visitor tidak dapat terhubung ke database MySQL.</p>
            <div style="background: #fff; padding: 12px; border-radius: 6px; border: 1px solid #feb2b2; font-family: monospace; font-size: 13px; color: #c53030; word-break: break-all; margin: 15px 0;">
                {e}
            </div>
            <hr style="border: none; border-top: 1px solid #fed7d7; margin: 20px 0;">
            <h3 style="font-size: 16px; margin-bottom: 8px;">Langkah Konfigurasi di Vercel:</h3>
            <ol style="font-size: 14px; line-height: 1.8; padding-left: 20px;">
                <li>Pastikan database MySQL cloud aktif (misal: <strong>TiDB Cloud Serverless</strong> atau <strong>Aiven MySQL</strong>).</li>
                <li>Import skema tabel menggunakan file <code>schema.sql</code> yang tersedia di repositori.</li>
                <li>Buka dashboard Vercel Anda: <strong>Project &gt; Settings &gt; Environment Variables</strong>, lalu tambahkan:
                    <ul style="margin-top: 6px;">
                        <li><code>DB_HOST</code> : host database cloud Anda</li>
                        <li><code>DB_USER</code> : username database</li>
                        <li><code>DB_PASSWORD</code> : password database</li>
                        <li><code>DB_NAME</code> : visitor_management</li>
                        <li><code>DB_PORT</code> : 3306 (atau port database cloud Anda)</li>
                        <li><code>GEMINI_API_KEY</code> : API Key Google Gemini Anda</li>
                    </ul>
                </li>
                <li>Redeploy aplikasi di Vercel setelah variabel disimpan.</li>
            </ol>
        </div>
        """,
        500,
    )


if __name__ == "__main__":
    app.run(debug=True)