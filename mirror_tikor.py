import asyncio
import re
import gspread
from telethon import TelegramClient
from oauth2client.service_account import ServiceAccountCredentials

# --- KONFIGURASI ---
API_ID = 37811433
API_HASH = 'c5656009e5b4d0b70a4f92a605c9eab4'
USERNAME_BOT = '@sc_tif_area1_bot'
LINK_SPREADSHEET = 'https://docs.google.com/spreadsheets/d/1awIFqR437EmG2PpfnqbTTYzIOSJloOe-d2cyW0XKep8/edit'
FILE_KREDENSIAL = 'kunci_rahasia_google.json'

def setup_google_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(FILE_KREDENSIAL, scope)
    client_gs = gspread.authorize(creds)
    return client_gs.open_by_url(LINK_SPREADSHEET).sheet1

def ekstrak_data_bot(teks_respon):
    match_no_odp = re.search(r'(No nearby ODPs found for coordinate:.*)', teks_respon, re.IGNORECASE)
    if match_no_odp:
        return match_no_odp.group(1)
    match_invalid = re.search(r'(Invalid format\..*)', teks_respon, re.IGNORECASE)
    if match_invalid:
        return "Invalid format"
    blok_alternatif = teks_respon.split("ALTERNATIF #")[1:]
    hasil_odp = []
    for blok in blok_alternatif:
        baris_pertama = blok.split('\n')[0]
        match_jarak = re.search(r'(\d+)\s*m\b', baris_pertama)
        if not match_jarak: 
            continue
            
        jarak = int(match_jarak.group(1))
        if jarak >= 230: 
            continue
            
        match_odp = re.search(r'(ODP-\S+)', blok)
        nama_odp = match_odp.group(1) if match_odp else "ODP-Unknown"
        
        match_port = re.search(r'Tersedia Port[^\d]*(\d+)', blok, re.IGNORECASE)
        port_idle = match_port.group(1) if match_port else "0"
        
        match_rx = re.search(r'Feasible Expand[^\d-]*(-?\d+\.\d+)\s*dBm', blok, re.IGNORECASE)
        rx_val = float(match_rx.group(1)) if match_rx else -99.99
            
        potensi = " (Potensi Expand)" if rx_val > -19.0 else ""
        hasil_odp.append(f"{nama_odp} - {jarak} m - {port_idle} idle - ({rx_val} dBm){potensi}")
        
    return " | ".join(hasil_odp)

async def proses_check_tikor(client, sheet):
    """Fungsi inti untuk scanning baris kosong dan eksekusi bot."""
    print("\n🔍 Memeriksa baris baru di Spreadsheet...")
    
    all_data = sheet.get_all_values() 
    
    for i in range(1, len(all_data)):
        baris_data = all_data[i]
        tikor = baris_data[0].strip() 

        hasil_b = baris_data[1].strip() if len(baris_data) > 1 else ""
        
        baris_ke = i + 1

        if tikor and not hasil_b:
            print(f"🚀 Menemukan TIKOR baru di baris {baris_ke}: {tikor}")
            
            pesan_kirim = await client.send_message(USERNAME_BOT, f'/check {tikor}')
            print("   Menunggu balasan bot (18 detik)...")
            await asyncio.sleep(18) 
            
            pesan_pesan = await client.get_messages(USERNAME_BOT, min_id=pesan_kirim.id, limit=10)
            
            teks_gabungan = "\n".join([msg.text for msg in reversed(pesan_pesan) if msg.text])
            
            hasil_akhir = ekstrak_data_bot(teks_gabungan)
            
            if not hasil_akhir:
                hasil_akhir = "Tidak ditemukan ODP < 230m"
            
            sheet.update_cell(baris_ke, 2, hasil_akhir)
            print(f"✅ Baris {baris_ke} Terupdate: {hasil_akhir}")
            
            await asyncio.sleep(2)
        else:
            continue

async def main():
    client = TelegramClient('sesi_mirror_tikor', API_ID, API_HASH)
    await client.start()
    print("🤖 Bot Pemantau Aktif!")
    
    sheet = setup_google_sheets()

    while True:
        try:
            await proses_check_tikor(client, sheet)
        except Exception as e:
            print(f"⚠️ Terjadi error: {e}. Mencoba lagi dalam 30 detik...")
            await asyncio.sleep(30)
            continue
            
        print("😴 Semua baris baru sudah diproses. Tidur selama 60 detik...")
        await asyncio.sleep(60)

if __name__ == '__main__':
    asyncio.run(main())