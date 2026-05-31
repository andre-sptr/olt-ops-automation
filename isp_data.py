import os
import re
import traceback
from dataclasses import dataclass, replace
from datetime import datetime
from zoneinfo import ZoneInfo


# ================== KONFIGURASI TELEGRAM ==================
api_id = 35153027
api_hash = "275a7916b30391e446366433d5427086"

ID_GRUP_BTM = -1001267017385
ID_GRUP_DUM = -332267455
ID_GRUP_PKU = -1001481602761
ID_GRUP_PDG = -1001281180665
ID_GRUP_BKT = -1003652501250
ID_GRUP_TESTING = -4883113309

daftar_grup_target = [ID_GRUP_DUM]

# ================== KONFIGURASI GOOGLE SHEETS ==================
FILE_KREDENSIAL = "kunci_rahasia_google.json"
SPREADSHEET_ID = "13faIcsHI34GjvImRgV_AEUh5MP3NnLWiSfk-Z4O49Do"
SPREADSHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "13faIcsHI34GjvImRgV_AEUh5MP3NnLWiSfk-Z4O49Do/edit?gid=929623986"
)
GID_SHEET_TARGET = 929623986

HEADER = ["No", "NE Hostname", "RCA", "Durasi Down", "Tanggal", "Distrik"]

# ======================================================

DISTRIK_TARGET = "DUMAI"
TAHUN_TARGET = 2026
BULAN_TARGET = (2, 3, 4, 5)
ZONA_WAKTU = ZoneInfo("Asia/Jakarta")

FOLDER_LOG = "logs"

STATUS_FIELDS = {
    "DOWN",
    "UP",
    "OPEN",
    "CLOSE",
    "CLOSED",
    "NORMAL",
    "OLT DOWN",
    "GPON DOWN",
}


@dataclass(frozen=True)
class ISPRecord:
    hostname: str
    rca: str
    durasi_down: str
    tanggal: str
    distrik: str


def tanggal_hari_ini():
    return datetime.now().strftime("%Y-%m-%d")


def nama_file_log():
    return os.path.join(FOLDER_LOG, "isp_data_log.txt")


def simpan_log(pesan):
    os.makedirs(FOLDER_LOG, exist_ok=True)

    waktu_log = datetime.now().strftime("%H:%M:%S")
    tanggal_sekarang = tanggal_hari_ini()
    pesan_full = f"[{waktu_log}] {pesan}"
    print(pesan_full)

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
        f.write(pesan_full + "\n")


def bersihkan_field(value):
    value = str(value or "").strip().strip("*")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def ekstrak_setelah_label(teks, labels):
    teks_bersih = str(teks or "").replace("*", "").strip()
    for label in labels:
        pattern = rf"(?i)\b{re.escape(label)}\b\s*[:=\-]?\s*(.+)$"
        match = re.search(pattern, teks_bersih)
        if match:
            return bersihkan_field(match.group(1))
    return ""


def normalisasi_hostname(value):
    value = bersihkan_field(value)
    value = re.sub(r"^\d+\s*[\).\-\:]\s*", "", value)
    return value.strip()


def normalisasi_tanggal(value="", now=None):
    if now is None:
        now = datetime.now()

    value = bersihkan_field(value)
    if not value:
        return now.strftime("%d-%m-%Y")

    match = re.search(r"\d{1,4}[/-]\d{1,2}[/-]\d{2,4}", value)
    if match:
        value = match.group(0)

    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%y", "%d/%m/%y"):
        try:
            return datetime.strptime(value, fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    return value


def terlihat_seperti_durasi(value):
    value = bersihkan_field(value)
    if not re.search(r"\d", value):
        return False

    pola_durasi = [
        r"\b\d{1,3}:\d{2}(?::\d{2})?\b",
        r"\b\d+\s*(?:hari|jam|menit|mnt|detik|day|hour|hours|hr|hrs|min|mins|minute|minutes)\b",
        r"\b\d+\s*[dhjm]\b",
    ]
    return any(re.search(pattern, value, re.IGNORECASE) for pattern in pola_durasi)


def field_status(value):
    return bersihkan_field(value).upper() in STATUS_FIELDS


def ekstrak_distrik(teks, default="UNKNOWN"):
    for baris in str(teks or "").splitlines():
        nilai = ekstrak_setelah_label(baris, ["DISTRICT", "DISTRIK"])
        if nilai:
            return nilai.upper()
    return default


def ekstrak_label_pesan(teks, labels):
    for baris in str(teks or "").splitlines():
        if "|" in baris:
            continue
        nilai = ekstrak_setelah_label(baris, labels)
        if nilai:
            return nilai
    return ""


def ekstrak_hostname_dari_baris(baris):
    for part in str(baris or "").split("|"):
        if "GPON" in part.upper():
            return normalisasi_hostname(part)
    return ""


def parse_down_message(teks_pesan, now=None, default_distrik="UNKNOWN"):
    distrik = ekstrak_distrik(teks_pesan, default=default_distrik)
    tanggal_pesan = normalisasi_tanggal(
        ekstrak_label_pesan(teks_pesan, ["TANGGAL", "DATE"]),
        now=now,
    )
    rca_pesan = ekstrak_label_pesan(teks_pesan, ["RCA", "ROOT CAUSE", "PENYEBAB"])
    durasi_pesan = ekstrak_label_pesan(teks_pesan, ["DURASI DOWN", "DURASI", "DURATION"])

    records = []
    for baris in str(teks_pesan or "").splitlines():
        if "GPON" not in baris.upper() or "|" not in baris:
            continue
        if "| UP" in baris.upper() or "UPLINK" in baris.upper():
            continue

        parts = [bersihkan_field(part) for part in baris.split("|")]
        hostname_index = None
        for index, part in enumerate(parts):
            if "GPON" in part.upper():
                hostname_index = index
                break

        if hostname_index is None:
            continue

        hostname = normalisasi_hostname(parts[hostname_index])
        if not hostname:
            continue

        rca = rca_pesan
        durasi_down = durasi_pesan
        sudah_melihat_durasi_di_baris = False

        for field in parts[hostname_index + 1:]:
            if not field:
                continue

            nilai_rca = ekstrak_setelah_label(field, ["RCA", "ROOT CAUSE", "PENYEBAB"])
            if nilai_rca:
                rca = nilai_rca
                continue

            nilai_durasi = ekstrak_setelah_label(field, ["DURASI DOWN", "DURASI", "DURATION"])
            if nilai_durasi:
                durasi_down = nilai_durasi
                sudah_melihat_durasi_di_baris = True
                continue

            if field_status(field):
                continue

            if terlihat_seperti_durasi(field):
                if not durasi_down:
                    durasi_down = field
                sudah_melihat_durasi_di_baris = True
                continue

            if not rca and not sudah_melihat_durasi_di_baris:
                rca = field

        records.append(
            ISPRecord(
                hostname=hostname,
                rca=rca,
                durasi_down=durasi_down,
                tanggal=tanggal_pesan,
                distrik=distrik,
            )
        )

    return records


def parse_up_hostnames(teks_pesan):
    hostnames = []
    for baris in str(teks_pesan or "").splitlines():
        baris_upper = baris.upper()
        if "GPON" not in baris_upper or "| UP" not in baris_upper:
            continue
        if "UPLINK" in baris_upper:
            continue

        hostname = ekstrak_hostname_dari_baris(baris)
        if hostname:
            hostnames.append(hostname)
    return hostnames


def tanggal_message_lokal(message_date):
    if message_date is None:
        return None
    if message_date.tzinfo is not None:
        return message_date.astimezone(ZONA_WAKTU)
    return message_date.replace(tzinfo=ZONA_WAKTU)


def dalam_bulan_target(message_date, tahun=TAHUN_TARGET, bulan_target=BULAN_TARGET):
    tanggal_lokal = tanggal_message_lokal(message_date)
    if tanggal_lokal is None:
        return False
    return tanggal_lokal.year == tahun and tanggal_lokal.month in bulan_target


def sebelum_rentang_target(message_date, tahun=TAHUN_TARGET, bulan_target=BULAN_TARGET):
    tanggal_lokal = tanggal_message_lokal(message_date)
    if tanggal_lokal is None:
        return False
    return (tanggal_lokal.year, tanggal_lokal.month) < (tahun, min(bulan_target))


def kumpulkan_records_dari_messages(
    messages,
    tahun=TAHUN_TARGET,
    bulan_target=BULAN_TARGET,
    distrik_target=DISTRIK_TARGET,
):
    hasil = []
    pesan_urut = sorted(
        messages,
        key=lambda msg: (
            tanggal_message_lokal(getattr(msg, "date", None)) or datetime.min.replace(tzinfo=ZONA_WAKTU),
            getattr(msg, "id", 0),
        ),
    )

    for message in pesan_urut:
        tanggal_lokal = tanggal_message_lokal(getattr(message, "date", None))
        if tanggal_lokal is None:
            continue
        if not dalam_bulan_target(tanggal_lokal, tahun=tahun, bulan_target=bulan_target):
            continue

        teks_pesan = getattr(message, "text", None) or getattr(message, "message", "") or ""
        if "!PROGRAM ZERO GAMAS OLT!" not in teks_pesan.upper():
            continue

        tanggal_sheet = tanggal_lokal.strftime("%d-%m-%Y")
        records = parse_down_message(
            teks_pesan,
            now=tanggal_lokal,
            default_distrik=distrik_target,
        )

        for record in records:
            if record.distrik.upper() != distrik_target.upper():
                continue
            hasil.append(replace(record, tanggal=tanggal_sheet, distrik=distrik_target.upper()))

    return hasil


def format_sheet_values(records):
    if isinstance(records, dict):
        records = records.values()

    values = [HEADER]
    for no, record in enumerate(records, start=1):
        values.append(
            [
                no,
                record.hostname,
                record.rca,
                record.durasi_down,
                record.tanggal,
                record.distrik,
            ]
        )
    return values


def load_records_from_values(values):
    records = {}
    for row in values[1:]:
        if len(row) < 2:
            continue

        hostname = bersihkan_field(row[1])
        if not hostname:
            continue

        padded = list(row) + [""] * (len(HEADER) - len(row))
        record = ISPRecord(
            hostname=hostname,
            rca=bersihkan_field(padded[2]),
            durasi_down=bersihkan_field(padded[3]),
            tanggal=bersihkan_field(padded[4]),
            distrik=bersihkan_field(padded[5]),
        )
        records[hostname] = record
    return records


def update_sheet(worksheet, records):
    values = format_sheet_values(records)
    worksheet.clear()
    try:
        worksheet.update(range_name="A1", values=values)
    except TypeError:
        worksheet.update("A1", values)


def pastikan_header(worksheet):
    values = worksheet.get_all_values()
    if not values:
        try:
            worksheet.update(range_name="A1", values=[HEADER])
        except TypeError:
            worksheet.update("A1", [HEADER])
        return {}

    if values[0][: len(HEADER)] != HEADER:
        try:
            worksheet.update(range_name="A1", values=[HEADER])
        except TypeError:
            worksheet.update("A1", [HEADER])

    return load_records_from_values(values)


def setup_google_sheets():
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(FILE_KREDENSIAL, scope)
    client_gs = gspread.authorize(creds)
    spreadsheet = client_gs.open_by_key(SPREADSHEET_ID)
    return spreadsheet.get_worksheet_by_id(GID_SHEET_TARGET)


def buat_telegram_client():
    from telethon import TelegramClient

    return TelegramClient("sesi_isp_data", api_id, api_hash)


async def scan_riwayat_chat(
    client,
    chat_id=ID_GRUP_DUM,
    tahun=TAHUN_TARGET,
    bulan_target=BULAN_TARGET,
):
    messages = []
    jumlah_dipindai = 0

    simpan_log(
        f"Scan riwayat grup {chat_id} untuk bulan {', '.join(map(str, bulan_target))} {tahun}..."
    )

    async for message in client.iter_messages(chat_id):
        tanggal_lokal = tanggal_message_lokal(getattr(message, "date", None))
        if tanggal_lokal is None:
            continue

        if sebelum_rentang_target(tanggal_lokal, tahun=tahun, bulan_target=bulan_target):
            break

        jumlah_dipindai += 1

        if dalam_bulan_target(tanggal_lokal, tahun=tahun, bulan_target=bulan_target):
            messages.append(message)

    simpan_log(f"Total pesan dalam rentang diproses: {len(messages)} dari {jumlah_dipindai} pesan discan")
    return kumpulkan_records_dari_messages(messages, tahun=tahun, bulan_target=bulan_target)


async def main():
    simpan_log("Menghubungkan ke Google Sheets...")
    worksheet = setup_google_sheets()

    client = buat_telegram_client()
    simpan_log("Memulai koneksi ke Telegram...")
    await client.start()

    try:
        records = await scan_riwayat_chat(client)
        simpan_log(f"Data DUMAI yang ditemukan: {len(records)} baris. Memperbarui spreadsheet...")
        update_sheet(worksheet, records)
        simpan_log("Selesai update spreadsheet.")
    except Exception as e:
        simpan_log(f"Error saat scan riwayat: {e}")
        simpan_log(traceback.format_exc())
        raise
    finally:
        await client.disconnect()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
