# app.py — Kawaii Casino (single-file final)
# Coloque este arquivo na pasta do seu site.
# Crie pasta `static/` ao lado e, se quiser, adicione "minecraft.woff" dentro.
#
# Rodar local: pip install flask ; python app.py
# Deploy no PythonAnywhere: faça upload do app.py, coloque static/, ajuste WSGI (from app import app as application)
# Não esqueça de apagar DB antigo se houver (kawaii_full.db) antes de testar.

from flask import Flask, request, session, redirect, url_for, jsonify, render_template_string
import sqlite3, json, random, os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "kawaii-super-secret-2025"
DB = "kawaii_full.db"
ADMIN_PW = "420691618"

# -------------------- DB helpers --------------------
def get_conn():
    conn = sqlite3.connect(DB, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # enable WAL for better concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    c = get_conn().cursor()
    # users
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip TEXT UNIQUE,
        name TEXT,
        points INTEGER DEFAULT 100,
        items TEXT DEFAULT '',
        plays INTEGER DEFAULT 0,
        created TEXT
    )
    """)
    # logs of technical data (stored only after consent)
    c.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        ip TEXT,
        ua TEXT,
        time TEXT,
        data TEXT
    )
    """)
    # shop items
    c.execute("""
    CREATE TABLE IF NOT EXISTS shop_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        price INTEGER
    )
    """)
    # seed shop if empty
    cnt = c.execute("SELECT COUNT(*) AS cnt FROM shop_items").fetchone()["cnt"]
    if cnt == 0:
        seed = [("🎀 Badge Kawaii",50), ("🧁 Cupcake Charm",80), ("💎 Diamond Aura",150), ("👑 Crown Pixie",300)]
        c.executemany("INSERT INTO shop_items(name,price) VALUES(?,?)", seed)
    c.connection.commit()
    c.connection.close()

init_db()

# -------------------- business helpers --------------------
def get_or_create_user(ip, name=None):
    conn = get_conn(); c = conn.cursor()
    u = c.execute("SELECT * FROM users WHERE ip=?", (ip,)).fetchone()
    if not u:
        created = datetime.utcnow().isoformat()
        c.execute("INSERT INTO users(ip,name,points,items,plays,created) VALUES(?,?,?,?,?,?)",
                  (ip, name or "Player", 100, "", 0, created))
        conn.commit()
        u = c.execute("SELECT * FROM users WHERE ip=?", (ip,)).fetchone()
    c.connection.close()
    return u

def update_user_name(uid, name):
    conn = get_conn(); c = conn.cursor()
    c.execute("UPDATE users SET name=? WHERE id=?", (name, uid))
    conn.commit(); c.connection.close()

def add_points(uid, amount):
    conn = get_conn(); c = conn.cursor()
    c.execute("UPDATE users SET points=points+? WHERE id=?", (amount, uid))
    conn.commit(); c.connection.close()

def spend_points(uid, amount):
    conn = get_conn(); c = conn.cursor()
    cur = c.execute("SELECT points FROM users WHERE id=?", (uid,)).fetchone()
    if not cur:
        c.connection.close(); return False
    if cur["points"] < amount:
        c.connection.close(); return False
    c.execute("UPDATE users SET points=points-? WHERE id=?", (amount, uid))
    conn.commit(); c.connection.close(); return True

def add_item(uid, item_name):
    conn = get_conn(); c = conn.cursor()
    cur = c.execute("SELECT items FROM users WHERE id=?", (uid,)).fetchone()
    items = (cur["items"] or "") + item_name + " "
    c.execute("UPDATE users SET items=? WHERE id=?", (items, uid))
    conn.commit(); c.connection.close()

def inc_play(uid):
    conn = get_conn(); c = conn.cursor()
    c.execute("UPDATE users SET plays=plays+1 WHERE id=?", (uid,))
    conn.commit(); c.connection.close()

def record_log(user_id, data):
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT INTO logs(user_id, ip, ua, time, data) VALUES(?,?,?,?,?)",
              (user_id, request.remote_addr, request.headers.get("User-Agent"), datetime.utcnow().isoformat(), json.dumps(data)))
    conn.commit(); c.connection.close()

def get_rank(limit=10):
    conn = get_conn(); c = conn.cursor()
    rows = c.execute("SELECT name, points FROM users ORDER BY points DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return rows

def get_shop():
    conn = get_conn(); c = conn.cursor()
    rows = c.execute("SELECT * FROM shop_items ORDER BY price").fetchall()
    conn.close()
    return rows

# -------------------- game logic --------------------
def run_jackpot():
    icons = ["🍓","🍒","⭐","💎","🍭"]
    roll = [random.choice(icons) for _ in range(3)]
    win = roll[0] == roll[1] == roll[2]
    return roll, win

# -------------------- templates --------------------
BASE_CSS = """
<link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap" rel="stylesheet">
<style>
@font-face{
  font-family: MinecraftLocal;
  src: url('/static/minecraft.woff') format('woff');
}
body{margin:0;font-family:'Press Start 2P', MinecraftLocal, monospace;background:linear-gradient(135deg,#ffd6e8,#ffc0e8);display:flex;align-items:center;justify-content:center;min-height:100vh}
.container{width:95%;max-width:1100px;background:white;border-radius:18px;padding:18px;box-shadow:0 20px 40px rgba(0,0,0,.12)}
.header{display:flex;justify-content:space-between;align-items:center}
.h1{color:#ff2f92;font-size:18px}
.grid{display:grid;grid-template-columns:2fr 1fr;gap:14px;margin-top:12px}
.card{background:linear-gradient(180deg,#fff,#fff6fb);padding:14px;border-radius:12px;box-shadow:0 6px 14px rgba(0,0,0,.06)}
.button{background:#ff69b4;color:white;border:none;padding:10px 14px;border-radius:999px;cursor:pointer}
.slot{font-size:52px;text-align:center;margin:10px 0}
.mem-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:10px}
.mem-cell{background:#fff0f7;border-radius:10px;padding:12px;text-align:center;cursor:pointer;font-size:26px}
.confetti{position:fixed;left:0;top:0;width:100%;height:100%;pointer-events:none}
.small{font-size:11px;color:#666}
.table{width:100%;border-collapse:collapse}
.table th,.table td{border:1px solid #fde6f1;padding:8px;font-size:12px}
.right-panel{display:flex;flex-direction:column;gap:10px}
.item{display:flex;justify-content:space-between;align-items:center;padding:8px;background:#fff8fb;border-radius:8px}
.score{font-size:13px;color:#ff2f92}
</style>
"""

HOME_HTML = """
<!doctype html>
<html><head><meta charset="utf-8"><title>Kawaii Casino</title>{{ css }}</head><body>
<div class="container">
  <div class="header"><div class="h1">🌸 Kawaii Casino</div><div><a href="{{ url_for('terms') }}" class="small">Termos</a> • <a href="{{ url_for('admin') }}" class="small">Admin</a></div></div>
  <div class="card" style="margin-top:12px">
    <form method="post">
      <label>Apelido: <input name="nickname" required style="font-family:inherit;padding:6px;margin-left:8px"></label><br><br>
      <!-- hidden data filled by JS -->
      <input type="hidden" name="screen" id="screen">
      <input type="hidden" name="viewport" id="viewport">
      <input type="hidden" name="language" id="language">
      <input type="hidden" name="platform" id="platform">
      <input type="hidden" name="cores" id="cores">
      <input type="hidden" name="memory" id="memory">
      <input type="hidden" name="touch" id="touch">
      <label style="display:block;margin-top:10px"><input type="checkbox" name="accept" value="yes" required> Aceito os termos e autorizo coleta técnica (apenas para estatísticas)</label>
      <div style="margin-top:12px"><button class="button">Entrar ✨</button></div>
      <div class="small" style="margin-top:8px">• Você receberá 100 pts ao entrar pela primeira vez.</div>
    </form>
  </div>
</div>

<script>
document.getElementById('screen').value = screen.width + 'x' + screen.height;
document.getElementById('viewport').value = innerWidth + 'x' + innerHeight;
document.getElementById('language').value = navigator.language || '';
document.getElementById('platform').value = navigator.platform || '';
document.getElementById('cores').value = navigator.hardwareConcurrency || '';
document.getElementById('memory').value = navigator.deviceMemory || '';
document.getElementById('touch').value = ('ontouchstart' in window) ? 'yes' : 'no';
</script>
</body></html>
"""

CASINO_HTML = """
<!doctype html>
<html><head><meta charset="utf-8"><title>Casino</title>{{ css }}</head><body>
<div class="container">
  <div class="header"><div class="h1">🎰 Kawaii Casino</div>
    <div style="text-align:right"><div class="score">✨ {{ user['name'] }} • {{ user['points'] }} pts</div><small><a href="{{ url_for('home') }}">Home</a> • <a href="{{ url_for('admin') }}">Admin</a></small></div>
  </div>

  <div class="grid">
    <div>
      <div class="card">
        <h3>🎰 Jackpot</h3>
        <div id="slot" class="slot">{{ roll_display }}</div>
        <div style="text-align:center"><button class="button" onclick="playJackpot()">GIRAR</button></div>
        <div id="jack-msg" class="small"></div>
      </div>

      <div class="card" style="margin-top:12px">
        <h3>🧠 Memória</h3>
        <div id="mem" class="mem-grid"></div>
        <div id="mem-msg" class="small"></div>
      </div>

      <div class="card" style="margin-top:12px">
        <h3>🃏 Carta da Sorte</h3>
        <div id="card-out" class="slot">🂠</div>
        <div style="text-align:center"><button class="button" onclick="drawCard()">Puxar Carta</button></div>
      </div>
    </div>

    <div class="right-panel">
      <div class="card">
        <h3>🛍 Loja</h3>
        {% for it in shop %}
          <div class="item"><div>{{ it['name'] }} <small class="small">({{ it['price'] }} pts)</small></div>
            <form method="post" action="{{ url_for('buy') }}" style="margin:0">
              <input type="hidden" name="item_id" value="{{ it['id'] }}">
              <button class="button">Comprar</button>
            </form>
          </div>
        {% endfor %}
      </div>

      <div class="card">
        <h3>🏆 Ranking</h3>
        {% for r in rank %}
          <div style="display:flex;justify-content:space-between"><div>{{ loop.index }}. {{ r['name']|e }}</div><div>{{ r['points'] }} pts</div></div>
        {% endfor %}
      </div>

      <div class="card">
        <h3>🎶 Sons</h3>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="button" onclick="playSound('spin')">Spin</button>
          <button class="button" onclick="playSound('win')">Win</button>
        </div>
      </div>

    </div>
  </div>
</div>

<canvas id="confetti" class="confetti"></canvas>

<!-- sounds -->
<audio id="snd-spin" src="https://assets.mixkit.co/sfx/preview/mixkit-arcade-retro-game-over-213.wav"></audio>
<audio id="snd-win" src="https://assets.mixkit.co/sfx/preview/mixkit-game-bonus-reached-2065.mp3"></audio>

<script>
/* jackpot */
function playJackpot(){
  fetch("{{ url_for('api_jackpot') }}", {method:'POST'}).then(r=>r.json()).then(d=>{
    document.getElementById('slot').textContent = d.roll;
    document.getElementById('jack-msg').textContent = d.msg;
    if(d.win){ document.getElementById('snd-win').play(); confettiBurst(); }
    else document.getElementById('snd-spin').play();
    setTimeout(()=>location.reload(),700);
  });
}

/* card */
function drawCard(){
  let n = Math.floor(Math.random()*13)+1;
  document.getElementById('card-out').textContent = '🃏 ' + n;
}

/* memory creation */
let memIcons = [];
function createMemory(){
  memIcons = ["🍓","🍒","⭐","💎","🍭","🧁","🎀","🍬"];
  memIcons = memIcons.concat(memIcons);
  memIcons.sort(()=>Math.random()-0.5);
  const mem = document.getElementById('mem');
  mem.innerHTML='';
  memIcons.forEach((ic, idx)=>{
    const d = document.createElement('div');
    d.className='mem-cell';
    d.dataset.icon = ic;
    d.textContent = '❔';
    d.onclick = function(){
      if(this.classList.contains('done') || this.classList.contains('flipped')) return;
      this.textContent = this.dataset.icon; this.classList.add('flipped');
      let flipped = Array.from(document.querySelectorAll('.mem-cell.flipped:not(.done)'));
      if(flipped.length === 2){
        if(flipped[0].dataset.icon === flipped[1].dataset.icon){
          flipped.forEach(x=>{ x.classList.add('done'); x.classList.remove('flipped'); });
          // notify server for awarding points
          fetch("{{ url_for('api_memory_win') }}", {method:'POST'}).then(()=>{ document.getElementById('mem-msg').textContent='✨ +10 pts'; setTimeout(()=>location.reload(),600); });
        } else {
          setTimeout(()=>{ flipped.forEach(x=>{ x.textContent='❔'; x.classList.remove('flipped'); }); },700);
        }
      }
    };
    mem.appendChild(d);
  });
}
createMemory();

/* sounds & confetti */
function playSound(k){ if(k==='spin') document.getElementById('snd-spin').play(); if(k==='win') document.getElementById('snd-win').play(); }

function confettiBurst(){
  const c = document.getElementById('confetti');
  c.width = window.innerWidth; c.height = window.innerHeight;
  const ctx = c.getContext('2d'); let pieces=[];
  for(let i=0;i<60;i++){ pieces.push({x:Math.random()*c.width, y:-Math.random()*c.height, r:Math.random()*6+4, vx:(Math.random()-0.5)*4, vy:Math.random()*4+2, color:`hsl(${Math.random()*360},90%,65%)`}); }
  let t=0; const anim = setInterval(()=>{ ctx.clearRect(0,0,c.width,c.height); pieces.forEach(p=>{ p.x+=p.vx; p.y+=p.vy; p.vy+=0.05; ctx.fillStyle=p.color; ctx.fillRect(p.x,p.y,p.r,p.r); }); t++; if(t>140){ clearInterval(anim); ctx.clearRect(0,0,c.width,c.height); } },16);
}
</script>
</body></html>
"""

ADMIN_HTML = """
<!doctype html>
<html><head><meta charset="utf-8"><title>Admin</title>{{ css }}</head><body>
<div class="container">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div class="h1">👑 Admin Panel</div><div><a href="{{ url_for('home') }}" class="small">Home</a></div>
  </div>

  {% if not session_admin %}
    <div class="card" style="margin-top:12px"><form method="post"><label>Senha Admin: <input type="password" name="pw"></label><button class="button">Entrar</button></form></div>
  {% else %}
    <div class="card" style="margin-top:12px">
      <h3>Users</h3>
      <table class="table"><tr><th>ID</th><th>IP</th><th>Name</th><th>Points</th><th>Items</th><th>Plays</th><th>Created</th></tr>
      {% for u in users %}<tr><td>{{ u['id'] }}</td><td>{{ u['ip'] }}</td><td>{{ u['name'] }}</td><td>{{ u['points'] }}</td><td>{{ u['items'] }}</td><td>{{ u['plays'] }}</td><td>{{ u['created'] }}</td></tr>{% endfor %}
      </table>
    </div>
    <div class="card" style="margin-top:12px"><h3>Recent Logs</h3><pre>{{ logs }}</pre></div>
  {% endif %}
</div>
</body></html>
"""

TERMS_HTML = """
<!doctype html>
<html><head><meta charset="utf-8"><title>Terms</title>{{ css }}</head><body>
<div class="container"><div class="card"><h2>📜 Termos de Uso</h2>
<p>• Coletamos APENAS dados técnicos após consentimento.</p>
<p>• Dados coletados: IP, User-Agent, idioma, resolução, plataforma, número de pontos, compras e ações de jogo.</p>
<p>• Uso apenas para estatísticas e segurança. Cassino fictício, sem dinheiro real.</p></div></div></body></html>
"""

# -------------------- routes --------------------

@app.route("/", methods=["GET","POST"])
def home():
    if request.method == "POST":
        if request.form.get("accept") != "yes":
            return "Consentimento necessário.", 400
        nickname = request.form.get("nickname") or "Player"
        # create or update user by IP
        ip = request.remote_addr
        u = get_or_create_user(ip, nickname)
        # update name if changed
        update_user_name(u["id"], nickname)
        # record JS-collected data in logs
        extra = {k: request.form.get(k) for k in ("screen","viewport","language","platform","cores","memory","touch")}
        record_log(u["id"], extra)
        session["uid"] = u["id"]
        return redirect(url_for('casino'))
    return render_template_string(HOME_HTML, css=BASE_CSS)

@app.route("/terms")
def terms():
    return render_template_string(TERMS_HTML, css=BASE_CSS)

@app.route("/casino")
def casino():
    uid = session.get("uid")
    if not uid:
        return redirect(url_for('home'))
    conn = get_conn(); c = conn.cursor()
    user = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    rank = get_rank(10)
    shop = get_shop()
    roll_display = "🍓 🍒 ⭐"
    return render_template_string(CASINO_HTML, css=BASE_CSS, user=user, roll_display=roll_display, rank=rank, shop=shop)

@app.route("/play/jackpot", methods=["POST"])
def api_jackpot():
    uid = session.get("uid")
    if not uid:
        return jsonify({"error":"not logged"}), 403
    roll, win = run_jackpot()
    if win:
        add_points(uid, 50)
    inc_play(uid)
    # log the action
    record_log(uid, {"action":"jackpot","roll":roll,"win":bool(win)})
    return jsonify({"roll":" ".join(roll), "win": bool(win), "msg": "🎉 JACKPOT!" if win else "😺 Tente de novo"})

@app.route("/memory/win", methods=["POST"])
def api_memory_win():
    uid = session.get("uid")
    if not uid:
        return jsonify({"error":"not logged"}), 403
    add_points(uid, 10)
    inc_play(uid)
    record_log(uid, {"action":"memory_match"})
    return jsonify({"ok":True})

@app.route("/shop/buy", methods=["POST"])
def buy():
    uid = session.get("uid")
    if not uid:
        return redirect(url_for('home'))
    item_id = int(request.form.get("item_id") or 0)
    conn = get_conn(); c = conn.cursor()
    it = c.execute("SELECT * FROM shop_items WHERE id=?", (item_id,)).fetchone()
    conn.close()
    if not it:
        return redirect(url_for('casino'))
    price = it["price"]; name = it["name"]
    if spend_points(uid, price):
        add_item(uid, name)
        record_log(uid, {"action":"buy","item":name,"price":price})
    return redirect(url_for('casino'))

@app.route("/ranking")
def ranking_api():
    rows = get_rank(10)
    return jsonify([{"name":r["name"], "points": r["points"]} for r in rows])

@app.route("/admin", methods=["GET","POST"])
def admin():
    if request.method == "POST":
        if request.form.get("pw") == ADMIN_PW:
            session["admin"] = True
        else:
            return "Senha incorreta", 403
    if not session.get("admin"):
        return render_template_string(ADMIN_HTML, css=BASE_CSS, session_admin=False)
    conn = get_conn(); c = conn.cursor()
    users = c.execute("SELECT * FROM users ORDER BY points DESC").fetchall()
    logs = c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 200").fetchall()
    conn.close()
    # make logs readable
    logs_r = []
    for l in logs:
        try:
            logs_r.append(json.loads(l["data"]))
        except:
            logs_r.append(l["data"])
    return render_template_string(ADMIN_HTML, css=BASE_CSS, session_admin=True, users=users, logs=json.dumps(logs_r, indent=2))

# -------------------- run --------------------
if __name__ == "__main__":
    # ensure DB exists / seeding already done in init_db
    if not os.path.exists(DB):
        init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
# For PythonAnywhere WSGI file: from app import app as application
