import sqlite3

DB_PATH = "tasks.db"
CHAT_DB_PATH = "chat_history.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            data BLOB NOT NULL,
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT NOT NULL,
            full_name TEXT,
            national_code TEXT,
            arguments TEXT,
            image_id INTEGER,
            ocr_data TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (image_id) REFERENCES images(id)
        );
    """)
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN ocr_data TEXT")
    except:
        pass
    conn.commit()
    conn.close()

def init_chat_db():
    conn = sqlite3.connect(CHAT_DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, identifier TEXT NOT NULL UNIQUE, metadata TEXT, createdAt TEXT
        );
        CREATE TABLE IF NOT EXISTS threads (
            id TEXT PRIMARY KEY, createdAt TEXT, name TEXT, userId TEXT,
            userIdentifier TEXT, tags TEXT, metadata TEXT
        );
        CREATE TABLE IF NOT EXISTS steps (
            id TEXT PRIMARY KEY, name TEXT, type TEXT, threadId TEXT, parentId TEXT,
            streaming INTEGER, waitForAnswer INTEGER, isError INTEGER, metadata TEXT,
            tags TEXT, input TEXT, output TEXT, createdAt TEXT, command TEXT,
            start TEXT, "end" TEXT, generation TEXT, showInput TEXT, language TEXT,
            indent INTEGER, defaultOpen INTEGER
        );
        CREATE TABLE IF NOT EXISTS elements (
            id TEXT PRIMARY KEY, threadId TEXT, type TEXT, url TEXT, chainlitKey TEXT,
            name TEXT, display TEXT, objectKey TEXT, size TEXT, page INTEGER,
            language TEXT, forId TEXT, mime TEXT, props TEXT
        );
        CREATE TABLE IF NOT EXISTS feedbacks (
            id TEXT PRIMARY KEY, forId TEXT, threadId TEXT, value INTEGER, comment TEXT
        );
    """)
    conn.commit()
    conn.close()

init_db()
init_chat_db()
