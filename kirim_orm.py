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
SPREADSHEET_ID = "15UqbvxNSuajjE8s8Pr6H_RStt9HR7nfONW17FFSnQ60"
GID_SHEET = 664819204
FILE_KREDENSIAL = "kunci_rahasia_google.json"

WAHA_URL = "https://waha-dutxvo095iqn.cgk-lab.sumopod.my.id"
WAHA_SESSION = "OLTReport"
WAHA_API_KEY = "ROpWNPkTUavqEbnz5zKU4mTiL0HIZoye"
GROUP_ID_TUJUAN = "120363422960378808@g.us"

FOLDER_LOG = "logs"

# Header ada di baris 1, jadi data mulai dari baris 2.
DATA_START_ROW = 2

# Pemetaan kolom (huruf kolom Google Sheet).
KOLOM = {
    "district": "A",
    "list": "B",
    "jenis": "C",
    "ach": "F",
    "progress": "G",
}

JENIS_ORM = "ORM"
JENIS_NON_ORM = "NON-ORM"
JENIS_URUTAN = [JENIS_ORM, JENIS_NON_ORM]

# Hanya district berikut yang diproses, sekaligus urutan kirim bubble-nya.
# Nilai dinormalisasi (kapital, tanpa spasi) sehingga "BUKIT TINGGI" dan
# "BUKITTINGGI" sama-sama lolos.
DISTRICT_URUTAN = ["PEKANBARU", "DUMAI", "BATAM", "PADANG", "BUKITTINGGI"]
DISTRICT_DIIZINKAN = set(DISTRICT_URUTAN)

# Nomor PIC per distrik untuk di-mention, mengikuti kirim_manja.py.
# Disimpan apa adanya; dinormalisasi ke format "62..." oleh normalisasi_nomor().
RAW_PIC_DISTRIK = {
    "BATAM": ["+62 812-7688-8543"],
    "PEKANBARU": ["+62 813-7226-4429"],
    "DUMAI": ["+62 821-1712-7892"],
    "BUKITTINGGI": ["+62 812-2055-8735"],
    "PADANG": ["+62 812-8914-9112"],
}

GARIS = "=" * 12
JEDA_KIRIM = 2
# =================================================


def tanggal_hari_ini():
    return datetime.now().strftime("%Y-%m-%d")


def nama_file_log():
    return os.path.join(FOLDER_LOG, "orm_log.txt")


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


def normalisasi_nomor(raw):
    """Ubah nomor apa pun jadi format mention WhatsApp: digit murni "62..."."""
    digits = "".join(karakter for karakter in str(raw or "") if karakter.isdigit())
    if not digits:
        return ""
    if digits.startswith("62"):
        return digits
    if digits.startswith("0"):
        return "62" + digits[1:]
    if digits.startswith("8"):
        return "62" + digits
    return digits


PIC_DISTRIK = {
    distrik: [normalisasi_nomor(nomor) for nomor in nomor_list]
    for distrik, nomor_list in RAW_PIC_DISTRIK.items()
}


def nama_distrik_tampil(distrik_norm):
    mapping = {
        "BATAM": "Batam",
        "PEKANBARU": "Pekanbaru",
        "DUMAI": "Dumai",
        "BUKITTINGGI": "Bukittinggi",
        "PADANG": "Padang",
    }
    return mapping.get(distrik_norm, str(distrik_norm).title())


def normalisasi_jenis(nilai):
    label = str(nilai or "").strip().upper()
    label = label.replace("_", "-").replace(" ", "-")
    while "--" in label:
        label = label.replace("--", "-")

    if label.replace("-", "") == "NONORM" or label == "NON":
        return JENIS_NON_ORM
    if label == JENIS_ORM:
        return JENIS_ORM
    return ""


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


def buat_bucket_kosong():
    return {jenis: [] for jenis in JENIS_URUTAN}


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


def ekstrak_data_per_distrik(semua_nilai):
    """Kelompokkan list ORM dan NON-ORM per district sesuai kolom A/B/C/F/G."""
    idx = {nama: kolom_ke_indeks(huruf) for nama, huruf in KOLOM.items()}
    hasil = {distrik: buat_bucket_kosong() for distrik in DISTRICT_URUTAN}

    start_idx = DATA_START_ROW - 1
    for row_idx in range(start_idx, len(semua_nilai)):
        district = nilai_cell(semua_nilai, row_idx, idx["district"])
        distrik_norm = normalisasi_distrik(district)
        if distrik_norm not in DISTRICT_DIIZINKAN:
            continue

        jenis = normalisasi_jenis(nilai_cell(semua_nilai, row_idx, idx["jenis"]))
        if jenis not in JENIS_URUTAN:
            continue

        list_pekerjaan = nilai_cell(semua_nilai, row_idx, idx["list"])
        if not list_pekerjaan:
            continue

        hasil[distrik_norm][jenis].append({
            "list": list_pekerjaan,
            "ach": nilai_cell(semua_nilai, row_idx, idx["ach"]),
            "progress": nilai_cell(semua_nilai, row_idx, idx["progress"]),
        })

    return hasil


def ada_data_distrik(bucket):
    return any(bucket.get(jenis) for jenis in JENIS_URUTAN)


def buat_baris_item(nomor, item):
    return (
        f"{nomor}. {isi_atau_strip(item.get('list'))} | "
        f"{isi_atau_strip(item.get('ach'))} | "
        f"{isi_atau_strip(item.get('progress'))}"
    )


def tambah_bagian(lines, judul, items):
    lines.append(judul)
    if not items:
        lines.append("-")
        return

    for nomor, item in enumerate(items, start=1):
        lines.append(buat_baris_item(nomor, item))


def baris_cc_distrik(distrik_norm):
    """Kembalikan (baris_cc, daftar_chat_id_mention) untuk satu distrik."""
    nomor_list = PIC_DISTRIK.get(distrik_norm, [])
    if not nomor_list:
        return None, []
    tokens = " ".join(f"@{nomor}" for nomor in nomor_list)
    chat_ids = [f"{nomor}@c.us" for nomor in nomor_list]
    return f"cc {tokens}", chat_ids


def buat_pesan_distrik(distrik_norm, bucket):
    lines = [
        nama_distrik_tampil(distrik_norm),
        GARIS,
    ]

    tambah_bagian(lines, "ORM:", bucket.get(JENIS_ORM, []))
    tambah_bagian(lines, "Non-ORM:", bucket.get(JENIS_NON_ORM, []))

    cc_line, _ = baris_cc_distrik(distrik_norm)
    if cc_line:
        lines.append(cc_line)

    return "\n".join(lines)


def kirim_teks_wa(chat_id, teks, mentions=None):
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
    if mentions:
        payload["mentions"] = mentions

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
    catat_log("Memulai tugas Report ORM...")

    try:
        semua_nilai = ambil_semua_nilai()
    except Exception as exc:
        catat_log(f"Gagal mengambil data sheet: {exc}")
        catat_log("Tugas Report ORM dibatalkan.")
        catat_log("=" * 50)
        return

    per_distrik = ekstrak_data_per_distrik(semua_nilai)
    total = sum(
        len(bucket[jenis])
        for bucket in per_distrik.values()
        for jenis in JENIS_URUTAN
    )
    jumlah_distrik = sum(1 for bucket in per_distrik.values() if ada_data_distrik(bucket))
    catat_log(f"Ditemukan {total} list ORM/NON-ORM di {jumlah_distrik} district.")

    if total == 0:
        kirim_teks_wa(GROUP_ID_TUJUAN, "Tidak ada list ORM/NON-ORM.")
        catat_log("Tugas Report ORM selesai.")
        catat_log("=" * 50)
        return

    # Satu bubble (pesan) per district, dikirim ke grup yang sama.
    for distrik_norm in DISTRICT_URUTAN:
        bucket = per_distrik.get(distrik_norm, buat_bucket_kosong())
        if not ada_data_distrik(bucket):
            continue
        pesan = buat_pesan_distrik(distrik_norm, bucket)
        _, mentions = baris_cc_distrik(distrik_norm)
        catat_log(f"Kirim bubble {nama_distrik_tampil(distrik_norm)}.")
        kirim_teks_wa(GROUP_ID_TUJUAN, pesan, mentions)
        time.sleep(JEDA_KIRIM)

    catat_log("Tugas Report ORM selesai.")
    catat_log("=" * 50)


if __name__ == "__main__":
    print("=" * 55)
    print("  Report ORM -> WhatsApp (WAHA)")
    print(f"  Grup Tujuan: {GROUP_ID_TUJUAN}")
    print("=" * 55)

    tugas()
