# 🤖 AIssist-IndexBot

AIssist-IndexBot is a self-hosted **AI knowledge assistant** that runs on Telegram.  
It can index documents, answer questions from them, and keep project-specific tasks — powered by [Ollama](https://ollama.com/) for local AI models.

## 💬 Join the Community
Chat, ask questions, and share ideas in our Telegram group:  
[![Join us on Telegram](https://img.shields.io/badge/Telegram-Join%20Chat-blue?logo=telegram)](https://t.me/AIssistIndexBot)

---

## ✨ Features

- 📂 Index any documents (PDF, DOCX, ODT, PPTX, XLSX, TXT, Markdown…)
- 🔍 Ask natural language questions and get answers from your indexed files
- 🗂️ Multiple projects, each with its own document index
- 📝 Built-in ToDo/task manager stored in PostgreSQL
- 🛠️ One-click setup via `setup.py` (installs everything you need)
- 💬 Telegram interface — control your bot from anywhere
- 🧠 Local AI processing with Ollama (no cloud API fees)

---

## 🚀 Setup

### 1. Clone the repository
```bash
git clone https://github.com/YourUser/AIssist-IndexBot.git
cd AIssist-IndexBot
```

### 2. Run the one-click setup
```bash
python3 setup.py
```
The setup will:
- Create a Python virtual environment
- Install dependencies
- Ask you for **project name** and **base path**
- Ask for **Telegram Bot Token** (see guide below)
- Configure PostgreSQL connection
- Create folders:
  ```
  <PROJECT_BASE>/<PROJECT_NAME>/input
  <PROJECT_BASE>/<PROJECT_NAME>/index
  ```
- Install Ollama (if local) and pull your chosen model

---

## 💬 Get a Telegram Bot Token

1. Open Telegram and search for **BotFather**.
2. Start a chat and send:
   ```
   /newbot
   ```
3. Follow the prompts:
   - Choose a display name (any)
   - Choose a username (must end with `bot`, e.g. `MyIndexBot`)
4. BotFather will reply with a token like:
   ```
   123456789:ABCdefGhIJKlmNoPQRstuVWXyz
   ```
5. Use this token when `setup.py` asks for **Telegram Bot Token**.

---

## ▶️ Start the bot
```bash
source .venv/bin/activate
python bot.py
```
You can now message your bot on Telegram.

---

## 📂 Adding Documents
Place documents into:
```
<PROJECT_BASE>/<PROJECT_NAME>/input
```
Then run `/reindex` in Telegram to update the index.

---

## ⚠️ Ollama Notes
- Ollama is a separate project from AIssist-IndexBot.
- If running locally, `setup.py` will try to install Ollama and pull the model.
- You can find Ollama’s own license here:  
  [https://github.com/ollama/ollama/blob/main/LICENSE](https://github.com/ollama/ollama/blob/main/LICENSE)

---

## 📜 License
This project uses the MIT License.  
If you redistribute or modify this project, you must **keep this license file** and include attribution.  
Ollama is licensed separately under its own terms.
