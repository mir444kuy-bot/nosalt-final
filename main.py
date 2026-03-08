import os
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

DB_URL = os.environ.get("DATABASE_URL")
TIMEOUT = 300  

def get_db_connection():
    if not DB_URL: 
        return None
    try: 
        return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)
    except Exception as e: 
        print(f"Connection Error: {e}")
        return None

def format_num(n):
    try: 
        return "{:,}".format(int(float(n)))
    except: 
        return "0"

def get_status(last_ts):
    if (time.time() - last_ts) < TIMEOUT:
        return "online"
    else:
        return "offline"

def get_time_ago(last_ts):
    if not last_ts: 
        return "-"
    
    diff = time.time() - float(last_ts)
    
    if diff < 0: 
        diff = 0
        
    if diff < 60: 
        return f"{int(diff)}s"
    elif diff < 3600: 
        return f"{int(diff//60)}m"
    else: 
        return f"{int(diff//3600)}h"

@app.route('/')
def index(): 
    return render_template('index.html')

@app.route('/device/<name>')
def device_page(name): 
    return render_template('device.html', device_name=name)

@app.route('/init-db-force')
def init_db_manual():
    try:
        conn = get_db_connection()
        if not conn:
            return "<h1>❌ เชื่อมต่อ Database ไม่ได้</h1>"
            
        cur = conn.cursor()
        
        # สร้างตารางหลัก (ถ้ายังไม่มี)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, 
                device TEXT, 
                username TEXT, 
                seed BIGINT, 
                gems BIGINT DEFAULT 0, 
                diff BIGINT, 
                gems_diff BIGINT DEFAULT 0,
                raff INTEGER, 
                lawn INTEGER DEFAULT 0, 
                last_update DOUBLE PRECISION, 
                last_seed_change DOUBLE PRECISION, 
                game TEXT
            )
        ''')
        conn.commit()
        
        # ไล่เพิ่ม Column ที่อาจจะยังไม่มี
        try: 
            cur.execute("ALTER TABLE users ADD COLUMN gems BIGINT DEFAULT 0")
            conn.commit()
        except: 
            conn.rollback()

        # 🔴 เพิ่ม Column ใหม่สำหรับเก็บส่วนต่างเพชร
        try: 
            cur.execute("ALTER TABLE users ADD COLUMN gems_diff BIGINT DEFAULT 0")
            conn.commit()
        except: 
            conn.rollback()
            
        try: 
            cur.execute("ALTER TABLE users ADD COLUMN lawn INTEGER DEFAULT 0")
            conn.commit()
        except: 
            conn.rollback()
            
        cur.close()
        conn.close()
        
        return """
        <body style='background:#0a0a0c; color:#00ff66; text-align:center; padding-top:50px; font-family:sans-serif;'>
            <h1>✅ Database Updated!</h1>
            <p>เพิ่มช่องเก็บ Gem Diff เรียบร้อยแล้ว</p>
            <a href='/' style='color:#fff;'>กลับหน้าหลัก</a>
        </body>
        """
    except Exception as e: 
        return f"<h1>❌ Error: {e}</h1>"

@app.route('/api/global')
def api_global():
    target_game = request.args.get('game', 'Garden TD')
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE game = %s OR game IS NULL", (target_game,))
        all_data = cur.fetchall()
        cur.close()
        conn.close()
    except: 
        return jsonify({"devices": [], "stats": {}})

    devices = {}
    t_on = 0
    t_seed = 0
    t_gems = 0
    
    for item in all_data:
        d_name = item['device']
        is_on = get_status(item['last_update']) == "online"
        
        if d_name not in devices: 
            devices[d_name] = {
                "name": d_name, 
                "on": 0, 
                "off": 0, 
                "total": 0, 
                "seeds": 0, 
                "gems": 0
            }
            
        devices[d_name]["total"] += 1
        
        try: 
            devices[d_name]["seeds"] += item['seed']
            devices[d_name]["gems"] += (item['gems'] or 0)
        except: 
            pass
            
        if is_on: 
            devices[d_name]["on"] += 1
            t_on += 1
        else: 
            devices[d_name]["off"] += 1
            
        t_seed += item['seed']
        t_gems += (item['gems'] or 0)

    sorted_devices = sorted(list(devices.values()), key=lambda x: x['name'])
    
    return jsonify({
        "devices": sorted_devices, 
        "stats": {
            "t_on": t_on, 
            "t_acc": len(all_data), 
            "t_dev": len(devices), 
            "t_seed": format_num(t_seed), 
            "t_gems": format_num(t_gems)
        }
    })

@app.route('/api/device/<name>')
def api_device(name):
    target_game = request.args.get('game', 'Garden TD')
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE device = %s AND (game = %s OR game IS NULL)", (name, target_game))
        users = cur.fetchall()
        cur.close()
        conn.close()
    except: 
        return jsonify({"stats":{}, "users":[]})
    
    d_on = 0
    d_off = 0
    d_seed = 0
    d_gems = 0
    user_list = []
    
    for u in users:
        status = get_status(u['last_update'])
        
        if status == "online": 
            d_on += 1
        else: 
            d_off += 1
            
        d_seed += u['seed']
        d_gems += (u['gems'] or 0)
        
        user_list.append({
            "username": u['username'], 
            "seed": format_num(u['seed']), 
            "gems": format_num(u['gems'] or 0),
            "diff": format_num(u['diff']), 
            "gems_diff": format_num(u['gems_diff'] if 'gems_diff' in u and u['gems_diff'] else 0), # ส่งค่า Gem Diff ไปหน้าเว็บ
            "raff": bool(u['raff'] if 'raff' in u else False), 
            "lawn": bool(u['lawn'] if 'lawn' in u else False),
            "status": status, 
            "time_ago": get_time_ago(u['last_update']) if u['last_update'] else "New",
            "raw_status": 1 if status == "online" else 0
        })
        
    return jsonify({
        "stats": { 
            "online": d_on, 
            "offline": d_off, 
            "total_acc": len(users), 
            "total_seed": format_num(d_seed), 
            "total_gems": format_num(d_gems) 
        }, 
        "users": user_list
    })

@app.route('/update', methods=['POST'])
def update():
    try:
        data = request.json
        game_name = data.get('game', 'Garden TD')
        uid = f"{data['device']}_{data['username']}_{game_name}"
        current_time = float(time.time())
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # ดึงค่าเดิมออกมาเพื่อคำนวณส่วนต่าง
        cur.execute("SELECT seed, gems, diff, gems_diff, last_seed_change FROM users WHERE id = %s", (uid,))
        row = cur.fetchone()
        
        old_seed = row['seed'] if row else 0
        old_gems = row['gems'] if row else 0
        old_diff = row['diff'] if row else 0
        old_gems_diff = row['gems_diff'] if row and 'gems_diff' in row else 0
        old_seed_time = float(row['last_seed_change']) if row and row['last_seed_change'] else current_time
        
        new_seed = int(data['seed'])
        new_gems = int(data.get('gems', 0))
        
        # คำนวณส่วนต่าง (Diff)
        diff_seed = new_seed - old_seed
        diff_gems = new_gems - old_gems
        
        # ถ้าไม่มีการเปลี่ยนแปลง ให้ใช้วันเวลาเดิม
        if new_seed != old_seed:
            last_chg = current_time
        else:
            last_chg = old_seed_time
            
        # ถ้าค่าลดลง (เช่น รีเกม) ให้ใช้ค่า Diff เดิมไปก่อน หรือเป็น 0
        if diff_seed <= 0: diff_seed = old_diff
        if diff_gems <= 0: diff_gems = old_gems_diff
            
        is_raff = 1 if data.get('raff') else 0
        is_lawn = 1 if data.get('lawn') else 0

        # อัปเดตข้อมูลลง Database
        cur.execute("""
            INSERT INTO users (id, device, username, seed, gems, diff, gems_diff, raff, lawn, last_update, last_seed_change, game) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) 
            ON CONFLICT (id) DO UPDATE SET 
            seed = EXCLUDED.seed, 
            gems = EXCLUDED.gems, 
            diff = EXCLUDED.diff, 
            gems_diff = EXCLUDED.gems_diff,
            raff = EXCLUDED.raff, 
            lawn = EXCLUDED.lawn, 
            last_update = EXCLUDED.last_update, 
            last_seed_change = EXCLUDED.last_seed_change, 
            game = EXCLUDED.game
        """, (uid, data['device'], data['username'], new_seed, new_gems, diff_seed, diff_gems, is_raff, is_lawn, current_time, last_chg, game_name))
        
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e: 
        return jsonify({"status": "error", "msg": str(e)}), 400

@app.route('/reset_admin_password_1234') 
def reset_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM users")
        conn.commit()
        cur.close()
        conn.close()
        return "<h1>✅ Database Cleared</h1><a href='/'>Back</a>"
    except Exception as e: 
        return f"Error: {e}"

if __name__ == '__main__': 
    app.run()