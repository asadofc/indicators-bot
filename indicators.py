import asyncio
import os
import logging
import signal
import sys
import threading
from typing import Dict, List, Optional
from http.server import BaseHTTPRequestHandler, HTTPServer
import time
import json

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Import telegram components
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, Bot as TelegramBot
    from telegram.constants import ChatAction, ChatType
    from telegram.error import NetworkError, BadRequest, TelegramError
    logger.info("Telegram imports successful")
except ImportError as e:
    logger.error(f"Import error: {e}")
    sys.exit(1)

# Reduce noise
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# Configuration
BOT_TOKENS = os.getenv("BOT_TOKENS", "").split(",")
if not BOT_TOKENS or BOT_TOKENS == [""]:
    logger.error("BOT_TOKENS environment variable required")
    sys.exit(1)

BOT_TOKENS = [token.strip() for token in BOT_TOKENS if token.strip()]
if not BOT_TOKENS:
    logger.error("No valid tokens")
    sys.exit(1)

# Actions
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

# Global state
active_bots = []
shutdown_signal = threading.Event()
http_server = None


class BotInstance:
    """Bot with direct polling"""
    
    def __init__(self, token: str, action: ChatAction):
        self.token = token
        self.action = action
        self.bot = TelegramBot(token)
        self.simulations = {}
        self.running = False
        self.bot_info = None
        self.offset = 0
    
    async def initialize(self):
        """Initialize bot"""
        try:
            self.bot_info = await self.bot.get_me()
            commands = [BotCommand("start", "Start activity simulation")]
            await self.bot.set_my_commands(commands)
            logger.info(f"Bot @{self.bot_info.username} initialized for {self.action}")
            return True
        except Exception as e:
            logger.error(f"Initialize error for {self.action}: {e}")
            return False
    
    async def handle_update(self, update_data: dict):
        """Handle incoming update"""
        try:
            update = Update.de_json(update_data, self.bot)
            if not update or not update.message:
                return
            
            message = update.message
            # Only respond to /start commands
            if not message.text or not message.text.startswith('/start'):
                return
            
            chat = message.chat
            if chat.type not in [ChatType.PRIVATE, ChatType.GROUP, ChatType.SUPERGROUP]:
                return
            
            # Construct the "Add Me To Your Group" URL
            username = self.bot_info.username if self.bot_info else "bot"
            add_to_group_url = f"https://t.me/{username}?startgroup=true"
            
            # Build the keyboard with updated button text
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
            
            # Prepare user mention via HTML link
            user = message.from_user
            # Use first_name if available, otherwise username or fallback text
            if user.first_name:
                display_name = user.first_name
            elif user.username:
                display_name = f"@{user.username}"
            else:
                display_name = "there"
            user_mention = f'<a href="tg://user?id={user.id}">{display_name}</a>'

            # Rich welcome text with emojis, HTML formatting, and user mention
            welcome_text = (
                f"👋 Hello {user_mention}! I'm here to keep your group active and engaging.\n\n"
                f"✨ <b>What I do:</b>\n"
                f"• Simulate typing, uploading, and more to boost visibility\n"
                f"• Help maintain conversation flow in your groups\n"
                f"• Super simple to set up—just add and go!\n\n"
                f"⚙️ <b>Action:</b> Simulates {self.action}\n\n"
                f"🚀 <b>Tap /start to begin the magic.</b>\n"
                f"👇 Or use the buttons below for support and adding me to your group!"
            )
            
            # Send the message with HTML parse mode
            await self.bot.send_message(
                chat_id=chat.id,
                text=welcome_text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            
            # Start simulation if not already running
            await self.start_simulation(chat.id)
            logger.info(f"Simulation started for chat {chat.id}")
            
        except Exception as e:
            logger.error(f"Handle update error: {e}")
    
    async def start_simulation(self, chat_id: int):
        """Start simulation"""
        if chat_id in self.simulations:
            self.simulations[chat_id].cancel()
        
        self.simulations[chat_id] = asyncio.create_task(
            self.simulate_loop(chat_id)
        )
    
    async def simulate_loop(self, chat_id: int):
        """Simulation loop"""
        try:
            while not shutdown_signal.is_set() and self.running:
                try:
                    await self.bot.send_chat_action(chat_id, self.action)
                    await asyncio.sleep(5.0)
                except (NetworkError, BadRequest):
                    await asyncio.sleep(10.0)
                except Exception:
                    await asyncio.sleep(5.0)
        except asyncio.CancelledError:
            pass
        finally:
            self.simulations.pop(chat_id, None)
    
    async def poll_updates(self):
        """Direct polling for updates"""
        while not shutdown_signal.is_set() and self.running:
            try:
                updates = await self.bot.get_updates(
                    offset=self.offset,
                    timeout=10,
                    limit=100
                )
                
                for update in updates:
                    self.offset = update.update_id + 1
                    await self.handle_update(update.to_dict())
                
                if not updates:
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.debug(f"Poll error for {self.action}: {e}")
                await asyncio.sleep(5)
    
    async def run(self):
        """Run bot"""
        try:
            self.running = True
            logger.info(f"Bot started for {self.action}")
            await self.poll_updates()
        except Exception as e:
            logger.error(f"Run error for {self.action}: {e}")
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """Cleanup"""
        try:
            self.running = False
            
            # Cancel simulations
            for task in list(self.simulations.values()):
                task.cancel()
            
            if self.simulations:
                await asyncio.gather(*self.simulations.values(), return_exceptions=True)
            
            logger.info(f"Bot cleaned up for {self.action}")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")


def run_bot_thread(token: str, action: ChatAction):
    """Run bot in thread"""
    async def bot_main():
        bot = BotInstance(token, action)
        active_bots.append(bot)
        
        try:
            if await bot.initialize():
                await bot.run()
        except Exception as e:
            logger.error(f"Bot thread error: {e}")
        finally:
            if bot in active_bots:
                active_bots.remove(bot)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(bot_main())
    except Exception as e:
        logger.error(f"Thread error: {e}")
    finally:
        loop.close()


class HealthHandler(BaseHTTPRequestHandler):
    """Health check handler"""
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        running = len([b for b in active_bots if b.running])
        sims = sum(len(b.simulations) for b in active_bots)
        
        status = (
            f"Telegram Multi-Bot Service\n"
            f"Running: {running}/{len(active_bots)}\n"
            f"Simulations: {sims}\n"
            f"Tokens: {len(BOT_TOKENS)}\n"
            f"Status: OK\n"
        )
        
        self.wfile.write(status.encode())
    
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()
    
    def log_message(self, format, *args):
        pass


def start_server():
    """Start HTTP server"""
    global http_server
    port = int(os.environ.get("PORT", 5000))
    
    try:
        http_server = HTTPServer(("0.0.0.0", port), HealthHandler)
        logger.info(f"Server on port {port}")
        http_server.serve_forever()
    except Exception as e:
        logger.error(f"Server error: {e}")


def signal_handler(signum, frame):
    """Handle signals"""
    logger.info("Shutting down")
    shutdown_signal.set()
    
    if http_server:
        http_server.shutdown()
    
    time.sleep(2)
    sys.exit(0)


def main():
    """Main function"""
    logger.info("=== Telegram Multi-Bot Service ===")
    logger.info(f"Tokens: {len(BOT_TOKENS)}")
    logger.info(f"Actions: {len(ACTIONS)}")
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start server
        server_thread = threading.Thread(
            target=start_server,
            daemon=True
        )
        server_thread.start()
        
        # Start bots
        threads = []
        tokens = BOT_TOKENS[:len(ACTIONS)]
        actions = ACTIONS[:len(tokens)]
        
        for i, (token, action) in enumerate(zip(tokens, actions)):
            if i > 0:
                time.sleep(2)
            
            thread = threading.Thread(
                target=run_bot_thread,
                args=(token, action),
                daemon=True
            )
            threads.append(thread)
            thread.start()
            logger.info(f"Started {action}")
        
        logger.info(f"All {len(threads)} bots started")
        
        # Keep running
        while not shutdown_signal.is_set():
            time.sleep(1)
        
    except Exception as e:
        logger.error(f"Main error: {e}")
        return 1
    finally:
        shutdown_signal.set()
        if http_server:
            http_server.shutdown()
        time.sleep(1)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())