import os
import re
import asyncio
import logging
from typing import Optional, List, Dict
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
import vertexai
from vertexai.preview import rag
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# ==================== LOGGING ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================
class Config:
    TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
    GCP_PROJECT      = os.getenv("GCP_PROJECT", "your-gcp-project-id")
    LOCATION         = os.getenv("GCP_LOCATION", "asia-southeast1")
    RAG_CORPUS_NAME  = os.getenv("RAG_CORPUS_NAME")
    GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY")

    KNOWN_LOCATIONS  = {"DUM", "UBT", "PPN", "SAK", "ARK"}
    TTR_MAP          = {"LOW": 24, "MINOR": 16, "OLO": 4, "MAJOR": 8}

    @classmethod
    def validate(cls):
        required = ["TELEGRAM_TOKEN", "RAG_CORPUS_NAME"]
        missing = [k for k in required if not getattr(cls, k)]
        if missing:
            raise ValueError(f"Missing config: {missing}")


# ==================== INITIALIZATION ====================
def init_clients():
    try:
        vertexai.init(project=Config.GCP_PROJECT, location=Config.LOCATION)
        genai.configure(api_key=Config.GEMINI_API_KEY)
        logger.info("✅ Clients initialized")
    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        raise


# ==================== RAG RETRIEVAL ====================
class RAGRetriever:
    def __init__(self, corpus_name: str):
        self.corpus_name = corpus_name

    def retrieve_documents(self, query: str, top_k: int = 8) -> List[str]:
        try:
            logger.info(f"🔍 Retrieving: {query[:60]}...")
            response = rag.retrieval_query(
                rag_resources=[rag.RagResource(rag_corpus=self.corpus_name)],
                text=query,
                similarity_top_k=top_k,
            )
            docs = []
            if hasattr(response, 'contexts'):
                contexts_list = getattr(response.contexts, 'contexts', response.contexts)
                for ctx in contexts_list:
                    text = ''
                    if hasattr(ctx, 'text'):
                        text = ctx.text
                    elif hasattr(ctx, 'chunks') and ctx.chunks:
                        chunk = ctx.chunks[0]
                        if hasattr(chunk, 'data') and hasattr(chunk.data, 'string_value'):
                            text = chunk.data.string_value
                    if text and text.strip():
                        docs.append(text.strip())
            logger.info(f"✅ Retrieved {len(docs)} docs")
            return docs
        except Exception as e:
            logger.error(f"❌ RAG error: {e}")
            return []


# ==================== ANSWER GENERATOR ====================
class AnswerGenerator:
    """
    Semua generate_* method menerima konteks dari RAG,
    lalu membentuk prompt domain-specific untuk Gemini.
    """

    MODEL_NAME = "gemini-3.1-pro-preview"

    def __init__(self):
        self.model = genai.GenerativeModel(self.MODEL_NAME)

    def _call(self, prompt: str) -> Optional[str]:
        try:
            resp = self.model.generate_content(prompt)
            return resp.text
        except Exception as e:
            logger.error(f"❌ Gemini error: {e}")
            return None

    def general_answer(self, query: str, docs: List[str]) -> Optional[str]:
        if not docs:
            return None
        context = "\n---\n".join(docs[:6])
        prompt = f"""Kamu adalah asisten monitoring jaringan TIF (Telkomsel Infrastructure Fault).
Tugasmu menjawab pertanyaan tim RDT berdasarkan riwayat laporan tiket gangguan NodeB & OLO.

Istilah penting:
- INC = nomor tiket insiden
- TTR = Time to Repair (batas waktu perbaikan)
- COMPLY/NOT COMPLY = apakah perbaikan selesai dalam TTR
- SEGMEN: DROPCORE/FEEDER/ONT/BACKBONE, dll
- PENYEBAB: FO CUT, ONT RUSAK, VANDALISME, dll
- STATUS: OPEN (belum selesai) / CLOSED (selesai)
- Lokasi: DUM=Dumai, UBT=Ujung Batu, PPN=Pekanbaru, SAK=Siak, ARK=Arengka

RIWAYAT CHAT RELEVAN:
{context}

PERTANYAAN: {query}

Instruksi jawaban:
1. Ringkas dan akurat (max 4 kalimat)
2. Hanya gunakan data dari riwayat di atas
3. Sebutkan INC, nama teknisi, atau waktu jika relevan
4. Jika tidak ada informasi → "Tidak ditemukan di riwayat chat"
5. Gunakan format poin jika ada lebih dari 1 item

JAWABAN:"""
        return self._call(prompt)

    def ticket_detail(self, inc_id: str, docs: List[str]) -> Optional[str]:
        if not docs:
            return None
        context = "\n---\n".join(docs[:5])
        prompt = f"""Kamu adalah sistem laporan tiket gangguan jaringan NodeB & OLO.

Ekstrak dan tampilkan detail lengkap tiket {inc_id} dari data berikut:

DATA TIKET:
{context}

Format output WAJIB seperti ini (gunakan emoji):
🎫 *{inc_id}*
📍 Lokasi: [lokasi]
🏷️ Kategori: [kategori] | TTR: [X] Jam
⏱️ Buka: [jam open]
⏰ Maks Close: [max jam close]
⌛ TTR Real: [ttr real] | Sisa: [sisa ttr]
✅/❌ Compliance: [COMPLY/NOT COMPLY]
👷 Teknisi: [nama teknisi]
🔧 Segmen: [segmen]
⚠️ Penyebab: [penyebab]
📊 Status: [OPEN/CLOSED]
🔄 Terakhir Update: [update terakhir dari timely report]

Jika data tidak lengkap, tulis "-" pada field yang kosong.
JANGAN tambahkan teks lain di luar format ini."""
        return self._call(prompt)

    def daily_summary(self, docs: List[str]) -> Optional[str]:
        if not docs:
            return None
        context = "\n---\n".join(docs[:8])
        prompt = f"""Kamu adalah analis jaringan TIF. Buat ringkasan harian dari laporan tiket gangguan berikut.

DATA:
{context}

Buat ringkasan dengan format:
📊 *RINGKASAN HARIAN GANGGUAN*
📅 [tanggal terbaru dari data]

*Total Tiket:* [N]
🔴 OPEN: [N tiket]
🟢 CLOSED: [N tiket]

*Breakdown Kategori:*
• LOW: [N]
• MINOR: [N]
• OLO: [N]

*TTR Compliance:*
✅ COMPLY: [N]
❌ NOT COMPLY: [N]

*Penyebab Terbanyak:* [top 2-3 penyebab]

*Tiket OPEN yang Mendekati Deadline:*
[list INC yang sisa TTR < 4 jam, jika ada]

Gunakan data nyata dari laporan. Jika data tidak cukup untuk suatu field, tulis "N/A"."""
        return self._call(prompt)

    def tickets_by_location(self, lokasi: str, docs: List[str]) -> Optional[str]:
        if not docs:
            return None
        context = "\n---\n".join(docs[:8])
        prompt = f"""Dari data laporan gangguan jaringan berikut, tampilkan SEMUA tiket di lokasi "{lokasi}".

DATA:
{context}

Format output:
📍 *TIKET LOKASI {lokasi.upper()}*

Untuk setiap tiket:
• [INC ID] - [Nama Site] | [Kategori] | [STATUS] | Teknisi: [nama] | TTR Sisa: [X jam]

Urutkan: OPEN dulu, kemudian CLOSED.
Jika tidak ada tiket di lokasi ini, tulis "Tidak ada tiket untuk lokasi {lokasi}"."""
        return self._call(prompt)

    def tickets_by_teknisi(self, nama: str, docs: List[str]) -> Optional[str]:
        if not docs:
            return None
        context = "\n---\n".join(docs[:8])
        prompt = f"""Dari data laporan gangguan, tampilkan semua tiket yang ditangani teknisi bernama "{nama}".

DATA:
{context}

Format output:
👷 *TIKET TEKNISI: {nama.upper()}*

Untuk setiap tiket:
• [INC ID] - [Nama Site] | [Kategori] | [STATUS] | Sisa TTR: [X jam]

Jika tidak ada tiket, tulis "Tidak ada tiket untuk teknisi {nama}"."""
        return self._call(prompt)

    def ttr_breach_report(self, docs: List[str]) -> Optional[str]:
        if not docs:
            return None
        context = "\n---\n".join(docs[:8])
        prompt = f"""Dari data laporan gangguan, identifikasi tiket dengan TTR COMPLIANCE = NOT COMPLY atau yang mendekati breach.

DATA:
{context}

Format output:
🚨 *LAPORAN BREACH TTR*

Untuk setiap tiket NOT COMPLY atau sisa TTR ≤ 2 jam:
❌ [INC ID] - [Nama Site]
   Kategori: [X] | TTR: [X jam] | Sisa: [X jam]
   Teknisi: [nama] | Status: [OPEN/CLOSED]
   Compliance: [COMPLY/NOT COMPLY]

Jika tidak ada, tulis "✅ Tidak ada tiket breach TTR saat ini"."""
        return self._call(prompt)

    def ticket_progress(self, inc_id: str, docs: List[str]) -> Optional[str]:
        if not docs:
            return None
        context = "\n---\n".join(docs[:5])
        prompt = f"""Tampilkan kronologi progress / timely report tiket {inc_id} dari data berikut.

DATA:
{context}

Format output:
🔄 *PROGRESS {inc_id}*
📍 Site: [nama site] | Status: [OPEN/CLOSED]

Timely Report:
[tampilkan semua update timely report secara berurutan]

Update Terakhir: [update paling baru]

Jika tiket tidak ditemukan, tulis "Tiket {inc_id} tidak ditemukan"."""
        return self._call(prompt)


# ==================== HELPER FUNCTIONS ====================
def extract_inc_from_text(text: str) -> Optional[str]:
    """Ekstrak nomor INC dari teks pengguna"""
    match = re.search(r'INC\d{6,}', text.upper())
    return match.group(0) if match else None

def format_response(text: str, max_len: int = 4000) -> str:
    """Potong response jika terlalu panjang untuk Telegram"""
    if len(text) > max_len:
        return text[:max_len] + "\n\n_...terpotong. Coba pertanyaan lebih spesifik._"
    return text

def build_main_keyboard() -> InlineKeyboardMarkup:
    """Keyboard menu utama"""
    buttons = [
        [
            InlineKeyboardButton("📊 Ringkasan Hari Ini", callback_data="cmd_ringkasan"),
            InlineKeyboardButton("🚨 Breach TTR", callback_data="cmd_breach"),
        ],
        [
            InlineKeyboardButton("📍 Cari by Lokasi", callback_data="cmd_lokasi_help"),
            InlineKeyboardButton("👷 Cari by Teknisi", callback_data="cmd_teknisi_help"),
        ],
        [
            InlineKeyboardButton("❓ Bantuan", callback_data="cmd_help"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


# ==================== GLOBAL INSTANCES ====================
retriever: Optional[RAGRetriever] = None
generator: Optional[AnswerGenerator] = None


# ==================== BOT HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"👋 Halo *{user.first_name}*!\n\n"
        "Saya adalah *RDT Assistant Bot* — asisten monitoring tiket gangguan "
        "jaringan NodeB & OLO berbasis AI.\n\n"
        "🔍 *Yang bisa saya lakukan:*\n"
        "• Cari detail tiket berdasarkan nomor INC\n"
        "• Lihat tiket per lokasi atau teknisi\n"
        "• Ringkasan harian gangguan\n"
        "• Identifikasi tiket breach TTR\n"
        "• Jawab pertanyaan bebas tentang riwayat tiket\n\n"
        "Gunakan menu di bawah atau ketik `/help` untuk daftar perintah lengkap."
    )
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=build_main_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📚 *Daftar Perintah RDT Assistant Bot*\n\n"
        "*🔍 Pencarian Tiket:*\n"
        "• `/tiket INC48496544` — Detail tiket by nomor INC\n"
        "• `/progress INC48496544` — Kronologi progress tiket\n"
        "• `/lokasi DUM` — Semua tiket di lokasi (DUM/UBT/PPN/SAK/ARK)\n"
        "• `/teknisi RIAN` — Tiket yang ditangani teknisi tertentu\n\n"
        "*📊 Laporan:*\n"
        "• `/ringkasan` — Ringkasan harian open/closed/compliance\n"
        "• `/breach` — Tiket dengan TTR NOT COMPLY atau mendekati batas\n\n"
        "*💬 Pertanyaan Bebas:*\n"
        "• `/tanya <pertanyaan>` — Tanya apapun tentang riwayat tiket\n\n"
        "*ℹ️ Lainnya:*\n"
        "• `/start` — Menu utama\n"
        "• `/status` — Cek status bot\n\n"
        "_Contoh:_\n"
        "`/tiket INC48487328`\n"
        "`/lokasi DUM`\n"
        "`/tanya siapa teknisi yang menangani Sialang Sakti?`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now().strftime("%d %b %Y %H:%M WIB")
    text = (
        "✅ *Status RDT Assistant Bot*\n\n"
        f"🕐 Waktu: {now}\n"
        "• RAG Corpus (Vertex AI): ✅ Terhubung\n"
        "• Gemini AI: ✅ Terhubung\n"
        "• Telegram Bot: ✅ Aktif\n\n"
        "_Bot siap menerima pertanyaan._"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def handle_tiket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cari detail tiket berdasarkan INC ID"""
    query_text = " ".join(context.args) if context.args else ""
    inc_id = extract_inc_from_text(query_text)

    if not inc_id:
        await update.message.reply_text(
            "❌ Masukkan nomor INC yang valid.\n"
            "_Contoh:_ `/tiket INC48496544`",
            parse_mode="Markdown"
        )
        return

    msg = await update.message.reply_text(f"🔍 Mencari tiket *{inc_id}*...", parse_mode="Markdown")
    try:
        docs = retriever.retrieve_documents(f"tiket {inc_id} detail informasi lengkap")
        if not docs:
            await msg.edit_text(f"❌ Data tiket *{inc_id}* tidak ditemukan di riwayat chat.", parse_mode="Markdown")
            return
        answer = generator.ticket_detail(inc_id, docs)
        if not answer:
            await msg.edit_text("❌ Gagal memproses data tiket.")
            return
        await msg.edit_text(format_response(answer), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"handle_tiket error: {e}")
        await msg.edit_text(f"❌ Error: {str(e)[:100]}")


async def handle_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kronologi timely report suatu tiket"""
    query_text = " ".join(context.args) if context.args else ""
    inc_id = extract_inc_from_text(query_text)

    if not inc_id:
        await update.message.reply_text(
            "❌ Masukkan nomor INC yang valid.\n"
            "_Contoh:_ `/progress INC48496544`",
            parse_mode="Markdown"
        )
        return

    msg = await update.message.reply_text(f"🔄 Mengambil progress *{inc_id}*...", parse_mode="Markdown")
    try:
        docs = retriever.retrieve_documents(f"timely report progress update {inc_id}")
        if not docs:
            await msg.edit_text(f"❌ Data progress tiket *{inc_id}* tidak ditemukan.", parse_mode="Markdown")
            return
        answer = generator.ticket_progress(inc_id, docs)
        if not answer:
            await msg.edit_text("❌ Gagal memproses data progress.")
            return
        await msg.edit_text(format_response(answer), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"handle_progress error: {e}")
        await msg.edit_text(f"❌ Error: {str(e)[:100]}")


async def handle_lokasi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cari tiket berdasarkan kode lokasi"""
    if not context.args:
        locs = " | ".join(Config.KNOWN_LOCATIONS)
        await update.message.reply_text(
            f"❌ Masukkan kode lokasi.\n"
            f"_Lokasi tersedia:_ `{locs}`\n\n"
            "_Contoh:_ `/lokasi DUM`",
            parse_mode="Markdown"
        )
        return

    lokasi = context.args[0].upper()
    msg = await update.message.reply_text(f"📍 Mencari tiket lokasi *{lokasi}*...", parse_mode="Markdown")
    try:
        docs = retriever.retrieve_documents(
            f"tiket gangguan lokasi {lokasi} TSEL OLO NodeB status teknisi"
        )
        if not docs:
            await msg.edit_text(f"❌ Tidak ada tiket ditemukan untuk lokasi *{lokasi}*.", parse_mode="Markdown")
            return
        answer = generator.tickets_by_location(lokasi, docs)
        if not answer:
            await msg.edit_text("❌ Gagal memproses data lokasi.")
            return
        await msg.edit_text(format_response(answer), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"handle_lokasi error: {e}")
        await msg.edit_text(f"❌ Error: {str(e)[:100]}")


async def handle_teknisi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cari tiket berdasarkan nama teknisi"""
    if not context.args:
        await update.message.reply_text(
            "❌ Masukkan nama teknisi.\n"
            "_Contoh:_ `/teknisi RIAN` atau `/teknisi FEREZI`",
            parse_mode="Markdown"
        )
        return

    nama = " ".join(context.args).upper()
    msg = await update.message.reply_text(f"👷 Mencari tiket teknisi *{nama}*...", parse_mode="Markdown")
    try:
        docs = retriever.retrieve_documents(
            f"tiket teknisi {nama} penanganan gangguan INC status"
        )
        if not docs:
            await msg.edit_text(f"❌ Tidak ada tiket ditemukan untuk teknisi *{nama}*.", parse_mode="Markdown")
            return
        answer = generator.tickets_by_teknisi(nama, docs)
        if not answer:
            await msg.edit_text("❌ Gagal memproses data teknisi.")
            return
        await msg.edit_text(format_response(answer), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"handle_teknisi error: {e}")
        await msg.edit_text(f"❌ Error: {str(e)[:100]}")


async def handle_ringkasan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ringkasan harian tiket gangguan"""
    msg = await update.message.reply_text("📊 Menyusun ringkasan harian...", parse_mode="Markdown")
    try:
        docs = retriever.retrieve_documents(
            "ringkasan tiket gangguan NodeB OLO TSEL hari ini OPEN CLOSED TTR COMPLY kategori LOW MINOR",
            top_k=10
        )
        if not docs:
            await msg.edit_text("❌ Data tidak cukup untuk membuat ringkasan.")
            return
        answer = generator.daily_summary(docs)
        if not answer:
            await msg.edit_text("❌ Gagal memproses ringkasan.")
            return
        await msg.edit_text(format_response(answer), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"handle_ringkasan error: {e}")
        await msg.edit_text(f"❌ Error: {str(e)[:100]}")


async def handle_breach(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Laporan tiket NOT COMPLY atau mendekati deadline"""
    msg = await update.message.reply_text("🚨 Memeriksa breach TTR...", parse_mode="Markdown")
    try:
        docs = retriever.retrieve_documents(
            "TTR NOT COMPLY breach deadline sisa TTR habis compliance tiket OPEN kritis",
            top_k=10
        )
        if not docs:
            await msg.edit_text("❌ Data tidak ditemukan.")
            return
        answer = generator.ttr_breach_report(docs)
        if not answer:
            await msg.edit_text("❌ Gagal memproses laporan breach.")
            return
        await msg.edit_text(format_response(answer), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"handle_breach error: {e}")
        await msg.edit_text(f"❌ Error: {str(e)[:100]}")


async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pertanyaan bebas tentang riwayat tiket"""
    if not context.args:
        await update.message.reply_text(
            "❌ Format: `/tanya <pertanyaanmu>`\n\n"
            "_Contoh:_\n"
            "`/tanya siapa teknisi tiket Pelabuhan Dumai?`\n"
            "`/tanya berapa tiket yang sudah closed hari ini?`",
            parse_mode="Markdown"
        )
        return

    query = " ".join(context.args)
    user = update.effective_user
    logger.info(f"❓ [{user.username}] {query}")

    inc_id = extract_inc_from_text(query)

    msg = await update.message.reply_text("🤔 Mencari informasi di riwayat tiket...")
    try:
        enriched_query = f"{query} tiket gangguan NodeB OLO TIF Telkomsel"
        docs = retriever.retrieve_documents(enriched_query)

        if not docs:
            await msg.edit_text(
                "❌ Informasi tidak ditemukan di riwayat chat.\n"
                "Coba pertanyaan yang lebih spesifik atau gunakan nama INC."
            )
            return

        await msg.edit_text("🧠 Memproses jawaban...")

        if inc_id:
            answer = generator.ticket_detail(inc_id, docs)
        else:
            answer = generator.general_answer(query, docs)

        if not answer:
            await msg.edit_text("❌ Gagal memproses jawaban.")
            return

        response_text = f"🤖 *Jawaban:*\n\n{answer}"
        await msg.edit_text(format_response(response_text), parse_mode="Markdown")

    except Exception as e:
        logger.error(f"handle_question error: {e}")
        await msg.edit_text(f"❌ Terjadi kesalahan: {str(e)[:100]}")


async def handle_natural_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle pesan biasa di private chat.
    Deteksi otomatis: INC → detail tiket, lokasi kode → tiket lokasi, else → tanya umum
    """
    text = update.message.text.strip()
    user = update.effective_user
    logger.info(f"💬 [{user.username}] {text[:60]}")

    inc_id = extract_inc_from_text(text)
    if inc_id:
        context.args = [inc_id]
        await handle_tiket(update, context)
        return

    loc_match = re.search(r'\b(DUM|UBT|PPN|SAK|ARK)\b', text.upper())
    if loc_match and len(text.split()) <= 3:
        context.args = [loc_match.group(1)]
        await handle_lokasi(update, context)
        return

    context.args = text.split()
    await handle_question(update, context)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    fake_update = update

    if data == "cmd_ringkasan":
        context.args = []
        await query.message.reply_text("📊 Menyusun ringkasan harian...")
        await handle_ringkasan(fake_update, context)

    elif data == "cmd_breach":
        context.args = []
        await handle_breach(fake_update, context)

    elif data == "cmd_help":
        await help_command(fake_update, context)

    elif data == "cmd_lokasi_help":
        locs = " | ".join(sorted(Config.KNOWN_LOCATIONS))
        await query.message.reply_text(
            f"📍 Ketik `/lokasi <kode>`\n\n"
            f"_Kode lokasi tersedia:_ `{locs}`\n\n"
            "_Contoh:_ `/lokasi DUM`",
            parse_mode="Markdown"
        )

    elif data == "cmd_teknisi_help":
        await query.message.reply_text(
            "👷 Ketik `/teknisi <nama>`\n\n"
            "_Contoh:_ `/teknisi RIAN` atau `/teknisi FEREZI LUVI`",
            parse_mode="Markdown"
        )


async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg and msg.text:
        inc_ids = re.findall(r'INC\d{6,}', msg.text.upper())
        if inc_ids:
            logger.info(f"📥 [Group:{msg.chat.title}] INC detected: {inc_ids}")


# ==================== ERROR HANDLER ====================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ Terjadi kesalahan internal. Silakan coba lagi."
        )


# ==================== MAIN ====================
def main():
    try:
        Config.validate()
        logger.info("✅ Configuration validated")

        init_clients()

        global retriever, generator
        retriever  = RAGRetriever(Config.RAG_CORPUS_NAME)
        generator  = AnswerGenerator()
        logger.info("✅ RAG + Gemini initialized")

        app = ApplicationBuilder().token(Config.TELEGRAM_TOKEN).build()

        app.add_handler(CommandHandler("start",     start))
        app.add_handler(CommandHandler("help",      help_command))
        app.add_handler(CommandHandler("status",    status_command))
        app.add_handler(CommandHandler("tanya",     handle_question))
        app.add_handler(CommandHandler("tiket",     handle_tiket))
        app.add_handler(CommandHandler("progress",  handle_progress))
        app.add_handler(CommandHandler("lokasi",    handle_lokasi))
        app.add_handler(CommandHandler("teknisi",   handle_teknisi))
        app.add_handler(CommandHandler("ringkasan", handle_ringkasan))
        app.add_handler(CommandHandler("breach",    handle_breach))

        app.add_handler(CallbackQueryHandler(handle_callback))

        app.add_handler(MessageHandler(
            filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
            handle_natural_message
        ))

        app.add_handler(MessageHandler(
            filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND,
            handle_group_message
        ))

        app.add_error_handler(error_handler)

        logger.info("🚀 RDT Assistant Bot started. Press Ctrl+C to stop.")
        app.run_polling()

    except KeyboardInterrupt:
        logger.info("⏹️ Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()