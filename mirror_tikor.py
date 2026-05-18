import asyncio
import re
import gspread
from telethon import TelegramClient
from oauth2client.service_account import ServiceAccountCredentials

# --- KONFIGURASI ---
API_ID = 37811433
API_HASH = 'c5656009e5b4d0b70a4f92a605c9eab4'
USERNAME_BOT = '@sc_tif_area1_bot'
FILE_KREDENSIAL = 'kunci_rahasia_google.json'

SPREADSHEETS = [
    {
        'nama': 'Spreadsheet A',
        'url': 'https://docs.google.com/spreadsheets/d/1awIFqR437EmG2PpfnqbTTYzIOSJloOe-d2cyW0XKep8/edit',
        'gid': 0,
        'kolom_tikor': 0,   # Kolom A (index 0)
        'kolom_hasil': 1,   # Kolom B (index 1)
    },
    {
        'nama': 'Spreadsheet B',
        'url': 'https://docs.google.com/spreadsheets/d/1Z7pLJ6X7Ynp_DjeN2O9eXGFkdU_qlzE6v6_xp4z_iKo/edit',
        'gid': 0,
        'kolom_tikor': 61,  # Kolom BJ (index 61)
        'kolom_hasil': 62,  # Kolom BK (index 62)
    },
]

lock_bot = asyncio.Lock()

INTERVAL_MIN = 15
INTERVAL_MAX = 120
INTERVAL_MULTIPLIER = 2

def setup_google_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(FILE_KREDENSIAL, scope)
    client_gs = gspread.authorize(creds)

    sheets = []
    for cfg in SPREADSHEETS:
        spreadsheet = client_gs.open_by_url(cfg['url'])
        sheet = None
        for ws in spreadsheet.worksheets():
            if ws.id == cfg['gid']:
                sheet = ws
                break
        if sheet is None:
            sheet = spreadsheet.sheet1
        sheets.append({**cfg, 'sheet': sheet})
    return sheets

def ekstrak_data_bot(teks_respon):
    match_no_odp = re.search(r'(No nearby ODPs found for coordinate:.*)', teks_respon, re.IGNORECASE)
    if match_no_odp:
        return match_no_odp.group(1)
    match_invalid = re.search(r'(Invalid format\..*)', teks_respon, re.IGNORECASE)
    if match_invalid:
        return "Invalid format"
    blok_alternatif = teks_respon.split("ALTERNATIF #")[1:]
    hasil_odp = []
    for blok in blok_alternatif:
        baris_pertama = blok.split('\n')[0]
        match_jarak = re.search(r'(\d+)\s*m\b', baris_pertama)
        if not match_jarak:
            continue

        jarak = int(match_jarak.group(1))
        if jarak >= 230:
            continue

        match_odp = re.search(r'(ODP-\S+)', blok)
        nama_odp = match_odp.group(1) if match_odp else "ODP-Unknown"

        match_port = re.search(r'Tersedia Port[^\d]*(\d+)', blok, re.IGNORECASE)
        port_idle = match_port.group(1) if match_port else "0"

        match_rx = re.search(r'Feasible Expand[^\d-]*(-?\d+\.\d+)\s*dBm', blok, re.IGNORECASE)
        rx_val = float(match_rx.group(1)) if match_rx else -99.99

        potensi = " (Potensi Expand)" if rx_val > -19.0 else ""
        hasil_odp.append(f"{nama_odp} - {jarak} m - {port_idle} idle - ({rx_val} dBm){potensi}")

    return " | ".join(hasil_odp)

async def kirim_dan_terima(client, tikor):
    """Kirim tikor ke bot dan tunggu balasan. Dilindungi lock agar tidak race."""
    async with lock_bot:
        pesan_kirim = await client.send_message(USERNAME_BOT, f'/check {tikor}')
        print("   Menunggu balasan bot (18 detik)...")
        await asyncio.sleep(18)

        pesan_pesan = await client.get_messages(USERNAME_BOT, min_id=pesan_kirim.id, limit=10)
        teks_gabungan = "\n".join([msg.text for msg in reversed(pesan_pesan) if msg.text])

        hasil_akhir = ekstrak_data_bot(teks_gabungan)
        if not hasil_akhir:
            hasil_akhir = "Tidak ditemukan ODP < 230m"

        await asyncio.sleep(2)
        return hasil_akhir

async def proses_check_tikor(client, sheet_cfg):
    """Scan baris kosong di satu spreadsheet. Return True jika ada data diproses."""
    nama = sheet_cfg['nama']
    sheet = sheet_cfg['sheet']
    kol_tikor = sheet_cfg['kolom_tikor']
    kol_hasil = sheet_cfg['kolom_hasil']
    ada_data = False

    print(f"\n🔍 [{nama}] Memeriksa baris baru...")

    all_data = sheet.get_all_values()

    for i in range(1, len(all_data)):
        baris_data = all_data[i]
        tikor = baris_data[kol_tikor].strip() if len(baris_data) > kol_tikor else ""
        hasil_b = baris_data[kol_hasil].strip() if len(baris_data) > kol_hasil else ""

        baris_ke = i + 1

        if tikor and not hasil_b:
            ada_data = True
            print(f"🚀 [{nama}] Baris {baris_ke}: {tikor}")

            hasil_akhir = await kirim_dan_terima(client, tikor)

            sheet.update_cell(baris_ke, kol_hasil + 1, hasil_akhir)
            print(f"✅ [{nama}] Baris {baris_ke} Terupdate: {hasil_akhir}")

    return ada_data

async def main():
    client = TelegramClient('sesi_mirror_tikor', API_ID, API_HASH)
    await client.start()
    print("🤖 Bot Pemantau Aktif! (2 Spreadsheets)")

    sheets = setup_google_sheets()
    interval = INTERVAL_MIN

    while True:
        try:
            ada_data = False
            for sheet_cfg in sheets:
                if await proses_check_tikor(client, sheet_cfg):
                    ada_data = True
        except Exception as e:
            print(f"⚠️ Terjadi error: {e}. Mencoba lagi dalam 30 detik...")
            await asyncio.sleep(30)
            continue

        if ada_data:
            interval = INTERVAL_MIN
        else:
            interval = min(interval * INTERVAL_MULTIPLIER, INTERVAL_MAX)

        print(f"😴 Tidur {interval} detik (next check)...")
        await asyncio.sleep(interval)

if __name__ == '__main__':
    asyncio.run(main())
