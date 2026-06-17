import asyncio
import os
import time
import requests
import base64
from datetime import datetime
from playwright.async_api import async_playwright
from PIL import Image

# ================== KONFIGURASI WAHA ==================
WAHA_URL = "https://waha-dutxvo095iqn.cgk-lab.sumopod.my.id" 
WAHA_SESSION = "OLTReport"
WAHA_API_KEY = "ROpWNPkTUavqEbnz5zKU4mTiL0HIZoye"
# 120363425065142845@g.us = real
# 120363423984319917@g.us = test
GROUP_ID_TUJUAN = "120363425065142845@g.us"
URL_SPREADSHEET = "https://docs.google.com/spreadsheets/d/13faIcsHI34GjvImRgV_AEUh5MP3NnLWiSfk-Z4O49Do/edit?usp=sharing"
# ======================================================

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
    return os.path.join(FOLDER_GAMBAR, f"Report_ISP_{tanggal_hari_ini()}.png")


def nama_file_log():
    return os.path.join(FOLDER_LOG, "isp_log.txt")


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


async def ambil_screenshot():
    """Mengambil screenshot dari Google Spreadsheet."""
    path_ss = nama_file_ss()
    catat_log(f"Mulai mengambil screenshot: {tanggal_hari_ini()}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 3500, "height": 5000})
        page = await context.new_page()

        target_url = URL_SPREADSHEET.replace(
            "/edit?usp=sharing",
            "/htmlembed?widget=false&headers=false&chrome=false"
        )

        try:
            await page.goto(target_url, wait_until="networkidle", timeout=90000)
            await page.wait_for_timeout(60000)

            batas = await page.evaluate('''() => {
                let maxX = 0, maxY = 0;
                const tds = document.querySelectorAll('td');
                for (let i = 0; i < tds.length; i++) {
                    const td = tds[i];
                    const text = td.innerText.trim();
                    const style = window.getComputedStyle(td);
                    const bgColor = style.backgroundColor;
                    const hasColor = bgColor !== 'rgba(0, 0, 0, 0)'
                        && bgColor !== 'rgb(255, 255, 255)'
                        && bgColor !== 'transparent';
                    if (text !== '' || hasColor) {
                        const rect = td.getBoundingClientRect();
                        if (rect.bottom > maxY) maxY = rect.bottom;
                        if (rect.right > maxX) maxX = rect.right;
                    }
                }
                return { width: maxX, height: maxY };
            }''')

            lebar = batas["width"] + 30
            tinggi = batas["height"] + 30

            if lebar > 30 and tinggi > 30:
                await page.screenshot(
                    path=path_ss,
                    clip={"x": 0, "y": 0, "width": lebar, "height": tinggi}
                )
            else:
                await page.screenshot(path=path_ss, full_page=True)

            catat_log("Screenshot berhasil diambil!")

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
                "filename": f"Report_ISP_{tanggal_hari_ini()}.png",
                "data": encoded_string
            },
            "caption": f"📊 *Reporting NE ISP Down*\n📝 Created by ISP.SBT\nTanggal: {tanggal_hari_ini()}"
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
    """Tugas harian: screenshot -> optimasi -> kirim via WA -> bersihkan storage."""
    catat_log("=" * 50)
    catat_log("🚀 Memulai tugas harian ISP...")

    path_ss = asyncio.run(ambil_screenshot())

    if os.path.exists(path_ss):
        optimalkan_resolusi(path_ss)

    kirim_via_whatsapp(path_ss)

    hapus_gambar(path_ss)

    catat_log("🏁 Tugas harian ISP selesai.")
    catat_log("=" * 50)


if __name__ == "__main__":
    print("=" * 55)
    print("  📱 Auto Screenshot & Kirim WA (ISP)")
    print(f"  📌 Grup Tujuan: {GROUP_ID_TUJUAN}")
    print("=" * 55)

    tugas_harian()