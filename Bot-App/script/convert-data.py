import json

with open("result.json", "r", encoding="utf-8") as f:
    data = json.load(f)

documents = []
for i, msg in enumerate(data["messages"]):
    if msg.get("type") == "message" and msg.get("text"):
        text = msg["text"] if isinstance(msg["text"], str) else " ".join(
            t if isinstance(t, str) else t.get("text", "") for t in msg["text"]
        )
        documents.append({
            "id": str(i),
            "jsonData": json.dumps({
                "sender": msg.get("from", "Unknown"),
                "date": msg.get("date", ""),
                "content": text,
                "reply_to": msg.get("reply_to_message_id", None)
            })
        })

with open("chat_docs.ndjson", "w") as f:
    for doc in documents:
        f.write(json.dumps(doc) + "\n")

print(f"Total {len(documents)} pesan dikonversi.")