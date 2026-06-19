import os
import csv
import json
import logging
from datetime import datetime
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ===================== LOGGING SETUP =====================
# Log ke file agar mudah debug di VPS
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "mirror_cnop.log"), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===================== KONFIGURASI =====================
# URL CSV Google Sheets dari permintaan user
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1ko7iYES1PJYViKwctu0zM3rP0cHxJV-03KiV1sdMex4/export?format=csv&gid=774292654"

# Konfigurasi WAHA dari file referensi
WAHA_URL = "https://waha-dutxvo095iqn.cgk-lab.sumopod.my.id"
WAHA_SESSION = "OLTReport"
WAHA_API_KEY = "ROpWNPkTUavqEbnz5zKU4mTiL0HIZoye"

def get_sheet_data():
    try:
        response = requests.get(SHEET_CSV_URL, timeout=15)
        response.raise_for_status()
        decoded_content = response.content.decode('utf-8')
        csv_reader = csv.reader(decoded_content.splitlines(), delimiter=',')
        return list(csv_reader)
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        return None

def cek_site_id(site_id):
    data = get_sheet_data()
    if not data:
        return "❌ Maaf, gagal mengambil data dari Spreadsheet."

    nilai = ""
    found = False
    
    # Cari di setiap baris
    for row in data:
        # Pastikan baris cukup panjang (Kolom AC adalah index 28, jadi min 29 kolom)
        if len(row) < 29:
            continue
            
        current_site_id = row[4] # Kolom E (Index 4) - SITE ID
        
        # Pencarian mengabaikan huruf besar/kecil
        if current_site_id and current_site_id.strip().upper() == site_id.strip().upper():
            found = True
            branch = row[2]           # Kolom C
            sto = row[3]              # Kolom D
            site_name = row[5]        # Kolom F
            order_nim = row[8]        # Kolom I
            status = row[26]          # Kolom AA
            detil_progress = row[28]  # Kolom AC
            
            nilai += (
                f"🏢 *DATA SITE ID: {current_site_id.upper()}*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🔹 *Branch:* {branch}\n"
                f"🔹 *STO:* {sto}\n"
                f"🔹 *Site Name:* {site_name}\n"
                f"🔹 *Order NIM:* {order_nim}\n"
                f"🔹 *Status:* {status}\n\n"
                f"📝 *Detil Progress:*\n_{detil_progress}_\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
            )
            
    if not found:
        return f"❌ Maaf, data untuk SITE ID *{site_id.upper()}* tidak ditemukan."
        
    return nilai.strip()

def send_whatsapp_message(to, message):
    url = f"{WAHA_URL.rstrip('/')}/api/sendText"
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Api-Key": WAHA_API_KEY,
        "Connection": "close"
    }
    
    payload = {
        "session": WAHA_SESSION,
        "chatId": to,
        "text": message
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code in [200, 201]:
            logger.info(f"✅ Pesan berhasil dikirim ke {to}")
        else:
            logger.error(f"❌ Gagal mengirim pesan. Status: {response.status_code}, Response: {response.text}")
    except Exception as e:
        logger.error(f"❌ Error saat mengirim pesan WA: {e}")

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # Baca raw body langsung, bypass Werkzeug form-data parsing
        raw_data = request.get_data(as_text=True)
        logger.info(f"Raw request - Content-Type: {request.content_type}, Body length: {len(raw_data)}")
        
        if not raw_data:
            logger.warning("Empty request body")
            return jsonify({"status": "error", "message": "No JSON payload"}), 400
        
        try:
            contents = json.loads(raw_data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"JSON parse error: {e}, Raw body: {raw_data[:500]}")
            return jsonify({"status": "error", "message": "Invalid JSON"}), 400
            
        event_type = contents.get("event")
        if event_type and event_type != "message":
            return jsonify({"status": "ignored"}), 200
            
        payload_data = contents.get("payload", {})
        
        # ====== FILTER fromMe: Abaikan pesan dari bot sendiri ======
        from_me = payload_data.get("fromMe", False)
        if from_me:
            logger.debug("Pesan dari bot sendiri, diabaikan.")
            return jsonify({"status": "ignored", "message": "Own message ignored"}), 200
        
        pesan = payload_data.get("body", "")
        sender = payload_data.get("from", "")
        
        logger.info(f"📩 Pesan masuk dari {sender}: {pesan}")
        
        # Hanya merespon pada chat pribadi (mengabaikan chat dari grup yg berakhiran @g.us)
        if sender and sender.endswith("@g.us"):
            logger.info(f"Pesan grup dari {sender}, diabaikan.")
            return jsonify({"status": "ignored", "message": "Group message ignored"}), 200
            
        if pesan:
            pesan = pesan.strip()
            input_arr = pesan.split(" ")
            command = input_arr[0].upper()
            
            site_id_to_search = ""
            
            if command == "/CEK" and len(input_arr) > 1:
                site_id_to_search = input_arr[1]
            elif len(input_arr) == 1 and command not in ["/HELP", "/START"]:
                # User mengetik langsung SITEID
                site_id_to_search = command
                
            if site_id_to_search:
                logger.info(f"🔍 Mencari SITE ID: {site_id_to_search}")
                balasan = cek_site_id(site_id_to_search)
                send_whatsapp_message(sender, balasan)
            elif command in ["/START", "/HELP"]:
                help_msg = "Halo! Kirimkan *SITE ID* untuk mengecek data.\nContoh format:\nAGR030\natau\n/cek AGR030"
                send_whatsapp_message(sender, help_msg)
            else:
                send_whatsapp_message(sender, "Format salah. Silakan kirimkan SITE ID yang valid (Contoh: AGR030).")
                
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return jsonify({"status": "error"}), 500

if __name__ == '__main__':
    logger.info("🚀 Mirror CNOP Bot started on port 5001")
    app.run(host='0.0.0.0', port=5001)
