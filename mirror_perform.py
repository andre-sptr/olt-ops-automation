from telethon import TelegramClient, events
from datetime import datetime
import gspread
from gspread.utils import rowcol_to_a1
from oauth2client.service_account import ServiceAccountCredentials
from perform_rollover import (
    indeks_baris_harian,
    label_bulan_indonesia,
    pastikan_bulan_aktif,
    waktu_wib,
)
import re
import os

api_id = 35153027
api_hash = '275a7916b30391e446366433d5427086'

ID_GRUP_NE_AKSES = -172352509
ID_GRUP_SIAGA_SERVO = -1001688234308
ID_GRUP_TESTING = -4883113309

daftar_grup_target = [ID_GRUP_NE_AKSES, ID_GRUP_SIAGA_SERVO, ID_GRUP_TESTING]
witel_target = ['SUMBAR', 'RIKEP', 'RIDAR']

MAP_DISTRIK = {
    "PEKANBARU": "PKU",
    "PADANG": "PDG",
    "BUKITTINGGI": "BKT",
    "BATAM": "BTM",
    "DUMAI": "DUM"
}

scope = ["https://spreadsheets.google.com/feeds", 
         "https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive.file", 
         "https://www.googleapis.com/auth/drive"]

creds = ServiceAccountCredentials.from_json_keyfile_name("kunci_rahasia_google.json", scope)
client_gs = gspread.authorize(creds)

nama_file_spreadsheet = "Performansi ISP" 
spreadsheet = client_gs.open(nama_file_spreadsheet)
worksheet = spreadsheet.worksheet("Gamas ISP")

client = TelegramClient('sesi_mirror_perform', api_id, api_hash)

if not os.path.exists("logs"):
    os.makedirs("logs")

def nama_file_log():
    return os.path.join("logs", "mirror_perform_log.txt")

def simpan_log(pesan):
    """Mencatat log dengan fitur auto-reset jika masuk hari baru."""
    waktu = datetime.now().strftime("%H:%M:%S")
    tanggal_sekarang = datetime.now().strftime("%Y-%m-%d")
    
    pesan_print = f"[{waktu}] {pesan}" if not pesan.startswith("\n") else f"\n[{waktu}] {pesan.lstrip()}"
    print(pesan_print)
    
    pesan_log = f"[{waktu}] {pesan.lstrip()}" 

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


@client.on(events.NewMessage(chats=daftar_grup_target))
async def proses_pesan_baru(event):
    teks_pesan = event.text.strip()
    
    if '✅✅Notifikasi OLT Recovery!✅✅' in teks_pesan or '✅✅Notifikasi Flicker Recovery!✅✅' in teks_pesan:
        baris_baris = teks_pesan.split('\n')
        data_sementara = {}
        
        for baris in baris_baris:
            baris = baris.strip()
            if baris.startswith('Node ID :'):
                data_sementara['Node ID'] = baris.split(':', 1)[1].strip()
            elif baris.startswith('Witel :'):
                data_sementara['Witel'] = baris.split(':', 1)[1].strip().upper()
            elif baris.startswith('Down Duration :') or baris.startswith('Flicker Duration :'):
                data_sementara['Down Duration'] = baris.split(':', 1)[1].strip()
        
        node_id_target = data_sementara.get('Node ID', '-')
        witel_saat_ini = data_sementara.get('Witel', '')
        down_duration = data_sementara.get('Down Duration', '')
        
        pesan_log_awal = f"\n🔔 Pesan Grup TR1 - OM NE Akses Terdeteksi! | Hostname: {node_id_target}"
        simpan_log(pesan_log_awal) 
        
        if witel_saat_ini in witel_target:
            keterangan_rca = "Data RCA Tidak Ditemukan"
            teks_gamas = ""
            
            async for pesan_cari in client.iter_messages(None, search=node_id_target, limit=30):
                if pesan_cari.text and '!PROGRAM ZERO GAMAS OLT!' in pesan_cari.text:
                    teks_gamas = pesan_cari.text
                    for b in pesan_cari.text.split('\n'):
                        if '- DISTRICT' in b.upper():
                            keterangan_rca = b.strip()
                            break
                if keterangan_rca != "Data RCA Tidak Ditemukan":
                    break
            
            district_val = ""
            rca_val = ""
            
            if '- DISTRICT' in keterangan_rca.upper():
                parts = keterangan_rca.upper().split('- DISTRICT')
                district_raw = parts[1].strip()

                if district_raw in MAP_DISTRIK:
                    district_val = MAP_DISTRIK[district_raw]
                else:
                    district_val = district_raw
                
                hostname_pln = node_id_target.upper().replace('GPON', 'PLN', 1)
                
                if hostname_pln != node_id_target.upper() and hostname_pln in teks_gamas.upper():
                    rca_val = "PLN"
                else:
                    rca_val = "Kable CUT"
            
            else:
                simpan_log(f"-> Info RCA tidak ada di Tele, mencoba cari di GDocs untuk: {node_id_target}")
                
                parts_node = node_id_target.split('-')
                
                if len(parts_node) >= 3:
                    site_code = parts_node[2]
                    
                    try:
                        pencarian = worksheet.find(re.compile(site_code), in_column=2)
                        
                        if pencarian:
                            baris_ditemukan = pencarian.row
                            district_val_sementara = worksheet.cell(baris_ditemukan, 3).value 
                            
                            if not district_val_sementara or district_val_sementara == "-":
                                district_val = ""
                                simpan_log(f"-> Site {site_code} ketemu di GDocs, tapi kolom distriknya kosong.")
                            else:
                                district_val = district_val_sementara
                                simpan_log(f"-> Ketemu di GDocs! Site {site_code} masuk ke distrik {district_val}")
                        else:
                            district_val = ""
                            simpan_log(f"-> Site {site_code} tidak ditemukan di GDocs.")
                            
                    except gspread.exceptions.CellNotFound:
                        district_val = ""
                        simpan_log(f"-> Site {site_code} tidak ditemukan di GDocs.")
                else:
                    district_val = ""
                    simpan_log("-> Format Node ID tidak valid untuk dicari.")

                rca_val = "Kable CUT"

            total_menit = 0
            teks_durasi = down_duration.lower()
            
            cari_jam = re.search(r'(\d+)\s*jam', teks_durasi)
            cari_menit = re.search(r'(\d+)\s*menit', teks_durasi)
            
            if cari_jam:
                total_menit += int(cari_jam.group(1)) * 60
            if cari_menit:
                total_menit += int(cari_menit.group(1))
                
            hasil_durasi = total_menit if total_menit > 0 else down_duration

            simpan_log(f"-> Memproses NE: {node_id_target} | Witel: {witel_saat_ini} | Distrik: {district_val} | RCA: {rca_val} | Durasi: {hasil_durasi}m")
            
            com_val = ""
            if isinstance(hasil_durasi, (int, float)):
                com_val = "C" if hasil_durasi <= 360 else "NC"

            try:
                sekarang = waktu_wib()
                rollover = pastikan_bulan_aktif(
                    spreadsheet,
                    worksheet,
                    sekarang,
                )
                if rollover.archived:
                    simpan_log(
                        f"-> Data bulan lama diarsipkan ke {rollover.archive_name}."
                    )

                baris_data_baru = [""] * 37
                baris_data_baru[1] = node_id_target
                baris_data_baru[2] = district_val
                baris_data_baru[3] = rca_val
                baris_data_baru[35] = com_val
                baris_data_baru[36] = label_bulan_indonesia(sekarang)

                kolom_tanggal = indeks_baris_harian(sekarang.day)
                baris_data_baru[kolom_tanggal] = hasil_durasi

                kolom_b = worksheet.col_values(2) 
                
                baris_target = len(kolom_b) + 1 
                
                for i, val in enumerate(kolom_b):
                    if i > 1 and val.strip() == "":
                        baris_target = i + 1
                        break
                
                worksheet.insert_row(baris_data_baru, baris_target)
                range_baris_baru = f"B{baris_target}:AK{baris_target}"
                
                worksheet.format(range_baris_baru, {
                    "borders": {
                        "top": {"style": "SOLID"}, "bottom": {"style": "SOLID"},
                        "left": {"style": "SOLID"}, "right": {"style": "SOLID"}
                    },
                    "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE"
                })

                sel_durasi = rowcol_to_a1(baris_target, kolom_tanggal + 1)
                
                warna_bg = {"red": 0.8, "green": 1.0, "blue": 0.8}
                if isinstance(hasil_durasi, (int, float)) and hasil_durasi > 360:
                    warna_bg = {"red": 1.0, "green": 0.8, "blue": 0.8}

                worksheet.format(sel_durasi, {
                    "backgroundColor": warna_bg, "textFormat": {"bold": False}
                })
                
                simpan_log(f"✅ Data TTR 6 Jam berhasil ditambahkan di Baris {baris_target}!")
                
            except Exception as e:
                simpan_log(f"❌ Gagal mengirim ke Spreadsheet: {e}")
                
        else:
            simpan_log(f"-> Diabaikan: Witel {witel_saat_ini} bukan target.")

    elif 'REPORT INTERNAL TELKOM GROUP' in teks_pesan and 'Current Status: Closed' in teks_pesan:
        simpan_log(f"\n🔔 Pesan Grup SIAGA_SERVO_REG-1 Terdeteksi!")
        
        distrik_val = ""
        witel_val = ""
        lokasi_lengkap = ""
        
        match_lokasi = re.search(r'Lokasi:\s*(.*)', teks_pesan, re.IGNORECASE)
        if match_lokasi:
            lokasi_lengkap = match_lokasi.group(1).strip().upper()
            
            distrik_raw = lokasi_lengkap.split('(')[0].strip()
            distrik_val = MAP_DISTRIK.get(distrik_raw, distrik_raw)

            if '(' in lokasi_lengkap and ')' in lokasi_lengkap:
                witel_val = lokasi_lengkap.split('(')[1].split(')')[0].strip()
        
        if any(witel in lokasi_lengkap for witel in witel_target):
            
            if "BLACKOUT" in teks_pesan.upper():
                
                ne_hostname = "-"

                match_ne = re.search(r'(\S+-\S+)\s+(?:TO|-)\s+(\S+-\S+)', teks_pesan, re.IGNORECASE)
                if match_ne:
                    ne_hostname = match_ne.group(1).upper()  
                    ne_hostname = re.sub(r'[,.]$', '', ne_hostname)

                down_duration = "-"
                match_durasi = re.search(r'Duration:\s*(.*)', teks_pesan, re.IGNORECASE)
                if match_durasi:
                    down_duration = match_durasi.group(1).strip()
                    
                total_menit = 0
                teks_durasi = down_duration.lower()
                cari_jam = re.search(r'(\d+)\s*jam', teks_durasi)
                cari_menit = re.search(r'(\d+)\s*menit', teks_durasi)
                if cari_jam: total_menit += int(cari_jam.group(1)) * 60
                if cari_menit: total_menit += int(cari_menit.group(1))
                hasil_durasi = total_menit if total_menit > 0 else down_duration

                rca_val = "BLACKOUT"
                    
                simpan_log(f"-> Memproses NE: {ne_hostname} | Witel: {witel_val} | Distrik: {distrik_val} | RCA: {rca_val} | Durasi: {hasil_durasi}m")
            
                try:
                    sekarang = waktu_wib()
                    rollover = pastikan_bulan_aktif(
                        spreadsheet,
                        worksheet,
                        sekarang,
                    )
                    if rollover.archived:
                        simpan_log(
                            f"-> Data bulan lama diarsipkan ke {rollover.archive_name}."
                        )

                    kolom_b = worksheet.col_values(2)
                    baris_target = -1
                    hitung_header_ne = 0
                
                    for i, val in enumerate(kolom_b):
                        if val.strip().upper() == "NE HOSTNAME":
                            hitung_header_ne += 1
                            if hitung_header_ne == 2:
                                for j in range(i + 1, len(kolom_b)):
                                    if kolom_b[j].strip() == "":
                                        baris_target = j + 1
                                        break
                                else:
                                    baris_target = len(kolom_b) + 1
                                break
                    
                    if baris_target == -1:
                        simpan_log("⚠️ Header tabel kedua tidak ditemukan! Meletakkan data di baris paling bawah.")
                        baris_target = len(kolom_b) + 1
                        
                    com_val = ""
                    if isinstance(hasil_durasi, (int, float)):
                        com_val = "C" if hasil_durasi <= 360 else "NC"

                    baris_data_baru = [""] * 37
                    
                    baris_data_baru[1] = ne_hostname
                    baris_data_baru[2] = distrik_val   
                    baris_data_baru[3] = rca_val  
                    baris_data_baru[35] = com_val
                    baris_data_baru[36] = label_bulan_indonesia(sekarang)
                    
                    kolom_tanggal = indeks_baris_harian(sekarang.day)
                    baris_data_baru[kolom_tanggal] = hasil_durasi 

                    worksheet.insert_row(baris_data_baru, baris_target)
                    range_baris_baru = f"B{baris_target}:AK{baris_target}"
                    
                    worksheet.format(range_baris_baru, {
                        "borders": {
                            "top": {"style": "SOLID"}, "bottom": {"style": "SOLID"},
                            "left": {"style": "SOLID"}, "right": {"style": "SOLID"}
                        },
                        "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE"
                    })

                    sel_durasi = rowcol_to_a1(baris_target, kolom_tanggal + 1)
                    
                    warna_bg = {"red": 0.8, "green": 1.0, "blue": 0.8}
                    if isinstance(hasil_durasi, (int, float)) and hasil_durasi > 180:
                        warna_bg = {"red": 1.0, "green": 0.8, "blue": 0.8}

                    worksheet.format(sel_durasi, {
                        "backgroundColor": warna_bg, "textFormat": {"bold": False}
                    })
                    
                    simpan_log(f"✅ Data TTR 3 Jam berhasil ditambahkan di Baris {baris_target}!")
                    
                except Exception as e:
                    simpan_log(f"❌ Gagal mengirim ke Spreadsheet: {e}")
            
            else:
                simpan_log(f"-> Diabaikan: Witel {witel_val} sesuai, tapi TIDAK ADA keterangan BLACKOUT.")
                
        else:
            simpan_log(f"-> Diabaikan: Lokasi '{lokasi_lengkap}' bukan target Witel.")

async def main():
    simpan_log("Memulai koneksi ke Telegram...")
    rollover = pastikan_bulan_aktif(
        spreadsheet,
        worksheet,
        waktu_wib(),
    )
    if rollover.archived:
        simpan_log(
            f"Data bulan lama berhasil diarsipkan ke {rollover.archive_name}."
        )
    await client.get_dialogs() 
    simpan_log(f"🚀 Program Real-time Aktif! Mendengarkan {len(daftar_grup_target)} grup...")
    await client.run_until_disconnected()

with client:
    client.loop.run_until_complete(main())
