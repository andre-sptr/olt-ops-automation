import asyncio
import os
import time
import requests
import base64
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, Request
from playwright.async_api import async_playwright
from PIL import Image

app = FastAPI()

# ================== KONFIGURASI ==================
WAHA_URL = "https://waha-dutxvo095iqn.cgk-lab.sumopod.my.id" 
WAHA_SESSION = "OLTReport"
WAHA_API_KEY = "ROpWNPkTUavqEbnz5zKU4mTiL0HIZoye"
# 120363423984319917@g.us Grup Test
# 120363422392801253@g.us Grup Test
# 120363422960378808@g.us Grup Real
# 120363202386395737@g.us Grup Real
GROUP_IDS = [
    "120363422960378808@g.us",
    "120363202386395737@g.us"
]

URL_SPREADSHEET = "https://docs.google.com/spreadsheets/d/1impgFooLJCAaJQ6zgZ8kdRLRgHhBetCfHjge4CsXh-4/edit?gid=238857195#gid=238857195"
TARGET_GID = "238857195"

WAKTU_TUNGGU_ADMIN = 30  
WAKTU_COOLDOWN = 300  
waktu_trigger_terakhir = 0.0
# ==================================================

FOLDER_GAMBAR = "images"
FOLDER_LOG = "logs"
os.makedirs(FOLDER_GAMBAR, exist_ok=True)
os.makedirs(FOLDER_LOG, exist_ok=True)


def waktu_sekarang_lengkap():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def tanggal_hari_ini():
    return datetime.now().strftime("%Y-%m-%d")


def nama_file_ss():
    return os.path.join(FOLDER_GAMBAR, f"Update_GGN_{waktu_sekarang_lengkap()}.png")


def nama_file_log():
    return os.path.join(FOLDER_LOG, "mirror_ggn_log.txt")


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


async def ambil_screenshot():
    """Mengambil screenshot dari Google Spreadsheet."""
    path_ss = nama_file_ss()
    catat_log(f"Mulai mengambil screenshot spreadsheet...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 3000})
        page = await context.new_page()

        target_url = f"https://docs.google.com/spreadsheets/d/1impgFooLJCAaJQ6zgZ8kdRLRgHhBetCfHjge4CsXh-4/htmlembed?widget=false&headers=false&chrome=false&gid={TARGET_GID}"

        try:
            await page.goto(target_url, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(5000)

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

            lebar = batas["width"] + 20
            tinggi = batas["height"] + 20

            await page.screenshot(
                path=path_ss,
                clip={"x": 0, "y": 0, "width": lebar, "height": tinggi}
            )

            catat_log(f"✅ Screenshot berhasil disimpan: {os.path.basename(path_ss)}")
            return path_ss

        except Exception as e:
            catat_log(f"❌ Gagal mengambil screenshot: {e}")
            return None
        finally:
            await browser.close()


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


def kirim_via_whatsapp(path_gambar, chat_id):
    """Mengirim gambar ke WhatsApp via WAHA API."""
    if not path_gambar or not os.path.exists(path_gambar):
        catat_log(f"File gambar tidak ditemukan untuk {chat_id}")
        return False

    catat_log(f"Mengirim gambar ke {chat_id} via WAHA...")
    
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
            "chatId": chat_id,
            "file": {
                "mimetype": "image/png",
                "filename": os.path.basename(path_gambar),
                "data": encoded_string
            },
            "caption": f"🔔 *Update Tiket Gangguan*\n*Waktu:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        }

        response = session.post(url, headers=headers, json=payload, timeout=60)
        
        if response.status_code in [200, 201]:
            catat_log(f"✅ Berhasil dikirim ke {chat_id}!")
        else:
            catat_log(f"❌ Gagal mengirim ke {chat_id}. Status: {response.status_code}")

    except Exception as e:
        catat_log(f"❌ Error saat mengirim ke {chat_id}: {e}")
    finally:
        session.close()


def hapus_gambar(path_gambar):
    """Menghapus gambar dari server untuk menghemat storage VPS."""
    try:
        if path_gambar and os.path.exists(path_gambar):
            os.remove(path_gambar)
            catat_log("🗑️ File gambar berhasil dihapus dari storage VPS.")
    except Exception as e:
        catat_log(f"⚠️ Gagal menghapus file gambar: {e}")


async def proses_tugas():
    """Tugas antrean background: Tunggu -> Screenshot -> Kirim ke Semua -> Hapus"""
    await asyncio.sleep(WAKTU_TUNGGU_ADMIN)
    path_ss = await ambil_screenshot()
    
    if path_ss:
        for gid in GROUP_IDS:
            kirim_via_whatsapp(path_ss, gid)
            await asyncio.sleep(2)
            
        hapus_gambar(path_ss)


@app.post("/trigger-ss")
async def terima_trigger(request: Request, background_tasks: BackgroundTasks):
    global waktu_trigger_terakhir
    waktu_sekarang = time.time()
    
    selisih_waktu = waktu_sekarang - waktu_trigger_terakhir
    if selisih_waktu < WAKTU_COOLDOWN:
        sisa_waktu = int(WAKTU_COOLDOWN - selisih_waktu)
        catat_log(f"⚠️ Cooldown aktif. Trigger diabaikan.")
        return {"status": "ignored", "message": f"Cooldown aktif. Sisa {sisa_waktu} detik."}
    
    waktu_trigger_terakhir = waktu_sekarang
    
    catat_log("🔔 Menerima trigger dari Webhook!")
    background_tasks.add_task(proses_tugas)
    
    return {
        "status": "success", 
        "message": f"Proses masuk antrean. Menunggu {WAKTU_TUNGGU_ADMIN} detik sebelum screenshot."
    }

if __name__ == "__main__":
    import uvicorn
    print("=" * 55)
    print("  🚀 Server Python Berjalan (Multi-Group Mode)")
    print("=" * 55)
    uvicorn.run(app, host="0.0.0.0", port=8000)