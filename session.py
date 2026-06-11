import asyncio
import re
import os
import sys
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import sqlite3
from datetime import datetime
from typing import Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load configuration from environment variables
API_ID = int(os.environ.get('38190726', 0))
API_HASH = os.environ.get('66a4eebff562f2035bf2acabec3dd7d5', '')
BOT_TOKEN = os.environ.get('8634603705:AAH7v0fwn4C3vK_SRQnWOh3OnqTdyFHRukA', '')
OWNER_ID = int(os.environ.get('1899208318', 0))

class SessionOTPBot:
    def __init__(self):
        # Validate configuration
        if API_ID == 0 or not API_HASH or not BOT_TOKEN or OWNER_ID == 0:
            error_msg = (
                "❌ Missing configuration!\n"
                "Please set these environment variables on Render.com:\n"
                "API_ID, API_HASH, BOT_TOKEN, OWNER_ID\n\n"
                "How to get them:\n"
                "1. API_ID & API_HASH: https://my.telegram.org\n"
                "2. BOT_TOKEN: @BotFather on Telegram\n"
                "3. OWNER_ID: Your Telegram user ID"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        self.bot = None
        self.active_sessions: Dict[int, Any] = {}
        self.conn = None
        self.is_running = True
        
        logger.info(f"Bot initializing with API_ID: {API_ID}")
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database"""
        try:
            self.conn = sqlite3.connect('sessions.db', check_same_thread=False)
            cursor = self.conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_string TEXT,
                    phone_number TEXT,
                    created_at TEXT,
                    is_active INTEGER DEFAULT 1
                )
            ''')
            self.conn.commit()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise
    
    async def monitor_session(self, session_string: str, session_id: int):
        """Monitor a single session for OTPs"""
        client = None
        try:
            logger.info(f"Starting monitor for session {session_id}")
            client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
            await client.start()
            
            @client.on(events.NewMessage(incoming=True))
            async def handle_message(event):
                try:
                    message_text = event.raw_text.lower()
                    
                    # OTP detection patterns
                    otp_patterns = [
                        r'\b\d{5,6}\b',
                        r'code[:\s]*(\d+)',
                        r'otp[:\s]*(\d+)',
                        r'verification[:\s]*(\d+)',
                        r'(\d{4,6})'
                    ]
                    
                    for pattern in otp_patterns:
                        match = re.search(pattern, message_text, re.IGNORECASE)
                        if match:
                            otp_code = match.group(1) if match.groups() else match.group(0)
                            
                            # Send OTP to owner
                            if self.bot:
                                await self.bot.send_message(
                                    OWNER_ID,
                                    f"🔐 **OTP Received!**\n"
                                    f"📱 Session ID: `{session_id}`\n"
                                    f"🔑 Code: `{otp_code}`\n"
                                    f"📝 Message: {event.raw_text[:200]}"
                                )
                                logger.info(f"OTP forwarded for session {session_id}")
                            break
                            
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
            
            # Keep client running
            while self.is_running and session_id in self.active_sessions:
                await asyncio.sleep(1)
                if not client.is_connected():
                    await client.disconnect()
                    break
                    
        except Exception as e:
            logger.error(f"Session {session_id} error: {e}")
            if self.bot:
                await self.bot.send_message(
                    OWNER_ID,
                    f"❌ Session {session_id} error: {str(e)[:100]}"
                )
        finally:
            if client:
                await client.disconnect()
            logger.info(f"Session {session_id} monitor stopped")
    
    async def run(self):
        """Start the bot"""
        try:
            # Create and start bot
            self.bot = TelegramClient('bot_session', API_ID, API_HASH)
            await self.bot.start(bot_token=BOT_TOKEN)
            logger.info("Bot started successfully!")
            
            # Notify owner
            await self.bot.send_message(
                OWNER_ID,
                "✅ **Session OTP Bot is online!**\n\n"
                "**Commands:**\n"
                "/add `<session_string>` `<phone>` - Add new session\n"
                "/list - List all active sessions\n"
                "/remove `<id>` - Remove a session\n"
                "/status - Check bot status\n"
                "/help - Show this help"
            )
            
            # Register command handlers
            @self.bot.on(events.NewMessage(pattern='/start'))
            async def start_command(event):
                if event.sender_id == OWNER_ID:
                    await event.reply("✅ Bot is running! Use /help for commands.")
            
            @self.bot.on(events.NewMessage(pattern='/help'))
            async def help_command(event):
                if event.sender_id == OWNER_ID:
                    help_text = """
**📱 Session OTP Bot Commands:**

`/add <session_string> <phone>` - Add a new session to monitor
`/list` - List all active sessions
`/remove <session_id>` - Remove a session
`/status` - Check bot status

**How to get session string:**
```python
from telethon import TelegramClient
from telethon.sessions import StringSession

client = TelegramClient(StringSession(), API_ID, API_HASH)
await client.start()
print(StringSession.save(client.session))
