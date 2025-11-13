from flask import Flask, request, render_template, jsonify, session, redirect, url_for
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
                first_name VARCHAR(100) NOT NULL,
                last_name VARCHAR(100) NOT NULL,
                email VARCHAR(255),
                phone VARCHAR(20),
                passport VARCHAR(50) UNIQUE
            );

            CREATE TABLE IF NOT EXISTS booking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guest_id INTEGER NOT NULL,
                room_type_id INTEGER NOT NULL,
                assigned_room_id INTEGER,
                desired_check_in_date DATE NOT NULL,
                desired_duration INTEGER NOT NULL,
                desired_check_out_date DATE,
                actual_check_in_date DATE,
                actual_check_out_date DATE,
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
                ('Стандарт', 'Стандартный номер с одной кроватью', 2500.00, 2),
                ('Комфорт', 'Улучшенный номер с TV и WiFi', 3500.00, 2),
                ('Люкс', 'Просторный номер с дополнительными удобствами', 5000.00, 3)
            ])

            cur.executemany('''
                INSERT INTO room (room_number, room_type_id, has_wifi, has_tv)
                VALUES (?, ?, ?, ?)
            ''', [
                ('101', 1, 0, 1), ('102', 1, 0, 1), ('103', 1, 0, 1),
                ('201', 2, 1, 1), ('202', 2, 1, 1), ('203', 2, 1, 1),
                ('301', 3, 1, 1), ('302', 3, 1, 1)
            ])

        cur.execute("SELECT COUNT(*) FROM admin")
        if cur.fetchone()[0] == 0:
            cur.execute('''
                INSERT INTO admin (username, password_hash, email, full_name)
                VALUES (?, ?, ?, ?)
            ''', ('admin', hash_password('admin123'), 'admin@hotel.com', 'Главный Администратор'))

        conn.commit()
        
    except Exception as e:
        print(f"Ошибка: {e}")
        conn.rollback()
    finally:
        conn.close()

@app.route("/")
def index():
    return '''
    <h1>Гостиница</h1>
    <a href="/booking-form">Бронирование</a> | 
    <a href="/admin/login">Админ-панель</a> |
    <a href="/debug-tables">Проверка БД</a>
    '''

@app.route("/booking-form")
def booking_form():
    return '''
    <h1>Бронирование номера</h1>
    <form action="/create-booking" method="POST">
        <input type="text" name="first_name" placeholder="Имя" required><br>
        <input type="text" name="last_name" placeholder="Фамилия" required><br>
        <input type="text" name="passport" placeholder="Паспорт" required><br>
        <input type="text" name="phone" placeholder="Телефон" required><br>
        <select name="room_type_id" required>
            <option value="1">Стандарт</option>
            <option value="2">Комфорт</option>
            <option value="3">Люкс</option>
        </select><br>
        <input type="date" name="desired_date" required><br>
        <input type="number" name="duration" placeholder="Количество дней" required><br>
        <button type="submit">Забронировать</button>
    </form>
    '''

@app.route("/create-booking", methods=["POST"])
def create_booking():
    form = request.form
    conn = get_db()
    cur = conn.cursor()

    desired_date = form["desired_date"]
    desired_dt = datetime.datetime.strptime(desired_date, "%Y-%m-%d").date()
    today = datetime.date.today()
    
    if (desired_dt - today).days < 14:
        return "Заявки принимаются не ранее, чем за 2 недели до заселения.", 400

    cur.execute("INSERT OR IGNORE INTO guest (first_name, last_name, passport, phone) VALUES (?, ?, ?, ?)",
                (form["first_name"], form["last_name"], form["passport"], form["phone"]))

    cur.execute("SELECT id FROM guest WHERE passport = ?", (form["passport"],))
    guest = cur.fetchone()
    guest_id = guest["id"]

    check_out_date = (desired_dt + timedelta(days=int(form["duration"]))).strftime("%Y-%m-%d")
    
    cur.execute("""
        SELECT r.id FROM room r
        WHERE r.room_type_id = ? 
        AND r.is_active = 1
        AND r.id NOT IN (
            SELECT b.assigned_room_id FROM booking b
            WHERE b.status IN ('confirmed', 'checked-in')
            AND ? < b.desired_check_out_date
            AND ? > b.desired_check_in_date
        )
        LIMIT 1
    """, (form["room_type_id"], check_out_date, desired_date))
    
    available_room = cur.fetchone()

    if available_room:
        room_type_info = cur.execute("SELECT base_price_per_night FROM room_type WHERE id = ?", 
                                   (form["room_type_id"],)).fetchone()
        total_price = room_type_info["base_price_per_night"] * int(form["duration"])
        
        cur.execute("""
            INSERT INTO booking (guest_id, room_type_id, assigned_room_id, desired_check_in_date, 
                               desired_duration, desired_check_out_date, status, total_price)
            VALUES (?, ?, ?, ?, ?, ?, 'confirmed', ?)
        """, (guest_id, form["room_type_id"], available_room["id"], desired_date, 
              form["duration"], check_out_date, total_price))
        
        conn.commit()
        conn.close()
        return "Заявка подтверждена! Номер забронирован.", 200
    else:
        alternatives = []
        for days in range(1, 30):
            alt_date = (desired_dt + timedelta(days=days)).strftime("%Y-%m-%d")
            alt_check_out = (desired_dt + timedelta(days=days + int(form["duration"]))).strftime("%Y-%m-%d")
            
            cur.execute("""
                SELECT COUNT(*) FROM room r
                WHERE r.room_type_id = ? 
                AND r.is_active = 1
                AND r.id NOT IN (
                    SELECT b.assigned_room_id FROM booking b
                    WHERE b.status IN ('confirmed', 'checked-in')
                    AND ? < b.desired_check_out_date
                    AND ? > b.desired_check_in_date
                )
            """, (form["room_type_id"], alt_check_out, alt_date))
            
            if cur.fetchone()[0] > 0:
                alternatives.append(alt_date)
                if len(alternatives) >= 3:
                    break
        
        conn.close()
        
        if alternatives:
            return f"Нет свободных номеров. Альтернативные даты: {', '.join(alternatives)}", 200
        else:
            return "Нет свободных номеров на ближайшие даты.", 200

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM admin WHERE username = ? AND is_active = 1", (username,))
        admin_user = cur.fetchone()
        conn.close()
        
        if admin_user and admin_user["password_hash"] == hash_password(password):
            session["admin_id"] = admin_user["id"]
            session["admin_username"] = admin_user["username"]
            session["admin_name"] = admin_user["full_name"]
            return redirect(url_for("admin_dashboard"))
        else:
            return "Неверные учетные данные"
    
    return '''
    <h1>Вход для администратора</h1>
    <form method="POST">
        <input type="text" name="username" placeholder="Логин" required><br>
        <input type="password" name="password" placeholder="Пароль" required><br>
        <button type="submit">Войти</button>
    </form>
    '''

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "admin_id" not in session:
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/admin")
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
    
    cur.execute("""
        SELECT b.*, g.first_name, g.last_name, rt.name as room_type_name
        FROM booking b
        JOIN guest g ON b.guest_id = g.id
        JOIN room_type rt ON b.room_type_id = rt.id
        ORDER BY b.created_at DESC LIMIT 5
    """)
    recent_bookings = cur.fetchall()
    
    conn.close()
    
    return f'''
    <h1>Панель администратора</h1>
    <p>Активные брони: {active_bookings}</p>
    <p>Ожидающие заявки: {pending_requests}</p>
    <p>Всего номеров: {total_rooms}</p>
    <p>Зарегистрировано гостей: {total_guests}</p>
    <a href="/admin/bookings">Управление бронями</a> | 
    <a href="/admin/rooms">Номера</a> | 
    <a href="/admin/logout">Выйти</a>
    <h3>Последние бронирования:</h3>
    ''' + "<br>".join([f"{b['first_name']} {b['last_name']} - {b['room_type_name']} - {b['desired_check_in_date']}" for b in recent_bookings])

@app.route("/admin/bookings")
@admin_required
def admin_bookings():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            b.*,
            g.first_name, g.last_name, g.phone, g.email,
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
    
    result = "<h1>Все бронирования</h1>"
    for booking in bookings:
        result += f"""
        <div style="border:1px solid #ccc; padding:10px; margin:5px;">
            <p><strong>{booking['first_name']} {booking['last_name']}</strong></p>
            <p>Тип номера: {booking['room_type_name']}</p>
            <p>Дата заезда: {booking['desired_check_in_date']}</p>
            <p>Статус: {booking['status']}</p>
            <p>Номер: {booking['room_number'] or 'Не назначен'}</p>
            <a href="/admin/booking/{booking['id']}">Управление</a>
        </div>
        """
    
    return result + '<br><a href="/admin">Назад</a>'

@app.route("/admin/booking/<int:booking_id>")
@admin_required
def admin_booking_detail(booking_id):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            b.*,
            g.first_name, g.last_name, g.phone, g.email, g.passport,
            rt.name as room_type_name, rt.base_price_per_night
        FROM booking b
        JOIN guest g ON b.guest_id = g.id
        JOIN room_type rt ON b.room_type_id = rt.id
        WHERE b.id = ?
    """, (booking_id,))
    booking = cur.fetchone()
    
    cur.execute("""
        SELECT r.* FROM room r
        WHERE r.room_type_id = ? 
        AND r.is_active = 1
    """, (booking["room_type_id"],))
    available_rooms = cur.fetchall()
    
    conn.close()
    
    rooms_options = "".join([f'<option value="{r["id"]}">{r["room_number"]}</option>' for r in available_rooms])
    
    return f'''
    <h1>Управление бронированием</h1>
    <p>Гость: {booking['first_name']} {booking['last_name']}</p>
    <p>Паспорт: {booking['passport']}</p>
    <p>Телефон: {booking['phone']}</p>
    <p>Тип номера: {booking['room_type_name']}</p>
    <p>Дата заезда: {booking['desired_check_in_date']}</p>
    <p>Статус: {booking['status']}</p>
    
    <form action="/admin/booking/{booking_id}" method="POST">
        <select name="room_id">
            <option value="">Выберите номер</option>
            {rooms_options}
        </select>
        <button type="submit" name="action" value="assign_room">Назначить номер</button>
    </form>
    
    <form action="/admin/booking/{booking_id}" method="POST">
        <select name="status">
            <option value="pending">Ожидание</option>
            <option value="confirmed">Подтверждено</option>
            <option value="checked-in">Заселен</option>
            <option value="checked-out">Выселен</option>
            <option value="cancelled">Отменено</option>
        </select>
        <button type="submit" name="action" value="update_status">Изменить статус</button>
    </form>
    
    <a href="/admin/bookings">Назад</a>
    '''

@app.route("/admin/booking/<int:booking_id>", methods=["POST"])
@admin_required
def admin_booking_update(booking_id):
    action = request.form["action"]
    conn = get_db()
    cur = conn.cursor()
    
    if action == "assign_room":
        room_id = request.form["room_id"]
        if room_id:
            cur.execute("UPDATE booking SET assigned_room_id = ?, status = 'confirmed' WHERE id = ?", 
                       (room_id, booking_id))
            conn.commit()
    
    elif action == "update_status":
        new_status = request.form["status"]
        cur.execute("UPDATE booking SET status = ? WHERE id = ?", (new_status, booking_id))
        conn.commit()
    
    conn.close()
    return redirect(f"/admin/booking/{booking_id}")

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
    
    result = "<h1>Все номера</h1>"
    for room in rooms:
        result += f"""
        <div style="border:1px solid #ccc; padding:10px; margin:5px;">
            <p><strong>Номер {room['room_number']}</strong></p>
            <p>Тип: {room['room_type_name']}</p>
            <p>Цена за ночь: {room['base_price_per_night']} руб.</p>
            <p>WiFi: {'Да' if room['has_wifi'] else 'Нет'}</p>
            <p>TV: {'Да' if room['has_tv'] else 'Нет'}</p>
            <p>Статус: {'Активен' if room['is_active'] else 'Неактивен'}</p>
        </div>
        """
    
    return result + '<br><a href="/admin">Назад</a>'

@app.route("/debug-tables")
def debug_tables():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cur.fetchall()
    
    result = "<h1>Таблицы в БД:</h1><ul>"
    for table in tables:
        table_name = table[0]
        result += f"<li><b>{table_name}</b></li>"
        
        cur.execute(f"PRAGMA table_info({table_name})")
        columns = cur.fetchall()
        
        result += "<ul>"
        for column in columns:
            result += f"<li>{column[1]} ({column[2]})</li>"
        result += "</ul>"
        
    result += "</ul>"
    conn.close()
    return result

if __name__ == "__main__":
    init_db()
    app.run(debug=True)