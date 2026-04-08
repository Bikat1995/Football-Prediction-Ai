import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'bot_database.sqlite')

async def init_db():
    """Initialize the database schema."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                nickname TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                match TEXT,
                bet_type TEXT,
                prediction TEXT,
                confidence REAL,
                risk_level TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        await db.commit()

async def register_user(user_id: int, username: str, nickname: str = None):
    """Register a new user or update their nickname."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO users (user_id, username, nickname)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            nickname=COALESCE(excluded.nickname, users.nickname)
        ''', (user_id, username, nickname))
        await db.commit()

async def is_user_registered(user_id: int) -> bool:
    """Check if a user is registered."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone() is not None

async def save_ticket(user_id: int, match: str, bet_type: str, prediction: str, confidence: float, risk_level: str):
    """Save a generated ticket to the user's history."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO tickets (user_id, match, bet_type, prediction, confidence, risk_level)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, match, bet_type, prediction, confidence, risk_level))
        await db.commit()

async def get_user_history(user_id: int, limit: int = 5):
    """Retrieve the user's recent tickets."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''
            SELECT match, bet_type, prediction, confidence, risk_level, created_at 
            FROM tickets 
            WHERE user_id = ? 
            ORDER BY created_at DESC LIMIT ?
        ''', (user_id, limit)) as cursor:
            return await cursor.fetchall()