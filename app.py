from flask import Flask, request, jsonify, session, redirect, url_for, render_template, flash, make_response, send_from_directory
from functools import wraps
import sqlite3
import os
import datetime
import hashlib
import time
from werkzeug.utils import secure_filename
import atexit
import csv
from io import StringIO
from datetime import timedelta

# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============

def cleanup_locks():
    """Очистка блокировок БД при завершении"""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(base_dir, "data")
        
        if os.path.exists(data_dir):
            db_path = os.path.join(data_dir, "hotel.db")
            lock_files = [
                db_path + '-wal', 
                db_path + '-shm', 
                db_path + '-journal',
                db_path + '.wal',
                db_path + '.shm',
                db_path + '.journal'
            ]
            for lock_file in lock_files:
                if os.path.exists(lock_file):
                    try:
                        os.remove(lock_file)
                        print(f"🗑️ Удален файл блокировки: {lock_file}")
                    except:
                        pass
    except Exception as e:
        print(f"⚠️ Ошибка при очистке блокировок: {e}")

atexit.register(cleanup_locks)

def create_missing_images():
    """Создание недостающих изображений"""
    images_dir = 'static/images'
    if not os.path.exists(images_dir):
        os.makedirs(images_dir)
        print(f"✅ Создана папка: {images_dir}")
    
    images = ['booking.jpg', 'about.jpg', 'login.jpg', 'reviews.jpg', 'orchid.jpg', 'info.jpg', 'favicon.ico']
    
    for filename in images:
        filepath = os.path.join(images_dir, filename)
        if not os.path.exists(filepath):
            try:
                with open(filepath, 'wb') as f:
                    f.write(b'')
                print(f"✅ Создан пустой файл: {filename}")
            except Exception as e2:
                print(f"⚠️ Не удалось создать {filename}: {e2}")

# ============ СОЗДАНИЕ ПРИЛОЖЕНИЯ ============

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'your-secret-key-here-change-this-in-production'
app.config['UPLOAD_FOLDER'] = 'static/images'

# ============ РЕДИРЕКТЫ ДЛЯ СТАРЫХ ССЫЛОК ============

@app.before_request
def fix_old_urls():
    """Исправление старых URL на новые"""
    old_to_new = {
        '/info_booking.html': '/info_booking',
        '/reviews.html': '/reviews', 
        '/avtorizacia_admin.html': '/admin_login_page',
        '/info_o_nas.html': '/info_o_nas',
        '/important_page.html': '/',
        '/booking_process.html': '/booking_process',
        '/avtorizacia_page.html': '/avtorizacia_page',
        '/registrazia_page.html': '/registrazia_page',
        '/ekonom_room.html': '/ekonom_room',
        '/standart_room.html': '/standart_room',
        '/lux_room.html': '/lux_room',
        '/info_booking_admin.html': '/basa_dannix',
        '/o_nas_admin.html': '/basa_dannix',
        '/important_avtor.html': '/admin_login_page'
    }
    
    if request.path in old_to_new:
        return redirect(old_to_new[request.path])

# ============ ФУНКЦИИ ДЛЯ РАБОТЫ С БД ============

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico', mimetype='image/vnd.microsoft.icon')

def get_db():
    """Подключение к базе данных"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, "data")
    
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    
    db_path = os.path.join(data_dir, "hotel.db")
    
    conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    """Хэширование пароля"""
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    """Создание базы данных и таблиц"""
    print("🔄 Инициализация базы данных...")
    
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Таблица гостей
        cur.execute('''
            CREATE TABLE IF NOT EXISTS guests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                full_name VARCHAR(100),
                phone VARCHAR(20),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login DATETIME
            )
        ''')
        
        # Таблица администраторов
        cur.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                email VARCHAR(255),
                full_name VARCHAR(100),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица типов номеров
        cur.execute('''
            CREATE TABLE IF NOT EXISTS room_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(50) NOT NULL,
                description TEXT,
                price_per_night DECIMAL(10,2),
                capacity INTEGER,
                amenities TEXT
            )
        ''')
        
        # Таблица бронирований
        cur.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guest_id INTEGER NOT NULL,
                room_type_id INTEGER,
                full_name VARCHAR(100) NOT NULL,
                passport VARCHAR(50),
                phone VARCHAR(20),
                check_in_date DATE,
                check_out_date DATE,
                status VARCHAR(20) DEFAULT 'pending',
                total_price DECIMAL(10,2),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (guest_id) REFERENCES guests(id),
                FOREIGN KEY (room_type_id) REFERENCES room_types(id)
            )
        ''')
        
        # Таблица отзывов
        cur.execute('''
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guest_id INTEGER NOT NULL,
                rating INTEGER CHECK(rating BETWEEN 1 AND 5),
                comment TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (guest_id) REFERENCES guests(id)
            )
        ''')
        
        # Добавляем тестовые данные
        cur.execute("SELECT COUNT(*) FROM admins WHERE username = 'admin'")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO admins (username, password_hash, email, full_name) VALUES (?, ?, ?, ?)",
                ('admin', hash_password('admin123'), 'admin@hotel.com', 'Главный администратор')
            )
            print("✅ Создан администратор: admin / admin123")
        
        cur.execute("SELECT COUNT(*) FROM room_types")
        if cur.fetchone()[0] == 0:
            room_types = [
                ('Экономный', 'Бюджетный номер с базовыми удобствами', 1500.00, 1, 'Wi-Fi, душ, телевизор'),
                ('Стандартный', 'Комфортабельный номер для 2-х человек', 2500.00, 2, 'Wi-Fi, кондиционер, мини-бар'),
                ('Люксовый', 'Просторный номер с улучшенным сервисом', 5000.00, 2, 'Wi-Fi, джакузи, персональный дворецкий')
            ]
            cur.executemany(
                "INSERT INTO room_types (name, description, price_per_night, capacity, amenities) VALUES (?, ?, ?, ?, ?)",
                room_types
            )
            print("✅ Созданы типы номеров")
        
        conn.commit()
        print("✅ База данных успешно инициализирована")
        
    except Exception as e:
        print(f"❌ Ошибка при инициализации БД: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

# ============ ДЕКОРАТОРЫ ДЛЯ ПРОВЕРКИ АВТОРИЗАЦИИ ============

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "guest_id" not in session:
            session['next_url'] = request.url
            flash("Для доступа к этой странице необходимо войти в систему", "error")
            return redirect(url_for("avtorizacia_page"))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "admin_id" not in session:
            flash("Требуется авторизация администратора", "error")
            return redirect(url_for("admin_login_page"))
        return f(*args, **kwargs)
    return decorated_function

# ============ МАРШРУТЫ ============

@app.route("/")
def index():
    """Главная страница"""
    is_logged_in = "guest_id" in session
    username = session.get("guest_username", None)
    
    return render_template("index.html", 
                          is_logged_in=is_logged_in, 
                          username=username)

# ============ АВТОРИЗАЦИЯ И РЕГИСТРАЦИЯ ============

@app.route("/avtorizacia_page", methods=["GET", "POST"])
def avtorizacia_page():
    """Страница авторизации пользователя"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        print(f"=== ДЕБАГ АВТОРИЗАЦИИ ===")
        print(f"Логин из формы: '{username}'")
        print(f"Пароль из формы: '{password}'")
        
        if not username or not password:
            print("Ошибка: пустой логин или пароль")
            flash("Логин и пароль обязательны", "error")
            return render_template("avtorizacia_page.html")
        
        conn = None
        try:
            conn = get_db()
            cur = conn.cursor()
            
            print(f"Ищу пользователя '{username}' в БД...")
            cur.execute("SELECT * FROM guests WHERE username = ?", (username,))
            guest = cur.fetchone()
            
            if not guest:
                print(f"Пользователь '{username}' не найден в БД")
                flash("Пользователь не найден", "error")
                return render_template("avtorizacia_page.html")
            
            print(f"Пользователь найден: ID={guest['id']}, логин={guest['username']}")
            print(f"Пароль из БД (хэш): {guest['password_hash']}")
            
            # Хэшируем введенный пароль
            input_hash = hash_password(password)
            print(f"Введенный пароль (хэш): {input_hash}")
            
            if guest["password_hash"] != input_hash:
                print("Пароли не совпадают!")
                flash("Неверный пароль", "error")
                return render_template("avtorizacia_page.html")
            
            print("Пароль верный! Устанавливаю сессию...")
            
            # Устанавливаем сессию
            session["guest_id"] = guest["id"]
            session["guest_username"] = guest["username"]
            session["guest_email"] = guest["email"]
            
            print(f"Сессия установлена: guest_id={session['guest_id']}")
            
            # Обновляем время последнего входа
            cur.execute(
                "UPDATE guests SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                (guest["id"],)
            )
            conn.commit()
            
            print("Успех! Редирект на главную...")
            flash("Вы успешно вошли в систему!", "success")
            return redirect(url_for("index"))
            
        except Exception as e:
            print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {str(e)}")
            import traceback
            traceback.print_exc()
            flash(f"Ошибка при авторизации: {str(e)}", "error")
            return render_template("avtorizacia_page.html")
        finally:
            if conn:
                conn.close()
    else:
        print("GET запрос на страницу авторизации")
    
    return render_template("avtorizacia_page.html")
    """Страница авторизации пользователя"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        print(f"=== ДЕБАГ АВТОРИЗАЦИИ ===")
        print(f"Логин из формы: '{username}'")
        print(f"Пароль из формы: '{password}'")
        
        if not username or not password:
            print("Ошибка: пустой логин или пароль")
            flash("Логин и пароль обязательны", "error")
            return render_template("avtorizacia_page.html")
        
        conn = None
        try:
            conn = get_db()
            cur = conn.cursor()
            
            print(f"Ищу пользователя '{username}' в БД...")
            cur.execute("SELECT * FROM guests WHERE username = ?", (username,))
            guest = cur.fetchone()
            
            if not guest:
                print(f"Пользователь '{username}' не найден в БД")
                flash("Пользователь не найден", "error")
                return render_template("avtorizacia_page.html")
            
            print(f"Пользователь найден: ID={guest['id']}, логин={guest['username']}")
            print(f"Пароль из БД (хэш): {guest['password_hash']}")
            
            # Хэшируем введенный пароль
            input_hash = hash_password(password)
            print(f"Введенный пароль (хэш): {input_hash}")
            
            if guest["password_hash"] != input_hash:
                print("Пароли не совпадают!")
                flash("Неверный пароль", "error")
                return render_template("avtorizacia_page.html")
            
            print("Пароль верный! Устанавливаю сессию...")
            
            # Устанавливаем сессию
            session["guest_id"] = guest["id"]
            session["guest_username"] = guest["username"]
            session["guest_email"] = guest["email"]
            
            print(f"Сессия установлена: guest_id={session['guest_id']}")
            
            # Обновляем время последнего входа
            cur.execute(
                "UPDATE guests SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                (guest["id"],)
            )
            conn.commit()
            
            print("Успех! Редирект на главную...")
            flash("Вы успешно вошли в систему!", "success")
            return redirect(url_for("index"))
            
        except Exception as e:
            print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {str(e)}")
            import traceback
            traceback.print_exc()
            flash(f"Ошибка при авторизации: {str(e)}", "error")
            return render_template("avtorizacia_page.html")
        finally:
            if conn:
                conn.close()
    else:
        print("GET запрос на страницу авторизации")
    
    return render_template("avtorizacia_page.html")
    """Страница авторизации пользователя"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        if not username or not password:
            flash("Логин и пароль обязательны", "error")
            return render_template("avtorizacia_page.html")
        
        conn = None
        try:
            conn = get_db()
            cur = conn.cursor()
            
            cur.execute("SELECT * FROM guests WHERE username = ?", (username,))
            guest = cur.fetchone()
            
            if not guest:
                flash("Пользователь не найден", "error")
                return render_template("avtorizacia_page.html")
            
            # Сравниваем хэши паролей
            input_password_hash = hash_password(password)
            if guest["password_hash"] != input_password_hash:
                flash("Неверный пароль", "error")
                return render_template("avtorizacia_page.html")
            
            session["guest_id"] = guest["id"]
            session["guest_username"] = guest["username"]
            session["guest_email"] = guest["email"]
            
            cur.execute(
                "UPDATE guests SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                (guest["id"],)
            )
            conn.commit()
            
            # Сообщение об успешном входе
            flash("Вы успешно вошли в систему!", "success")
            
            # Редирект на главную страницу
            return redirect(url_for("index"))
            
        except Exception as e:
            print(f"Ошибка авторизации: {str(e)}")
            flash(f"Ошибка при авторизации: {str(e)}", "error")
            return render_template("avtorizacia_page.html")
        finally:
            if conn:
                conn.close()
    
    return render_template("avtorizacia_page.html")
    """Страница авторизации пользователя"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        if not username or not password:
            flash("Логин и пароль обязательны", "error")
            return render_template("avtorizacia_page.html")
        
        conn = None
        try:
            conn = get_db()
            cur = conn.cursor()
            
            cur.execute("SELECT * FROM guests WHERE username = ?", (username,))
            guest = cur.fetchone()
            
            if not guest:
                flash("Пользователь не найден", "error")
                return render_template("avtorizacia_page.html")
            
            if guest["password_hash"] != hash_password(password):
                flash("Неверный пароль", "error")
                return render_template("avtorizacia_page.html")
            
            session["guest_id"] = guest["id"]
            session["guest_username"] = guest["username"]
            session["guest_email"] = guest["email"]
            
            cur.execute(
                "UPDATE guests SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                (guest["id"],)
            )
            conn.commit()
            
            # Сообщение об успешном входе
            flash("Вы успешно вошли в систему!", "success")
            
            # Редирект на главную страницу
            return redirect(url_for("index"))
            
        except Exception as e:
            print(f"Ошибка авторизации: {str(e)}")
            flash(f"Ошибка при авторизации: {str(e)}", "error")
            return render_template("avtorizacia_page.html")
        finally:
            if conn:
                conn.close()
    
    return render_template("avtorizacia_page.html")

@app.route("/registrazia_page", methods=["GET", "POST"])
def registrazia_page():
    """Страница регистрации"""
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        
        # Без сообщений об ошибках на сайте
        errors = []
        
        if not all([username, email, password, confirm_password]):
            errors.append("Все поля обязательны для заполнения")
        
        if password != confirm_password:
            errors.append("Пароли не совпадают")
        
        if len(password) < 6:
            errors.append("Пароль должен быть не менее 6 символов")
        
        # Если есть ошибки - просто возвращаем
        if errors:
            return render_template("registrazia_page.html")
        
        conn = None
        try:
            conn = get_db()
            cur = conn.cursor()
            
            cur.execute("SELECT id FROM guests WHERE username = ?", (username,))
            if cur.fetchone():
                # Без сообщения об ошибке
                return render_template("registrazia_page.html")
            
            cur.execute("SELECT id FROM guests WHERE email = ?", (email,))
            if cur.fetchone():
                # Без сообщения об ошибке
                return render_template("registrazia_page.html")
            
            password_hash = hash_password(password)
            cur.execute(
                "INSERT INTO guests (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, password_hash)
            )
            
            guest_id = cur.lastrowid
            conn.commit()
            
            session["guest_id"] = guest_id
            session["guest_username"] = username
            session["guest_email"] = email
            
            # Только успешное сообщение
            flash("Регистрация успешна! Вы вошли в систему.", "success")
            return redirect("/")
            
        except Exception as e:
            print(f"Ошибка регистрации: {str(e)}")
            # Без сообщения об ошибке
            return render_template("registrazia_page.html")
        finally:
            if conn:
                conn.close()
    
    return render_template("registrazia_page.html")

@app.route("/booking_process", methods=["GET", "POST"])
@login_required
def booking_process():
    """Страница бронирования"""
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute("SELECT * FROM room_types ORDER BY price_per_night")
        room_types = cur.fetchall()
        
        if request.method == "POST":
            full_name = request.form.get("fullname")
            passport = request.form.get("passport")
            phone = request.form.get("phone")
            room_type_name = request.form.get("room-type")
            check_in_str = request.form.get("arrival")
            check_out_str = request.form.get("departure")
            consent = request.form.get("consent")
            
            if not all([full_name, passport, phone, room_type_name, check_in_str, check_out_str]):
                flash("Пожалуйста, заполните все обязательные поля", "error")
                return render_template("booking_process.html", room_types=room_types)
            
            if not consent:
                flash("Необходимо согласие на обработку персональных данных", "error")
                return render_template("booking_process.html", room_types=room_types)
            
            try:
                check_in_date = datetime.datetime.strptime(check_in_str, "%Y-%m-%d")
                check_out_date = datetime.datetime.strptime(check_out_str, "%Y-%m-%d")
                
                if check_out_date <= check_in_date:
                    flash("Дата выезда должна быть позже даты заезда", "error")
                    return render_template("booking_process.html", room_types=room_types)
                
                # Проверка на 2 недели
                two_weeks_later = datetime.datetime.now() + timedelta(days=14)
                if check_in_date <= two_weeks_later:
                    flash("Бронирование возможно только за 2 недели до заселения", "error")
                    return render_template("booking_process.html", room_types=room_types)
                
                # Проверка доступности номера
                cur.execute("SELECT id, price_per_night, capacity FROM room_types WHERE name = ?", (room_type_name,))
                room_type = cur.fetchone()
                
                if not room_type:
                    flash("Неверный тип номера", "error")
                    return render_template("booking_process.html", room_types=room_types)
                
                # Проверяем, занят ли номер на эти даты
                cur.execute('''
                    SELECT COUNT(*) FROM bookings 
                    WHERE room_type_id = ? 
                    AND status IN ('pending', 'confirmed')
                    AND (
                        (check_in_date <= ? AND check_out_date >= ?) OR
                        (check_in_date <= ? AND check_out_date >= ?) OR
                        (check_in_date >= ? AND check_out_date <= ?)
                    )
                ''', (room_type["id"], check_in_str, check_in_str, check_out_str, check_out_str, 
                     check_in_str, check_out_str))
                
                occupied_count = cur.fetchone()[0]
                
                if occupied_count > 0:
                    # Находим альтернативные варианты
                    cur.execute('''
                        SELECT * FROM room_types 
                        WHERE id != ? 
                        AND capacity >= ?
                        ORDER BY price_per_night
                    ''', (room_type["id"], room_type["capacity"]))
                    
                    alternatives = cur.fetchall()
                    
                    if alternatives:
                        alt_text = "Доступны альтернативные номера: "
                        for alt in alternatives:
                            alt_text += f"{alt['name']} ({alt['price_per_night']} руб./ночь), "
                        flash(f"Этот номер занят на выбранные даты. {alt_text[:-2]}", "error")
                    else:
                        flash("Этот номер занят на выбранные даты. Попробуйте другие даты.", "error")
                    
                    return render_template("booking_process.html", room_types=room_types)
                
                nights = (check_out_date - check_in_date).days
                total_price = room_type["price_per_night"] * nights
                
                cur.execute('''
                    INSERT INTO bookings (guest_id, room_type_id, full_name, passport, phone, 
                                        check_in_date, check_out_date, total_price, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                ''', (session["guest_id"], room_type["id"], full_name, passport, phone, 
                      check_in_str, check_out_str, total_price))
                
                conn.commit()
                flash("Бронирование успешно создано! Ожидайте подтверждения.", "success")
                return redirect("/info_booking")
                
            except ValueError:
                flash("Некорректный формат даты", "error")
            except Exception as e:
                print(f"Ошибка бронирования: {str(e)}")
                conn.rollback()
                flash(f"Ошибка при бронировании: {str(e)}", "error")
        
        return render_template("booking_process.html", room_types=room_types)
        
    except Exception as e:
        print(f"Ошибка подключения к БД: {e}")
        flash("Ошибка подключения к базе данных", "error")
        return redirect("/")
    finally:
        if conn:
            conn.close()

# ============ ОТЧЕТЫ ============

@app.route("/reports")
@admin_required
def reports():
    """Страница отчетов"""
    return render_template("report_1.html")

@app.route("/report/free_rooms", methods=["GET", "POST"])
@admin_required
def report_free_rooms():
    """Отчет о свободных номерах за указанную дату"""
    if request.method == "POST":
        date_str = request.form.get("date")
        
        try:
            date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            
            conn = get_db()
            cur = conn.cursor()
            
            # Получаем все номера
            cur.execute("SELECT * FROM room_types ORDER BY name")
            all_rooms = cur.fetchall()
            
            # Получаем занятые номера на эту дату
            cur.execute('''
                SELECT DISTINCT room_type_id FROM bookings 
                WHERE status IN ('pending', 'confirmed')
                AND ? BETWEEN check_in_date AND DATE(check_out_date, '-1 day')
            ''', (date_str,))
            
            occupied_ids = [row[0] for row in cur.fetchall()]
            
            # Формируем отчет
            output = StringIO()
            writer = csv.writer(output, delimiter=',', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(['Отчет о свободных номерах', f'Дата: {date_str}'])
            writer.writerow([])
            writer.writerow(['Тип номера', 'Описание', 'Цена за ночь', 'Вместимость', 'Статус'])
            
            free_count = 0
            occupied_count = 0
            
            for room in all_rooms:
                status = "Занят" if room['id'] in occupied_ids else "Свободен"
                if status == "Свободен":
                    free_count += 1
                else:
                    occupied_count += 1
                    
                writer.writerow([
                    room['name'],
                    room['description'],
                    f"{room['price_per_night']:.2f}",
                    room['capacity'],
                    status
                ])
            
            writer.writerow([])
            writer.writerow(['ИТОГО:'])
            writer.writerow(['Свободных номеров:', free_count])
            writer.writerow(['Занятых номеров:', occupied_count])
            writer.writerow(['Всего номеров:', len(all_rooms)])
            
            conn.close()
            
            # Создаем ответ для скачивания
            response = make_response(output.getvalue())
            response.headers["Content-Disposition"] = f"attachment; filename=free_rooms_{date_str}.csv"
            response.headers["Content-type"] = "text/csv; charset=utf-8"
            return response
            
        except ValueError:
            flash("Некорректный формат даты. Используйте формат ГГГГ-ММ-ДД", "error")
            return redirect("/reports")
        except Exception as e:
            print(f"Ошибка формирования отчета: {e}")
            flash(f"Ошибка при формировании отчета: {str(e)}", "error")
            return redirect("/reports")
    
    return render_template("report_1.html")

@app.route("/report/bookings", methods=["GET", "POST"])
@admin_required
def report_bookings():
    """Отчет принятых заявок за указанный период"""
    if request.method == "POST":
        start_date = request.form.get("start_date")
        end_date = request.form.get("end_date")
        
        try:
            start = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
            
            if end < start:
                flash("Конечная дата должна быть позже начальной", "error")
                return redirect("/reports")
            
            conn = get_db()
            cur = conn.cursor()
            
            cur.execute('''
                SELECT b.*, g.username, g.email, g.phone as guest_phone,
                       rt.name as room_type_name, rt.price_per_night
                FROM bookings b
                JOIN guests g ON b.guest_id = g.id
                LEFT JOIN room_types rt ON b.room_type_id = rt.id
                WHERE DATE(b.created_at) BETWEEN ? AND ?
                AND b.status IN ('pending', 'confirmed')
                ORDER BY b.created_at DESC
            ''', (start_date, end_date))
            
            bookings = cur.fetchall()
            
            # Формируем отчет
            output = StringIO()
            writer = csv.writer(output, delimiter=',', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(['Отчет о заявках на бронирование', f'Период: {start_date} - {end_date}'])
            writer.writerow([])
            writer.writerow(['ID', 'Гость', 'Email гостя', 'Телефон гостя', 
                           'Тип номера', 'ФИО в заявке', 'Телефон в заявке',
                           'Паспорт', 'Дата заезда', 'Дата выезда', 'Ночей',
                           'Цена за ночь', 'Общая стоимость', 'Статус', 'Дата создания'])
            
            total_price = 0
            total_nights = 0
            
            for booking in bookings:
                nights = (datetime.datetime.strptime(booking['check_out_date'], "%Y-%m-%d") - 
                         datetime.datetime.strptime(booking['check_in_date'], "%Y-%m-%d")).days
                
                writer.writerow([
                    booking['id'],
                    booking['username'],
                    booking['email'],
                    booking['guest_phone'] or '',
                    booking['room_type_name'] or 'Не указан',
                    booking['full_name'],
                    booking['phone'],
                    booking['passport'] or '',
                    booking['check_in_date'],
                    booking['check_out_date'],
                    nights,
                    f"{booking['price_per_night']:.2f}" if booking['price_per_night'] else '0.00',
                    f"{booking['total_price']:.2f}" if booking['total_price'] else '0.00',
                    booking['status'],
                    booking['created_at']
                ])
                total_price += booking['total_price'] or 0
                total_nights += nights
            
            writer.writerow([])
            writer.writerow(['ИТОГО:'])
            writer.writerow(['Всего заявок:', len(bookings)])
            writer.writerow(['Общая стоимость:', f"{total_price:.2f} руб."])
            writer.writerow(['Общее количество ночей:', total_nights])
            
            conn.close()
            
            response = make_response(output.getvalue())
            response.headers["Content-Disposition"] = f"attachment; filename=bookings_{start_date}_{end_date}.csv"
            response.headers["Content-type"] = "text/csv; charset=utf-8"
            return response
            
        except ValueError:
            flash("Некорректный формат даты. Используйте формат ГГГГ-ММ-ДД", "error")
            return redirect("/reports")
        except Exception as e:
            print(f"Ошибка формирования отчета: {e}")
            flash(f"Ошибка при формировании отчета: {str(e)}", "error")
            return redirect("/reports")
    
    return render_template("report_2.html")

# ============ ОТЗЫВЫ ============

@app.route("/reviews", methods=["GET", "POST"])
def reviews():
    """Страница с отзывами"""
    if request.method == "POST":
        if "guest_id" not in session:
            flash("Для отправки отзыва необходимо войти в систему", "error")
            return redirect("/avtorizacia_page")
        
        rating = request.form.get("stars")
        comment = request.form.get("review")
        
        if not rating or not comment:
            flash("Пожалуйста, заполните все поля", "error")
            return redirect("/reviews")
        
        conn = None
        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                flash("Рейтинг должен быть от 1 до 5", "error")
                return redirect("/reviews")
            
            conn = get_db()
            cur = conn.cursor()
            
            # Сохраняем отзыв в БД
            cur.execute(
                "INSERT INTO reviews (guest_id, rating, comment) VALUES (?, ?, ?)",
                (session["guest_id"], rating, comment)
            )
            
            conn.commit()
            flash("Спасибо за ваш отзыв! Он успешно сохранен.", "success")
            
        except ValueError:
            flash("Некорректный рейтинг", "error")
        except Exception as e:
            print(f"Ошибка при сохранении отзыва: {str(e)}")
            if conn:
                conn.rollback()
            flash(f"Ошибка при сохранении отзыва: {str(e)}", "error")
        finally:
            if conn:
                conn.close()
        
        # ВСЕГДА возвращаем на страницу отзывов
        return redirect("/reviews")
    
    # GET запрос - показываем все отзывы
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT r.*, g.username 
            FROM reviews r 
            JOIN guests g ON r.guest_id = g.id 
            ORDER BY r.created_at DESC
        ''')
        
        reviews_list = cur.fetchall()
        
        # Получаем статистику
        cur.execute('''
            SELECT 
                AVG(rating) as avg_rating,
                COUNT(*) as total_reviews,
                COUNT(CASE WHEN rating = 5 THEN 1 END) as five_stars,
                COUNT(CASE WHEN rating = 4 THEN 1 END) as four_stars,
                COUNT(CASE WHEN rating = 3 THEN 1 END) as three_stars,
                COUNT(CASE WHEN rating = 2 THEN 1 END) as two_stars,
                COUNT(CASE WHEN rating = 1 THEN 1 END) as one_stars
            FROM reviews
        ''')
        
        stats = cur.fetchone()
        
        return render_template("reviews.html", 
                             reviews=reviews_list, 
                             stats=stats)
        
    except Exception as e:
        print(f"Ошибка работы с отзывами: {e}")
        flash("Ошибка при загрузке отзывов", "error")
        return redirect("/")
    finally:
        if conn:
            conn.close()

# ============ ОСТАЛЬНЫЕ СТРАНИЦЫ ============

@app.route("/info_booking")
@login_required
def info_booking():
    """Страница с информацией о бронированиях"""
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT b.*, rt.name as room_type_name, rt.price_per_night
            FROM bookings b
            LEFT JOIN room_types rt ON b.room_type_id = rt.id
            WHERE b.guest_id = ?
            ORDER BY b.created_at DESC
        ''', (session["guest_id"],))
        
        bookings = cur.fetchall()
        return render_template("info_booking.html", bookings=bookings)
        
    except Exception as e:
        print(f"Ошибка получения бронирований: {e}")
        flash("Ошибка при получении информации о бронированиях", "error")
        return redirect("/")
    finally:
        if conn:
            conn.close()

@app.route("/info_o_nas")
def info_o_nas():
    """Страница 'О нас'"""
    return render_template("info_o_nas.html")

@app.route("/ekonom_room")
def ekonom_room():
    """Страница с информацией об экономных номерах"""
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM room_types WHERE name LIKE '%Эконом%'")
        room = cur.fetchone()
        
        if not room:
            flash("Информация о номерах временно недоступна", "error")
            return redirect("/")
        
        return render_template("ekonom_room.html", room=room)
    finally:
        if conn:
            conn.close()

@app.route("/standart_room")
def standart_room():
    """Страница с информацией о стандартных номерах"""
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM room_types WHERE name LIKE '%Стандарт%'")
        room = cur.fetchone()
        
        if not room:
            flash("Информация о номерах временно недоступна", "error")
            return redirect("/")
        
        return render_template("standart_room.html", room=room)
    finally:
        if conn:
            conn.close()

@app.route("/lux_room")
def lux_room():
    """Страница с информацией о люксовых номерах"""
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM room_types WHERE name LIKE '%Люкс%'")
        room = cur.fetchone()
        
        if not room:
            flash("Информация о номерах временно недоступна", "error")
            return redirect("/")
        
        return render_template("lux_room.html", room=room)
    finally:
        if conn:
            conn.close()

@app.route("/admin_login_page", methods=["GET", "POST"])
def admin_login_page():
    """Страница авторизации администратора"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        if not username or not password:
            flash("Логин и пароль обязательны", "error")
            return render_template("avtorizacia_admin.html")
        
        conn = None
        try:
            conn = get_db()
            cur = conn.cursor()
            
            cur.execute("SELECT * FROM admins WHERE username = ?", (username,))
            admin = cur.fetchone()
            
            if not admin:
                flash("Администратор не найден", "error")
            elif admin["password_hash"] != hash_password(password):
                flash("Неверный пароль", "error")
            else:
                session["admin_id"] = admin["id"]
                session["admin_username"] = admin["username"]
                session["admin_name"] = admin["full_name"]
                flash("Авторизация администратора успешна", "success")
                return redirect("/basa_dannix")
                
        except Exception as e:
            print(f"Ошибка авторизации админа: {str(e)}")
            flash(f"Ошибка при авторизации: {str(e)}", "error")
        finally:
            if conn:
                conn.close()
    
    return render_template("avtorizacia_admin.html")

@app.route("/basa_dannix")
def basa_dannix():
    """Панель администратора"""
    if "admin_id" not in session:
        flash("Требуется авторизация администратора", "error")
        return redirect("/admin_login_page")
    
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM guests")
        total_guests = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM bookings")
        total_bookings = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM bookings WHERE status = 'pending'")
        pending_bookings = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM reviews")
        total_reviews = cur.fetchone()[0]
        
        cur.execute("SELECT * FROM guests ORDER BY created_at DESC LIMIT 10")
        recent_guests = cur.fetchall()
        
        cur.execute('''
            SELECT b.*, g.username, rt.name as room_type_name
            FROM bookings b
            JOIN guests g ON b.guest_id = g.id
            LEFT JOIN room_types rt ON b.room_type_id = rt.id
            ORDER BY b.created_at DESC LIMIT 10
        ''')
        recent_bookings = cur.fetchall()
        
        cur.execute('''
            SELECT r.*, g.username
            FROM reviews r
            JOIN guests g ON r.guest_id = g.id
            ORDER BY r.created_at DESC LIMIT 10
        ''')
        recent_reviews = cur.fetchall()
        
        return render_template(
            "basa_dannix.html",
            total_guests=total_guests,
            total_bookings=total_bookings,
            pending_bookings=pending_bookings,
            total_reviews=total_reviews,
            recent_guests=recent_guests,
            recent_bookings=recent_bookings,
            recent_reviews=recent_reviews
        )
        
    except Exception as e:
        print(f"Ошибка панели администратора: {e}")
        flash("Ошибка при загрузке данных администратора", "error")
        return redirect("/")
    finally:
        if conn:
            conn.close()

@app.route("/logout")
def logout():
    """Выход из системы (гость)"""
    session.pop("guest_id", None)
    session.pop("guest_username", None)
    session.pop("guest_email", None)
    flash("Вы вышли из системы", "info")
    return redirect("/")

@app.route("/admin/logout")
def admin_logout():
    """Выход из системы (администратор)"""
    session.pop("admin_id", None)
    session.pop("admin_username", None)
    session.pop("admin_name", None)
    flash("Вы вышли из системы администратора", "info")
    return redirect("/")

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# ============ ЗАПУСК ПРИЛОЖЕНИЯ ============

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 ЗАПУСК ГОСТИНИЦЫ L&N")
    print("=" * 60)
    
    cleanup_locks()
    
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/images', exist_ok=True)
    os.makedirs('data', exist_ok=True)
    
    create_missing_images()
    
    time.sleep(1)
    
    try:
        init_db()
    except Exception as e:
        print(f"⚠️ Ошибка инициализации БД: {e}")
    
    print("\n" + "=" * 60)
    print("✅ ПРИЛОЖЕНИЕ ЗАПУЩЕНО!")
    print("👉 Главная: http://localhost:5000")
    print("👉 Бронирование: http://localhost:5000/booking_process")
    print("👉 Отчеты: http://localhost:5000/reports")
    print("👉 Админ: http://localhost:5000/admin_login_page")
    print("=" * 60 + "\n")
    
    try:
        app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
    except Exception as e:
        print(f"\n❌ Ошибка запуска сервера: {e}")