import asyncio
import os
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.constants import ChatAction, ChatType
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ─── Imports for Dummy HTTP Server ──────────────────────────────────────────
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# ------------- Telegram‐bot SETUP -------------
# Read tokens from environment variable
BOT_TOKENS = os.getenv("BOT_TOKENS", "").split(",")
if not BOT_TOKENS or BOT_TOKENS == [""]:
    raise ValueError("No bot tokens found. Set BOT_TOKENS environment variable.")

# All available Telegram chat indicators
ACTIONS = [
    ChatAction.TYPING,
    ChatAction.UPLOAD_PHOTO,
    ChatAction.RECORD_VIDEO,
    ChatAction.UPLOAD_VIDEO,
    ChatAction.RECORD_VOICE,
    ChatAction.UPLOAD_VOICE,
    ChatAction.UPLOAD_DOCUMENT,
    ChatAction.CHOOSE_STICKER,
    ChatAction.FIND_LOCATION,
    ChatAction.RECORD_VIDEO_NOTE,
    ChatAction.UPLOAD_VIDEO_NOTE,
]

# ------------- Simulate “typing”/“uploading” actions -------------
async def simulate_action(chat_id: int, app, action: ChatAction):
    try:
        while True:
            await app.bot.send_chat_action(chat_id=chat_id, action=action)
            await asyncio.sleep(4.5)
    except asyncio.CancelledError:
        pass

# ------------- Run a single bot instance -------------
async def run_bot(token, action: ChatAction):
    # Build the Application
    app = ApplicationBuilder().token(token).build()

    # Define a /start handler that:
    #  1) sends the welcome text with dynamic “Add Me To Your Group” link
    #  2) immediately kicks off the simulate_action task for this chat
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        if chat.type not in [ChatType.PRIVATE, ChatType.GROUP, ChatType.SUPERGROUP]:
            return

        # 1) Dynamically build the “Add Me To Your Group” URL using this bot’s username
        bot_username = context.bot.username  # e.g. "ZoyaArwaBot"
        add_to_group_url = f"https://t.me/{bot_username}?startgroup=true"

        keyboard = [
            [
                InlineKeyboardButton(text="Updates", url="https://t.me/WorkGlows"),
                InlineKeyboardButton(text="Support", url="https://t.me/TheCryptoElders"),
            ],
            [
                InlineKeyboardButton(
                    text="Add Me To Your Group",
                    url=add_to_group_url,
                ),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        welcome_text = (
    "👋 Hello! I'm here to keep your group active and engaging.\n\n"
    "✨ <b>What I do:</b>\n"
    "• Simulate typing, uploading, and more to boost visibility\n"
    "• Help maintain conversation flow in your groups\n"
    "• Super simple to set up—just add and go!\n\n"
    "🚀 <b>Tap /start to begin the magic.</b>\n"
    "👇 Or use the buttons below for support and adding me to your group!"
        )
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="HTML")

        # 2) Start simulating the chosen “typing/uploading/etc.” action immediately
        chat_id = chat.id
        task_key = f"{context.bot.token}_{chat_id}"
        if task_key not in context.chat_data:
            context.chat_data[task_key] = asyncio.create_task(
                simulate_action(chat_id, context.application, action)
            )

    # Register /start for this specific bot instance
    app.add_handler(CommandHandler("start", start))

    # Initialize the bot (this allows us to fetch `bot.get_me()` and set commands)
    await app.initialize()

    # Now set /start in the Telegram commands menu
    await app.bot.set_my_commands([BotCommand(command="start", description="Show welcome & buttons")])

    # Print out the username so you know which bot is running
    bot_user = await app.bot.get_me()
    print(f"Bot with token {token[:8]}... is running as @{bot_user.username}")

    # Finally, start polling
    await app.start()
    await app.updater.start_polling()

    return app

# ------------- Main entrypoint -------------
async def main():
    # 1) Start all bot instances concurrently
    apps = await asyncio.gather(
        *(run_bot(token, action) for token, action in zip(BOT_TOKENS, ACTIONS))
    )

    # 2) Keep the script alive forever
    while True:
        await asyncio.sleep(3600)
        
# ─── Dummy HTTP Server to Keep Render Happy ─────────────────────────────────
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"AFK bot is alive!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def start_dummy_server():
    port = int(os.environ.get("PORT", 10000))  # Render injects this
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    print(f"Dummy server listening on port {port}")
    server.serve_forever()

if __name__ == "__main__":

    # Start dummy HTTP server (needed for Render health check)
    threading.Thread(target=start_dummy_server, daemon=True).start()
    asyncio.run(main())