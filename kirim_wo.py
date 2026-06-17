import asyncio
import os
import time
import requests
import base64
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from playwright.async_api import async_playwright
from PIL import Image

# ================== KONFIGURASI ==================
WAHA_URL = "https://waha-dutxvo095iqn.cgk-lab.sumopod.my.id"
WAHA_SESSION = "OLTReport"
WAHA_API_KEY = "ROpWNPkTUavqEbnz5zKU4mTiL0HIZoye"
# 120363423984319917@g.us Test
# 120363408272932837@g.us Real
GROUP_ID_TUJUAN = "120363408272932837@g.us"

SPREADSHEET_ID = "1uS0uMw9yHnHOjt00lG8lUuw-ddYiV8882w7-gFZ74cA"
URL_SPREADSHEET = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
GID_SHEET = "792427942"
FILE_KREDENSIAL = "kunci_rahasia_google.json"

# Token "Publish to web" (dari File > Share > Publish to web). htmlembed tidak
# berfungsi untuk sheet ini, jadi screenshot diambil dari grid pubhtml lalu di-crop.
PUBLISH_TOKEN = "2PACX-1vTVA0ksG8lT42r9LTXdPrQA4OZbzWgCeZl3y9-RcxeTqzR8xvbTW2w_Q_Rcc2ui6alV8WuSQmXDkNrq"
URL_GRID = (
    f"https://docs.google.com/spreadsheets/d/e/{PUBLISH_TOKEN}"
    f"/pubhtml/sheet?headers=false&gid={GID_SHEET}"
)

# Baris awal area yang di-screenshot (dinamis mengikuti data terakhir)
BARIS_AWAL = 2
BARIS_FALLBACK = 70  # dipakai bila deteksi baris terakhir gagal

# Tiap distrik = satu blok kolom 8 lebar (teknisi .. grand total) pada sheet yang sama.
# Kolom ringkasan caption diturunkan otomatis dari offset 'kolom_awal':
#   teknisi=+0, aktivasi=+1, ogp_ikr=+4, pickup=+5, ps=+6, grand_total=+7
DISTRIK = [
    {"nama": "Distrik Padang",       "slug": "PDG", "kolom_awal": "C", "kolom_akhir": "J"},
    {"nama": "Distrik Bukit Tinggi", "slug": "BKT", "kolom_awal": "N", "kolom_akhir": "U"},
    {"nama": "Distrik Batam",        "slug": "BTM", "kolom_awal": "Y", "kolom_akhir": "AF"},
]

# Retry berbatas (referensi pola mirror_tikor.py)
MAX_RETRY = 3
JEDA_RETRY = 30  # detik antar putaran retry

FOLDER_GAMBAR = "images"
FOLDER_LOG = "logs"
os.makedirs(FOLDER_GAMBAR, exist_ok=True)
os.makedirs(FOLDER_LOG, exist_ok=True)
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


def nama_file_ss(slug):
    return os.path.join(FOLDER_GAMBAR, f"Reporting_WO_{slug}_{tanggal_hari_ini()}.png")


def nama_file_log():
    return os.path.join(FOLDER_LOG, "wo_log.txt")


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


def _kolom_ke_indeks(huruf):
    """Konversi huruf kolom (mis. 'C') ke indeks 1-based (C -> 3)."""
    indeks = 0
    for ch in huruf.upper():
        indeks = indeks * 26 + (ord(ch) - ord("A") + 1)
    return indeks


def _buka_sheet():
    """Autentikasi service account dan buka worksheet sesuai GID_SHEET."""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(FILE_KREDENSIAL, scope)
    client_gs = gspread.authorize(creds)

    spreadsheet = client_gs.open_by_url(URL_SPREADSHEET)
    for ws in spreadsheet.worksheets():
        if str(ws.id) == str(GID_SHEET):
            return ws
    return spreadsheet.sheet1


def deteksi_baris_terakhir(cfg, semua_nilai):
    """Baris terakhir berisi data pada blok kolom distrik (kolom_awal..kolom_akhir).

    Mengembalikan nomor baris absolut (1-indexed). Bila kosong, BARIS_FALLBACK.
    """
    idx_awal = _kolom_ke_indeks(cfg["kolom_awal"]) - 1   # 0-based
    idx_akhir = _kolom_ke_indeks(cfg["kolom_akhir"])     # batas slice (eksklusif)

    baris_terakhir = 0
    for nomor_baris, baris in enumerate(semua_nilai, start=1):
        if nomor_baris < BARIS_AWAL:
            continue
        sel_area = baris[idx_awal:idx_akhir]
        if any(str(sel).strip() for sel in sel_area):
            baris_terakhir = nomor_baris

    if baris_terakhir == 0:
        catat_log(f"⚠️ [{cfg['nama']}] Tidak ada data terdeteksi, memakai baris fallback.")
        return BARIS_FALLBACK

    catat_log(f"🔎 [{cfg['nama']}] Baris data terakhir terdeteksi: {baris_terakhir}")
    return baris_terakhir


def buat_caption(cfg, semua_nilai):
    """Caption dinamis per distrik.

    Tim/Teknisi = COUNTA(kolom_awal) - 2; Aktivasi/OGP IKR/PICK UP/PS dari baris 4
    pada offset kolom_awal +1/+4/+5/+6.
    """
    base = _kolom_ke_indeks(cfg["kolom_awal"]) - 1  # indeks 0-based kolom teknisi

    jumlah_teknisi = sum(
        1 for baris in semua_nilai if len(baris) > base and str(baris[base]).strip()
    ) - 2
    if jumlah_teknisi < 0:
        jumlah_teknisi = 0

    def sel(offset, nomor_baris):
        i = nomor_baris - 1
        j = base + offset
        if 0 <= i < len(semua_nilai) and j < len(semua_nilai[i]):
            return str(semua_nilai[i][j]).strip()
        return "0"

    aktivasi = sel(1, 4)
    ogp_ikr = sel(4, 4)
    pick_up = sel(5, 4)
    ps = sel(6, 4)

    waktu_caption = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"*{cfg['nama']}*\n"
        f"Tim/Teknisi : {jumlah_teknisi}\n"
        f"PICK UP : {pick_up}\n"
        f"OGP IKR : {ogp_ikr}\n"
        f"Aktivasi : {aktivasi}\n"
        f"PS : {ps}\n\n"
        f"📝Created by FBB.SBT\n"
        f"Tanggal: {waktu_caption}"
    )


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


async def ambil_screenshot(cfg, baris_akhir):
    """Screenshot blok kolom distrik (kolom_awal..kolom_akhir) dari grid pubhtml, crop dinamis."""
    path_ss = nama_file_ss(cfg["slug"])

    if os.path.exists(path_ss):
        os.remove(path_ss)

    rentang_cell = f"{cfg['kolom_awal']}{BARIS_AWAL}:{cfg['kolom_akhir']}{baris_akhir}"
    catat_log(f"📸 [{cfg['nama']}] Mengambil screenshot area {rentang_cell} pada: {tanggal_hari_ini()}")

    # td index 0-based dalam tiap baris: kolom A=0, B=1, C=2, ... (sel <th> nomor baris diabaikan)
    td_awal = _kolom_ke_indeks(cfg["kolom_awal"]) - 1
    td_akhir = _kolom_ke_indeks(cfg["kolom_akhir"]) - 1

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 2400, "height": 2000})
        page = await context.new_page()

        try:
            await page.goto(URL_GRID, wait_until="load", timeout=90000)
            await page.wait_for_selector("table.waffle", timeout=60000)
            await page.wait_for_timeout(2000)

            rect = await page.evaluate(
                """({lastRow, firstRow, tdAwal, tdAkhir}) => {
                    const t = document.querySelector('table.waffle');
                    const rows = t.querySelectorAll('tbody tr');
                    // baris referensi = baris dengan jumlah td terbanyak (tanpa merge)
                    let ref = null, best = 0;
                    for (let i = 0; i < Math.min(rows.length, 10); i++) {
                        const td = rows[i].querySelectorAll('td');
                        if (td.length > best) { best = td.length; ref = rows[i]; }
                    }
                    const td = ref.querySelectorAll('td');
                    const cA = td[tdAwal].getBoundingClientRect();
                    const cB = td[tdAkhir].getBoundingClientRect();
                    const rTop = rows[firstRow - 1].getBoundingClientRect();
                    const idxLast = Math.min(lastRow, rows.length) - 1;
                    const rBot = rows[idxLast].getBoundingClientRect();
                    const sx = window.scrollX, sy = window.scrollY;
                    return {
                        x: cA.left + sx, y: rTop.top + sy,
                        right: cB.right + sx, bottom: rBot.bottom + sy
                    };
                }""",
                {"lastRow": baris_akhir, "firstRow": BARIS_AWAL, "tdAwal": td_awal, "tdAkhir": td_akhir},
            )

            clip = {
                "x": rect["x"],
                "y": rect["y"],
                "width": rect["right"] - rect["x"],
                "height": rect["bottom"] - rect["y"],
            }

            # Perbesar viewport agar seluruh area masuk (baris bisa banyak)
            await page.set_viewport_size({
                "width": int(rect["right"]) + 60,
                "height": int(rect["bottom"]) + 60,
            })
            await page.wait_for_timeout(500)

            await page.screenshot(path=path_ss, clip=clip)

        except Exception as e:
            catat_log(f"❌ Gagal mengambil screenshot: {e}")
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


def kirim_via_whatsapp(path_gambar, caption_baru, slug):
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
                "filename": f"Reporting_WO_{slug}_{tanggal_hari_ini()}.png",
                "data": encoded_string
            },
            "caption": caption_baru
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


def proses_satu_distrik(cfg):
    """Ambil data, screenshot, dan kirim WA untuk satu distrik. Return True bila sukses."""
    try:
        sheet = _buka_sheet()
        semua_nilai = sheet.get_all_values()

        baris_akhir = deteksi_baris_terakhir(cfg, semua_nilai)
        caption = buat_caption(cfg, semua_nilai)

        path_ss = asyncio.run(ambil_screenshot(cfg, baris_akhir))
        if not os.path.exists(path_ss):
            catat_log(f"❌ [{cfg['nama']}] Screenshot gagal, akan dicoba ulang bila masih ada percobaan.")
            return False

        optimalkan_resolusi(path_ss)
        berhasil = kirim_via_whatsapp(path_ss, caption, cfg["slug"])
        hapus_gambar(path_ss)
        return berhasil

    except Exception as e:
        catat_log(f"❌ [{cfg['nama']}] Error saat proses: {e}")
        return False


def tugas_harian():
    """Alur utama: proses semua distrik, retry hanya yang gagal (pola mirror_tikor)."""
    catat_log("=" * 50)
    catat_log("🚀 Memulai tugas harian WO (3 Distrik)...")

    tertunda = list(DISTRIK)
    for percobaan in range(1, MAX_RETRY + 1):
        catat_log(f"--- Percobaan {percobaan}/{MAX_RETRY} ({len(tertunda)} distrik) ---")
        gagal = []
        for cfg in tertunda:
            if not proses_satu_distrik(cfg):
                gagal.append(cfg)

        if not gagal:
            catat_log("✅ Semua distrik berhasil dikirim.")
            break

        tertunda = gagal
        if percobaan < MAX_RETRY:
            nama_gagal = ", ".join(c["nama"] for c in tertunda)
            catat_log(f"🔁 {len(tertunda)} distrik gagal ({nama_gagal}). Retry dalam {JEDA_RETRY} detik...")
            time.sleep(JEDA_RETRY)
    else:
        if tertunda:
            nama_gagal = ", ".join(c["nama"] for c in tertunda)
            catat_log(f"❌ Menyerah setelah {MAX_RETRY}x. Distrik gagal: {nama_gagal}")

    catat_log("🏁 Tugas harian WO selesai.")
    catat_log("=" * 50)


if __name__ == "__main__":
    print("=" * 55)
    print("  📱 Auto Screenshot & Kirim WA (WO 3 Distrik)")
    print(f"  📌 Grup Tujuan: {GROUP_ID_TUJUAN}")
    print(f"  🏙️ Distrik: {', '.join(d['nama'] for d in DISTRIK)}")
    print("=" * 55)

    tugas_harian()
