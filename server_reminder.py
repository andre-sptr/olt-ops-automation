from flask import Flask, jsonify
import kirim_reminder
import kirim_daman

app = Flask(__name__)

@app.route('/trigger-reminder', methods=['POST', 'GET'])
def trigger_reminder():
    try:
        print("Menerima request trigger dari Apps Script...")
        kirim_reminder.main()
        return jsonify({
            "status": "success", 
            "message": "Proses pengecekan dan pengiriman reminder telah selesai dijalankan!"
        }), 200
    except Exception as e:
        print(f"Error pada server_reminder: {e}")
        return jsonify({
            "status": "error", 
            "message": f"Terjadi kesalahan di server: {str(e)}"
        }), 500

@app.route('/trigger-daman', methods=['POST', 'GET'])
def trigger_daman():
    try:
        print("Menerima request trigger DAMAN dari Apps Script...")
        kirim_daman.tugas_harian()
        return jsonify({
            "status": "success", 
            "message": "Proses pengecekan dan pengiriman DAMAN telah selesai dijalankan!"
        }), 200
    except Exception as e:
        print(f"Error pada server_daman: {e}")
        return jsonify({
            "status": "error", 
            "message": f"Terjadi kesalahan di server: {str(e)}"
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3002)
