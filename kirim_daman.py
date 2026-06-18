import os
import time
import requests
import base64
from datetime import datetime
import fitz  # PyMuPDF
from PIL import Image, ImageChops
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ================== KONFIGURASI WAHA ==================
WAHA_URL = "https://waha-dutxvo095iqn.cgk-lab.sumopod.my.id"
WAHA_SESSION = "OLTReport"
WAHA_API_KEY = "ROpWNPkTUavqEbnz5zKU4mTiL0HIZoye"
# 120363423984319917@g.us = test
# 120363425048343238@g.us = real
GROUP_ID_TUJUAN = [
    # "120363423984319917@g.us",  # test
    "120363425048343238@g.us", # real
]

# ================== KONFIGURASI SPREADSHEET ==================
SPREADSHEET_ID = "18Hr1cksepok5Dn4bZUnL15jXi7h1b9wYkltgHvjg7eo"
SOURCE_GID = 1054791128   # DASHBOARD AQI (sumber dinamis)
TARGET_GID = 725804554    # TABEL BOT (tabel hasil yang di-screenshot)

JSON_KEY = "kunci_rahasia_google.json"
# ============================================================

FOLDER_GAMBAR = "images"
FOLDER_LOG = "logs"
os.makedirs(FOLDER_GAMBAR, exist_ok=True)
os.makedirs(FOLDER_LOG, exist_ok=True)

DISTRICTS = ["BATAM", "BUKITTINGGI", "DUMAI", "PADANG", "PEKANBARU"]
BULAN = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
         "Juli", "Agustus", "September", "Oktober", "November", "Desember"]

# Index kolom (0-based) di sheet sumber DASHBOARD AQI
IDX = dict(L=11, Q=16, R=17, S=18, T=19, W=22, Z=25, AC=28,
           AF=31, AG=32, AH=33, AI=34, AJ=35, AK=36, AL=37)

# Pemetaan: tiap tabel target -> range tulis + urutan kolom sumber
# Tiap range mencakup 5 distrik + 1 baris SUMBAGTENG (regional = TOTAL) di bawah PEKANBARU.
TABEL_TULIS = [
    {"range": "C5:G10",  "kolom": ["L", "Q", "R", "S", "T"]},                # VALINS SERVICE
    {"range": "C14:I19", "kolom": ["W", "Z", "AC", "AF", "AG", "AH", "AI"]}, # VALIDASI INFRA FTTH
    {"range": "C24:E29", "kolom": ["AJ", "AK", "AL"]},                       # VALIDASI DATA INVENTORY
]

# Spesifikasi tiap pesan/screenshot (1 per 1)
#   judul   = nama tabel (judul di TABEL BOT)
#   range   = area di TABEL BOT untuk di-export jadi gambar
#   nomor   = nomor metrik utama
#   utama   = (label, kolom_sumber) -> metrik REAL gabungan
#   sub     = daftar (label, kolom_sumber) -> komponen
PESAN = [
    {
        "judul": "VALINS SERVICE",
        "range": "B3:G10",
        "nomor": "1",
        "utama": ("VALIDASI SERVICE FTTH", "R"),
        "sub": [
            ("1.a VALINS DC QR CODE & SERVICE", "L"),
            ("1.b VALINS VISIT ODP (PROV ASR & MAINT)", "Q"),
        ],
    },
    {
        "judul": "VALIDASI INFRA FTTH",
        "range": "B12:I19",
        "nomor": "2",
        "utama": ("VALIDASI INFRA FTTH", "AG"),
        "sub": [
            ("2.a CORE FEEDER", "W"),
            ("2.b CORE DISTRIBUSI", "Z"),
            ("2.c CONNECTIVITY E2E", "AC"),
            ("2.d VALIDASI TIANG", "AF"),
        ],
    },
    {
        "judul": "VALIDASI DATA INVENTORY ACCESS 2026",
        "range": "B22:E29",
        "nomor": "3",
        "utama": ("VALIDASI DATA INVENTORY ACCESS 2026", "AJ"),
        "sub": [],
    },
]


# ====================================================================
# LOGGING
# ====================================================================
def tanggal_hari_ini():
    return datetime.now().strftime("%Y-%m-%d")


def nama_file_log():
    return os.path.join(FOLDER_LOG, "daman_log.txt")


def catat_log(pesan):
    """Mencatat log dengan auto-reset jika masuk hari baru."""
    waktu = datetime.now().strftime("%H:%M:%S")
    tanggal_sekarang = tanggal_hari_ini()
    pesan_log = f"[{waktu}] {pesan}"
    print(pesan_log)

    file_log = nama_file_log()
    mode = "a"
    if os.path.exists(file_log):
        tgl_mod = datetime.fromtimestamp(os.path.getmtime(file_log)).strftime("%Y-%m-%d")
        if tgl_mod != tanggal_sekarang:
            mode = "w"
    with open(file_log, mode, encoding="utf-8") as f:
        if mode == "w":
            f.write(f"=== Log Hari Ini: {tanggal_sekarang} ===\n")
        f.write(pesan_log + "\n")


# ====================================================================
# GOOGLE SHEETS
# ====================================================================
def buat_creds():
    scope = ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file",
             "https://www.googleapis.com/auth/drive"]
    return ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY, scope)


def _cell(vals, r, c):
    """Ambil nilai sel (r = 1-based baris, c = 0-based kolom)."""
    if 0 <= r - 1 < len(vals) and 0 <= c < len(vals[r - 1]):
        return vals[r - 1][c].strip()
    return ""


def baca_dashboard(ss):
    """Baca DASHBOARD AQI, kembalikan peta baris distrik+TOTAL untuk blok
    terbaru dan blok sebelumnya, plus tanggal blok terbaru."""
    src = ss.get_worksheet_by_id(SOURCE_GID)
    vals = src.get_all_values()

    # Tiap blok diawali sel kolom B == "TGL"
    awal_blok = [i + 1 for i, row in enumerate(vals)
                 if len(row) > 1 and row[1].strip() == "TGL"]
    if not awal_blok:
        raise RuntimeError("Tidak menemukan blok tanggal (TGL) di DASHBOARD AQI.")

    def peta_baris(bstart):
        peta = {}
        for rr in range(bstart, bstart + 18):
            nama = _cell(vals, rr, 4)          # kolom E = DISTRICT
            if nama in DISTRICTS:
                peta[nama] = rr
            if _cell(vals, rr, 1) == "TOTAL":  # kolom B = TOTAL
                peta["TOTAL"] = rr
        return peta

    def tanggal(bstart):
        try:
            tgl = int(_cell(vals, bstart + 1, 1))
            bln = int(_cell(vals, bstart + 1, 2))
            thn = _cell(vals, bstart + 1, 3)
            return f"{tgl} {BULAN[bln]} {thn}"
        except Exception:
            return tanggal_hari_ini()

    terbaru = awal_blok[-1]
    sebelum = awal_blok[-2] if len(awal_blok) >= 2 else awal_blok[-1]

    return {
        "vals": vals,
        "rows_terbaru": peta_baris(terbaru),
        "rows_sebelum": peta_baris(sebelum),
        "tanggal": tanggal(terbaru),
    }


def tulis_ke_tabel(ss, data):
    """Tulis 15 kolom x (5 distrik + SUMBAGTENG) blok terbaru ke 3 tabel di TABEL BOT.
    Baris SUMBAGTENG diisi dari baris TOTAL DASHBOARD AQI, di bawah PEKANBARU."""
    tgt = ss.get_worksheet_by_id(TARGET_GID)
    vals = data["vals"]
    rows = data["rows_terbaru"]
    r_total = rows.get("TOTAL")

    payload = []
    for tabel in TABEL_TULIS:
        nilai = []
        for d in DISTRICTS:
            r = rows[d]
            nilai.append([_cell(vals, r, IDX[k]) for k in tabel["kolom"]])
        # Baris regional SUMBAGTENG (= TOTAL); kosong jika TOTAL tak ditemukan.
        nilai.append([_cell(vals, r_total, IDX[k]) if r_total else "" for k in tabel["kolom"]])
        payload.append({"range": tabel["range"], "values": nilai})

    tgt.batch_update(payload, value_input_option="USER_ENTERED")
    total_sel = sum(len(p["values"]) * len(p["values"][0]) for p in payload)
    catat_log(f"✅ Data blok '{data['tanggal']}' ditulis ke TABEL BOT ({total_sel} sel).")


# ====================================================================
# CAPTION
# ====================================================================
def _angka(s):
    try:
        return float(str(s).replace("%", "").replace(",", "").strip())
    except Exception:
        return None


def _tren(cur, prv):
    a, b = _angka(cur), _angka(prv)
    if a is None or b is None:
        return ""
    if a > b:
        return "📈"
    if a < b:
        return "📉"
    return "➡️"


def buat_caption(spesifikasi, data):
    """Bangun caption rapi (WhatsApp) untuk satu pesan/tabel."""
    vals = data["vals"]
    rc, rp = data["rows_terbaru"], data["rows_sebelum"]

    def baris(label, kolom, who):
        cur = _cell(vals, rc[who], IDX[kolom]) if who in rc else ""
        prv = _cell(vals, rp[who], IDX[kolom]) if who in rp else ""
        return f"{label} : {cur} {_tren(cur, prv)}".rstrip()

    def blok_metrik(label_utama, kolom):
        out = []
        cur = _cell(vals, rc["TOTAL"], IDX[kolom]) if "TOTAL" in rc else ""
        prv = _cell(vals, rp["TOTAL"], IDX[kolom]) if "TOTAL" in rp else ""
        out.append(f"*{label_utama}* : {cur} {_tren(cur, prv)}".rstrip())
        for d in DISTRICTS:
            out.append("  " + baris(f"• {d.title()}", kolom, d))
        # Baris regional di bawah PEKANBARU (di-bold), sejajar dengan tabel di gambar.
        st_cur = _cell(vals, rc["TOTAL"], IDX[kolom]) if "TOTAL" in rc else ""
        st_prv = _cell(vals, rp["TOTAL"], IDX[kolom]) if "TOTAL" in rp else ""
        out.append(f"  *• Sumbagteng : {st_cur}* {_tren(st_cur, st_prv)}".rstrip())
        return out

    lines = []
    lines.append("📊 *REPORT PERFORMANSI DAMAN*")
    lines.append("📍 Regional Sumbagteng")
    lines.append(f"🗓️ {data['tanggal']}")
    lines.append("*Day over Day*")
    lines.append("➖➖➖➖➖➖➖➖➖")
    lines.append("")

    nomor = spesifikasi["nomor"]
    label_utama, kolom_utama = spesifikasi["utama"]
    lines += blok_metrik(f"{nomor}. {label_utama}", kolom_utama)

    for sub_label, sub_kolom in spesifikasi["sub"]:
        lines.append("")
        lines += blok_metrik(sub_label, sub_kolom)

    return "\n".join(lines)


# ====================================================================
# EXPORT TABEL -> GAMBAR (PNG)  [pakai akun service account, sheet privat]
# ====================================================================
def nama_file_ss(idx):
    return os.path.join(FOLDER_GAMBAR, f"Daman_{idx}_{tanggal_hari_ini()}.png")


def export_tabel_png(creds, rng, out_path, scale=3):
    """Export satu range TABEL BOT jadi PDF (terautentikasi) lalu render +
    auto-crop jadi PNG rapi. Mengembalikan path jika sukses, None jika gagal."""
    token = creds.get_access_token().access_token
    params = {
        "format": "pdf", "gid": str(TARGET_GID), "range": rng,
        "portrait": "true", "fitw": "true",
        "gridlines": "false", "sheetnames": "false", "printtitle": "false",
        "pagenumbers": "false", "fzr": "false",
        "top_margin": "0", "bottom_margin": "0", "left_margin": "0", "right_margin": "0",
    }
    url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export"
    try:
        r = requests.get(url, params=params,
                         headers={"Authorization": f"Bearer {token}"}, timeout=60)
    except Exception as e:
        catat_log(f"❌ Gagal request export {rng}: {e}")
        return None

    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("application/pdf"):
        catat_log(f"❌ Export {rng} gagal (status {r.status_code}, "
                  f"type {r.headers.get('content-type')}).")
        return None

    pdf_path = out_path + ".pdf"
    with open(pdf_path, "wb") as f:
        f.write(r.content)

    try:
        doc = fitz.open(pdf_path)
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(scale, scale))
        raw_path = out_path + ".raw.png"
        pix.save(raw_path)
        doc.close()

        img = Image.open(raw_path).convert("RGB")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bbox = ImageChops.difference(img, bg).getbbox()
        if bbox:
            img = img.crop(bbox)
        img.save(out_path)
    except Exception as e:
        catat_log(f"❌ Gagal render PDF->PNG untuk {rng}: {e}")
        return None
    finally:
        for tmp in (pdf_path, out_path + ".raw.png"):
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass

    return out_path


# ====================================================================
# WHATSAPP (WAHA)
# ====================================================================
def buat_session_baru():
    s = requests.Session()
    adapter = requests.adapters.HTTPAdapter(max_retries=0, pool_connections=1, pool_maxsize=1)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


def kirim_via_whatsapp(path_gambar, caption, nama_file):
    """Kirim satu gambar + caption ke semua grup tujuan."""
    if not os.path.exists(path_gambar):
        catat_log(f"File {path_gambar} tidak ada, dilewati.")
        return False

    session = buat_session_baru()
    try:
        with open(path_gambar, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")

        url = f"{WAHA_URL.rstrip('/')}/api/sendImage"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Api-Key": WAHA_API_KEY,
            "Connection": "close",
        }
        for group_id in GROUP_ID_TUJUAN:
            catat_log(f"Mengirim '{nama_file}' ke grup {group_id} ...")
            payload = {
                "session": WAHA_SESSION,
                "chatId": group_id,
                "file": {"mimetype": "image/png", "filename": nama_file, "data": encoded},
                "caption": caption,
            }
            try:
                resp = session.post(url, headers=headers, json=payload, timeout=60)
                if resp.status_code in (200, 201):
                    catat_log(f"✅ Terkirim ke {group_id}!")
                else:
                    catat_log(f"❌ Gagal ke {group_id}. Status {resp.status_code}: {resp.text}")
            except (ConnectionResetError, requests.exceptions.ConnectionError) as e:
                catat_log(f"⚠️ Koneksi terputus ke {group_id}: {e} (kemungkinan tetap terkirim).")
            except Exception as e:
                catat_log(f"❌ Error kirim ke {group_id}: {e}")
            time.sleep(2)
        return True
    except Exception as e:
        catat_log(f"❌ Error fatal menyiapkan pengiriman: {e}")
        return False
    finally:
        session.close()


def hapus_gambar(path_gambar):
    try:
        if os.path.exists(path_gambar):
            os.remove(path_gambar)
    except Exception as e:
        catat_log(f"⚠️ Gagal hapus {path_gambar}: {e}")


# ====================================================================
# ORKESTRASI
# ====================================================================
def tugas_harian():
    catat_log("=" * 50)
    catat_log("🚀 Memulai tugas harian DAMAN...")

    creds = buat_creds()
    try:
        ss = gspread.authorize(creds).open_by_key(SPREADSHEET_ID)
        data = baca_dashboard(ss)
    except Exception as e:
        catat_log(f"❌ Gagal membaca DASHBOARD AQI: {e}")
        catat_log("=" * 50)
        return

    catat_log(f"📅 Blok terbaru yang dipakai: {data['tanggal']}")

    try:
        tulis_ke_tabel(ss, data)
    except Exception as e:
        catat_log(f"❌ Gagal menulis ke TABEL BOT: {e}")
        catat_log("=" * 50)
        return

    # beri jeda singkat agar perubahan tersimpan sebelum di-export
    time.sleep(3)

    for i, spec in enumerate(PESAN, start=1):
        path_ss = nama_file_ss(i)
        hasil = export_tabel_png(creds, spec["range"], path_ss)
        if not hasil:
            catat_log(f"⚠️ Lewati pengiriman tabel {i} ({spec['judul']}) karena export gagal.")
            continue
        catat_log(f"📸 Export tabel {i} ({spec['judul']}) berhasil.")

        caption = buat_caption(spec, data)
        nama = f"Daman_{spec['judul'].replace(' ', '_')}_{tanggal_hari_ini()}.png"
        kirim_via_whatsapp(path_ss, caption, nama)
        hapus_gambar(path_ss)
        time.sleep(2)

    catat_log("🏁 Tugas harian DAMAN selesai.")
    catat_log("=" * 50)


if __name__ == "__main__":
    print("=" * 55)
    print("  📱 Auto Copy + Screenshot + Kirim WA (DAMAN)")
    print(f"  📌 Mengirim ke {len(GROUP_ID_TUJUAN)} Grup Tujuan")
    print("=" * 55)
    tugas_harian()
