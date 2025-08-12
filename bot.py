
#!/usr/bin/env python3
# AIssist-IndexBot – Telegram bot with Ollama + LlamaIndex + Postgres
# Layout: <PROJECT_BASE>/<PROJECT_NAME>/{input,index}

import os
import asyncio
import logging
import requests
import psycopg2
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

from llama_index.core import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    StorageContext,
    load_index_from_storage,
)
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.readers.file import PDFReader, DocxReader, UnstructuredReader

# ---------- env & logging ----------
load_dotenv(Path(__file__).parent / ".env")
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("aissist-indexbot")
print("Starting AIssist-IndexBot…")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OLLAMA_URL     = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL          = os.getenv("MODEL", "llama3")
EMBED_MODEL    = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

PROJECT_NAME   = os.getenv("PROJECT_NAME", "AIssist")
PROJECT_BASE   = os.getenv("PROJECT_BASE", ".")
PROJECT_DIR    = os.path.join(PROJECT_BASE, PROJECT_NAME)
DOCUMENTS_DIR  = os.path.join(PROJECT_DIR, "input")
INDEX_DIR      = os.path.join(PROJECT_DIR, "index")

os.makedirs(DOCUMENTS_DIR, exist_ok=True)
os.makedirs(INDEX_DIR, exist_ok=True)

# shared thread pool
executor = ThreadPoolExecutor(max_workers=2)

# ---------- helpers ----------
def get_db_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "aidb"),
        user=os.getenv("DB_USER", "aiuser"),
        password=os.getenv("DB_PASSWORD", ""),
    )

def ai_reply(text: str) -> str:
    payload = {"model": MODEL, "prompt": text, "stream": False}
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=600)
        r.raise_for_status()
        return r.json().get("response", "No response from AI.")
    except Exception as e:
        return f"AI error: {e}"

def index_files_present() -> bool:
    return os.path.isdir(INDEX_DIR) and bool(os.listdir(INDEX_DIR))

def persist_index(index):
    print(f"[DEBUG] Saving index to {INDEX_DIR}")
    index.storage_context.persist(persist_dir=INDEX_DIR)


def build_and_persist_index():
    if not os.path.isdir(DOCUMENTS_DIR) or not os.listdir(DOCUMENTS_DIR):
        log.info("[Index] No docs found in: %s", DOCUMENTS_DIR)
        return None, 0

    log.debug("[Index] Scanning input folder: %s", DOCUMENTS_DIR)
    for fname in os.listdir(DOCUMENTS_DIR):
        log.debug(" - Found file: %s", fname)

    # readers
    file_extractor = {
        ".pdf": PDFReader(),
        ".docx": DocxReader(),
        ".doc": UnstructuredReader(),
        ".odt": UnstructuredReader(),
        ".xls": UnstructuredReader(),
        ".xlsx": UnstructuredReader(),
        ".pptx": UnstructuredReader(),
        ".txt": UnstructuredReader(),
        ".md": UnstructuredReader(),
        ".rst": UnstructuredReader(),
        ".html": UnstructuredReader(),
        ".htm": UnstructuredReader(),
    }
    for ext, reader in file_extractor.items():
        log.debug("Reader registered: %-6s -> %s", ext, reader.__class__.__name__)

    # load files one-by-one so a bad file doesn't crash the run
    documents = []
    for path in Path(DOCUMENTS_DIR).iterdir():
        if not path.is_file():
            continue
        try:
            log.debug("[Index] Loading: %s", path)
            docs = SimpleDirectoryReader(
                input_files=[str(path)],
                file_extractor=file_extractor
            ).load_data()
            documents.extend(docs)
            log.debug("[Index] Loaded %d node(s) from %s", len(docs), path.name)
            # short preview for first node
            if docs:
                preview = (docs[0].text[:200] + "...") if len(docs[0].text) > 200 else docs[0].text
                log.debug("[Index] Preview(%s): %s", path.name, preview.replace("\n", " ")[:200])
        except Exception as e:
            log.warning("[Index] Skipped %s due to error: %s", path.name, e)

    doc_count = len(documents)
    log.info("[Index] Total documents ready for embedding: %d", doc_count)
    if doc_count == 0:
        return None, 0

    embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL, device="cpu")
    index = VectorStoreIndex.from_documents(documents, embed_model=embed_model)

    log.debug("[Index] Persisting index to: %s", INDEX_DIR)
    persist_index(index)
    log.info("[Index] Saved index to: %s", INDEX_DIR)
    return index, doc_count




def load_index():
    print(f"[DEBUG] Checking index at: {INDEX_DIR}")
    if not index_files_present():
        return None
    storage_context = StorageContext.from_defaults(persist_dir=INDEX_DIR)
    embed_model = HuggingFaceEmbedding(
        model_name=EMBED_MODEL,
        device="cpu"
    )
    return load_index_from_storage(storage_context, embed_model=embed_model)

def query_index(question: str) -> str:
    llm = Ollama(model=MODEL, base_url=OLLAMA_URL, request_timeout=600)
    index = load_index()
    if index is None:
        return "Error: index could not be loaded."
    qe = index.as_query_engine(llm=llm, similarity_top_k=2)
    return str(qe.query(question))

# ---------- telegram handlers ----------
async def start(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👋 Hi! I'm your AI assistant for **{PROJECT_NAME}**.\n"
        "- /task … add tasks (multiline; optional `status:`)\n"
        "- /todo → show ToDo list\n"
        "- /ask <question> → search project docs\n"
        "- /docs → list all files in input/\n"
        "- /reindex → rebuild the index now\n"
        "- Send files → saved to input/ and indexed\n"
        "- Normal messages → AI chat"
    )

async def add_task(update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    message_text = update.message.text
    tasks = []
    default_status = "todo"

    lines = message_text.replace("/task", "", 1).strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        status = default_status
        if "status:" in line:
            before, after = line.split("status:", 1)
            after = after.strip()
            if " " in after:
                stat, rest = after.split(" ", 1)
                status = stat.strip()
                line = (before + rest).strip()
            else:
                status = after.strip()
                line = before.strip()
        tasks.append((chat_id, line, PROJECT_NAME, status))

    added = []
    try:
        conn = get_db_conn()
        with conn:
            with conn.cursor() as cur:
                for t in tasks:
                    if t[1]:
                        cur.execute(
                            "INSERT INTO tasks (chat_id, task_text, project, status) VALUES (%s, %s, %s, %s)",
                            t,
                        )
                        added.append(f"[{t[2]} / {t[3]}] {t[1]}")
        if added:
            await update.message.reply_text(
                f"{len(added)} task(s) added:\n" + "\n".join(f"- {t}" for t in added)
            )
        else:
            await update.message.reply_text("No tasks recognized.")
    except Exception as e:
        await update.message.reply_text(f"DB error: {e}")

async def show_todo(update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = get_db_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT task_text FROM tasks WHERE project = %s AND status = 'todo' ORDER BY id",
                    (PROJECT_NAME,),
                )
                rows = cur.fetchall()
        if rows:
            msg = f"To-Do list for project: {PROJECT_NAME}\n\n"
            msg += "\n".join(f"- {r[0]}" for r in rows)
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text(f"No open ToDos for project: {PROJECT_NAME}")
    except Exception as e:
        await update.message.reply_text(f"DB error: {e}")

async def ask_docs(update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /ask <your question>")
        return
    question = " ".join(context.args)

    if not index_files_present():
        await update.message.reply_text("No index found. Building index … please wait …")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(executor, build_and_persist_index)  # returns (index, count)


    await update.message.reply_text("🔍 Searching the project index …")
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(executor, query_index, question)
        await update.message.reply_text(str(result))
    except Exception as e:
        await update.message.reply_text(f"AI error: {e}")

async def handle_any_file(update, context: ContextTypes.DEFAULT_TYPE):
    file_obj, file_name = None, None
    if getattr(update.message, "document", None):
        file_obj = await context.bot.get_file(update.message.document.file_id)
        file_name = update.message.document.file_name
    elif getattr(update.message, "photo", None):
        largest = update.message.photo[-1]
        file_obj = await context.bot.get_file(largest.file_id)
        file_name = f"photo_{largest.file_id}.jpg"
    elif getattr(update.message, "audio", None):
        file_obj = await context.bot.get_file(update.message.audio.file_id)
        file_name = update.message.audio.file_name or f"audio_{update.message.audio.file_id}.mp3"
    elif getattr(update.message, "voice", None):
        file_obj = await context.bot.get_file(update.message.voice.file_id)
        file_name = f"voice_{update.message.voice.file_id}.ogg"
    elif getattr(update.message, "video", None):
        file_obj = await context.bot.get_file(update.message.video.file_id)
        file_name = update.message.video.file_name or f"video_{update.message.video.file_id}.mp4"
    elif getattr(update.message, "sticker", None):
        file_obj = await context.bot.get_file(update.message.sticker.file_id)
        file_name = f"sticker_{update.message.sticker.file_id}.webp"

    if not file_obj or not file_name:
        await update.message.reply_text("❌ Unsupported file type.")
        return

    download_path = os.path.join(DOCUMENTS_DIR, file_name)
    await file_obj.download_to_drive(download_path)
    await update.message.reply_text(f"✅ File saved: {file_name}")

    await update.message.reply_text("🔄 Updating index …")
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(executor, build_and_persist_index)  # return ignored
    await update.message.reply_text("✅ Index updated!")

async def list_docs(update, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.isdir(DOCUMENTS_DIR):
        await update.message.reply_text("No documents folder.")
        return
    files = []
    for root, _, names in os.walk(DOCUMENTS_DIR):
        for n in names:
            files.append(os.path.relpath(os.path.join(root, n), DOCUMENTS_DIR))
    if not files:
        await update.message.reply_text("No documents found.")
        return
    files.sort(key=str.lower)
    # chunk to avoid Telegram 4096 char limit
    buf = []
    for i, f in enumerate(files, 1):
        buf.append(f"{i}. {f}")
        if sum(len(x)+1 for x in buf) > 3500:
            await update.message.reply_text("\n".join(buf))
            buf = []
    if buf:
        await update.message.reply_text("\n".join(buf))

async def reindex_cmd(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Rebuilding index …")
    loop = asyncio.get_running_loop()
    try:
        index, doc_count = await loop.run_in_executor(executor, build_and_persist_index)
        if index is None or doc_count == 0:
            await update.message.reply_text("No documents found in input/ — nothing to index.")
            return
        await update.message.reply_text(f"✅ Index updated. Documents indexed: {doc_count}")
    except Exception as e:
        await update.message.reply_text(f"Index error: {e}")

async def handle_message(update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    ai_text = ai_reply(user_text)
    await update.message.reply_text(ai_text)

# ---------- bootstrap ----------
def main():
    if not TELEGRAM_TOKEN:
        print("ERROR: TELEGRAM_TOKEN is empty. Check .env next to bot.py")
        return

    print("Init Telegram app…")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # clear webhook
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
    except Exception:
        pass

    # auto-reindex if missing
    if not index_files_present():
        print("[Init] No index found. Building…")
        build_and_persist_index()

    # handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("task", add_task))
    app.add_handler(CommandHandler("todo", show_todo))
    app.add_handler(CommandHandler("ask", ask_docs))
    app.add_handler(CommandHandler("docs", list_docs))
    app.add_handler(CommandHandler("reindex", reindex_cmd))

    file_filter = (
        filters.Document.ALL
        | filters.PHOTO
        | filters.AUDIO
        | filters.VOICE
        | filters.VIDEO
        | filters.Sticker.ALL
    )
    app.add_handler(MessageHandler(file_filter, handle_any_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Polling started.")
    app.run_polling()

if __name__ == "__main__":
    main()
