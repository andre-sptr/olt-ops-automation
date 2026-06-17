import asyncio
import os
import requests
import base64
import pandas as pd
from datetime import datetime
from playwright.async_api import async_playwright

# ================== KONFIGURASI ==================
WAHA_URL = "https://waha-dutxvo095iqn.cgk-lab.sumopod.my.id"
WAHA_SESSION = "OLTReport"
WAHA_API_KEY = "ROpWNPkTUavqEbnz5zKU4mTiL0HIZoye"
# 120363422960378808@g.us = real
# 120363423984319917@g.us = test
GROUP_ID_TUJUAN = "120363422960378808@g.us"

URL_SS = "https://docs.google.com/spreadsheets/d/15UqbvxNSuajjE8s8Pr6H_RStt9HR7nfONW17FFSnQ60/edit"
GID_SHEET = "249249530" 
RENTANG_SS = "A1:S18"

FOLDER_GAMBAR = "images"
FOLDER_LOG = "logs"
os.makedirs(FOLDER_GAMBAR, exist_ok=True)
os.makedirs(FOLDER_LOG, exist_ok=True)
# =================================================

def tanggal_hari_ini():
    return datetime.now().strftime("%Y-%m-%d")


def nama_file_ss():
    return os.path.join(FOLDER_GAMBAR, f"Report_MTTR_{tanggal_hari_ini()}.png")


def nama_file_log():
    return os.path.join(FOLDER_LOG, "mttr_log.txt")


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


def get_status_emoji(nilai, threshold=100):
    """Logika: >= threshold adalah Achieve (Hijau). Kosong/NaN dianggap Achieve."""
    if pd.isna(nilai) or str(nilai).strip() == "" or str(nilai).strip() == "-":
        return "🟢"
    
    try:
        cleaned = str(nilai).replace('%', '').strip()
        cleaned = cleaned.replace(',', '.')
        num = float(cleaned)
        return "🟢" if num >= threshold else "🔴"
    except:
        return "⚪"


def ambil_tanggal_indo():
    sekarang = datetime.now()
    bulan = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", 
             "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    return sekarang.strftime(f"%d {bulan[sekarang.month]} %Y")


async def ambil_screenshot():
    path_ss = nama_file_ss()
    target_url = f"{URL_SS.replace('/edit', '/htmlembed')}?gid={GID_SHEET}&range={RENTANG_SS}&widget=false&chrome=false"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 2100, "height": 600})
        try:
            catat_log("📸 Mengambil screenshot...")
            await page.goto(target_url, wait_until="load", timeout=60000)
            await page.wait_for_timeout(8000)

            tables_info = await page.evaluate("""() => {
                const tables = document.querySelectorAll('table');
                return Array.from(tables).map(t => ({
                    className: t.className,
                    id: t.id,
                    role: t.getAttribute('role'),
                    rowCount: t.rows.length
                }));
            }""")

            target_table_index = await page.evaluate("""() => {
                const tables = document.querySelectorAll('table.waffle');
                for (let i = 0; i < tables.length; i++) {
                    if (tables[i].rows.length >= 17 && tables[i].rows.length <= 20) {
                        return i;
                    }
                }
                return 0;
            }""")
            catat_log(f"✅ Menggunakan tabel index: {target_table_index}")
            
            element = page.locator("table.waffle").nth(target_table_index)
            try:
                await element.wait_for(timeout=5000)
            except Exception:
                catat_log("⚠️ Tabel tidak ditemukan...")
                await page.screenshot(path=path_ss, full_page=True)
                catat_log("✅ Screenshot berhasil diambil secara full page.")
                return path_ss
            
            box = await element.bounding_box()

            if box:
                clip = {
                    "x": max(0, box["x"] - 10),
                    "y": max(0, box["y"] - 10),
                    "width": box["width"] + 20,
                    "height": box["height"] + 20
                }
                await page.screenshot(path=path_ss, clip=clip)
                catat_log("✅ Screenshot berhasil diambil.")
            else:
                catat_log("⚠️ Gagal mendapatkan bounding box...")
                await page.screenshot(path=path_ss, full_page=True)
                catat_log("✅ Screenshot berhasil diambil secara full page.")

        except Exception as e:
            catat_log(f"❌ Gagal Screenshot: {e}")
        finally:
            await browser.close()
    return path_ss


def generate_caption():
    """Membaca data dari GSheets untuk membuat teks caption."""
    csv_url = f"{URL_SS.replace('/edit', '/export')}?format=csv&gid={GID_SHEET}"
    
    try:
        catat_log("📊 Mengunduh dan membaca data spreadsheet...")
        df = pd.read_csv(csv_url, header=None)
        
        status_data = {
            "Low":          {"Btm": df.iloc[3, 5], "Bkt": df.iloc[4, 5], "Dmi": df.iloc[5, 5], "Pdg": df.iloc[6, 5], "Pku": df.iloc[7, 5], "threshold": 91},
            "Minor":        {"Btm": df.iloc[3, 10], "Bkt": df.iloc[4, 10], "Dmi": df.iloc[5, 10], "Pdg": df.iloc[6, 10], "Pku": df.iloc[7, 10], "threshold": 91},
            "Major":        {"Btm": df.iloc[12, 5], "Bkt": df.iloc[13, 5], "Dmi": df.iloc[14, 5], "Pdg": df.iloc[15, 5], "Pku": df.iloc[16, 5], "threshold": 82},
            "Critical":     {"Btm": df.iloc[12, 10], "Bkt": df.iloc[13, 10], "Dmi": df.iloc[14, 10], "Pdg": df.iloc[15, 10], "Pku": df.iloc[16, 10], "threshold": 73},
            "Premium Site": {"Btm": df.iloc[3, 17], "Bkt": df.iloc[4, 17], "Dmi": df.iloc[5, 17], "Pdg": df.iloc[6, 17], "Pku": df.iloc[7, 17], "threshold": 90},
        }

        text = (
            f"*Report Performansi MBB Regional Sumbagteng*\n"
            f"*CNOP 3.0 : MTTRi All*\n"
            f"*Tanggal {ambil_tanggal_indo()}*\n\n"
            f"🟢 Achieve\n"
            f"🔴 Not Achieve\n\n"
        )

        for kategori, lokasi in status_data.items():
            threshold = lokasi.pop("threshold")
            text += f"*MTTRi {kategori} ({threshold}%)*\n"
            text += f"Batam {get_status_emoji(lokasi['Btm'], threshold)}\n"
            text += f"Bukittinggi {get_status_emoji(lokasi['Bkt'], threshold)}\n"
            text += f"Dumai {get_status_emoji(lokasi['Dmi'], threshold)}\n"
            text += f"Padang {get_status_emoji(lokasi['Pdg'], threshold)}\n"
            text += f"Pekanbaru {get_status_emoji(lokasi['Pku'], threshold)}\n\n"
        
        return text.strip()
        
    except Exception as e:
        catat_log(f"❌ Gagal generate caption: {e}")
        return f"*Report Performansi MBB Regional Sumbagteng*\n(Gagal memproses data otomatis: {e})"


def kirim_ke_wa(path_gambar, caption_teks):
    if not os.path.exists(path_gambar): 
        catat_log("❌ File gambar tidak ditemukan, batal mengirim.")
        return
    
    catat_log(f"📨 Mengirim ke WhatsApp grup: {GROUP_ID_TUJUAN} via WAHA...")
    with open(path_gambar, "rb") as f:
        encoded_string = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "session": WAHA_SESSION,
        "chatId": GROUP_ID_TUJUAN,
        "file": {
            "mimetype": "image/png", 
            "filename": f"Report_MTTR_{tanggal_hari_ini()}.png", 
            "data": encoded_string
        },
        "caption": caption_teks
    }
    
    headers = {"X-Api-Key": WAHA_API_KEY, "Content-Type": "application/json"}
    
    try:
        response = requests.post(f"{WAHA_URL}/api/sendImage", json=payload, headers=headers, timeout=60)
        if response.status_code in [200, 201]:
            catat_log("✅ Laporan berhasil dikirim ke WhatsApp!")
        else:
            catat_log(f"❌ Gagal kirim WA. Status: {response.status_code}, Info: {response.text}")
    except Exception as e:
        catat_log(f"❌ Error saat mengirim ke WA: {e}")


def hapus_gambar(path_gambar):
    """Menghapus gambar dari server untuk menghemat storage VPS."""
    try:
        if os.path.exists(path_gambar):
            os.remove(path_gambar)
            catat_log("🗑️ File gambar berhasil dihapus dari storage VPS.")
    except Exception as e:
        catat_log(f"⚠️ Gagal menghapus file gambar: {e}")


async def main():
    catat_log("=" * 50)
    catat_log("🚀 Memulai proses Laporan MBB Regional (MTTR)...")
    
    path_ss = await ambil_screenshot()
    
    caption = generate_caption()
    
    kirim_ke_wa(path_ss, caption)
    
    hapus_gambar(path_ss)
    
    catat_log("🏁 Tugas harian MTTR selesai.")
    catat_log("=" * 50)


if __name__ == "__main__":
    print("=" * 55)
    print("  📱 Auto Screenshot & Kirim WA (MTTR)")
    print(f"  📌 Grup Tujuan: {GROUP_ID_TUJUAN}")
    print("=" * 55)
    asyncio.run(main())