import csv
import io
import os
from datetime import datetime

try:
    import requests
except ModuleNotFoundError:
    requests = None


# ================== KONFIGURASI ==================
# Spreadsheet bersifat publik (siapa pun dengan link = editor), jadi datanya
# diambil lewat endpoint export CSV tanpa kredensial / Service Account.
SPREADSHEET_ID = "1nFIBj5EjoyQxjcLAYF0kfnEN_5wKUsNvp03stW7csUw"
GID_SHEET = "1416909766"

WAHA_URL = "https://waha-dutxvo095iqn.cgk-lab.sumopod.my.id"
WAHA_SESSION = "OLTReport"
WAHA_API_KEY = "ROpWNPkTUavqEbnz5zKU4mTiL0HIZoye"
GROUP_ID_TUJUAN = "120363422960378808@g.us"

FOLDER_LOG = "logs"

# Header ada di baris 2, jadi data tiket mulai dari baris 3.
DATA_START_ROW = 3
STATUS_OPEN = "OPEN"

# Pemetaan kolom (huruf kolom Google Sheet).
KOL_STATUS = "K"     # STATUS TICKET (filter == OPEN)
KOL_DISTRICT = "B"
KOL_INCIDENT = "D"
KOL_SITE_ID = "C"
KOL_TTRQ_HARI = "G"  # TTRq (hari)
KOL_TTRQ_JAM = "H"   # TTRq (jam)
KOL_INDICATOR = "M"

JUDUL = "Report Tiket Quality"
HEADER = "District | Incident | Site ID | TTRq | Indicator"
PEMISAH = "-" * 56  # garis pemisah antar-district

# Hanya district berikut yang dikirim, sekaligus jadi urutan tampil per grup.
# Nilai dinormalisasi (kapital, tanpa spasi) sehingga "BUKIT TINGGI" dan
# "BUKITTINGGI" sama-sama lolos.
DISTRICT_URUTAN = ["PEKANBARU", "DUMAI", "BATAM", "PADANG", "BUKITTINGGI"]
DISTRICT_DIIZINKAN = set(DISTRICT_URUTAN)
# =================================================


def tanggal_hari_ini():
    return datetime.now().strftime("%Y-%m-%d")


def waktu_judul():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


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


def nilai_cell(semua_nilai, row_idx, col_idx):
    if row_idx < 0 or row_idx >= len(semua_nilai):
        return ""
    row = semua_nilai[row_idx]
    if col_idx < 0 or col_idx >= len(row):
        return ""
    return str(row[col_idx]).strip()


def url_export_csv():
    return (
        f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"
        f"/export?format=csv&gid={GID_SHEET}"
    )


def ambil_semua_nilai():
    """Ambil seluruh isi sheet sebagai list-of-list lewat export CSV publik."""
    if requests is None:
        catat_log("Dependency belum tersedia: requests")
        raise RuntimeError("requests tidak tersedia")

    url = url_export_csv()
    response = requests.get(url, timeout=60, allow_redirects=True)
    response.raise_for_status()

    konten = response.content.decode("utf-8", errors="replace")
    # Kalau sheet tidak benar-benar publik, Google mengembalikan HTML login,
    # bukan CSV. Deteksi dan beri pesan jelas.
    awal = konten.lstrip()[:200].lower()
    if awal.startswith("<!doctype html") or "<html" in awal:
        raise RuntimeError(
            "Sheet tidak bisa diakses publik (dapat HTML, bukan CSV). "
            "Pastikan share-nya 'anyone with the link'."
        )

    pembaca = csv.reader(io.StringIO(konten))
    return [list(baris) for baris in pembaca]


def format_ttrq(jam, hari):
    """Gabungkan TTRq jam (kolom H) dan hari (kolom G): '{jam} jam ({hari} hari)'."""
    return f"{jam} jam ({hari} hari)"


def ekstrak_tiket_open(semua_nilai):
    """Ambil baris berstatus OPEN dan susun jadi 5 kolom siap tampil."""
    idx_status = kolom_ke_indeks(KOL_STATUS)
    idx_district = kolom_ke_indeks(KOL_DISTRICT)
    idx_incident = kolom_ke_indeks(KOL_INCIDENT)
    idx_site = kolom_ke_indeks(KOL_SITE_ID)
    idx_hari = kolom_ke_indeks(KOL_TTRQ_HARI)
    idx_jam = kolom_ke_indeks(KOL_TTRQ_JAM)
    idx_indicator = kolom_ke_indeks(KOL_INDICATOR)

    rows = []
    start_idx = DATA_START_ROW - 1
    for row_idx in range(start_idx, len(semua_nilai)):
        status = nilai_cell(semua_nilai, row_idx, idx_status)
        if status.upper() != STATUS_OPEN:
            continue

        district = nilai_cell(semua_nilai, row_idx, idx_district)
        if normalisasi_distrik(district) not in DISTRICT_DIIZINKAN:
            continue

        incident = nilai_cell(semua_nilai, row_idx, idx_incident)
        site_id = nilai_cell(semua_nilai, row_idx, idx_site)
        ttrq_hari = nilai_cell(semua_nilai, row_idx, idx_hari)
        ttrq_jam = nilai_cell(semua_nilai, row_idx, idx_jam)
        indicator = nilai_cell(semua_nilai, row_idx, idx_indicator)

        # Lewati baris kosong yang kebetulan kolom status-nya ber-OPEN.
        if not (district or incident or site_id):
            continue

        rows.append([
            district.title(),  # Sheet pakai KAPITAL (PEKANBARU) -> tampil "Pekanbaru".
            incident,
            site_id,
            format_ttrq(ttrq_jam, ttrq_hari),
            indicator,
        ])

    return rows


def buat_pesan(rows):
    judul = f"*{JUDUL} {waktu_judul()}*"
    if not rows:
        return f"{judul}\nTidak ada tiket Quality OPEN."

    # Kelompokkan baris per district (urut sheet di dalam grup).
    grup = {}
    for row in rows:
        kunci = normalisasi_distrik(row[0])
        grup.setdefault(kunci, []).append(" | ".join(row))

    urutan = [d for d in DISTRICT_URUTAN if d in grup]
    urutan += [d for d in grup if d not in DISTRICT_URUTAN]  # jaga-jaga di luar daftar

    blok = ["\n".join(grup[d]) for d in urutan]
    return f"{judul}\n{HEADER}\n\n" + f"\n{PEMISAH}\n".join(blok)


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

    rows = ekstrak_tiket_open(semua_nilai)
    catat_log(f"Ditemukan {len(rows)} tiket Quality OPEN.")

    pesan = buat_pesan(rows)
    kirim_teks_wa(GROUP_ID_TUJUAN, pesan)

    catat_log("Tugas Report Quality selesai.")
    catat_log("=" * 50)


if __name__ == "__main__":
    print("=" * 55)
    print("  Report Tiket Quality -> WhatsApp (WAHA)")
    print(f"  Grup Tujuan: {GROUP_ID_TUJUAN}")
    print("=" * 55)

    tugas()
