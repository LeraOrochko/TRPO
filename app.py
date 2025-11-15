from flask import Flask, request, jsonify, session, redirect, url_for
from functools import wraps
import sqlite3
import os
import datetime
from datetime import timedelta
import hashlib

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

def get_db():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, "data")
    
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    
    db_path = os.path.join(data_dir, "hotel.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.executescript('''
            CREATE TABLE IF NOT EXISTS admin (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                email VARCHAR(255),
                full_name VARCHAR(100),
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS room_type (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(50) NOT NULL,
                description TEXT,
                base_price_per_night DECIMAL(10, 2) NOT NULL,
                max_guests INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS room (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_number VARCHAR(10) UNIQUE NOT NULL,
                room_type_id INTEGER NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                has_wifi BOOLEAN DEFAULT 0,
                has_tv BOOLEAN DEFAULT 0,
                FOREIGN KEY (room_type_id) REFERENCES room_type(id)
            );

            CREATE TABLE IF NOT EXISTS guest (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS booking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guest_id INTEGER NOT NULL,
                room_type_id INTEGER NOT NULL,
                assigned_room_id INTEGER,
                first_name VARCHAR(100) NOT NULL,
                last_name VARCHAR(100) NOT NULL,
                passport VARCHAR(50) NOT NULL,
                phone VARCHAR(20) NOT NULL,
                check_in_date DATE NOT NULL,
                check_out_date DATE NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                total_price DECIMAL(10, 2),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (guest_id) REFERENCES guest(id),
                FOREIGN KEY (room_type_id) REFERENCES room_type(id),
                FOREIGN KEY (assigned_room_id) REFERENCES room(id)
            );
        ''')

        cur.execute("SELECT COUNT(*) FROM room_type")
        if cur.fetchone()[0] == 0:
            cur.executemany('''
                INSERT INTO room_type (name, description, base_price_per_night, max_guests)
                VALUES (?, ?, ?, ?)
            ''', [
                ('Эконом', 'Бюджетный номер с минимальными удобствами', 1500.00, 1),
                ('Стандарт', 'Стандартный номер с одной кроватью', 2500.00, 2),
                ('Люкс', 'Просторный номер с дополнительными удобствами', 5000.00, 2)
            ])

            cur.executemany('''
                INSERT INTO room (room_number, room_type_id, has_wifi, has_tv)
                VALUES (?, ?, ?, ?)
            ''', [
                ('101', 1, 0, 0),  # Эконом
                ('201', 2, 0, 1),  # Стандарт
                ('301', 3, 1, 1)   # Люкс
            ])
            
        cur.execute("SELECT COUNT(*) FROM admin")
        if cur.fetchone()[0] == 0:
            cur.execute('''
                INSERT INTO admin (username, password_hash, email, full_name)
                VALUES (?, ?, ?, ?)
            ''', ('admin', hash_password('admin123'), 'admin@hotel.com', 'Главный Администратор'))

        conn.commit()
        print("База данных успешно инициализирована")
        
    except Exception as e:
        print(f"Ошибка при инициализации БД: {e}")
        conn.rollback()
    finally:
        conn.close()

@app.route("/")
def index():
    return jsonify({"message": "Гостиница API", "endpoints": ["/register_guest", "/guest/login", "/booking", "/admin"]})

@app.route("/register_guest", methods=["POST"])
def register_guest():
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    required_fields = ["username", "email", "password"]
    for field in required_fields:
        if field not in data or not data[field].strip():
            return jsonify({"error": f"Missing required field: {field}"}), 400

    username = data["username"].strip()
    email = data["email"].strip()
    password = data["password"].strip()

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    conn = get_db()
    cur = conn.cursor()

    try:
        # Проверяем, нет ли уже пользователя с таким username или email
        cur.execute("SELECT id FROM guest WHERE username = ? OR email = ?", (username, email))
        existing_guest = cur.fetchone()
        
        if existing_guest:
            return jsonify({"error": "Username or email already exists"}), 400

        # Хешируем пароль и создаем гостя
        password_hash = hash_password(password)
        
        cur.execute('''
            INSERT INTO guest (username, email, password_hash)
            VALUES (?, ?, ?)
        ''', (username, email, password_hash))
        
        conn.commit()
        guest_id = cur.lastrowid
        
        return jsonify({
            "message": "Guest registered successfully",
            "guest_id": guest_id,
            "username": username
        }), 201

    except sqlite3.IntegrityError as e:
        conn.rollback()
        return jsonify({"error": "Username or email already exists"}), 400
    except Exception as e:
        conn.rollback()
        return jsonify({"error": f"Registration failed: {str(e)}"}), 500
    finally:
        conn.close()

@app.route("/guest/login", methods=["POST"])
def guest_login():
    data = request.get_json()
    
    if not data or "username" not in data or "password" not in data:
        return jsonify({"error": "Username and password required"}), 400
    
    username = data["username"]
    password = data["password"]
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM guest WHERE username = ?", (username,))
    guest = cur.fetchone()
    conn.close()
    
    if guest and guest["password_hash"] == hash_password(password):
        session["guest_id"] = guest["id"]
        session["guest_username"] = guest["username"]
        return jsonify({
            "message": "Login successful",
            "guest": {
                "id": guest["id"],
                "username": guest["username"],
                "email": guest["email"]
            }
        })
    else:
        return jsonify({"error": "Invalid credentials"}), 401

@app.route("/booking", methods=["POST"])
def create_booking():
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    required_fields = ["guest_id", "first_name", "last_name", "passport", "phone", "room_type_id", "check_in_date", "check_out_date"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    conn = get_db()
    cur = conn.cursor()

    try:
        guest_id = data["guest_id"]
        first_name = data["first_name"]
        last_name = data["last_name"]
        passport = data["passport"]
        phone = data["phone"]
        room_type_id = data["room_type_id"]
        check_in_date = data["check_in_date"]
        check_out_date = data["check_out_date"]

        # Проверяем существование гостя
        cur.execute("SELECT id FROM guest WHERE id = ?", (guest_id,))
        guest = cur.fetchone()
        if not guest:
            return jsonify({"error": "Guest not found"}), 404

        # Проверяем доступность номера
        cur.execute("""
            SELECT r.id FROM room r
            WHERE r.room_type_id = ? 
            AND r.is_active = 1
            AND r.id NOT IN (
                SELECT b.assigned_room_id FROM booking b
                WHERE b.status IN ('confirmed', 'checked-in')
                AND ? < b.check_out_date
                AND ? > b.check_in_date
            )
            LIMIT 1
        """, (room_type_id, check_out_date, check_in_date))
        
        available_room = cur.fetchone()
        
        # Рассчитываем стоимость
        cur.execute("SELECT base_price_per_night FROM room_type WHERE id = ?", (room_type_id,))
        room_type_info = cur.fetchone()
        
        # Вычисляем количество ночей
        check_in = datetime.datetime.strptime(check_in_date, "%Y-%m-%d").date()
        check_out = datetime.datetime.strptime(check_out_date, "%Y-%m-%d").date()
        nights = (check_out - check_in).days
        total_price = room_type_info["base_price_per_night"] * nights
        
        if available_room:
            # Есть свободный номер - подтверждаем бронь
            cur.execute("""
                INSERT INTO booking (guest_id, room_type_id, assigned_room_id, first_name, last_name, 
                                   passport, phone, check_in_date, check_out_date, status, total_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', ?)
            """, (guest_id, room_type_id, available_room["id"], first_name, last_name, 
                  passport, phone, check_in_date, check_out_date, total_price))
            
            conn.commit()
            return jsonify({
                "message": "Бронирование подтверждено! Номер забронирован.",
                "booking_id": cur.lastrowid,
                "total_price": total_price,
                "status": "confirmed"
            }), 200
        else:
            # Нет свободных номеров - создаем бронь в статусе pending
            cur.execute("""
                INSERT INTO booking (guest_id, room_type_id, first_name, last_name, 
                                   passport, phone, check_in_date, check_out_date, status, total_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """, (guest_id, room_type_id, first_name, last_name, 
                  passport, phone, check_in_date, check_out_date, total_price))
            
            conn.commit()
            return jsonify({
                "message": "Бронирование создано. Ожидается подтверждение администратора.",
                "booking_id": cur.lastrowid,
                "total_price": total_price,
                "status": "pending"
            }), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "admin_id" not in session:
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route("/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json()
    
    if not data or "username" not in data or "password" not in data:
        return jsonify({"error": "Username and password required"}), 400
    
    username = data["username"]
    password = data["password"]
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM admin WHERE username = ? AND is_active = 1", (username,))
    admin_user = cur.fetchone()
    conn.close()
    
    if admin_user and admin_user["password_hash"] == hash_password(password):
        session["admin_id"] = admin_user["id"]
        session["admin_username"] = admin_user["username"]
        session["admin_name"] = admin_user["full_name"]
        return jsonify({
            "message": "Login successful",
            "admin": {
                "id": admin_user["id"],
                "username": admin_user["username"],
                "full_name": admin_user["full_name"],
                "email": admin_user["email"]
            }
        })
    else:
        return jsonify({"error": "Неверные учетные данные"}), 401

@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return jsonify({"message": "Logged out successfully"})

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM booking WHERE status = 'confirmed'")
    active_bookings = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM booking WHERE status = 'pending'")
    pending_requests = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM room WHERE is_active = 1")
    total_rooms = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM guest")
    total_guests = cur.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        "active_bookings": active_bookings,
        "pending_requests": pending_requests,
        "total_rooms": total_rooms,
        "total_guests": total_guests
    })

@app.route("/admin/bookings")
@admin_required
def admin_bookings():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            b.*,
            g.username, g.email,
            rt.name as room_type_name,
            r.room_number
        FROM booking b
        JOIN guest g ON b.guest_id = g.id
        JOIN room_type rt ON b.room_type_id = rt.id
        LEFT JOIN room r ON b.assigned_room_id = r.id
        ORDER BY b.created_at DESC
    """)
    bookings = cur.fetchall()
    
    conn.close()
    
    bookings_list = []
    for booking in bookings:
        bookings_list.append({
            "id": booking["id"],
            "guest_username": booking["username"],
            "guest_email": booking["email"],
            "first_name": booking["first_name"],
            "last_name": booking["last_name"],
            "passport": booking["passport"],
            "phone": booking["phone"],
            "room_type": booking["room_type_name"],
            "check_in_date": booking["check_in_date"],
            "check_out_date": booking["check_out_date"],
            "status": booking["status"],
            "room_number": booking["room_number"],
            "total_price": booking["total_price"]
        })
    
    return jsonify({"bookings": bookings_list})

@app.route("/admin/rooms")
@admin_required
def admin_rooms():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            r.*,
            rt.name as room_type_name,
            rt.base_price_per_night
        FROM room r
        JOIN room_type rt ON r.room_type_id = rt.id
        ORDER BY r.room_number
    """)
    rooms = cur.fetchall()
    
    conn.close()
    
    rooms_list = []
    for room in rooms:
        rooms_list.append({
            "id": room["id"],
            "room_number": room["room_number"],
            "room_type": room["room_type_name"],
            "base_price": room["base_price_per_night"],
            "has_wifi": bool(room["has_wifi"]),
            "has_tv": bool(room["has_tv"]),
            "is_active": bool(room["is_active"])
        })
    
    return jsonify({"rooms": rooms_list})

@app.route("/debug/tables")
def debug_tables():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cur.fetchall()
    
    tables_info = {}
    for table in tables:
        table_name = table[0]
        cur.execute(f"PRAGMA table_info({table_name})")
        columns = cur.fetchall()
        
        tables_info[table_name] = [{"name": col[1], "type": col[2]} for col in columns]
    
    conn.close()
    return jsonify({"tables": tables_info})

if __name__ == "__main__":
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)