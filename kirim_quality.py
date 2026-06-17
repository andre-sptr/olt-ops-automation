import os
import time
from datetime import datetime

try:
    import gspread
except ModuleNotFoundError:
    gspread = None

try:
    import requests
except ModuleNotFoundError:
    requests = None

try:
    from oauth2client.service_account import ServiceAccountCredentials
except ModuleNotFoundError:
    ServiceAccountCredentials = None


# ================== KONFIGURASI ==================
# Sheet dibaca via Service Account (gspread). Sheet harus di-share ke email
# service account (lihat client_email di kunci_rahasia_google.json) min. Viewer.
SPREADSHEET_ID = "1nFIBj5EjoyQxjcLAYF0kfnEN_5wKUsNvp03stW7csUw"
GID_SHEET = 1416909766
FILE_KREDENSIAL = "kunci_rahasia_google.json"

WAHA_URL = "https://waha-dutxvo095iqn.cgk-lab.sumopod.my.id"
WAHA_SESSION = "OLTReport"
WAHA_API_KEY = "ROpWNPkTUavqEbnz5zKU4mTiL0HIZoye"
GROUP_ID_TUJUAN = "120363422960378808@g.us"

FOLDER_LOG = "logs"

# Header ada di baris 1, jadi data tiket mulai dari baris 2.
DATA_START_ROW = 2
STATUS_OPEN = "OPEN"

# Pemetaan kolom (huruf kolom Google Sheet).
KOLOM = {
    "district": "B",
    "site_id": "C",
    "incident": "D",
    "status": "K",   # STATUS LAPANGAN (filter == OPEN)
    "progres": "Q",  
    "plan": "P",     
}

# Hanya district berikut yang diproses, sekaligus urutan kirim bubble-nya.
# Nilai dinormalisasi (kapital, tanpa spasi) sehingga "BUKIT TINGGI" dan
# "BUKITTINGGI" sama-sama lolos.
DISTRICT_URUTAN = ["PEKANBARU", "DUMAI", "BATAM", "PADANG", "BUKITTINGGI"]
DISTRICT_DIIZINKAN = set(DISTRICT_URUTAN)

JUDUL_PESAN = "*Tiket Quality Open*"
GARIS = "=" * 12  # garis di bawah judul "Branch <District>"
JEDA_KIRIM = 2    # jeda detik antar pengiriman bubble per district
# =================================================


def tanggal_hari_ini():
    return datetime.now().strftime("%Y-%m-%d")


def nama_file_log():
    return os.path.join(FOLDER_LOG, "quality_log.txt")


def catat_log(pesan):
    """Mencatat log dengan fitur auto-reset jika masuk hari baru."""
    waktu = datetime.now().strftime("%H:%M:%S")
    tanggal_sekarang = tanggal_hari_ini()
    pesan_log = f"[{waktu}] {pesan}"
    print(pesan_log)

    os.makedirs(FOLDER_LOG, exist_ok=True)
    file_log = nama_file_log()
    mode = "a"
    if os.path.exists(file_log):
        timestamp_modifikasi = os.path.getmtime(file_log)
        tanggal_modifikasi = datetime.fromtimestamp(timestamp_modifikasi).strftime("%Y-%m-%d")
        if tanggal_modifikasi != tanggal_sekarang:
            mode = "w"

    with open(file_log, mode, encoding="utf-8") as f:
        if mode == "w":
            f.write(f"=== Log Hari Ini: {tanggal_sekarang} ===\n")
        f.write(pesan_log + "\n")


def kolom_ke_indeks(huruf):
    if not isinstance(huruf, str):
        raise ValueError(f"Kolom tidak valid: {huruf!r}")

    label = huruf.strip().upper()
    if not label or any(karakter < "A" or karakter > "Z" for karakter in label):
        raise ValueError(f"Kolom tidak valid: {huruf!r}")

    hasil = 0
    for karakter in label:
        hasil = hasil * 26 + (ord(karakter) - ord("A") + 1)
    return hasil - 1


def normalisasi_distrik(nama):
    return str(nama or "").strip().upper().replace(" ", "")


def nama_distrik_tampil(distrik_norm):
    mapping = {
        "BATAM": "Batam",
        "PEKANBARU": "Pekanbaru",
        "DUMAI": "Dumai",
        "BUKITTINGGI": "Bukittinggi",
        "PADANG": "Padang",
    }
    return mapping.get(distrik_norm, str(distrik_norm).title())


def nilai_cell(semua_nilai, row_idx, col_idx):
    if row_idx < 0 or row_idx >= len(semua_nilai):
        return ""
    row = semua_nilai[row_idx]
    if col_idx < 0 or col_idx >= len(row):
        return ""
    return str(row[col_idx]).strip()


def isi_atau_strip(nilai):
    """Kembalikan nilai apa adanya, atau '-' kalau kosong."""
    return nilai if nilai else "-"


def buka_worksheet():
    missing = []
    if gspread is None:
        missing.append("gspread")
    if ServiceAccountCredentials is None:
        missing.append("oauth2client.service_account.ServiceAccountCredentials")
    if missing:
        pesan = "Dependency Google Sheet belum tersedia: " + ", ".join(missing)
        catat_log(pesan)
        raise RuntimeError(pesan)

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(FILE_KREDENSIAL, scope)
    client_gs = gspread.authorize(creds)
    spreadsheet = client_gs.open_by_key(SPREADSHEET_ID)
    return spreadsheet.get_worksheet_by_id(GID_SHEET)


def ambil_semua_nilai():
    """Ambil seluruh isi sheet sebagai list-of-list lewat Service Account."""
    worksheet = buka_worksheet()
    return worksheet.get_all_values()


def ekstrak_open_per_distrik(semua_nilai):
    """Kelompokkan baris STATUS LAPANGAN == OPEN per district (urut sheet).

    Return dict: district_norm -> list of dict tiket.
    """
    idx = {nama: kolom_ke_indeks(huruf) for nama, huruf in KOLOM.items()}
    hasil = {}

    start_idx = DATA_START_ROW - 1
    for row_idx in range(start_idx, len(semua_nilai)):
        status = nilai_cell(semua_nilai, row_idx, idx["status"])
        if status.upper() != STATUS_OPEN:
            continue

        district = nilai_cell(semua_nilai, row_idx, idx["district"])
        distrik_norm = normalisasi_distrik(district)
        if distrik_norm not in DISTRICT_DIIZINKAN:
            continue

        tiket = {
            "district": district,
            "site_id": nilai_cell(semua_nilai, row_idx, idx["site_id"]),
            "incident": nilai_cell(semua_nilai, row_idx, idx["incident"]),
            "progres": nilai_cell(semua_nilai, row_idx, idx["progres"]),
            "plan": nilai_cell(semua_nilai, row_idx, idx["plan"]),
        }
        # Lewati baris tanpa identitas tiket.
        if not (tiket["incident"] or tiket["site_id"]):
            continue

        hasil.setdefault(distrik_norm, []).append(tiket)

    return hasil


def buat_blok_tiket(tiket):
    incident = isi_atau_strip(tiket["incident"])
    site_id = isi_atau_strip(tiket["site_id"])
    return "\n".join([
        f"➡️ *{incident} / {site_id}*",
        "⚠️ *Progres :*",
        isi_atau_strip(tiket["progres"]),
        "",
        "🚀 *Plan Repair :*",
        isi_atau_strip(tiket["plan"]),
    ])


def buat_pesan_distrik(distrik_norm, tikets):
    judul = f"Branch {nama_distrik_tampil(distrik_norm)}"
    blok = [buat_blok_tiket(t) for t in tikets]
    return f"{JUDUL_PESAN}\n{judul}\n{GARIS}\n" + "\n\n".join(blok)


def kirim_teks_wa(chat_id, teks):
    if requests is None:
        catat_log("Dependency WAHA belum tersedia: requests")
        return False

    url = f"{WAHA_URL.rstrip('/')}/api/sendText"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Api-Key": WAHA_API_KEY,
        "Connection": "close",
    }
    payload = {
        "session": WAHA_SESSION,
        "chatId": chat_id,
        "text": teks,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code in [200, 201]:
            catat_log(f"Berhasil mengirim ke WhatsApp: {chat_id}")
            return True
        catat_log(
            f"Gagal mengirim ke {chat_id}. Status: {response.status_code}, "
            f"Response: {response.text}"
        )
    except Exception as exc:
        catat_log(f"Error saat mengirim ke WAHA ({chat_id}): {exc}")

    return False


def tugas():
    catat_log("=" * 50)
    catat_log("Memulai tugas Report Quality...")

    try:
        semua_nilai = ambil_semua_nilai()
    except Exception as exc:
        catat_log(f"Gagal mengambil data sheet: {exc}")
        catat_log("Tugas Report Quality dibatalkan.")
        catat_log("=" * 50)
        return

    per_distrik = ekstrak_open_per_distrik(semua_nilai)
    total = sum(len(v) for v in per_distrik.values())
    catat_log(f"Ditemukan {total} tiket OPEN di {len(per_distrik)} district.")

    if total == 0:
        kirim_teks_wa(GROUP_ID_TUJUAN, "Tidak ada tiket Quality OPEN.")
        catat_log("Tugas Report Quality selesai.")
        catat_log("=" * 50)
        return

    # Satu bubble (pesan) per district, dikirim ke grup yang sama.
    for distrik_norm in DISTRICT_URUTAN:
        tikets = per_distrik.get(distrik_norm)
        if not tikets:
            continue
        pesan = buat_pesan_distrik(distrik_norm, tikets)
        catat_log(f"Kirim bubble {nama_distrik_tampil(distrik_norm)} ({len(tikets)} tiket).")
        kirim_teks_wa(GROUP_ID_TUJUAN, pesan)
        time.sleep(JEDA_KIRIM)

    catat_log("Tugas Report Quality selesai.")
    catat_log("=" * 50)


if __name__ == "__main__":
    print("=" * 55)
    print("  Report Tiket Quality -> WhatsApp (WAHA)")
    print(f"  Grup Tujuan: {GROUP_ID_TUJUAN}")
    print("=" * 55)

    tugas()
