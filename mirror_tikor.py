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
    {
        'nama': 'Spreadsheet C',
        'url': 'https://docs.google.com/spreadsheets/d/1vZCjlRFMlrgoPl7Fl44dnoAOY_JxZ9N58e37py1PoLI/edit',
        'gid': 213178140,
        'kolom_tikor': 29,  # Kolom AD (index 29)
        'kolom_hasil': 30,  # Kolom AE (index 30)
    },
]

lock_bot = asyncio.Lock()

INTERVAL_MIN = 15
INTERVAL_MAX = 120
INTERVAL_MULTIPLIER = 2
TIMEOUT_BUBBLE_PERTAMA = 30
BOT_DIAM_TIMEOUT = 5
RESPON_POLL_INTERVAL = 1
BATAS_PESAN_BOT = 20
BOT_TIDAK_MENJAWAB = "Bot tidak menjawab, coba lagi"


class BotTidakMenjawabError(TimeoutError):
    pass

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
    blok_alternatif = re.split(r'ALTERNATIF\s*#', teks_respon, flags=re.IGNORECASE)[1:]
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
        match_core = re.search(r'Core_Idle:\s*(\d+)', blok, re.IGNORECASE)
        core_idle = match_core.group(1) if match_core else "0"

        potensi = " (Potensi Expand)" if rx_val > -19.0 else ""
        hasil_odp.append(f"{nama_odp} - {jarak} m - {port_idle} idle - Core_Idle: {core_idle} - ({rx_val} dBm){potensi}")

    return " | ".join(hasil_odp)

def pesan_berteks_urut(pesan_pesan):
    pesan_berteks = [
        (getattr(msg, "id", index), index, msg)
        for index, msg in enumerate(pesan_pesan)
        if msg.text
    ]
    pesan_berteks.sort(key=lambda item: (item[0], item[1]))
    return [msg for _, _, msg in pesan_berteks]


def gabungkan_teks_pesan(pesan_pesan):
    return "\n".join([msg.text for msg in pesan_berteks_urut(pesan_pesan)])


def tanda_tangan_pesan(pesan_pesan):
    return tuple(
        (getattr(msg, "id", index), msg.text)
        for index, msg in enumerate(pesan_berteks_urut(pesan_pesan))
    )


async def tunggu_teks_balasan_bot(
    client,
    pesan_kirim_id,
    timeout_bubble_pertama=TIMEOUT_BUBBLE_PERTAMA,
    idle_timeout=BOT_DIAM_TIMEOUT,
    poll_interval=RESPON_POLL_INTERVAL,
    sleep=asyncio.sleep,
    time_func=None,
):
    loop = asyncio.get_running_loop()
    if time_func is None:
        time_func = loop.time

    batas_bubble_pertama = time_func() + timeout_bubble_pertama
    batas_bot_diam = None
    signature_terakhir = ()
    teks_terakhir = ""

    while True:
        pesan_pesan = await client.get_messages(
            USERNAME_BOT,
            min_id=pesan_kirim_id,
            limit=BATAS_PESAN_BOT,
        )
        signature_saat_ini = tanda_tangan_pesan(pesan_pesan)

        if signature_saat_ini:
            if signature_saat_ini != signature_terakhir:
                signature_terakhir = signature_saat_ini
                teks_terakhir = gabungkan_teks_pesan(pesan_pesan)
                batas_bot_diam = time_func() + idle_timeout
                print(
                    f"   Menerima {len(signature_saat_ini)} bubble bot, "
                    f"tunggu bot diam {idle_timeout} detik..."
                )
            elif batas_bot_diam is not None and time_func() >= batas_bot_diam:
                print(
                    f"   Bot diam {idle_timeout} detik, "
                    f"balasan dianggap selesai ({len(signature_saat_ini)} bubble)."
                )
                return teks_terakhir

        elif time_func() >= batas_bubble_pertama:
            raise BotTidakMenjawabError(
                f"Bot tidak mengirim bubble pertama setelah {timeout_bubble_pertama} detik."
            )

        await sleep(poll_interval)

async def kirim_dan_terima(
    client,
    tikor,
    timeout_bubble_pertama=TIMEOUT_BUBBLE_PERTAMA,
    idle_timeout=BOT_DIAM_TIMEOUT,
    poll_interval=RESPON_POLL_INTERVAL,
    sleep=asyncio.sleep,
    time_func=None,
):
    """Kirim tikor ke bot dan tunggu balasan. Dilindungi lock agar tidak race."""
    async with lock_bot:
        pesan_kirim = await client.send_message(USERNAME_BOT, f'/check {tikor}')
        print(
            f"   Menunggu bubble pertama bot (maks {timeout_bubble_pertama} detik), "
            f"lalu tunggu bot diam {idle_timeout} detik..."
        )

        try:
            teks_gabungan = await tunggu_teks_balasan_bot(
                client,
                pesan_kirim.id,
                timeout_bubble_pertama=timeout_bubble_pertama,
                idle_timeout=idle_timeout,
                poll_interval=poll_interval,
                sleep=sleep,
                time_func=time_func,
            )
        except BotTidakMenjawabError as e:
            print(f"   {e}")
            return BOT_TIDAK_MENJAWAB

        hasil_akhir = ekstrak_data_bot(teks_gabungan)
        if not hasil_akhir:
            hasil_akhir = "Tidak ditemukan ODP < 230m"

        await sleep(2)
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
    print("🤖 Bot Pemantau Aktif! (3 Spreadsheets)")

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
