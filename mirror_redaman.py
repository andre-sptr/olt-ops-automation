from telethon import TelegramClient, events
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import math
import re
from datetime import datetime

# ==========================================
# 1. KONFIGURASI TELEGRAM & SPREADSHEET
# ==========================================
api_id = 35153027
api_hash = '275a7916b30391e446366433d5427086'

ID_GRUP_NE_AKSES = -1001298576249

WITEL_TARGET = ['SUMBAR', 'RIDAR', 'RIKEP']

scope = ["https://spreadsheets.google.com/feeds", 
         "https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive.file", 
         "https://www.googleapis.com/auth/drive"]

creds = ServiceAccountCredentials.from_json_keyfile_name("kunci_rahasia_google.json", scope)
client_gs = gspread.authorize(creds)

SPREADSHEET_ID = "13faIcsHI34GjvImRgV_AEUh5MP3NnLWiSfk-Z4O49Do"
spreadsheet = client_gs.open_by_key(SPREADSHEET_ID)

worksheet = spreadsheet.worksheet("Redaman")

client = TelegramClient('sesi_mirror_redaman', api_id, api_hash)

sesi_pengambilan_aktif = False

# ==========================================
# 2. EVENT LISTENER UNTUK MEMBACA PESAN
# ==========================================
@client.on(events.NewMessage(chats=[ID_GRUP_NE_AKSES]))
async def proses_laporan_rx(event):
    global sesi_pengambilan_aktif 
    
    teks_pesan = event.text.strip()
    
    if 'Berikut data Interface Uplink OLT ZTE Rx Powernya' in teks_pesan or 'Berikut data Interface Uplink OLT Huawei Rx Powernya' in teks_pesan:
        print("🔔 Laporan OLT (ZTE/Huawei) terdeteksi! Membuka sesi...")
        sesi_pengambilan_aktif = True
        folder_logs = "logs"
        path_log_clear = os.path.join(folder_logs, "redaman_clear.txt")
        if not os.path.exists(folder_logs):
            os.makedirs(folder_logs)
        tanggal_sekarang = datetime.now().strftime("%Y-%m-%d")
        tanggal_terakhir_clear = ""
        if os.path.exists(path_log_clear):
            with open(path_log_clear, "r") as f:
                tanggal_terakhir_clear = f.read().strip()
        if tanggal_sekarang != tanggal_terakhir_clear:
            try:
                worksheet.batch_clear(['B3:H1000'])
                with open(path_log_clear, "w") as f:
                    f.write(tanggal_sekarang)
                print(f"✅ Masuk hari baru ({tanggal_sekarang}). Tabel lama dibersihkan!")
            except Exception as e:
                print(f"❌ Gagal membersihkan tabel: {e}")
        else:
            print(f"-> Masih di hari yang sama ({tanggal_sekarang}). Data baru akan ditambahkan ke bawahnya (Tabel tidak dibersihkan).")
            
        return
        
    is_pesan_tabel = ('WITEL | HOSTNAME | INTERFACE' in teks_pesan.upper()) or ('|' in teks_pesan and 'GPON' in teks_pesan.upper())

    if is_pesan_tabel:
        if sesi_pengambilan_aktif:
            print("📊 Pesan data tabel terdeteksi! Memulai ekstraksi data...")
            
            baris_baris = teks_pesan.split('\n')
            data_baru = []
            
            try:
                kolom_b = worksheet.col_values(2)
                baris_terakhir = len(kolom_b)
                if baris_terakhir < 2:
                    baris_terakhir = 2
                
                baris_mulai_input = baris_terakhir + 1
                
                no_urut_terakhir = 0
                if len(kolom_b) >= 3 and str(kolom_b[-1]).isdigit():
                    no_urut_terakhir = int(kolom_b[-1])
            except Exception as e:
                print(f"⚠️ Gagal membaca baris terakhir di Spreadsheet: {e}")
                return

            for baris in baris_baris:
                if '|' in baris and 'HOSTNAME' not in baris.upper():
                    parts = baris.split('|')
                    if len(parts) >= 6:
                        witel_saat_ini = parts[0].strip().upper()
                        
                        if witel_saat_ini in WITEL_TARGET:
                            try:
                                hostname = parts[1].strip()
                                interface = parts[2].strip()
                                deskripsi = parts[3].strip()
                                rx_raw = parts[5].strip()
                                rx_clean = re.sub(r'[^\d.\-]', '', rx_raw)

                                sto = hostname.split('-')[2] if '-' in hostname else "-"
                                rx_float = float(rx_clean)
                                while abs(rx_float) > 100:
                                    rx_float /= 1000
                                rx_val = math.trunc(rx_float)
                                
                                no_urut_terakhir += 1
                                baris_saat_ini = baris_mulai_input + len(data_baru)
                                
                                formula_distrik = f"=VLOOKUP(D{baris_saat_ini}, 'STO DISTRIK'!A:G, 7, FALSE)"
                                
                                baris_data = [no_urut_terakhir, formula_distrik, sto, hostname, interface, deskripsi, rx_val]
                                data_baru.append(baris_data)
                                
                            except Exception as e:
                                print(f"⚠️ Gagal memproses baris ({baris}): {e}")
            
            if data_baru:
                try:
                    rentang_target = f'B{baris_mulai_input}:H{baris_mulai_input + len(data_baru) - 1}'
                    worksheet.update(range_name=rentang_target, values=data_baru, value_input_option='USER_ENTERED')
                    print(f"✅ Mantap! {len(data_baru)} baris (Witel Filtered) berhasil ditambahkan ke Spreadsheet.")
                except Exception as e:
                    print(f"❌ Terjadi kesalahan saat mengupdate Spreadsheet: {e}")
            else:
                print("-> Tidak ada baris data untuk WITEL target di pesan ini.")
        else:
            print("-> Pesan tabel diabaikan karena sesi pengambilan sedang ditutup/tidak aktif.")
    
    else:
        if sesi_pengambilan_aktif:
            cuplikan_pesan = teks_pesan[:30] + '...' if len(teks_pesan) > 30 else teks_pesan
            print(f"🛑 Pesan penyela terdeteksi: '{cuplikan_pesan}'. Sesi pengambilan ditutup!")
            sesi_pengambilan_aktif = False


# ==========================================
# 3. MENJALANKAN PROGRAM
# ==========================================
async def main():
    print("🚀 Sistem Siaga! Mendengarkan Laporan Redaman (Anti-Penyela Aktif)...")
    await client.get_dialogs() 
    await client.run_until_disconnected()

if __name__ == '__main__':
    with client:
        client.loop.run_until_complete(main())