from telethon import TelegramClient, events
from datetime import datetime
import requests
import os
import re
import sys
import traceback

try:
    import gspread
except ModuleNotFoundError:
    gspread = None

try:
    from oauth2client.service_account import ServiceAccountCredentials
except ModuleNotFoundError:
    ServiceAccountCredentials = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ================== KONFIGURASI TELEGRAM ==================
api_id = 35153027
api_hash = '275a7916b30391e446366433d5427086'

ID_GRUP_BTM = -1001267017385
ID_GRUP_DUM = -332267455
ID_GRUP_PKU = -1001481602761
ID_GRUP_PDG = -1001281180665
ID_GRUP_BKT = -1003652501250
ID_GRUP_TESTING = -4883113309

daftar_grup_target = [ID_GRUP_BTM, ID_GRUP_DUM, ID_GRUP_PKU, ID_GRUP_PDG, ID_GRUP_BKT, ID_GRUP_TESTING]

# ================== KONFIGURASI WAHA ==================
WAHA_URL = "https://waha-dutxvo095iqn.cgk-lab.sumopod.my.id" 
WAHA_SESSION = "OLTReport"
WAHA_API_KEY = "ROpWNPkTUavqEbnz5zKU4mTiL0HIZoye"
# 120363425065142845@g.us = real
# 120363423984319917@g.us = test
GROUP_ISP = "120363425065142845@g.us"
GROUP_POSKO = "120363427217043012@g.us"
GROUP_ID_TUJUAN = [
    GROUP_ISP,
    GROUP_POSKO
]

# ================== KONFIGURASI ESKALASI ==================
RAW_MANAGER_WA = [
    "+628126723729",
    "+6282269171322",
    "+6285272352267",
    "+628117410017",
]

RAW_OFFICER_DISTRIK = {
    "BATAM": ["+6281334729757", "+6281289149112"],
    "PEKANBARU": ["+6281372264429", "+6281371717102"],
    "DUMAI": ["+6281374559924", "+6282117127892"],
    "BUKITTINGGI": ["+628116888112", "+6281220558735"],
    "PADANG": ["+6282171996392", "+6281395233452"],
}

# ================== KONFIGURASI METADATA OLT ==================
SPREADSHEET_ID_METADATA = "1crQdVmqXoROtuiaB4-ce7sIwJh26oxKMPq3Mj6-GyLU"
GID_SHEET_METADATA = 1706912635
GID_SHEET_DH = 1918665126
FILE_KREDENSIAL_GOOGLE = "kunci_rahasia_google.json"

SEVERITY_VALID = {
    "very low": "Very Low",
    "low": "Low",
    "minor": "Minor",
    "major": "Major",
    "critical": "Critical",
}

EMOJI_SEVERITY = {
    "Very Low": "⭐ Very Low",
    "Low": "🟡 Low",
    "Minor": "🟠 Minor",
    "Major": "🔴 Major",
    "Critical": "🟥 Critical",
}

GARIS_TABEL = "-" * 52

# ======================================================

FOLDER_LOG = "logs"
os.makedirs(FOLDER_LOG, exist_ok=True)

client = TelegramClient('sesi_mirror_isp', api_id, api_hash)

data_gpon_down = {}
data_gpon_up = {}

tanggal_data_sekarang = datetime.now().strftime("%Y-%m-%d")


def nama_file_log():
    """KONSISTENSI: Nama log sistem menjadi statis agar hanya ada 1 file"""
    return os.path.join(FOLDER_LOG, "mirror_isp_log.txt")


def simpan_log(pesan):
    """Mencatat log dengan fitur auto-reset jika masuk hari baru."""
    waktu_log = datetime.now().strftime("%H:%M:%S")
    tanggal_sekarang = datetime.now().strftime("%Y-%m-%d")
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


def normalisasi_hostname(hostname):
    return str(hostname or "").strip().strip("*`_").upper()


def normalisasi_distrik(distrik):
    return str(distrik or "").strip().upper().replace(" ", "")


def normalisasi_nomor(raw):
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


def normalisasi_daftar_nomor(daftar_nomor):
    hasil = []
    sudah_ada = set()

    for raw in daftar_nomor or []:
        nomor = normalisasi_nomor(raw)
        if nomor and nomor not in sudah_ada:
            sudah_ada.add(nomor)
            hasil.append(nomor)

    return hasil


def durasi_ke_menit(durasi):
    teks = str(durasi or "").strip()
    if not teks:
        return None

    cocok_jam = re.fullmatch(
        r"(\d{1,3}):([0-5]\d)(?::([0-5]\d))?",
        teks,
    )
    if cocok_jam:
        return int(cocok_jam.group(1)) * 60 + int(cocok_jam.group(2))

    cocok_jam_teks = re.search(r"(\d+)\s*jam", teks, re.IGNORECASE)
    cocok_menit_teks = re.search(r"(\d+)\s*menit", teks, re.IGNORECASE)
    if not cocok_jam_teks and not cocok_menit_teks:
        return None

    total_menit = 0
    if cocok_jam_teks:
        total_menit += int(cocok_jam_teks.group(1)) * 60
    if cocok_menit_teks:
        total_menit += int(cocok_menit_teks.group(1))
    return total_menit


def ambil_olt_down_lebih_satu_jam(data_down=None, hostname_pemicu=None):
    sumber_data = data_gpon_down if data_down is None else data_down
    hasil = []
    ada_pemicu = False

    for hostname_kunci, info in sumber_data.items():
        bagian = [nilai.strip() for nilai in str(info or "").split("|")]
        bagian += [""] * (5 - len(bagian))

        durasi = bagian[2]
        total_menit = durasi_ke_menit(durasi)
        if total_menit is None or total_menit <= 60:
            continue

        hasil.append(
            {
                "district": normalisasi_distrik(bagian[0]),
                "hostname": normalisasi_hostname(bagian[1] or hostname_kunci),
                "duration": durasi,
                "minutes": total_menit,
            }
        )

        if hostname_pemicu and hostname_kunci in hostname_pemicu:
            ada_pemicu = True

    # Jika hostname_pemicu diberikan tapi tidak ada satupun hostname
    # yang baru di-update memiliki durasi > 1 jam, jangan trigger eskalasi
    if hostname_pemicu is not None and not ada_pemicu:
        return []

    return hasil


def buat_pesan_eskalasi(
    daftar_down=None,
    manager_numbers=None,
    officer_by_district=None,
    mapping_metadata=None,
):
    if daftar_down is None:
        daftar_down = ambil_olt_down_lebih_satu_jam()
    if not daftar_down:
        return None, []

    if manager_numbers is None:
        manager_numbers = RAW_MANAGER_WA
    if officer_by_district is None:
        officer_by_district = RAW_OFFICER_DISTRIK

    if mapping_metadata is None:
        mapping_metadata = {}

    managers = normalisasi_daftar_nomor(manager_numbers)
    officers = {
        normalisasi_distrik(distrik): normalisasi_daftar_nomor(daftar_nomor)
        for distrik, daftar_nomor in officer_by_district.items()
    }

    lines = ["🚨 *ESKALASI OLT DOWN > 1 JAM*"]
    distrik_terdampak = []
    no = 1
    for insiden in daftar_down:
        distrik = normalisasi_distrik(insiden.get("district"))
        hostname = normalisasi_hostname(insiden.get("hostname")) or "-"
        durasi = str(insiden.get("duration") or "-").strip()
        metadata = mapping_metadata.get(hostname, {})
        severity = normalisasi_severity(metadata.get("severity", ""))
        severity_tampil = EMOJI_SEVERITY.get(severity, "") if severity else ""
        if severity_tampil:
            lines.append(f"{no}. ({severity_tampil}) {distrik or 'UNKNOWN'} | {hostname} | {durasi}")
        else:
            lines.append(f"{no}. {distrik or 'UNKNOWN'} | {hostname} | {durasi}")
        no += 1
        if distrik and distrik not in distrik_terdampak:
            distrik_terdampak.append(distrik)

    baris_pic = []
    if managers:
        baris_pic.append(" ".join(f"@{nomor}" for nomor in managers))

    mentions = []
    mention_tercatat = set()

    def tambah_mentions(daftar_nomor):
        for nomor in daftar_nomor:
            chat_id = f"{nomor}@c.us"
            if chat_id not in mention_tercatat:
                mention_tercatat.add(chat_id)
                mentions.append(chat_id)

    tambah_mentions(managers)

    for distrik in distrik_terdampak:
        daftar_officer = officers.get(distrik, [])
        if not daftar_officer:
            continue
        token_officer = " ".join(f"@{nomor}" for nomor in daftar_officer)
        baris_pic.append(f"PIC {distrik}: {token_officer}")
        tambah_mentions(daftar_officer)

    if baris_pic:
        lines.extend(["", *baris_pic])

    lines.extend(["", "*SEGERA CONCALL & UPDATE PROGRES PENANGANAN.*"])
    return "\n".join(lines), mentions


def normalisasi_severity(severity):
    return SEVERITY_VALID.get(str(severity or "").strip().casefold(), "")


def buat_mapping_metadata(semua_nilai):
    """Buat mapping HOSTNAME -> metadata dari range E3:Q."""
    mapping = {}

    for baris in semua_nilai:
        if not baris:
            continue

        nilai = [str(item or "").strip() for item in baris]
        nilai += [""] * (13 - len(nilai))

        hostname = normalisasi_hostname(nilai[0])
        if not hostname:
            continue

        mapping[hostname] = {
            "severity": normalisasi_severity(nilai[7]),
            "olo": nilai[8],
            "k2": nilai[9],
            "k3": nilai[10],
            "ds": nilai[12],
        }

    return mapping


def buat_mapping_dh(semua_nilai):
    """Buat mapping HOSTNAME -> status DH dari range D3:F."""
    mapping = {}

    for baris in semua_nilai:
        if not baris:
            continue

        nilai = [str(item or "").strip() for item in baris]
        nilai += [""] * (3 - len(nilai))

        hostname = normalisasi_hostname(nilai[0])
        if not hostname:
            continue

        status_dh = nilai[2].strip().upper()
        mapping[hostname] = "DH" if status_dh == "DUALHOMING" else "NON"

    return mapping


def ambil_mapping_metadata():
    """Ambil hostname, severity, OLO, K2, K3, dan DH dari Google Sheet."""
    missing = []
    if gspread is None:
        missing.append("gspread")
    if ServiceAccountCredentials is None:
        missing.append("oauth2client")
    if missing:
        raise RuntimeError(
            "Dependency Google Sheet belum tersedia: " + ", ".join(missing)
        )

    scope = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
    ]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        FILE_KREDENSIAL_GOOGLE,
        scope,
    )
    client_gs = gspread.authorize(credentials)
    spreadsheet = client_gs.open_by_key(SPREADSHEET_ID_METADATA)
    worksheet = spreadsheet.get_worksheet_by_id(GID_SHEET_METADATA)
    mapping = buat_mapping_metadata(worksheet.get("E3:Q"))

    try:
        worksheet_dh = spreadsheet.get_worksheet_by_id(GID_SHEET_DH)
        mapping_dh = buat_mapping_dh(worksheet_dh.get("D3:F"))
        simpan_log(
            f"Berhasil mengambil {len(mapping_dh)} data DH "
            f"dari GID {GID_SHEET_DH}"
        )
        for hostname, dh_val in mapping_dh.items():
            if hostname in mapping:
                mapping[hostname]["dh"] = dh_val
            else:
                mapping[hostname] = {
                    "severity": "",
                    "olo": "",
                    "k2": "",
                    "k3": "",
                    "ds": "",
                    "dh": dh_val,
                }
    except Exception as exc:
        simpan_log(f"Gagal mengambil data DH, menggunakan '-': {exc}")
        for hostname in mapping:
            mapping[hostname].setdefault("dh", "-")

    return mapping


def format_baris_down(no, info, mapping_metadata):
    bagian = [nilai.strip() for nilai in str(info or "").split("|")]
    bagian += [""] * (4 - len(bagian))

    district = bagian[0] or "-"
    hostname = normalisasi_hostname(bagian[1]) or "-"
    durasi_down = bagian[2] or "-"
    node_b = bagian[3] or "0"

    if mapping_metadata is None:
        severity_tampil = "-"
        olo = "0"
        k2 = "0"
        k3 = "0"
        dh = "-"
        ds = "-"
    else:
        metadata = mapping_metadata.get(hostname, {})
        severity = normalisasi_severity(metadata.get("severity", ""))
        severity_tampil = EMOJI_SEVERITY.get(severity, "⭐ Very Low")
        olo = str(metadata.get("olo", "") or "").strip() or "0"
        k2 = str(metadata.get("k2", "") or "").strip() or "0"
        k3 = str(metadata.get("k3", "") or "").strip() or "0"
        dh = str(metadata.get("dh", "") or "").strip() or "-"
        ds = str(metadata.get("ds", "") or "").strip() or "-"

    return (
        f"{no}. {district} | {hostname} | {durasi_down} | "
        f"{severity_tampil} | {node_b} | {olo} | {k2} | {k3} | {dh} | {ds}"
    )


def buat_laporan_list(mapping_metadata=None):
    if mapping_metadata is None:
        try:
            mapping_metadata = ambil_mapping_metadata()
            simpan_log(
                f"Berhasil mengambil {len(mapping_metadata)} data metadata OLT "
                f"dari GID {GID_SHEET_METADATA}"
            )
        except Exception as exc:
            mapping_metadata = None
            simpan_log(
                f"Gagal mengambil metadata OLT, menggunakan '-': {exc}"
            )

    teks_laporan = "*OLT DOWN*\n"
    teks_laporan += (
        "NO | DISTRICT | HOSTNAME | DURASI DOWN | SEVERITY | "
        "NodeB | OLO | K2 | K3 | DH | DS\n"
        f"{GARIS_TABEL}\n"
    )
    
    no = 1
    for hostname, info in data_gpon_down.items():
        teks_laporan += format_baris_down(no, info, mapping_metadata) + "\n"
        no += 1
        
    teks_laporan += "\n*OLT UP*\n"
    teks_laporan += "NO | HOSTNAME | STATUS\n"
    teks_laporan += f"{GARIS_TABEL}\n"
    
    no = 1
    for hostname, info in data_gpon_up.items():
        teks_laporan += f"{no}. {info}\n"
        no += 1
        
    return teks_laporan


def simpan_ke_file_laporan(teks):
    """KONSISTENSI: Menyimpan teks list laporan ke dalam satu file statis agar tidak menumpuk."""
    nama_file = os.path.join(FOLDER_LOG, "isp_new_report.txt")
    
    try:
        with open(nama_file, "w", encoding="utf-8") as file:
            file.write(teks)
        simpan_log(f"✅ Berhasil mengupdate file {nama_file}")
    except Exception as e:
        simpan_log(f"❌ Error saat membuat file laporan: {e}")


def kirim_pesan_wa(teks, mentions=None):
    url = f"{WAHA_URL.rstrip('/')}/api/sendText"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Api-Key": WAHA_API_KEY,
        "Connection": "close"
    }

    semua_berhasil = True

    for chat_id in GROUP_ID_TUJUAN:
        payload = {
            "session": WAHA_SESSION,
            "chatId": chat_id, 
            "text": teks
        }
        if mentions:
            payload["mentions"] = mentions
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code in [200, 201]:
                simpan_log(f"✅ Berhasil mirroring ke WhatsApp (Grup: {chat_id})")
            else:
                simpan_log(f"❌ Gagal mirroring ke {chat_id}. Status: {response.status_code}, Response: {response.text}")
                semua_berhasil = False
        except Exception as e:
            simpan_log(f"❌ Error saat mengirim ke WAHA ({chat_id}): {e}")
            semua_berhasil = False
            
    return semua_berhasil


@client.on(events.NewMessage(chats=daftar_grup_target))
async def proses_pesan_baru(event):
    global tanggal_data_sekarang
    
    try:
        tanggal_hari_ini = datetime.now().strftime("%Y-%m-%d")
        if tanggal_hari_ini != tanggal_data_sekarang:
            simpan_log("🕛 Pergantian hari terdeteksi. Mereset data laporan kemarin...")
            data_gpon_up.clear()
            tanggal_data_sekarang = tanggal_hari_ini
            
        teks_pesan = event.text.strip() if event.text else ""
        teks_pesan_upper = teks_pesan.upper()
        baris_pesan = teks_pesan.split('\n')
        
        ada_perubahan = False
        hostname_terupdate = set()

        if '!PROGRAM ZERO GAMAS OLT!' in teks_pesan_upper:
            nama_distrik = "UNKNOWN"
            for baris in baris_pesan:
                if 'DISTRICT' in baris.upper():
                    parts = baris.split('DISTRICT')
                    if len(parts) > 1:
                        nama_distrik = parts[1].strip().replace('*', '')
            
            for baris in baris_pesan:
                if 'GPON' in baris.upper() and '|' in baris:
                    bagian = [b.strip() for b in baris.split('|')]
                    if len(bagian) >= 1:
                        hostname = normalisasi_hostname(bagian[0])
                        data_gabungan = f"{nama_distrik} | {baris.strip()}"
                        data_gpon_down[hostname] = data_gabungan
                        ada_perubahan = True
                        hostname_terupdate.add(hostname)
                        
                        if hostname in data_gpon_up:
                            del data_gpon_up[hostname]

        elif '| UP' in teks_pesan_upper:
            for baris in baris_pesan:
                if 'GPON' in baris.upper() and '| UP' in baris.upper() and 'UPLINK' not in baris.upper():
                    bagian = [b.strip() for b in baris.split('|')]
                    hostname = next((b for b in bagian if 'GPON' in b.upper()), None)
                    if hostname:
                        hostname = normalisasi_hostname(hostname)
                        data_gpon_up[hostname] = baris.strip()
                        ada_perubahan = True
                        
                        if hostname in data_gpon_down:
                            del data_gpon_down[hostname]

        if ada_perubahan:
            simpan_log("🔔 Perubahan data GPON terdeteksi. Memperbarui laporan...")

            try:
                mapping_metadata = ambil_mapping_metadata()
                simpan_log(
                    f"Berhasil mengambil {len(mapping_metadata)} data metadata OLT "
                    f"dari GID {GID_SHEET_METADATA}"
                )
            except Exception as exc:
                mapping_metadata = {}
                simpan_log(
                    f"Gagal mengambil metadata OLT, menggunakan '-': {exc}"
                )

            teks_laporan_baru = buat_laporan_list(mapping_metadata)
            simpan_ke_file_laporan(teks_laporan_baru)
            kirim_pesan_wa(teks_laporan_baru)

            daftar_eskalasi = ambil_olt_down_lebih_satu_jam(
                hostname_pemicu=hostname_terupdate
            )
            teks_eskalasi, mentions = buat_pesan_eskalasi(
                daftar_down=daftar_eskalasi,
                mapping_metadata=mapping_metadata,
            )
            if teks_eskalasi:
                kirim_pesan_wa(teks_eskalasi, mentions)

    except Exception as e:
        simpan_log(f"❌ Error dalam proses_pesan_baru: {e}")
        simpan_log(traceback.format_exc())


async def main():
    simpan_log("Memulai koneksi ke Telegram...")
    await client.start()
    simpan_log(f"🚀 Program Mirroring Aktif! Mendengarkan {len(daftar_grup_target)} grup...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    with client:
        client.loop.run_until_complete(main())
