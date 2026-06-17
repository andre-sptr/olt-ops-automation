import asyncio
import os
import time
import requests
import base64
from datetime import datetime
from playwright.async_api import async_playwright
from PIL import Image, ImageChops 

# ================== KONFIGURASI WAHA ==================
WAHA_URL = "https://waha-dutxvo095iqn.cgk-lab.sumopod.my.id" 
WAHA_SESSION = "OLTReport"
WAHA_API_KEY = "ROpWNPkTUavqEbnz5zKU4mTiL0HIZoye"
# 120363421972540697@g.us = real
# 120363423984319917@g.us = test
GROUP_ID_TUJUAN = "120363421972540697@g.us"

# ================== KONFIGURASI GOOGLE SHEET ==================
URL_SPREADSHEET = "https://docs.google.com/spreadsheets/d/14-kuUd115VsqmrR88MKqe3jtq_zdlYarB7HvNIDa4fE/edit?usp=sharing"
GID_SHEET = "1742966914" 
RENTANG_SEL = "B1:N29" 
PADDING_GAMBAR = 30
# ==============================================================

FOLDER_GAMBAR = "images"
FOLDER_LOG = "logs"
os.makedirs(FOLDER_GAMBAR, exist_ok=True)
os.makedirs(FOLDER_LOG, exist_ok=True)


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


def nama_file_ss():
    return os.path.join(FOLDER_GAMBAR, f"Report_HK_{tanggal_hari_ini()}.png")


def nama_file_log():
    return os.path.join(FOLDER_LOG, "hk_log.txt")


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


def potong_area_putih(path_gambar):
    """Memotong margin putih, dengan menyisakan sedikit jarak (padding)."""
    try:
        img = Image.open(path_gambar)
        img_rgb = img.convert("RGB")
        
        bg_putih = Image.new(img_rgb.mode, img_rgb.size, (255, 255, 255))
        diff = ImageChops.difference(img_rgb, bg_putih)
        bbox = diff.getbbox()
        
        if bbox:
            left, top, right, bottom = bbox
            
            new_left = max(0, left - PADDING_GAMBAR)
            new_top = max(0, top - PADDING_GAMBAR)
            new_right = min(img.width, right + PADDING_GAMBAR)
            new_bottom = min(img.height, bottom + PADDING_GAMBAR)
            
            new_bbox = (new_left, new_top, new_right, new_bottom)
            
            img_potong = img.crop(new_bbox)
            img_potong.save(path_gambar)
            catat_log(f"✂️ Area putih berhasil dipotong dengan padding {PADDING_GAMBAR}px!")
        else:
            catat_log("Tidak ada area putih yang perlu dipotong.")
    except Exception as e:
        catat_log(f"Gagal memotong area putih: {e}")


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


async def ambil_screenshot():
    """Mengambil screenshot dari Google Spreadsheet berdasarkan rentang sel."""
    path_ss = nama_file_ss()
    
    if os.path.exists(path_ss):
        os.remove(path_ss)

    catat_log(f"Mulai mengambil screenshot untuk rentang {RENTANG_SEL}: {tanggal_hari_ini()}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        target_url = URL_SPREADSHEET.replace(
            "/edit?usp=sharing",
            f"/htmlembed?gid={GID_SHEET}&range={RENTANG_SEL}&widget=false&headers=false&chrome=false"
        )

        try:
            await page.goto(target_url, wait_until="networkidle", timeout=90000)
            await page.wait_for_timeout(30000) 
            
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(10000)

            await page.screenshot(
                path=path_ss, 
                full_page=True, 
                timeout=90000,
                animations="disabled"
            )
            
            catat_log(f"Screenshot rentang sel {RENTANG_SEL} berhasil diambil!")

        except Exception as e:
            catat_log(f"Gagal mengambil screenshot: {e}")
        finally:
            await browser.close()

    return path_ss


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

    group_id = GROUP_ID_TUJUAN

    catat_log(f"Mengirim gambar ke grup WhatsApp: {group_id} via WAHA")

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
            "chatId": group_id,
            "file": {
                "mimetype": "image/png",
                "filename": f"Report_HK_{tanggal_hari_ini()}.png",
                "data": encoded_string
            },
            "caption": f"📊 *Reporting Realisasi PT2 SUMBAGTENG HI*\nTanggal: {tanggal_hari_ini()}"
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
        catat_log("⚠️ Pesan kemungkinan TETAP terkirim (server memproses sebelum disconnect).")
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
    """Tugas harian: screenshot -> crop -> optimasi -> kirim via WA -> bersihkan storage."""
    catat_log("=" * 50)
    catat_log("🚀 Memulai tugas harian HK...")

    path_ss = asyncio.run(ambil_screenshot())

    if os.path.exists(path_ss):
        potong_area_putih(path_ss)
        optimalkan_resolusi(path_ss)
        kirim_via_whatsapp(path_ss)
        hapus_gambar(path_ss)
    else:
        catat_log("❌ Proses dibatalkan karena tidak ada gambar yang berhasil diambil.")

    catat_log("🏁 Tugas harian HK selesai.")
    catat_log("=" * 50)


if __name__ == "__main__":
    print("=" * 55)
    print("  📱 Auto Screenshot & Kirim WA (HK)")
    print(f"  📌 Grup Tujuan: {GROUP_ID_TUJUAN}")
    print(f"  📌 Rentang Sel : {RENTANG_SEL}")
    print(f"  📌 Padding Area: {PADDING_GAMBAR}px")
    print("=" * 55)

    tugas_harian()