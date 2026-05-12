import os
import sys
from pathlib import Path
from typing import List
import vertexai
from vertexai.preview import rag

# ==================== CONFIG ====================
GCP_PROJECT = "gemini-agent-494105"
LOCATION = "asia-southeast1"

EXISTING_CORPUS_ID = "713820540938223616" 
BUCKET_NAME = "telegram-chat-rag-corpus" 
GCS_FILE_URI = f"gs://{BUCKET_NAME}/chat_history.txt"

# ==================== STEP 3: IMPORT FILES (VIA GCS) ====================
def import_files_to_corpus(corpus_resource_name: str) -> bool:
    """
    Import file dari GCS ke korpus yang sudah ada
    """
    print(f"\n📤 Menghubungkan ke Korpus: {corpus_resource_name}")
    print(f"   Mencoba menarik file dari: {GCS_FILE_URI}")
    
    try:
        import_response = rag.import_files(
            corpus_name=corpus_resource_name,
            paths=[GCS_FILE_URI]
        )
        
        print(f"   ✅ Permintaan import berhasil dikirim!")
        print(f"   ⏳ Tunggu 5-10 menit untuk proses indexing.")
        return True
        
    except Exception as e:
        print(f"❌ Error saat import: {e}")
        print("\n💡 Tips Perbaikan:")
        print(f"1. Pastikan Bucket '{BUCKET_NAME}' ada di Project '{GCP_PROJECT}'.")
        print(f"2. Pastikan file 'chat_history.txt' ada di dalam bucket tersebut.")
        print(f"3. Berikan izin 'Storage Object Viewer' ke Service Account Vertex AI jika error berlanjut.")
        return False

# ==================== MAIN WORKFLOW ====================
def main():
    print("=" * 70)
    print("🚀 Vertex AI RAG Corpus - Import to Existing Corpus")
    print("=" * 70)
    
    vertexai.init(project=GCP_PROJECT, location=LOCATION)
    
    corpus_resource_name = f"projects/{GCP_PROJECT}/locations/{LOCATION}/ragCorpora/{EXISTING_CORPUS_ID}"
    
    success = import_files_to_corpus(corpus_resource_name)
    
    if success:
        print("\n" + "=" * 70)
        print("✅ PROSES SELESAI!")
        print(f"RAG_CORPUS_NAME: {corpus_resource_name}")
        print("=" * 70)
        print("\nSilakan tunggu beberapa saat, lalu coba jalankan bot Telegram-mu!")

if __name__ == "__main__":
    main()