from flask import Flask, request, render_template
import sqlite3
import os
import datetime

class MrBooking:
    guest_name: str
    room_class: int
    desired_date: datetime
    duration: int

    def __str__(self):
        return f"{self.guest_name} — {self.room_class} ({self.desired_date})"

app = Flask(__name__)  # исправлено: name → __name__

def get_db():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "data", "hotel.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def index():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
    br.rowid AS booking_id, 
    g.first_name, 
    g.last_name, 
    br.room_class, 
    br.desired_date, 
    br.duration
FROM BookingRequest AS br
JOIN Guest AS g ON br.guest_id = g.guest_id
ORDER BY br.desired_date ASC;
    """)
    requests = cur.fetchall()
    print(len(requests))
    conn.close()

    return render_template("project.html", requests=requests)



@app.route("/create-request", methods=["POST"])
def create_request():
    form = request.form
    conn = get_db()
    cur = conn.cursor()

    # Проверка даты: минимум за 14 дней
    desired_date = form["desired_date"]
    desired_dt = datetime.datetime.strptime(desired_date, "%Y-%m-%d")
    today = datetime.datetime.today()
    if (desired_dt - today).days < 14:
        return "❌ Заявки принимаются не ранее, чем за 2 недели до заселения.", 400

    # Вставка гостя
    cur.execute("""
        INSERT OR IGNORE INTO Guest (first_name, last_name, passport)
        VALUES (?, ?, ?)
    """, (form["first_name"], form["last_name"], form["passport"]))

    # Получение guest_id
    cur.execute("SELECT guest_id FROM Guest WHERE passport = ?", (form["passport"],))
    guest = cur.fetchone()
    if not guest:
        return "❌ Не удалось найти гостя после вставки.", 500
    guest_id = guest["guest_id"]

    # Проверка доступности номера
    cur.execute("""
        SELECT COUNT(*) as available FROM Room
        WHERE room_class = ? AND is_available = 1
    """, (form["room_class"],))
    available = cur.fetchone()["available"]

    if available > 0:
        # Вставка заявки
        cur.execute("""
            INSERT INTO BookingRequest (guest_id, room_class, desired_date, duration)
            VALUES (?, ?, ?, ?)
        """, (guest_id, form["room_class"], desired_date, form["duration"]))
        conn.commit()
        conn.close()
        return "✅ Заявка зарегистрирована!", 200
    else:
        # Альтернатива
        cur.execute("""
            SELECT desired_date FROM BookingRequest
            WHERE room_class = ?
            ORDER BY desired_date ASC LIMIT 1
        """, (form["room_class"],))
        alt = cur.fetchone()
        conn.close()
        if alt:
            return f"❌ Нет свободных номеров. Альтернативная дата: {alt['desired_date']}", 200
        else:
            return "❌ Нет свободных номеров и альтернативных дат.", 200

if __name__ == "__main__":
    app.run(debug=True)
