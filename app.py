from flask import Flask, render_template, request, jsonify, session, redirect
from transformers import pipeline
import difflib, re, numpy as np, os, sqlite3, json
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# ---------------- APP ----------------
app = Flask(__name__)
app.secret_key = "speaksmart_secret_key"

# ---------------- DATABASE ----------------
def get_db():
    conn = sqlite3.connect("speaksmart.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# ---------------- DB INIT ----------------
with get_db() as db:
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            original_text TEXT,
            corrected_text TEXT,
            scores TEXT,
            confidence INTEGER,
            emotion TEXT,
            timeline TEXT,
            created_at TEXT
        )
    """)

# ---------------- AUTH DECORATOR ----------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper

# ---------------- GRAMMAR MODEL ----------------
grammar_model = pipeline(
    "text2text-generation",
    model="prithivida/grammar_error_correcter_v1"
)

# ===================== GRAMMAR ENGINE =====================

def clean_text(text):
    text = re.sub(r"\s+", " ", text)

    replacements = {
        r"\bmarried with\b": "married to",
        r"\bnews are\b": "news is",
        r"\bi goes\b": "i went",
        r"\bi am went\b": "i went",
        r"\bi was available by tomorrow\b": "i will be available tomorrow",
        r"\bmeet me by tomorrow\b": "meet me tomorrow",
        r"\bi was like\b": "i felt that",
        r"\byou know\b": "",
        r"\bactually\b": ""
    }

    for k, v in replacements.items():
        text = re.sub(k, v, text, flags=re.I)

    return text.strip()

def split_sentences(text):
    return re.split(r'(?<=[.!?])\s+', text)

def remove_duplicate_sentences(text):
    seen = set()
    final = []
    for s in split_sentences(text):
        key = s.lower().strip()
        if key and key not in seen:
            seen.add(key)
            final.append(s)
    return " ".join(final)

def smart_semantic_correction(text):
    rules = {
        r"\bi was available tomorrow\b": "I will be available tomorrow",
        r"\bi was available by tomorrow\b": "I will be available tomorrow",
        r"\bi was like why\b": "I wondered why",
        r"\bso better\b": "so please",
        r"\bdon't come to me\b": "please do not approach me unnecessarily",
        r"\band\.$": "."
    }

    for k, v in rules.items():
        text = re.sub(k, v, text, flags=re.I)

    return text

def restore_punctuation(text):
    sentences = split_sentences(text)
    fixed = []
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        s = s[0].upper() + s[1:]
        if not s.endswith(('.', '!', '?')):
            s += '.'
        fixed.append(s)
    return " ".join(fixed)

def highlight_diff(orig, corr):
    o, c = orig.split(), corr.split()
    sm = difflib.SequenceMatcher(a=o, b=c)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out += o[i1:i2]
        else:
            out.append(f"<span style='color:red'>{' '.join(c[j1:j2])}</span>")
    return " ".join(out)

def scores(orig, corr):
    return {
        "grammar": 90,
        "fluency": 85,
        "repetition": 92
    }

# ================= AUTH ROUTES =================
@app.route("/")
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        with get_db() as db:
            user = db.execute(
                "SELECT * FROM users WHERE email=?", (email,)
            ).fetchone()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["email"] = user["email"]
            return redirect("/dashboard")

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        try:
            with get_db() as db:
                db.execute(
                    "INSERT INTO users (email, password) VALUES (?,?)",
                    (
                        request.form["email"],
                        generate_password_hash(request.form["password"])
                    )
                )
            return redirect("/login")
        except:
            return render_template("signup.html", error="Email already exists")

    return render_template("signup.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ================= MAIN =================
@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

@app.route("/sitting")
@login_required
def sitting():
    return render_template("sitting.html")

# ================= SAVE SESSION =================
@app.route("/save_session", methods=["POST"])
@login_required
def save_session():
    data = request.json
    with get_db() as db:
        cur = db.execute("""
            INSERT INTO sessions
            (user_id, original_text, corrected_text, scores, confidence, emotion, timeline, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            data["original"],
            data["corrected"],
            json.dumps(data["scores"]),
            data["confidence"],
            data["emotion"],
            json.dumps(data.get("timeline", [])),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
    return jsonify({"session_id": cur.lastrowid})

# ================= GET SESSIONS =================
@app.route("/get_sessions")
@login_required
def get_sessions():
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM sessions WHERE user_id=? ORDER BY created_at ASC",
            (session["user_id"],)
        ).fetchall()

    sessions = [dict(r) for r in rows]

    improvement = 0
    if len(sessions) > 1:
        improvement = round(
            ((sessions[-1]["confidence"] - sessions[0]["confidence"]) /
             max(sessions[0]["confidence"], 1)) * 100
        )

    week_ago = datetime.now() - timedelta(days=7)
    weekly = [
        s["confidence"] for s in sessions
        if datetime.fromisoformat(s["created_at"]) >= week_ago
    ]

    return jsonify({
        "sessions": sessions[::-1],
        "improvement": improvement,
        "weekly_avg": round(sum(weekly)/len(weekly)) if weekly else 0
    })

# ================= REPORT =================
@app.route("/report")
@login_required
def report():
    sid = request.args.get("id")
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM sessions WHERE id=? AND user_id=?",
            (sid, session["user_id"])
        ).fetchone()

    if not row:
        return render_template("report.html", session=None)

    s = dict(row)
    s["scores"] = json.loads(s["scores"])
    s["timeline"] = json.loads(s["timeline"])
    s["email"] = session["email"]

    return render_template("report.html", session=s)

# ================= TEXT PROCESS (CORRECTED) =================
@app.route("/process_text", methods=["POST"])
def process_text():
    raw_text = request.json["text"]          # ✅ untouched
    working_text = clean_text(raw_text)      # ✅ copy only

    sentences = split_sentences(working_text)
    corrected_parts = []

    for s in sentences:
        try:
            out = grammar_model(
                s,
                max_new_tokens=64,
                do_sample=False
            )[0]["generated_text"]
            corrected_parts.append(out)
        except:
            corrected_parts.append(s)

    corrected = " ".join(corrected_parts)
    corrected = clean_text(corrected)
    corrected = smart_semantic_correction(corrected)
    corrected = remove_duplicate_sentences(corrected)
    corrected = restore_punctuation(corrected)

    return jsonify({
        "original": raw_text,                  # ✅ real speech
        "corrected": corrected,
        "highlighted": highlight_diff(raw_text, corrected),
        "scores": scores(raw_text, corrected)
    })

# ================= VOICE =================
@app.route("/analyze_voice_secure", methods=["POST"])
def analyze_voice_secure():
    confidence = np.random.randint(65, 95)
    emotion = "confident" if confidence > 75 else "nervous"
    return jsonify({"confidence": confidence, "voiceEmotion": emotion})

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=False)
