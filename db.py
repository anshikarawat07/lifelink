import sqlite3
import os

DB_FILE = "blood_bank.db"

def get_db():
    # return DB connection with foreign keys enabled
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    # create DB file if missing
    if not os.path.exists(DB_FILE):
        open(DB_FILE, "w").close()

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")

    # USERS TABLE
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT CHECK(role IN ('admin', 'user')) NOT NULL
        )
    """)

    # DONOR TABLE
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Donor (
            donor_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            name TEXT NOT NULL,
            blood_group TEXT NOT NULL,
            contact TEXT,
            city TEXT,
            camp_location TEXT,
            aadhaar TEXT UNIQUE,
            FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE
        )
    """)

    # DONOR PROFILE
    cur.execute("""
        CREATE TABLE IF NOT EXISTS DonorProfile (
            donor_id INTEGER PRIMARY KEY,
            full_name TEXT,
            age INTEGER,
            gender TEXT,
            email TEXT,
            address TEXT,
            FOREIGN KEY(donor_id) REFERENCES Donor(donor_id) ON DELETE CASCADE
        )
    """)

    # DONATION TABLE
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Donation (
            donation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            donor_id INTEGER NOT NULL,
            amount INTEGER CHECK(amount > 0),
            donation_date TEXT,
            expiry_date TEXT,
            camp_location TEXT,
            FOREIGN KEY (donor_id) REFERENCES Donor(donor_id) ON DELETE CASCADE
        )
    """)

    # BLOOD STOCK
    cur.execute("""
        CREATE TABLE IF NOT EXISTS BloodStock (
            blood_group TEXT PRIMARY KEY,
            available_units INTEGER DEFAULT 0 CHECK(available_units >= 0),
            expiry_date TEXT
        )
    """)

    # RECIPIENT TABLE
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Recipient (
            recipient_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            blood_group TEXT NOT NULL,
            contact TEXT,
            aadhaar TEXT UNIQUE
        )
    """)

    # REQUEST TABLE
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Request (
            request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_name TEXT NOT NULL,
            blood_group TEXT NOT NULL,
            req_units INTEGER CHECK(req_units > 0),
            fulfilled_units INTEGER DEFAULT 0 CHECK(fulfilled_units >= 0),
            status TEXT CHECK(status IN ('Pending', 'Fulfilled', 'Partially Fulfilled', 'Rejected')),
            request_date TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ONLINE DONATION REQUESTS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS OnlineDonationRequests (
            request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT NOT NULL,
            blood_group TEXT NOT NULL,
            contact TEXT,
            city TEXT,
            amount INTEGER CHECK(amount > 0),
            status TEXT DEFAULT 'Pending',
            request_date TEXT,
            FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE
        )
    """)

    # ONLINE BLOOD REQUESTS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS OnlineRequest (
            online_request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            recipient_name TEXT NOT NULL,
            blood_group TEXT NOT NULL,
            req_units INTEGER CHECK(req_units > 0),
            status TEXT DEFAULT 'Pending',
            request_date TEXT,
            FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE
        )
    """)

    # NOTIFICATIONS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Notifications (
            notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            sent_by TEXT DEFAULT 'Admin'
        )
    """)

    # CAMP TABLE
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Camp (
            camp_id INTEGER PRIMARY KEY AUTOINCREMENT,
            camp_name TEXT NOT NULL,
            location TEXT NOT NULL,
            camp_date TEXT NOT NULL,
            description TEXT,
            total_donations INTEGER DEFAULT 0,
            total_units INTEGER DEFAULT 0
        )
    """)

    # CAMP REGISTRATIONS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS CampRegistrations (
            registration_id INTEGER PRIMARY KEY AUTOINCREMENT,
            camp_id INTEGER NOT NULL,
            user_id INTEGER,
            donor_name TEXT,
            amount INTEGER,
            mode TEXT CHECK(mode IN ('online', 'admin')) DEFAULT 'online',
            status TEXT CHECK(status IN ('Pending', 'Confirmed')) DEFAULT 'Pending',
            registered_on TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (camp_id) REFERENCES Camp(camp_id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE SET NULL,
            UNIQUE (camp_id, user_id)
        )
    """)

    # INDEXES
    cur.execute("CREATE INDEX IF NOT EXISTS idx_camp_date ON Camp(camp_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON CampRegistrations(user_id)")

    conn.commit()
    conn.close()
    print("Database initialized successfully.")


if __name__ == "__main__":
    init_db()