import asyncio
import os
import requests
import base64
from datetime import datetime
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
from PIL import Image

# ================== KONFIGURASI ==================
WAHA_URL = "https://waha-dutxvo095iqn.cgk-lab.sumopod.my.id"
WAHA_SESSION = "BotWA"
WAHA_API_KEY = "ROpWNPkTUavqEbnz5zKU4mTiL0HIZoye"
GROUP_ID_TUJUAN = "120363424766297041@g.us"

URL_SPREADSHEET = "https://docs.google.com/spreadsheets/d/1QvP6JCOekZ4b6sUbG3gaua3dp9yGD-XNgMTuVcB1jPU/edit?usp=sharing"
GID_SHEET = "109817928"
RENTANG_CELL = "M2:AG70"

FOLDER_GAMBAR = "images"
FOLDER_LOG = "logs"
os.makedirs(FOLDER_GAMBAR, exist_ok=True)
os.makedirs(FOLDER_LOG, exist_ok=True)

MAX_RETRY_SCREENSHOT = 3
NAVIGATION_TIMEOUT_MS = 90000
SELECTOR_TIMEOUT_MS = 60000
SCREENSHOT_TIMEOUT_MS = 60000
RETRY_DELAY_MS = 10000
# =================================================


def cari_group_id(nama_grup):
    """Mencari Group ID berdasarkan nama grup via WAHA API."""
    url = f"{WAHA_URL.rstrip('/')}/api/{WAHA_SESSION}/chats"
    headers = {
        "Accept": "application/json",
        "X-Api-Key": WAHA_API_KEY
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            chats = response.json()
            for chat in chats:
                chat_id = chat.get("id", "")
                chat_name = chat.get("name", "")
                if chat_name == nama_grup and chat_id.endswith("@g.us"):
                    return chat_id
        catat_log(f"❌ Grup '{nama_grup}' tidak ditemukan.")
    except Exception as e:
        catat_log(f"❌ Error saat mencari grup: {e}")
    return None


def tanggal_hari_ini():
    return datetime.now().strftime("%Y-%m-%d")


def nama_bulan_indonesia(angka_bulan):
    bulan = [
        "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember"
    ]
    return bulan[angka_bulan]


def tanggal_indo():
    sekarang = datetime.now()
    return f"{sekarang.day} {nama_bulan_indonesia(sekarang.month)} {sekarang.year}"


def bulan_indo():
    sekarang = datetime.now()
    return f"{nama_bulan_indonesia(sekarang.month)} {sekarang.year}"


def nama_file_ss():
    return os.path.join(FOLDER_GAMBAR, f"Reporting_YtD_{tanggal_hari_ini()}.png")


def nama_file_log():
    return os.path.join(FOLDER_LOG, "ytd_log.txt")


def buat_url_screenshot():
    """Membuat URL embed Google Sheet untuk area yang akan di-screenshot."""
    base_url = URL_SPREADSHEET.split("/edit", 1)[0]
    return (
        f"{base_url}/htmlembed"
        f"?gid={GID_SHEET}&range={RENTANG_CELL}"
        "&widget=false&headers=false&chrome=false"
    )


def ringkas_error(error):
    """Ambil baris utama error agar log retry tetap mudah dibaca."""
    return str(error).splitlines()[0]


def catat_log(pesan):
    """Mencatat log dengan fitur auto-reset jika masuk hari baru."""
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
        catat_log(f"Gagal mengoptimalkan resolusi: {e}")


async def simpan_debug_halaman(page, percobaan, error):
    """Simpan kondisi halaman saat gagal agar penyebab timeout bisa dilihat."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nama_dasar = os.path.join(FOLDER_LOG, f"ytd_debug_{timestamp}_try{percobaan}")
    path_html = f"{nama_dasar}.html"
    path_png = f"{nama_dasar}.png"

    try:
        html = await page.content()
        with open(path_html, "w", encoding="utf-8") as f:
            f.write(html)

        try:
            await page.screenshot(path=path_png, full_page=True, timeout=15000)
            catat_log(f"Debug halaman tersimpan: {path_html} dan {path_png}")
        except Exception as e_screenshot:
            catat_log(f"Debug HTML tersimpan: {path_html}")
            catat_log(f"Gagal menyimpan screenshot debug: {ringkas_error(e_screenshot)}")
    except Exception as e_debug:
        catat_log(
            "Gagal menyimpan debug halaman "
            f"setelah error '{ringkas_error(error)}': {ringkas_error(e_debug)}"
        )


async def ambil_screenshot():
    """Mengambil screenshot dari area Google Sheet dengan retry dan debug log."""
    path_ss = nama_file_ss()

    if path_ss and os.path.exists(path_ss):
        os.remove(path_ss)

    target_url = buat_url_screenshot()
    catat_log(f"Mulai mengambil screenshot area {RENTANG_CELL} pada: {tanggal_hari_ini()}")
    catat_log(f"URL screenshot: {target_url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 3000, "height": 1500})

        try:
            for percobaan in range(1, MAX_RETRY_SCREENSHOT + 1):
                page = await context.new_page()
                try:
                    catat_log(
                        f"Percobaan screenshot {percobaan}/{MAX_RETRY_SCREENSHOT}: "
                        "membuka Google Sheets..."
                    )
                    response = await page.goto(
                        target_url,
                        wait_until="domcontentloaded",
                        timeout=NAVIGATION_TIMEOUT_MS,
                    )
                    if response:
                        catat_log(f"Status halaman Google Sheets: HTTP {response.status}")

                    await page.wait_for_selector(
                        "table.waffle:visible",
                        timeout=SELECTOR_TIMEOUT_MS,
                    )
                    await page.wait_for_timeout(3000)

                    tabel_sheet = page.locator("table.waffle:visible").first
                    await tabel_sheet.screenshot(
                        path=path_ss,
                        timeout=SCREENSHOT_TIMEOUT_MS,
                    )
                    catat_log("Screenshot YtD berhasil diambil.")
                    return path_ss

                except PlaywrightTimeoutError as e:
                    catat_log(
                        f"Timeout screenshot pada percobaan {percobaan}/"
                        f"{MAX_RETRY_SCREENSHOT}: {ringkas_error(e)}"
                    )
                    if percobaan == MAX_RETRY_SCREENSHOT:
                        await simpan_debug_halaman(page, percobaan, e)
                except Exception as e:
                    catat_log(
                        f"Gagal screenshot pada percobaan {percobaan}/"
                        f"{MAX_RETRY_SCREENSHOT}: {ringkas_error(e)}"
                    )
                    if percobaan == MAX_RETRY_SCREENSHOT:
                        await simpan_debug_halaman(page, percobaan, e)
                finally:
                    await page.close()

                if percobaan < MAX_RETRY_SCREENSHOT:
                    catat_log(f"Menunggu {RETRY_DELAY_MS // 1000} detik sebelum retry...")
                    await asyncio.sleep(RETRY_DELAY_MS / 1000)
        finally:
            await browser.close()

    catat_log("Gagal mengambil screenshot YtD setelah semua percobaan.")
    return None


def buat_session_baru():
    """Buat requests session baru tanpa connection pooling."""
    s = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        max_retries=0,
        pool_connections=1,
        pool_maxsize=1
    )
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


def kirim_via_whatsapp(path_gambar):
    """Mengirim gambar ke WhatsApp via WAHA API."""
    if not os.path.exists(path_gambar):
        catat_log("File gambar tidak ditemukan, pengiriman dibatalkan.")
        return False

    catat_log(f"Mengirim gambar ke grup WhatsApp: {GROUP_ID_TUJUAN} via WAHA")
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

        payload = {
            "session": WAHA_SESSION,
            "chatId": GROUP_ID_TUJUAN,
            "file": {
                "mimetype": "image/png",
                "filename": f"Reporting_YtD_{tanggal_hari_ini()}.png",
                "data": encoded_string
            },
            "caption": f"*Laporan YtD Jumlah Gangguan Node-B FO | MBB*\n\n*Periode: {bulan_indo()}*\n(Cut Off Tanggal {tanggal_indo()})"
        }

        response = session.post(url, headers=headers, json=payload, timeout=60)
        
        if response.status_code in [200, 201]:
            catat_log("✅ Berhasil dikirim ke WhatsApp via WAHA!")
            return True
        else:
            catat_log(f"❌ Gagal mengirim. Status: {response.status_code}, Response: {response.text}")
            return False

    except (ConnectionResetError, requests.exceptions.ConnectionError) as e:
        catat_log(f"⚠️ Koneksi terputus setelah request: {e}")
        return True
    except Exception as e:
        catat_log(f"❌ Error saat mengirim via WhatsApp: {e}")
        return False
    finally:
        session.close()


def hapus_gambar(path_gambar):
    """Menghapus gambar dari server untuk menghemat storage VPS."""
    try:
        if os.path.exists(path_gambar):
            os.remove(path_gambar)
            catat_log("🗑️ File gambar berhasil dihapus dari storage VPS.")
    except Exception as e:
        catat_log(f"⚠️ Gagal menghapus file gambar: {e}")


def tugas_harian():
    """Alur utama program."""
    catat_log("=" * 50)
    catat_log("🚀 Memulai tugas harian YtD...")

    path_ss = asyncio.run(ambil_screenshot())

    if path_ss and os.path.exists(path_ss):
        optimalkan_resolusi(path_ss)
        
        kirim_via_whatsapp(path_ss)
        
        hapus_gambar(path_ss)
    else:
        catat_log("❌ Proses dibatalkan karena tidak ada gambar yang berhasil diambil.")

    catat_log("🏁 Tugas harian YtD selesai.")
    catat_log("=" * 50)


if __name__ == "__main__":
    print("=" * 55)
    print("  📱 Auto Screenshot & Kirim WA (YtD)")
    print(f"  📌 Grup Tujuan: {GROUP_ID_TUJUAN}")
    print("=" * 55)

    tugas_harian()
