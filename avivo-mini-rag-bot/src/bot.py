import os
from dotenv import load_dotenv
import logging

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from rag_core import answer_query, client  # using the HF client from rag_core

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# In-memory per-user chat history
USER_HISTORY = {}

HELP_TEXT = (
    "/ask <your question> - Ask a question to the knowledge base\n"
    "/summarize - Summarize your last answer\n"
    "/help - Show this help message"
)

# --------- COMMAND: /start ---------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! I am your Mini-RAG bot.\n\n" + HELP_TEXT
    )

# --------- COMMAND: /help ---------
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)

# --------- COMMAND: /ask ---------
async def ask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Usage: /ask <your question>")
        return

    await update.message.reply_text("Thinking...")

    try:
        answer, contexts = answer_query(query, k=3)

        # Save user history
        user_id = update.effective_user.id
        USER_HISTORY.setdefault(user_id, [])
        USER_HISTORY[user_id].append({"query": query, "answer": answer})
        USER_HISTORY[user_id] = USER_HISTORY[user_id][-3:]  # keep last 3 only

        # Format sources
        sources = "\n\n".join({c["doc_path"] for c in contexts})

        message = f"{answer}\n\nSources:\n{sources}"
        await update.message.reply_text(message)

    except Exception as e:
        logging.exception("Error in /ask")
        await update.message.reply_text(f"Error: {e}")

# --------- COMMAND: /summarize ---------
async def summarize_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    history = USER_HISTORY.get(user_id, [])
    if not history:
        await update.message.reply_text("No history to summarize.")
        return

    last_answer = history[-1]["answer"]

    prompt = (
        "Summarize the following answer in 2-3 short bullet points:\n\n"
        + last_answer
    )

    try:
        response = client.chat.completions.create(
            model="meta-llama/Llama-3.1-8B-Instruct",
            messages=[
                {"role": "system", "content": "Provide a short, clean summary."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=128,
            temperature=0.3
        )

        summary = response.choices[0].message["content"]
        await update.message.reply_text(summary)

    except Exception as e:
        logging.exception("Error in /summarize")
        await update.message.reply_text(f"Error: {e}")

# --------- MAIN ---------
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ask", ask_cmd))
    app.add_handler(CommandHandler("summarize", summarize_cmd))

    app.run_polling()

if __name__ == "__main__":
    main()
