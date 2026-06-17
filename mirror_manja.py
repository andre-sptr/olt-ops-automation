import hashlib
import json
import os
import time
from dataclasses import dataclass
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


SPREADSHEET_ID = "1Jl-povDud6JKpb4qqB8pRIA0FbpB6lbNomhs9iL5F98"
GID_SHEET = 1992709075
FILE_KREDENSIAL = "kunci_rahasia_google.json"

WAHA_URL = "https://waha-dutxvo095iqn.cgk-lab.sumopod.my.id"
WAHA_SESSION = "OLTReport"
WAHA_API_KEY = "ROpWNPkTUavqEbnz5zKU4mTiL0HIZoye"

DISTRIK_GRUP = {
    "BATAM": "120363344001225501@g.us",
    "PEKANBARU": "120363421111463203@g.us",
    "DUMAI": "120363407219688646@g.us",
    "BUKITTINGGI": "120363424731277526@g.us",
    "PADANG": "120363424680411991@g.us",
}
GRUP_INTI = "120363406101184780@g.us"
TARGET_DISTRIK = list(DISTRIK_GRUP.keys())
SUFFIX_INTI = "SBT"

# Nomor PIC per distrik untuk di-mention di pesan grup inti.
# Disimpan apa adanya; dinormalisasi ke format "62..." oleh normalisasi_nomor().
RAW_PIC_DISTRIK = {
    "BATAM": ["+62 813-7683-6000", "+62 812-7720-0469", "+62 813-6321-0112"],
    "PEKANBARU": ["+62 812-6132-3575", "+62 812-6465-895"],
    "DUMAI": ["+62 812-7556-6031", "+62 812-6465-895"],
    "BUKITTINGGI": ["+62 853-6311-8159", "+62 812-6771-5408"],
    "PADANG": ["+62 811-6393-933", "+62 822-8454-5038"],
}

FOLDER_LOG = "logs"


TABLE_CONFIGS = {
    "MANJA": {
        "key": "MANJA",
        "title": "Alarm 3 Jam Manja Open",
        "start_row": 5,
        "display_cols": ["B", "C", "D", "E"],
        "district_col": "F",
        "header": "Tiket | Jam Booking | STO | SA",
        "send_inti": True,
        # Jam Booking statis, jadi seluruh kolom dipakai untuk deteksi perubahan.
        "volatile_col_idx": None,
    },
    "DIAMOND": {
        "key": "DIAMOND",
        "title": "Alarm 3 Jam Diamond",
        "start_row": 5,
        "display_cols": ["H", "I", "J", "K"],
        "district_col": "L",
        "header": "Tiket | Open Berjalan (Jam) | STO | SA",
        "send_inti": True,
        # Kolom 1 = "Open Berjalan (Jam)" naik tiap recalc; jangan dipakai untuk hash.
        "volatile_col_idx": 1,
    },
    "PLATINUM": {
        "key": "PLATINUM",
        "title": "Alarm 6 Jam Platinum",
        "start_row": 5,
        "display_cols": ["N", "O", "P", "Q"],
        "district_col": "R",
        "header": "Tiket | Open Berjalan (Jam) | STO | SA",
        "send_inti": False,
        "volatile_col_idx": 1,
    },
    "JAM72": {
        "key": "JAM72",
        "title": "Alarm 72 Jam Tiket Open",
        "start_row": 5,
        "display_cols": ["U", "V", "W", "X"],
        "district_col": "X",
        "header": "Tiket | Open Berjalan (Jam) | STO | Distrik",
        "send_inti": True,
        "volatile_col_idx": 1,
    },
}


@dataclass
class TableData:
    by_district: dict[str, list[list[str]]]
    all_rows: list[list[str]]
    all_rows_distrik: list[str]
    skipped: list[tuple[int, str, list[str]]]


def tanggal_hari_ini():
    return datetime.now().strftime("%Y-%m-%d")


def nama_file_log():
    return os.path.join(FOLDER_LOG, "kirim_manja_log.txt")


def catat_log(pesan):
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
    """Ubah nomor apa pun jadi format mention WhatsApp: digit murni "62...".

    Contoh: "+62 813-7683-6000" -> "6281376836000", "081277200469" -> "6281277200469".
    """
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


def nilai_cell(semua_nilai, row_idx, col_idx):
    if row_idx < 0 or row_idx >= len(semua_nilai):
        return ""
    row = semua_nilai[row_idx]
    if col_idx < 0 or col_idx >= len(row):
        return ""
    return str(row[col_idx]).strip()


def ekstrak_table(cfg, semua_nilai):
    by_district = {distrik: [] for distrik in TARGET_DISTRIK}
    all_rows = []
    all_rows_distrik = []
    skipped = []

    start_idx = int(cfg["start_row"]) - 1
    display_indices = [kolom_ke_indeks(col) for col in cfg["display_cols"]]
    district_idx = kolom_ke_indeks(cfg["district_col"])

    for row_idx in range(start_idx, len(semua_nilai)):
        display_row = [nilai_cell(semua_nilai, row_idx, col_idx) for col_idx in display_indices]
        tiket = display_row[0] if display_row else ""
        if not tiket:
            continue

        distrik_asli = nilai_cell(semua_nilai, row_idx, district_idx)
        distrik_norm = normalisasi_distrik(distrik_asli)
        all_rows.append(display_row)
        all_rows_distrik.append(distrik_norm)

        if distrik_norm in by_district:
            by_district[distrik_norm].append(display_row)
        else:
            skipped.append((row_idx + 1, distrik_asli, display_row))

    return TableData(
        by_district=by_district,
        all_rows=all_rows,
        all_rows_distrik=all_rows_distrik,
        skipped=skipped,
    )


def buat_pesan_data(cfg, judul_suffix, rows):
    title = cfg["title"] if not judul_suffix else f'{cfg["title"]} | {judul_suffix}'
    lines = [title, "==============", cfg["header"]]
    lines.extend(" | ".join(row) for row in rows)
    return "\n".join(lines)


def buat_pesan_clear(cfg, judul_suffix):
    title = cfg["title"] if not judul_suffix else f'{cfg["title"]} | {judul_suffix}'
    return "\n".join([title, "==============", "CLEAR - Tidak ada tiket aktif."])


def hash_rows(rows):
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def baris_identitas(cfg, rows):
    """Buang kolom volatile (mis. "Open Berjalan (Jam)") sebelum hash.

    Nilai jam berjalan naik tiap kali sheet dihitung ulang, sehingga kalau ikut
    di-hash, pesan akan terkirim ulang terus walau set tiket tidak berubah.
    """
    idx = cfg.get("volatile_col_idx")
    if idx is None:
        return rows
    return [[nilai for i, nilai in enumerate(row) if i != idx] for row in rows]


def proses_target(snapshot, snapshot_key, chat_id, cfg, suffix, rows, send_func):
    if not rows:
        return False

    rows_hash = hash_rows(baris_identitas(cfg, rows))
    previous_hash = snapshot.get(snapshot_key)

    if previous_hash == rows_hash:
        return False

    pesan = buat_pesan_data(cfg, suffix, rows)
    if send_func(chat_id, pesan):
        snapshot[snapshot_key] = rows_hash
        return True

    return False


def baris_cc_distrik(distrik_norm):
    """Kembalikan (baris_cc, daftar_chat_id_mention) untuk satu distrik.

    Distrik tanpa PIC (mis. di luar 5 target) menghasilkan (None, []).
    """
    nomor_list = PIC_DISTRIK.get(distrik_norm, [])
    if not nomor_list:
        return None, []
    tokens = " ".join(f"@{nomor}" for nomor in nomor_list)
    chat_ids = [f"{nomor}@c.us" for nomor in nomor_list]
    return f"cc {tokens}", chat_ids


def buat_pesan_inti(cfg, suffix, rows_with_distrik):
    """Bangun pesan grup inti yang dikelompokkan per distrik + mention PIC.

    rows_with_distrik: list of (display_row, distrik_norm).
    Return (teks, mentions) di mana mentions adalah daftar chatId unik untuk WAHA.
    """
    title = cfg["title"] if not suffix else f'{cfg["title"]} | {suffix}'
    lines = [title, "==============", cfg["header"]]

    grouped = {distrik: [] for distrik in TARGET_DISTRIK}
    unknown = []
    for display_row, distrik_norm in rows_with_distrik:
        if distrik_norm in grouped:
            grouped[distrik_norm].append(display_row)
        else:
            unknown.append(display_row)

    blocks = []
    mentions = []
    seen = set()

    def catat_mention(chat_ids):
        for chat_id in chat_ids:
            if chat_id not in seen:
                seen.add(chat_id)
                mentions.append(chat_id)

    # Satu blok per distrik: semua tiket distrik itu dulu, lalu SATU baris cc PIC.
    for distrik_norm in TARGET_DISTRIK:
        rows = grouped[distrik_norm]
        if not rows:
            continue
        baris_tiket = [" | ".join(display_row) for display_row in rows]
        cc_line, chat_ids = baris_cc_distrik(distrik_norm)
        if cc_line:
            catat_mention(chat_ids)
            blocks.append("\n".join(baris_tiket + [cc_line]))
        else:
            blocks.append("\n".join(baris_tiket))

    # Distrik di luar target: tampil tanpa cc, dikumpulkan di satu blok akhir.
    if unknown:
        blocks.append("\n".join(" | ".join(display_row) for display_row in unknown))

    teks = "\n".join(lines) + "\n" + "\n\n".join(blocks)
    return teks, mentions


def proses_target_inti(snapshot, snapshot_key, chat_id, cfg, suffix, rows_with_distrik, send_func):
    if not rows_with_distrik:
        return False

    basis = [
        baris_identitas(cfg, [display_row])[0] + [distrik_norm]
        for display_row, distrik_norm in rows_with_distrik
    ]
    rows_hash = hash_rows(basis)
    previous_hash = snapshot.get(snapshot_key)

    if previous_hash == rows_hash:
        return False

    teks, mentions = buat_pesan_inti(cfg, suffix, rows_with_distrik)
    if send_func(chat_id, teks, mentions):
        snapshot[snapshot_key] = rows_hash
        return True

    return False


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
        catat_log(f"Gagal mengirim ke {chat_id}. Status: {response.status_code}, Response: {response.text}")
    except Exception as exc:
        catat_log(f"Error saat mengirim ke WAHA ({chat_id}): {exc}")

    return False


def proses_siklus(snapshot):
    worksheet = buka_worksheet()
    semua_nilai = worksheet.get_all_values()
    ada_perubahan = False

    for cfg in TABLE_CONFIGS.values():
        table_data = ekstrak_table(cfg, semua_nilai)

        for row_number, distrik_asli, display_row in table_data.skipped:
            catat_log(
                f"Baris {row_number} table {cfg['key']} dilewati untuk per-distrik: "
                f"DISTRIK='{distrik_asli}', DATA={display_row}"
            )

        for distrik_norm in TARGET_DISTRIK:
            rows = table_data.by_district[distrik_norm]
            suffix = nama_distrik_tampil(distrik_norm)
            chat_id = DISTRIK_GRUP[distrik_norm]
            sent = proses_target(
                snapshot,
                (cfg["key"], distrik_norm),
                chat_id,
                cfg,
                suffix,
                rows,
                kirim_teks_wa,
            )
            ada_perubahan = ada_perubahan or sent

        if cfg.get("send_inti"):
            rows_with_distrik = list(zip(table_data.all_rows, table_data.all_rows_distrik))
            sent = proses_target_inti(
                snapshot,
                (cfg["key"], "__INTI__"),
                GRUP_INTI,
                cfg,
                SUFFIX_INTI,
                rows_with_distrik,
                kirim_teks_wa,
            )
            ada_perubahan = ada_perubahan or sent

    return ada_perubahan


def main():
    snapshot = {}
    interval = 30
    max_interval = 300

    catat_log("Program Kirim Manja aktif. Memulai polling Google Sheet.")

    while True:
        try:
            try:
                ada_perubahan = proses_siklus(snapshot)
                if ada_perubahan:
                    interval = 30
                    catat_log("Perubahan terkirim. Interval polling kembali ke 30 detik.")
                else:
                    interval = min(max_interval, int(interval * 1.5))
                    catat_log(f"Tidak ada perubahan. Polling berikutnya dalam {interval} detik.")
            except Exception as exc:
                catat_log(f"Error dalam siklus utama: {exc}")

            time.sleep(interval)
        except KeyboardInterrupt:
            catat_log("Program dihentikan oleh pengguna.")
            raise


if __name__ == "__main__":
    main()
