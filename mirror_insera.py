import asyncio
import os
import requests
import base64
from datetime import datetime
from telethon import TelegramClient, events
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import numpy as np
from playwright.async_api import async_playwright
from PIL import Image

# ==========================================
# 1. KONFIGURASI TELEGRAM
# ==========================================
api_id = 35153027
api_hash = '275a7916b30391e446366433d5427086'
# -1003202563880 Real
# -4883113309 Test
ID_GRUP_TARGET = -1003202563880, -4883113309

client = TelegramClient('sesi_mirror_insera', api_id, api_hash)

# ==========================================
# 2. KONFIGURASI GOOGLE SHEETS
# ==========================================
scope = ["https://spreadsheets.google.com/feeds", 
         "https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive.file", 
         "https://www.googleapis.com/auth/drive"]

creds = ServiceAccountCredentials.from_json_keyfile_name("kunci_rahasia_google.json", scope)
client_gs = gspread.authorize(creds)

SPREADSHEET_ID = "1Jl-povDud6JKpb4qqB8pRIA0FbpB6lbNomhs9iL5F98"
GID_SHEET_TARGET = 0

# ==========================================
# 3. KONFIGURASI WAHA & SCREENSHOT
# ==========================================
WAHA_URL = "https://waha-dutxvo095iqn.cgk-lab.sumopod.my.id"
WAHA_SESSION = "OLTReport"
WAHA_API_KEY = "ROpWNPkTUavqEbnz5zKU4mTiL0HIZoye"
GROUP_ID_TUJUAN = [
    "120363408272932837@g.us", # Real
    "120363406101184780@g.us", # Real
    # "120363423984319917@g.us", # Test
]

URL_PUBLISHED = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQMeEHrKcSrqZcoiFvTbXOFv-TxTj0BojoPRm5go1PZBlLHzyjVGiVyDmYfMEIUJ3hDQb1mQGfpHfsC/pubhtml" 
GID_SHEET_SS = "633289218"

# ==========================================
# 4. MANAJEMEN FOLDER & LOG
# ==========================================
FOLDER_LOG = "logs"
FOLDER_GAMBAR = "images"
os.makedirs(FOLDER_LOG, exist_ok=True)
os.makedirs(FOLDER_GAMBAR, exist_ok=True)

def tanggal_hari_ini():
    return datetime.now().strftime("%Y-%m-%d")

def nama_file_log():
    return os.path.join(FOLDER_LOG, "mirror_insera_log.txt")

def nama_file_ss(label=""):
    if label:
        return os.path.join(FOLDER_GAMBAR, f"Report_Insera_{tanggal_hari_ini()}_{label}.png")
    return os.path.join(FOLDER_GAMBAR, f"Report_Insera_{tanggal_hari_ini()}.png")

def catat_log(pesan):
    waktu = datetime.now().strftime("%H:%M:%S")
    tanggal_sekarang = tanggal_hari_ini()
    pesan_log = f"[{waktu}] {pesan}"
    print(pesan_log)

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

def hapus_file(path_file):
    try:
        if os.path.exists(path_file):
            os.remove(path_file)
            catat_log(f"🗑️ File lokal '{path_file}' berhasil dihapus.")
    except Exception as e:
        catat_log(f"⚠️ Gagal menghapus file lokal: {e}")

def _nilai_aman_json(v):
    """Konversi satu nilai sel agar bisa di-serialize ke JSON (Google Sheets API).

    - NaN / NaT / None        -> "" (string kosong)
    - Timestamp / datetime    -> string "%Y-%m-%d %H:%M:%S"
    - tipe numpy (int64, dll) -> tipe Python native (angka tetap angka)
    """
    if v is None:
        return ""
    if not isinstance(v, str) and pd.isna(v):
        return ""
    if isinstance(v, datetime):  # pandas.Timestamp adalah turunan datetime
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, np.generic):
        return v.item()
    return v

def siapkan_data_sheets(df):
    """Ubah DataFrame menjadi list-of-list yang aman dikirim ke Google Sheets."""
    return [[_nilai_aman_json(v) for v in baris] for baris in df.values.tolist()]

# ==========================================
# 5. FUNGSI SCREENSHOT & WAHA
# ==========================================
def optimalkan_resolusi(path_gambar):
    try:
        img = Image.open(path_gambar)
        batas_maks = 2500
        if img.width > batas_maks or img.height > batas_maks:
            rasio = min(batas_maks / img.width, batas_maks / img.height)
            ukuran_baru = (int(img.width * rasio), int(img.height * rasio))
            img = img.resize(ukuran_baru, Image.Resampling.LANCZOS)
            img.save(path_gambar)
    except Exception as e:
        catat_log(f"⚠️ Gagal mengoptimalkan resolusi: {e}")

async def ambil_screenshot(rentang_cell, label=""):
    path_ss = nama_file_ss(label)
    if os.path.exists(path_ss):
        os.remove(path_ss)
        
    catat_log(f"📸 Mulai memproses screenshot area {rentang_cell}...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 3000, "height": 1500})
        page = await context.new_page()

        target_url = f"{URL_PUBLISHED}?gid={GID_SHEET_SS}&single=true&range={rentang_cell}&widget=false&headers=false&chrome=false"

        try:
            catat_log(f"-> Mengakses URL untuk rentang {rentang_cell}...")
            await page.goto(target_url, wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_selector("table.waffle:visible", timeout=60000)
            await page.wait_for_timeout(3000) 

            await page.evaluate("""() => {
                const images = document.querySelectorAll('img');
                images.forEach(img => {
                    img.style.border = 'none';
                    img.style.outline = 'none';
                    
                    let parent = img.parentElement;
                    while (parent && parent.tagName !== 'TABLE') {
                        parent.style.border = 'none';
                        if (parent.tagName === 'TD' || parent.tagName === 'TH') {
                            parent.style.borderTop = 'none';
                            parent.style.borderRight = 'none';
                            parent.style.borderBottom = 'none';
                            parent.style.borderLeft = 'none';
                            break;
                        }
                        parent = parent.parentElement;
                    }
                });
            }""")

            tabel_sheet = page.locator("table.waffle:visible").first
            
            berhasil_ss = False
            for percobaan in range(1, 4):
                try:
                    catat_log(f"-> Mengambil tangkapan layar {rentang_cell} (Percobaan {percobaan}/3)...")
                    await tabel_sheet.screenshot(path=path_ss, timeout=60000)
                    catat_log(f"✅ Screenshot {label} ({rentang_cell}) berhasil diambil!")
                    berhasil_ss = True
                    break
                except Exception as e_ss:
                    catat_log(f"⚠️ Gagal mengambil screenshot pada percobaan {percobaan}: {e_ss}")
                    if percobaan < 3:
                        catat_log("🔄 Menunggu 5 detik sebelum mencoba lagi...")
                        await page.wait_for_timeout(5000)
            
            if not berhasil_ss:
                catat_log(f"❌ Menyerah, gagal mengambil screenshot untuk {rentang_cell} setelah 3 percobaan.")
                return None

        except Exception as e:
            catat_log(f"❌ Gagal memuat halaman untuk screenshot: {e}")
            return None
        finally:
            await browser.close()

    return path_ss

def buat_session_baru():
    s = requests.Session()
    adapter = requests.adapters.HTTPAdapter(max_retries=0, pool_connections=1, pool_maxsize=1)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

def kirim_via_whatsapp(path_gambar, info_bagian=""):
    if not path_gambar or not os.path.exists(path_gambar):
        catat_log(f"❌ File gambar {info_bagian} tidak ditemukan, pengiriman WA dibatalkan.")
        return False

    session = buat_session_baru()
    try:
        with open(path_gambar, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode("utf-8")

        url = f"{WAHA_URL.rstrip('/')}/api/sendImage"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Api-Key": WAHA_API_KEY,
            "Connection": "close"
        }

        waktu_caption = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        label_bagian = f"({info_bagian})" if info_bagian else ""
        
        if info_bagian == "Part 2":
            judul_utama = "Monitor Tiket Open TTR 6 JAM"
        else:
            judul_utama = "Monitor Tiket Open TTR 3 JAM"

        caption_baru = (
            f"📊 *{judul_utama}*\n"
            f"📝 Created by FBB.SBT\n"
            f"📅 Tanggal: {waktu_caption}\n"
            f" Check Tiket : https://tlkm.id/KIyeooFgn5GCeh"
        )
        
        nama_file_asli = os.path.basename(path_gambar)

        for group_id in GROUP_ID_TUJUAN:
            catat_log(f"🚀 Mengirim {info_bagian} ke WhatsApp: {group_id}...")
            payload = {
                "session": WAHA_SESSION,
                "chatId": group_id,
                "file": {
                    "mimetype": "image/png",
                    "filename": nama_file_asli,
                    "data": encoded_string
                },
                "caption": caption_baru
            }

            try:
                response = session.post(url, headers=headers, json=payload, timeout=60)
                if response.status_code in [200, 201]:
                    catat_log(f"✅ {info_bagian} berhasil dikirim ke WhatsApp ({group_id})!")
                else:
                    catat_log(f"❌ Gagal mengirim {info_bagian} ke {group_id}. Status: {response.status_code}")
            except Exception as e:
                catat_log(f"⚠️ Koneksi terputus ke {group_id} saat mengirim {info_bagian}: {e}")
            
    except Exception as e:
        catat_log(f"❌ Error keseluruhan saat mengirim via WhatsApp: {e}")
    finally:
        session.close()

# ==========================================
# 6. LOGIKA UTAMA BOT (TELEGRAM)
# ==========================================
@client.on(events.NewMessage(chats=ID_GRUP_TARGET))
async def proses_dokumen_baru(event):
    if event.message.document:
        nama_file = event.message.file.name
        
        if nama_file and "Report TTR WSA" in nama_file and nama_file.endswith(".xlsx"):
            catat_log(f"🔔 File target terdeteksi: {nama_file}")
            
            lokasi_unduh = f"./{nama_file}"
                
            try:
                catat_log("-> Sedang mengunduh file dari Telegram...")
                await client.download_media(event.message, file=lokasi_unduh)
                catat_log("-> File berhasil diunduh. Sedang membaca dan menyaring data...")
                
                df = pd.read_excel(lokasi_unduh, sheet_name="Insera", engine="openpyxl")
                df.columns = df.columns.astype(str).str.strip()
                
                cabang_target = ["BATAM", "PADANG", "BUKIT TINGGI", "BUKITTINGGI", "PEKANBARU", "DUMAI"]
                
                if "BRANCH" in df.columns:
                    df["BRANCH"] = df["BRANCH"].astype(str).str.strip().str.upper()
                    df = df[df["BRANCH"].isin(cabang_target)]
                else:
                    col_cc = df.columns[80]
                    df[col_cc] = df[col_cc].astype(str).str.strip().str.upper()
                    df = df[df[col_cc].isin(cabang_target)]
                
                df = df.iloc[:, :80]
                df = df.fillna("")
                data_untuk_dikirim = siapkan_data_sheets(df)
                
                catat_log(f"-> Data berhasil difilter: {len(data_untuk_dikirim)} baris ditemukan. Memperbarui Google Sheets...")
                
                spreadsheet = client_gs.open_by_key(SPREADSHEET_ID)
                worksheet = spreadsheet.get_worksheet_by_id(GID_SHEET_TARGET)
                worksheet.batch_clear(["A2:CB"])
                
                if len(data_untuk_dikirim) > 0:
                    worksheet.update(range_name='A2', values=data_untuk_dikirim)
                    catat_log(f"✅ SUKSES! {len(data_untuk_dikirim)} baris data berhasil ditimpa ke sheet.")
                    catat_log("⏳ Menunggu 15 detik agar Google Sheets web ter-refresh...")
                    await asyncio.sleep(15)
                    
                    rentang_1 = "B6:AG39"
                    rentang_2 = "B40:AG72"
                    MAX_RETRY = 5

                    async def proses_screenshot(rentang, label, info):
                        path_ss = await ambil_screenshot(rentang, label=label)
                        if path_ss:
                            optimalkan_resolusi(path_ss)
                            await asyncio.to_thread(kirim_via_whatsapp, path_ss, info)
                            hapus_file(path_ss)
                            return True
                        return False

                    sukses_1 = await proses_screenshot(rentang_1, "Part_1", "Part 1")
                    if not sukses_1:
                        catat_log("⚠️ Part 1 gagal di percobaan pertama. Lanjut ke Part 2 dulu, Part 1 akan dicoba lagi setelahnya.")

                    catat_log("⏳ Jeda 5 detik sebelum mengambil screenshot bagian ke-2...")
                    await asyncio.sleep(5)

                    sukses_2 = await proses_screenshot(rentang_2, "Part_2", "Part 2")
                    if not sukses_2:
                        catat_log("⚠️ Part 2 gagal di percobaan pertama. Akan dicoba ulang nanti.")

                    for nama, rentang, label, info, sudah_sukses in [
                        ("Part 1", rentang_1, "Part_1", "Part 1", sukses_1),
                        ("Part 2", rentang_2, "Part_2", "Part 2", sukses_2),
                    ]:
                        if sudah_sukses:
                            continue
                        catat_log(f"🔁 Mencoba ulang screenshot {nama} (maks {MAX_RETRY}x)...")
                        berhasil = False
                        for percobaan_ulang in range(1, MAX_RETRY + 1):
                            catat_log(f"🔁 Percobaan ulang {nama} ke-{percobaan_ulang}/{MAX_RETRY}...")
                            await asyncio.sleep(10)
                            if await proses_screenshot(rentang, label, info):
                                catat_log(f"✅ {nama} akhirnya berhasil setelah {percobaan_ulang} percobaan ulang.")
                                berhasil = True
                                break
                            else:
                                catat_log(f"⚠️ Percobaan ulang {nama} ke-{percobaan_ulang} masih gagal.")
                        if not berhasil:
                            catat_log(f"❌ Menyerah pada {nama} setelah {MAX_RETRY} percobaan ulang.")
                    
                else:
                    catat_log("⚠️ Proses selesai. Namun tidak ada data yang masuk kriteria (Cabang tidak ditemukan).")

            except Exception as e:
                catat_log(f"❌ TERJADI KESALAHAN saat memproses {nama_file}: {e}")
                
            finally:
                if lokasi_unduh:
                    hapus_file(lokasi_unduh)

# ==========================================
# 7. MENJALANKAN BOT
# ==========================================
async def main():
    catat_log("Memulai koneksi ke Telegram...")
    await client.get_dialogs() 
    catat_log("🚀 Program Pemantau Report TTR WSA Aktif! Mendengarkan grup...")
    await client.run_until_disconnected()

with client:
    client.loop.run_until_complete(main())