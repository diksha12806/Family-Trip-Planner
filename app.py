import os
import sqlite3
from flask import Flask, g, render_template, request, redirect, url_for, jsonify, flash, send_from_directory, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import hashlib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database', 'app.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'images')
ALLOWED_EXT = {'png','jpg','jpeg','gif','mp4'}
SECRET_KEY = os.environ.get('FTP_SECRET') or 'change-me-in-prod'

app = Flask(__name__)
app.config.update(UPLOAD_FOLDER=UPLOAD_FOLDER, SECRET_KEY=SECRET_KEY)

# --- Database helpers ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    if not os.path.exists(os.path.dirname(DB_PATH)):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    # Create tables
    cur.executescript('''
    CREATE TABLE IF NOT EXISTS admin_users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT);
    CREATE TABLE IF NOT EXISTS destinations (id INTEGER PRIMARY KEY, title TEXT, category TEXT, description TEXT, image TEXT, budget INTEGER, season TEXT, rating REAL);
    CREATE TABLE IF NOT EXISTS family_members (id INTEGER PRIMARY KEY, name TEXT, relationship TEXT, age INTEGER, prefs TEXT, photo TEXT);
    CREATE TABLE IF NOT EXISTS itinerary (id INTEGER PRIMARY KEY, trip_id INTEGER, day INTEGER, activity TEXT, time TEXT, notes TEXT);
    CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY, category TEXT, amount REAL, date TEXT, notes TEXT);
    CREATE TABLE IF NOT EXISTS journals (id INTEGER PRIMARY KEY, title TEXT, date TEXT, location TEXT, content TEXT);
    CREATE TABLE IF NOT EXISTS contact_messages (id INTEGER PRIMARY KEY, name TEXT, email TEXT, message TEXT, date TEXT);
    CREATE TABLE IF NOT EXISTS gallery (id INTEGER PRIMARY KEY, filename TEXT, category TEXT, caption TEXT, uploaded_at TEXT);
    CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, created_at TEXT DEFAULT (datetime('now')));
    CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, destination TEXT, start_date TEXT, end_date TEXT, budget REAL, notes TEXT, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, image_path TEXT, description TEXT, created_at TEXT DEFAULT (datetime('now')), FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
    ''')
    # Seed admin
    try:
        cur.execute('INSERT INTO admin_users (username,password_hash) VALUES (?,?)', ('admin', hashlib.sha256('admin123'.encode()).hexdigest()))
    except Exception:
        pass
    # Seed sample destinations
    try:
        cur.execute('INSERT INTO destinations (title,category,description,image,budget,season,rating) VALUES (?,?,?,?,?,?,?)',
                    ('Sunny Beach','Beaches','Family-friendly beach with calm waters.','/static/images/beach.jpg',1200,'Summer',4.7))
        cur.execute('INSERT INTO destinations (title,category,description,image,budget,season,rating) VALUES (?,?,?,?,?,?,?)',
                    ('Misty Mountains','Mountains','Scenic mountain retreat for families.','/static/images/mountains.jpg',1500,'Spring',4.8))
    except Exception:
        pass
    db.commit()
    db.close()

# Initialize DB when starting
init_db()

# --- Database diagnostics ---
def show_tables():
    """Print all SQLite tables and row counts."""
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = cur.fetchall()
    print("\n" + "="*60)
    print("DATABASE TABLES")
    print("="*60)
    for table in tables:
        table_name = table[0]
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cur.fetchone()[0]
            print(f"  [OK] {table_name:<28} ({count} rows)")
        except Exception as e:
            print(f"  [ERROR] {table_name:<26} {str(e)}")
    print("="*60 + "\n")
    db.close()

# Print tables on startup
show_tables()

# --- Helpers ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED_EXT

# --- Routes ---
@app.route('/')
def index():
    db = get_db()
    dests = db.execute('SELECT * FROM destinations').fetchall()
    return render_template('index.html', destinations=dests)

@app.route('/destination/<int:id>')
def destination_detail(id):
    db = get_db()
    dest = db.execute('SELECT * FROM destinations WHERE id=?',(id,)).fetchone()
    return render_template('destination_detail.html', dest=dest)

@app.route('/planner', methods=['GET','POST'])
def planner():
    if request.method == 'POST':
        data = request.form
        # Simple intelligent suggestion mock
        dest = data.get('destination')
        start = data.get('start_date')
        end = data.get('end_date')
        members = int(data.get('members') or 1)
        budget = int(data.get('budget') or 1000)
        days = max(1, (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days + 1) if start and end else 3
        itinerary = []
        for d in range(days):
            itinerary.append({'day': d+1, 'activities': [f'Explore {dest} - family activity {i+1}' for i in range(3)]})
        est_budget = budget
        tips = [f'Pack for {days} days', 'Carry sunscreen', 'Book family rooms in advance']
        return jsonify({'itinerary': itinerary,'est_budget': est_budget,'tips': tips})
    return render_template('planner.html')

# Itinerary CRUD
@app.route('/api/itinerary', methods=['GET','POST','PUT','DELETE'])
def api_itinerary():
    db = get_db()
    if request.method == 'GET':
        rows = db.execute('SELECT * FROM itinerary').fetchall()
        return jsonify([dict(r) for r in rows])
    if request.method == 'POST':
        payload = request.json
        db.execute('INSERT INTO itinerary (trip_id,day,activity,time,notes) VALUES (?,?,?,?,?)',(
            payload.get('trip_id'), payload.get('day'), payload.get('activity'), payload.get('time'), payload.get('notes')
        ))
        db.commit()
        return jsonify({'status':'ok'})
    if request.method == 'PUT':
        payload = request.json
        db.execute('UPDATE itinerary SET activity=?,time=?,notes=? WHERE id=?',(
            payload.get('activity'), payload.get('time'), payload.get('notes'), payload.get('id')
        ))
        db.commit()
        return jsonify({'status':'ok'})
    if request.method == 'DELETE':
        payload = request.json
        db.execute('DELETE FROM itinerary WHERE id=?',(payload.get('id'),))
        db.commit()
        return jsonify({'status':'ok'})

# Family members
@app.route('/api/family', methods=['GET','POST','PUT','DELETE'])
def api_family():
    db = get_db()
    if request.method == 'GET':
        rows = db.execute('SELECT * FROM family_members').fetchall(); return jsonify([dict(r) for r in rows])
    if request.method == 'POST':
        name = request.form.get('name')
        rel = request.form.get('relationship')
        age = request.form.get('age')
        prefs = request.form.get('prefs')
        photo = None
        if 'photo' in request.files:
            f = request.files['photo']
            if allowed_file(f.filename):
                fname = secure_filename(f.filename)
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                photo = '/static/images/' + fname
        db.execute('INSERT INTO family_members (name,relationship,age,prefs,photo) VALUES (?,?,?,?,?)',(name,rel,age,prefs,photo))
        db.commit(); return redirect(url_for('index'))
    if request.method == 'PUT':
        payload = request.json
        db.execute('UPDATE family_members SET name=?,relationship=?,age=?,prefs=? WHERE id=?',(
            payload.get('name'),payload.get('relationship'),payload.get('age'),payload.get('prefs'),payload.get('id')
        ))
        db.commit(); return jsonify({'status':'ok'})
    if request.method == 'DELETE':
        payload = request.json
        db.execute('DELETE FROM family_members WHERE id=?',(payload.get('id'),))
        db.commit(); return jsonify({'status':'ok'})

# Expenses
@app.route('/api/expenses', methods=['GET','POST','PUT','DELETE'])
def api_expenses():
    db = get_db()
    if request.method == 'GET':
        rows = db.execute('SELECT * FROM expenses').fetchall(); return jsonify([dict(r) for r in rows])
    if request.method == 'POST':
        p = request.json
        db.execute('INSERT INTO expenses (category,amount,date,notes) VALUES (?,?,?,?)',(p.get('category'),p.get('amount'),p.get('date'),p.get('notes')))
        db.commit(); return jsonify({'status':'ok'})
    if request.method == 'PUT':
        p = request.json
        db.execute('UPDATE expenses SET category=?,amount=?,date=?,notes=? WHERE id=?',(p.get('category'),p.get('amount'),p.get('date'),p.get('notes'),p.get('id')))
        db.commit(); return jsonify({'status':'ok'})
    if request.method == 'DELETE':
        p = request.json
        db.execute('DELETE FROM expenses WHERE id=?',(p.get('id'),))
        db.commit(); return jsonify({'status':'ok'})

# Journals
@app.route('/api/journals', methods=['GET','POST','DELETE'])
def api_journals():
    db = get_db()
    if request.method == 'GET':
        rows = db.execute('SELECT * FROM journals ORDER BY date DESC').fetchall(); return jsonify([dict(r) for r in rows])
    if request.method == 'POST':
        p = request.json
        db.execute('INSERT INTO journals (title,date,location,content) VALUES (?,?,?,?)',(p.get('title'),p.get('date'),p.get('location'),p.get('content')))
        db.commit(); return jsonify({'status':'ok'})
    if request.method == 'DELETE':
        p = request.json
        db.execute('DELETE FROM journals WHERE id=?',(p.get('id'),))
        db.commit(); return jsonify({'status':'ok'})

# Gallery upload
@app.route('/api/gallery', methods=['GET','POST','DELETE'])
def api_gallery():
    db = get_db()
    if request.method == 'GET':
        rows = db.execute('SELECT * FROM gallery ORDER BY uploaded_at DESC').fetchall(); return jsonify([dict(r) for r in rows])
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({'error':'no file'}),400
        f = request.files['file']
        cat = request.form.get('category')
        caption = request.form.get('caption')
        if f and allowed_file(f.filename):
            fname = secure_filename(f.filename)
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
            db.execute('INSERT INTO gallery (filename,category,caption,uploaded_at) VALUES (?,?,?,?)',( '/static/images/'+fname,cat,caption, datetime.utcnow().isoformat()))
            db.commit(); return jsonify({'status':'ok'})
        return jsonify({'error':'invalid file'}),400
    if request.method == 'DELETE':
        p = request.json
        db.execute('DELETE FROM gallery WHERE id=?',(p.get('id'),))
        db.commit(); return jsonify({'status':'ok'})

# Contact messages
@app.route('/contact', methods=['GET','POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        db = get_db()
        db.execute('INSERT INTO contact_messages (name,email,message,date) VALUES (?,?,?,?)',(name,email,message, datetime.utcnow().isoformat()))
        db.commit(); flash('Message received. Thank you!')
        return redirect(url_for('index'))
    return render_template('contact.html')

# Admin
@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method=='POST':
        user = request.form.get('username')
        pwd = request.form.get('password')
        db = get_db()
        row = db.execute('SELECT * FROM admin_users WHERE username=?',(user,)).fetchone()
        if row and row['password_hash'] == hashlib.sha256(pwd.encode()).hexdigest():
            session['admin'] = user
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials')
    return render_template('admin/login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    db = get_db()
    stats = {
        'dest_count': db.execute('SELECT COUNT(*) as c FROM destinations').fetchone()['c'],
        'families': db.execute('SELECT COUNT(*) as c FROM family_members').fetchone()['c']
    }
    return render_template('admin/dashboard.html', stats=stats)

# Static video streaming route
@app.route('/videos/<path:filename>')
def videos(filename):
    return send_from_directory(os.path.join(BASE_DIR,'static','videos'), filename)

# --- User auth and trip routes ---
from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        if not (name and email and password):
            flash('All fields required'); return render_template('register.html')
        db = get_db()
        existing = db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
        if existing:
            flash('Email already registered'); return render_template('register.html')
        pw_hash = generate_password_hash(password)
        db.execute('INSERT INTO users (name,email,password) VALUES (?,?,?)',(name,email,pw_hash))
        db.commit()
        user = db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            return redirect(url_for('dashboard'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('user_name', None)
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    trips = db.execute('SELECT * FROM trips WHERE user_id=? ORDER BY start_date DESC',(session['user_id'],)).fetchall()
    memories = db.execute('SELECT * FROM memories WHERE user_id=? ORDER BY created_at DESC LIMIT 6',(session['user_id'],)).fetchall()
    return render_template('dashboard.html', trips=trips, memories=memories)

@app.route('/add-trip', methods=['GET','POST'])
@login_required
def add_trip():
    if request.method == 'POST':
        dest = request.form.get('destination')
        start = request.form.get('start_date')
        end = request.form.get('end_date')
        budget = request.form.get('budget')
        notes = request.form.get('notes')
        db = get_db()
        db.execute('INSERT INTO trips (user_id,destination,start_date,end_date,budget,notes) VALUES (?,?,?,?,?,?)',(
            session['user_id'], dest, start, end, budget, notes
        ))
        db.commit()
        return redirect(url_for('view_trips'))
    return render_template('add_trip.html')

@app.route('/view-trips')
@login_required
def view_trips():
    db = get_db()
    rows = db.execute('SELECT * FROM trips WHERE user_id=? ORDER BY start_date DESC',(session['user_id'],)).fetchall()
    return render_template('view_trips.html', trips=rows)

# Database diagnostics route
@app.route('/db-check')
def db_check():
    """Return database status, list of tables, and row counts."""
    try:
        db = sqlite3.connect(DB_PATH)
        cur = db.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        tables = cur.fetchall()
        
        table_info = {}
        for table in tables:
            table_name = table[0]
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cur.fetchone()[0]
                table_info[table_name] = count
            except Exception as e:
                table_info[table_name] = f"ERROR: {str(e)}"
        
        db.close()
        
        return jsonify({
            'status': 'connected',
            'db_path': DB_PATH,
            'tables': table_info,
            'total_tables': len(tables)
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=True)
