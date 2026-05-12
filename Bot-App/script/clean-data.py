import json

def clean_telegram_json(input_file, output_file):
    print("Mulai membaca file JSON...")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    messages = data.get('messages', [])
    clean_count = 0

    with open(output_file, 'w', encoding='utf-8') as out:
        for msg in messages:
            if msg.get('type') == 'message':
                sender = msg.get('from', 'Anonim')
                raw_text = msg.get('text', '')
                
                if isinstance(raw_text, list):
                    text = "".join([t if isinstance(t, str) else t.get('text', '') for t in raw_text])
                else:
                    text = raw_text
                
                text = text.strip()
                if text: 
                    out.write(f"{sender}: {text}\n\n")
                    clean_count += 1

    print(f"Selesai! {clean_count} pesan berhasil diekstrak ke {output_file}")

clean_telegram_json('result.json', 'chat_bersih.txt')