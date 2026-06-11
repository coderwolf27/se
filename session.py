import asyncio
import re
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import sqlite3
from datetime import datetime
import os

# Configuration - YOU MUST SET THESE
API_ID = 38190726  # Get from https://my.telegram.org
API_HASH = 66a4eebff562f2035bf2acabec3dd7d5  # Get from https://my.telegram.org
BOT_TOKEN = 8634603705:AAH7v0fwn4C3vK_SRQnWOh3OnqTdyFHRukA  # Get from @BotFather on Telegram
OWNER_ID = 1899208318  # Your Telegram user ID

class SessionOTPBot:
    def __init__(self):
        # Check if credentials are set
        if not all([API_ID, API_HASH, BOT_TOKEN, OWNER_ID]):
            raise ValueError("Please set API_ID, API_HASH, BOT_TOKEN, and OWNER_ID")
        
        self.bot = TelegramClient('bot_session', API_ID, API_HASH)
        self.bot_token = BOT_TOKEN
        self.owner_id = OWNER_ID
        self.active_sessions = {}
        
        # Setup database
        self.init_database()
    
    def init_database(self):
        self.conn = sqlite3.connect('sessions.db')
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
    
    async def monitor_session(self, session_string, session_id):
        """Monitor a single session for OTPs"""
        try:
            client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
            await client.start()
            
            @client.on(events.NewMessage(incoming=True))
            async def handle_message(event):
                # Check for OTP patterns
                message_text = event.raw_text.lower()
                otp_patterns = [
                    r'\b\d{5,6}\b',  # 5-6 digit codes
                    r'code[:\s]*(\d+)',
                    r'otp[:\s]*(\d+)',
                    r'verification[:\s]*(\d+)'
                ]
                
                for pattern in otp_patterns:
                    match = re.search(pattern, message_text, re.IGNORECASE)
                    if match:
                        otp_code = match.group(1) if match.groups() else match.group(0)
                        await self.bot.send_message(
                            self.owner_id,
                            f"🔐 **OTP Received!**\n"
                            f"Session ID: {session_id}\n"
                            f"Code: `{otp_code}`\n"
                            f"Full Message: {event.raw_text[:200]}"
                        )
                        break
            
            # Keep the client running
            await client.run_until_disconnected()
            
        except Exception as e:
            await self.bot.send_message(
                self.owner_id,
                f"❌ Session {session_id} error: {str(e)}"
            )
    
    async def run(self):
        """Start the bot"""
        await self.bot.start(bot_token=self.bot_token)
        print("Bot started successfully!")
        
        # Send startup message to owner
        await self.bot.send_message(
            self.owner_id,
            "✅ Bot is online and ready!\n"
            "Commands:\n"
            "/add - Add new session\n"
            "/list - List active sessions\n"
            "/remove <id> - Remove a session\n"
            "/help - Show this help"
        )
        
        @self.bot.on(events.NewMessage(pattern='/start'))
        async def start_command(event):
            await event.reply("Welcome! Use /help for commands.")
        
        @self.bot.on(events.NewMessage(pattern='/help'))
        async def help_command(event):
            help_text = """
**📱 Session OTP Bot Commands:**

/add <session_string> <phone> - Add a new session
/list - List all active sessions
/remove <session_id> - Remove a session
/status - Check bot status

**How to use:**
1. Get session string using telethon
2. Send: /add YOUR_SESSION_STRING PHONE_NUMBER
3. Bot will monitor for OTPs automatically
            """
            await event.reply(help_text)
        
        @self.bot.on(events.NewMessage(pattern='/add'))
        async def add_session(event):
            try:
                # Parse command: /add session_string phone_number
                parts = event.raw_text.split(maxsplit=2)
                if len(parts) < 3:
                    await event.reply("❌ Usage: /add <session_string> <phone_number>")
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
                
                # Start monitoring in background
                task = asyncio.create_task(self.monitor_session(session_string, session_id))
                self.active_sessions[session_id] = task
                
                await event.reply(f"✅ Session {session_id} added and monitoring started for {phone_number}")
                
            except Exception as e:
                await event.reply(f"❌ Error: {str(e)}")
        
        @self.bot.on(events.NewMessage(pattern='/list'))
        async def list_sessions(event):
            cursor = self.conn.cursor()
            cursor.execute("SELECT id, phone_number, created_at, is_active FROM sessions WHERE is_active=1")
            sessions = cursor.fetchall()
            
            if not sessions:
                await event.reply("No active sessions found.")
                return
            
            response = "**📋 Active Sessions:**\n\n"
            for sid, phone, created, active in sessions:
                status = "✅ Active" if sid in self.active_sessions else "⚠️ Not running"
                response += f"ID: `{sid}`\n📞 {phone}\n📅 Added: {created[:10]}\nStatus: {status}\n\n"
            
            await event.reply(response)
        
        @self.bot.on(events.NewMessage(pattern='/remove'))
        async def remove_session(event):
            try:
                parts = event.raw_text.split()
                if len(parts) < 2:
                    await event.reply("❌ Usage: /remove <session_id>")
                    return
                
                session_id = int(parts[1])
                
                # Stop monitoring if active
                if session_id in self.active_sessions:
                    self.active_sessions[session_id].cancel()
                    del self.active_sessions[session_id]
                
                # Remove from database
                cursor = self.conn.cursor()
                cursor.execute("UPDATE sessions SET is_active=0 WHERE id=?", (session_id,))
                self.conn.commit()
                
                await event.reply(f"✅ Session {session_id} removed successfully")
                
            except Exception as e:
                await event.reply(f"❌ Error: {str(e)}")
        
        @self.bot.on(events.NewMessage(pattern='/status'))
        async def status_command(event):
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sessions WHERE is_active=1")
            total = cursor.fetchone()[0]
            running = len(self.active_sessions)
            
            await event.reply(
                f"**📊 Bot Status:**\n"
                f"Total sessions: {total}\n"
                f"Running: {running}\n"
                f"Bot uptime: Active"
            )
        
        await self.bot.run_until_disconnected()
    
    async def stop(self):
        """Clean shutdown"""
        for task in self.active_sessions.values():
            task.cancel()
        self.conn.close()

async def main():
    try:
        bot = SessionOTPBot()
        await bot.run()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("\nPlease set these environment variables or edit the code:")
        print("API_ID, API_HASH, BOT_TOKEN, OWNER_ID")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
