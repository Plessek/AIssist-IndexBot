#!/usr/bin/env python3
# AIssist-IndexBot one-click setup

# ---- bootstrap into venv (no external imports yet) ----
import os, sys, subprocess, shutil
from pathlib import Path

if not os.path.exists(".venv"):
    subprocess.run([sys.executable, "-m", "venv", ".venv"], check=True)

# restart inside venv if not already
if os.path.abspath(sys.prefix) != os.path.abspath(".venv"):
    python_path = os.path.join(".venv", "bin", "python")
    os.execv(python_path, [python_path, __file__])

# ---- now we're in venv ----
import getpass
from urllib.parse import urlparse

print("=== AIssist-IndexBot Setup ===")

pip_path    = os.path.join(".venv", "bin", "pip")
python_path = os.path.join(".venv", "bin", "python")

def ask(name, default=None, secret=False, required=False):
    while True:
        prompt = f"{name}" + (f" [{default}]" if default else "") + ": "
        val = getpass.getpass(prompt).strip() if secret else input(prompt).strip()
        val = val or (default or "")
        if required and not val:
            print("  -> This value is required.")
            continue
        return val

def install_pandoc_if_needed():
    if shutil.which("pandoc"):
        print("✅ pandoc already installed.")
        return
    print("ℹ️ pandoc not found. Trying to install via apt…")
    apt = shutil.which("apt-get") or shutil.which("apt")
    if not apt:
        print("⚠️ Could not find apt. Please install pandoc manually.")
        return
    try:
        subprocess.run(["sudo", apt, "update"], check=True)
        subprocess.run(["sudo", apt, "install", "-y", "pandoc"], check=True)
        print("✅ pandoc installed.")
    except Exception as e:
        print(f"⚠️ Could not install pandoc automatically: {e}")
        print("   Please install it manually: sudo apt-get install pandoc")
        print("   macOS: brew install pandoc  |  Fedora: sudo dnf install pandoc")

# 1) Install Python deps (readers included)
print("📦 Installing Python dependencies into venv…")
deps = [
    "python-telegram-bot>=21.0,<22.0",
    "requests>=2.31.0,<3.0",
    "psycopg2-binary>=2.9.9,<3.0",
    "python-dotenv>=1.0.1,<2.0",
    "llama-index-core>=0.12.4,<0.13.0",
    "llama-index-llms-ollama==0.6.2",
    "llama-index-embeddings-huggingface==0.4.0",
    "llama-index-readers-file>=0.2.0",
    # Full document parsing support
    "unstructured[all-docs]>=0.15.0",
    "pypdf>=4.2.0",
    "pdfplumber>=0.11.0",
    "python-docx>=1.1.2",
    "docx2txt>=0.8",
    "odfpy>=1.4.1",
    "openpyxl>=3.1.5",
    "python-pptx>=0.6.23",
    "pypandoc>=1.13",
]
subprocess.run([pip_path, "install", "--upgrade", "pip"], check=True)
subprocess.run([pip_path, "install"] + deps, check=True)

# Optional but recommended: get system pandoc for ODT/complex docs
install_pandoc_if_needed()

# safe to import external packages
import psycopg2, requests

# 2) Collect variables
env = {
    "PROJECT_NAME": ask("Project name", required=True),
    "PROJECT_BASE": ask("Project base path", str(Path.cwd()), required=True),

    "TELEGRAM_TOKEN": ask("Telegram Bot Token", secret=True, required=True),

    "DB_HOST": ask("PostgreSQL Host", "localhost"),
    "DB_PORT": ask("PostgreSQL Port", "5432"),
    "DB_NAME": ask("PostgreSQL DB name", "aidb"),
    "DB_USER": ask("PostgreSQL user", "aiuser"),
    "DB_PASSWORD": ask("PostgreSQL password", secret=True, required=True),

    "OLLAMA_URL": ask("Ollama URL", "http://localhost:11434"),
    "MODEL": ask("Ollama model", "llama3"),
    "EMBED_MODEL": ask("Embedding model", "sentence-transformers/all-MiniLM-L6-v2"),
}

# 3) Write .env next to setup.py/bot.py
dotenv_path = Path(__file__).parent / ".env"
with open(dotenv_path, "w", encoding="utf-8") as f:
    for k, v in env.items():
        f.write(f'{k}="{v}"\n')
os.chmod(dotenv_path, 0o600)
print(f"✅ .env file written to {dotenv_path}")

# 4) Create folders: <PROJECT_BASE>/<PROJECT_NAME>/{input,index}
PROJECT_DIR = os.path.join(env["PROJECT_BASE"], env["PROJECT_NAME"])
DOCS_DIR    = os.path.join(PROJECT_DIR, "input")
INDEX_DIR   = os.path.join(PROJECT_DIR, "index")
for path in [PROJECT_DIR, DOCS_DIR, INDEX_DIR]:
    os.makedirs(path, exist_ok=True)
    try: os.chmod(path, 0o775)
    except Exception: pass
print(f"✅ Folders ready:\n  {DOCS_DIR}\n  {INDEX_DIR}")

# 4.1) Seed a commands file so first index always builds
commands_file = os.path.join(DOCS_DIR, "commands.txt")
if not os.path.exists(commands_file):
    with open(commands_file, "w", encoding="utf-8") as cf:
        cf.write(
            "AIssist-IndexBot — Commands\n"
            "===========================\n\n"
            "/start  - Show welcome & features\n"
            "/ask <question>  - Ask using indexed project documents\n"
            "/docs            - List files in input/\n"
            "/reindex         - Rebuild index now\n"
            "/task <lines>    - Add tasks (multiline; optional 'status:')\n"
            "/todo            - Show ToDo list for current project\n"
        )
    try: os.chmod(commands_file, 0o664)
    except Exception: pass
    print(f"✅ Seeded docs with {commands_file}")

# 5) Ensure PostgreSQL user & DB (best effort)
def psql(cmd):
    return subprocess.run(["psql", "-U", "postgres", "-c", cmd], check=False)

try:
    print("📚 Ensuring PostgreSQL user & database…")
    psql(
        f"DO $$ BEGIN "
        f"IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{env['DB_USER']}') "
        f"THEN CREATE USER {env['DB_USER']} WITH PASSWORD '{env['DB_PASSWORD']}'; END IF; END $$;"
    )
    psql(
        f"DO $$ BEGIN "
        f"IF NOT EXISTS (SELECT FROM pg_database WHERE datname='{env['DB_NAME']}') "
        f"THEN CREATE DATABASE {env['DB_NAME']} OWNER {env['DB_USER']}; END IF; END $$;"
    )
    psql(f"GRANT ALL PRIVILEGES ON DATABASE {env['DB_NAME']} TO {env['DB_USER']};")
    print("✅ PostgreSQL user & DB ready.")
except Exception as e:
    print(f"⚠️ Skipped auto-create user/DB: {e}")

# 6) Create tasks table
try:
    conn = psycopg2.connect(
        host=env["DB_HOST"], port=env["DB_PORT"],
        dbname=env["DB_NAME"], user=env["DB_USER"], password=env["DB_PASSWORD"]
    )
    with conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                task_text TEXT NOT NULL,
                project TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'todo',
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_project_status
            ON tasks(project, status);
        """)
    conn.close()
    print("✅ DB table 'tasks' ready.")
except Exception as e:
    print(f"⚠️ Could not create table: {e}")

# 7) Ollama (local) install/check + model pull (best effort)
def is_local_ollama(url: str) -> bool:
    try:
        h = (urlparse(url).hostname or "").lower()
        return h in ("localhost", "127.0.0.1", "::1")
    except:
        return False

def ollama_reachable(url: str) -> bool:
    try:
        r = requests.get(f"{url.rstrip('/')}/api/tags", timeout=5)
        return r.status_code == 200
    except:
        return False

ollama_url = env["OLLAMA_URL"]
try:
    if is_local_ollama(ollama_url):
        if shutil.which("ollama") is None:
            print("📦 Installing Ollama (Linux/macOS)…")
            try:
                subprocess.run("curl -fsSL https://ollama.com/install.sh | sh", shell=True, check=True)
                print("✅ Ollama installed.")
            except Exception as e:
                print(f"⚠️ Ollama install failed: {e}")
                
        if not ollama_reachable(ollama_url) and shutil.which("systemctl"):
                subprocess.run(["systemctl", "start", "ollama"], check=False)

        if ollama_reachable(ollama_url):
            print(f"✅ Ollama reachable at {ollama_url}")
        else:
            print(f"⚠️ Ollama not reachable at {ollama_url}. You can run:  ollama serve")
    else:
        print(f"ℹ️ Remote OLLAMA_URL detected ({ollama_url}); skipping local install.")

    print(f"📥 Pulling model '{env['MODEL']}' …")
    subprocess.run(["ollama", "pull", env["MODEL"]], check=True)
    print(f"✅ Model '{env['MODEL']}' ready.")
except Exception as e:
    print(f"⚠️ Could not pull model: {e}")

print("\n🎯 Setup complete.")
print(f"To start the bot:\n  source .venv/bin/activate\n  {python_path} bot.py")
