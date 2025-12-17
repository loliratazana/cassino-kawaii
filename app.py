# app.py
from flask import Flask, request, session, redirect, url_for, jsonify, render_template_string, abort
import sqlite3, random, json, os
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "kawaii-super-secret-2025")
DB = os.environ.get("KAWAII_DB", "kawaii_full.db")
ADMIN_PW = os.environ.get("ADMIN_PW", "420691618")  # override in env for prod

# -------------------- DB helpers --------------------
def get_conn():
    conn = sqlite3.connect(DB, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    c = get_conn().cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip TEXT UNIQUE,
        name TEXT,
        points INTEGER DEFAULT 100,
        items TEXT DEFAULT '',
        plays INTEGER DEFAULT 0,
        created TEXT,
        is_admin INTEGER DEFAULT 0
    )
    """)
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
    c.execute("""
    CREATE TABLE IF NOT EXISTS shop_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        price INTEGER
    )
    """)
    cnt = c.execute("SELECT COUNT(*) AS cnt FROM shop_items").fetchone()["cnt"]
    if cnt == 0:
        seed = [("🎀 Badge Kawaii",50), ("🧁 Cupcake Charm",80), ("💎 Diamond Aura",150), ("👑 Crown Pixie",300)]
        c.executemany("INSERT INTO shop_items(name,price) VALUES(?,?)", seed)
    # ensure admin user exists
    admin_exists = c.execute("SELECT * FROM users WHERE is_admin=1").fetchone()
    if not admin_exists:
        created = datetime.utcnow().isoformat()
        c.execute("INSERT INTO users(ip,name,points,items,plays,created,is_admin) VALUES(?,?,?,?,?,?,?)",
                  ("admin@local", "Admin", 9999, "", 0, created, 1))
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
        record_log(u["id"], {"event":"create_user","name":u["name"]})
    conn.close()
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
        conn.close(); return False
    if cur["points"] < amount:
        conn.close(); return False
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
    try:
        ua = request.headers.get("User-Agent")
        ip = request.remote_addr
    except RuntimeError:
        ua = None; ip = None
    c.execute("INSERT INTO logs(user_id, ip, ua, time, data) VALUES(?,?,?,?,?)",
              (user_id or None, ip, ua, datetime.utcnow().isoformat(), json.dumps(data)))
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

def get_user_by_id(uid):
    conn = get_conn(); c = conn.cursor()
    u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return u

# -------------------- game logic --------------------
def run_jackpot(bet):
    icons = ["🍓","🍒","⭐","💎","🍭"]
    roll = [random.choice(icons) for _ in range(3)]
    win = roll[0] == roll[1] == roll[2]
    payout = int(bet*3) if win else 0
    return roll, win, payout

# -------------------- templates --------------------
BASE_CSS = """
<style>
/* try to load a Minecraft-style pixel font from a public repo (fallback included) */
@font-face {
  font-family: 'Minecraftia';
  src: url('https://raw.githubusercontent.com/avdan/font-minecraft/master/Minecraft.ttf') format('truetype');
  font-weight: normal;
  font-style: normal;
  font-display: swap;
}
@import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');

body{
  margin:0;
  font-family: 'Minecraftia', 'Press Start 2P', monospace;
  background:linear-gradient(135deg,#ffd6e8,#ffc0e8);
  display:flex;justify-content:center;align-items:center;min-height:100vh;transition:0.3s;
}
/* ... rest of styles ... */
.container{width:95%;max-width:1100px;background:white;border-radius:20px;padding:20px;box-shadow:0 20px 40px rgba(0,0,0,.2);animation:fadeIn 1s;}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.h1{color:#ff2f92;font-size:20px;font-weight:bold}
.grid{display:grid;grid-template-columns:2fr 1fr;gap:14px;margin-top:12px}
.card{background:linear-gradient(180deg,#fff,#ffe6f0);padding:14px;border-radius:15px;box-shadow:0 6px 14px rgba(0,0,0,.08);transition:0.2s}
.button{background:#ff69b4;color:white;border:none;padding:10px 14px;border-radius:999px;cursor:pointer;transition:0.2s}
.slot{font-size:48px;text-align:center;margin:10px 0}
.mem-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:10px}
.mem-cell{background:#fff0f7;border-radius:12px;padding:12px;text-align:center;cursor:pointer;font-size:28px;transition:0.3s}
.mem-cell.flipped,.mem-cell.done{background:#ffcced}
.confetti{position:fixed;left:0;top:0;width:100%;height:100%;pointer-events:none}
.small{font-size:12px;color:#666}
.table{width:100%;border-collapse:collapse;margin-top:10px}
.table th,.table td{border:1px solid #fde6f1;padding:8px;font-size:12px}
.right-panel{display:flex;flex-direction:column;gap:10px}
.item{display:flex;justify-content:space-between;align-items:center;padding:8px;background:#fff0f7;border-radius:10px}
.score{font-size:13px;color:#ff2f92;margin-bottom:5px}
.menu{position:relative;display:inline-block}
.menu-content{display:none;position:absolute;right:0;background:#fff0f7;box-shadow:0 6px 12px rgba(0,0,0,.15);border-radius:10px;padding:10px;z-index:10}
.menu:hover .menu-content{display:block}
.avatar-part{width:50px;height:50px;margin:2px;display:inline-block;background:#ffd6e8;border-radius:50%;text-align:center;line-height:50px;font-size:24px;cursor:pointer;transition:0.2s}
.avatar-part:hover{transform:scale(1.2)}
/* loader */
.loader-wrap{display:flex;justify-content:center;align-items:center;min-height:100vh;flex-direction:column}
.loader{width:120px;height:120px;border-radius:50%;background:conic-gradient(#ff7ab3,#ffd6e8,#ff7ab3);animation:spin 2s linear infinite;box-shadow:0 10px 40px rgba(255,110,180,.18)}
@keyframes spin{to{transform:rotate(360deg)}}
.small-note{font-size:12px;color:#99446c;margin-top:12px}
</style>
"""

HOME_HTML = """
<!doctype html>
<html><head><meta charset="utf-8"><title>Entrada Kawaii</title>{{ css }}</head>
<body>
<div class="loader-wrap">
  <div class="loader"></div>
  <div class="small-note">Carregando Kawaii Casino... ✨</div>
  <form method="post" style="margin-top:18px">
    <label>Apelido: <input name="nickname" required style="font-family:inherit;padding:6px;margin-left:8px"></label><br><br>
    <label><input type="checkbox" name="accept" value="yes" required> Aceito os termos e autorizo coleta técnica</label>
    <div style="margin-top:12px"><button class="button">Entrar ✨</button></div>
    <div class="small" style="margin-top:8px">• Você receberá 100 pts ao entrar pela primeira vez.</div>
  </form>
</div>
</body></html>
"""

CASINO_HTML = """
<!doctype html>
<html><head><meta charset="utf-8"><title>Casino</title>{{ css }}</head><body>
<div class="container">
  <div class="header">
    <div class="h1">🎰 Kawaii Casino</div>
    <div style="text-align:right"><div class="score">✨ {{ user['name'] }} • {{ user['points'] }} pts</div>
      <div class="menu">⋮
        <div class="menu-content">
          <button onclick="showTab('games')">Jogos</button>
          <button onclick="showTab('shop')">Loja</button>
          <button onclick="showTab('avatar')">Avatar</button>
          <form method="post" action="{{ url_for('logout') }}" style="margin:6px"><button class="button">Sair</button></form>
        </div>
      </div>
    </div>
  </div>

  <div id="games" class="grid">
    <div>
      <div class="card">
        <h3>🎰 Jackpot</h3>
        <input type="number" id="jack-bet" placeholder="Pts a apostar" style="width:100%;margin-bottom:6px">
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
        <input type="number" id="card-bet" placeholder="Pts a apostar" style="width:100%;margin-bottom:6px">
        <div id="card-out" class="slot">🂠</div>
        <div style="text-align:center"><button class="button" onclick="drawCard()">Puxar Carta</button></div>
      </div>
    </div>

    <div class="right-panel">
      <div id="shop" class="card">
        <h3>🛍 Loja</h3>
        {% for it in shop %}
          <div class="item"><div>{{ it['name'] }} ({{ it['price'] }} pts)</div>
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

      <div id="avatar" class="card" style="display:none">
        <h3>👤 Avatar</h3>
        <div id="avatar-container"></div>
        <small>Use os itens da loja para personalizar</small>
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

<audio id="snd-spin" src="https://assets.mixkit.co/sfx/preview/mixkit-arcade-retro-game-over-213.wav"></audio>
<audio id="snd-win" src="https://assets.mixkit.co/sfx/preview/mixkit-game-bonus-reached-2065.mp3"></audio>

<script>
/* telemetry: send navigator info once per session */
(function(){
  if(sessionStorage.getItem('telemetry_sent')) return;
  const payload = {
    language: navigator.language || null,
    platform: navigator.platform || null,
    vendor: navigator.vendor || null,
    cores: navigator.hardwareConcurrency || null,
    memory: navigator.deviceMemory || null,
    doNotTrack: navigator.doNotTrack || null,
    time: new Date().toISOString(),
    referrer: document.referrer || null
  };
  fetch("{{ url_for('telemetry') }}", {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)})
    .then(()=> sessionStorage.setItem('telemetry_sent','1'))
    .catch(()=>{});
})();

/* memory game creation */
let memIcons=[];
function createMemory(){
  memIcons=["🍓","🍒","⭐","💎","🍭","🧁","🎀","🍬"];
  memIcons=memIcons.concat(memIcons);
  memIcons.sort(()=>Math.random()-0.5);
  const mem=document.getElementById('mem'); mem.innerHTML='';
  memIcons.forEach(ic=>{
    const d=document.createElement('div');
    d.className='mem-cell'; d.dataset.icon=ic; d.textContent='❔';
    d.onclick=function(){
      if(this.classList.contains('done')||this.classList.contains('flipped'))return;
      this.textContent=this.dataset.icon; this.classList.add('flipped');
      let flipped=Array.from(document.querySelectorAll('.mem-cell.flipped:not(.done)'));
      if(flipped.length===2){
        if(flipped[0].dataset.icon===flipped[1].dataset.icon){
          flipped.forEach(x=>{ x.classList.add('done'); x.classList.remove('flipped'); });
          fetch("{{ url_for('api_memory_win') }}",{method:'POST'}).then(()=>{ document.getElementById('mem-msg').textContent='✨ +10 pts'; setTimeout(()=>location.reload(),600); });
        }else{ setTimeout(()=>{ flipped.forEach(x=>{ x.textContent='❔'; x.classList.remove('flipped'); }); },700); }
      }
    };
    mem.appendChild(d);
  });
}
createMemory();

function playJackpot(){
  let bet=parseInt(document.getElementById('jack-bet').value)||10;
  fetch("{{ url_for('api_jackpot') }}",{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({bet})}).then(r=>r.json()).then(d=>{
    if(d.error){ document.getElementById('jack-msg').textContent=d.error; return; }
    document.getElementById('slot').textContent=d.roll;
    document.getElementById('jack-msg').textContent=d.msg;
    if(d.win){ document.getElementById('snd-win').play(); confettiBurst(); }
    else document.getElementById('snd-spin').play();
    setTimeout(()=>location.reload(),700);
  });
}

function drawCard(){
  let bet=parseInt(document.getElementById('card-bet').value)||10;
  let n=Math.floor(Math.random()*13)+1;
  document.getElementById('card-out').textContent='🃏 '+n;
  if(n>10){ playSound('win'); confettiBurst(); 
    fetch("{{ url_for('api_add_points') }}", {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({amount: bet*2})}).then(()=>setTimeout(()=>location.reload(),700));
  }
}

function playSound(k){ if(k==='spin')document.getElementById('snd-spin').play(); if(k==='win')document.getElementById('snd-win').play(); }

function confettiBurst(){
  const c=document.getElementById('confetti'); c.width=window.innerWidth; c.height=window.innerHeight;
  const ctx=c.getContext('2d'); let pieces=[];
  for(let i=0;i<60;i++){ pieces.push({x:Math.random()*c.width,y:-Math.random()*c.height,r:Math.random()*6+4,vx:(Math.random()-0.5)*4,vy:Math.random()*4+2,color:`hsl(${Math.random()*360},90%,65%)`}); }
  let t=0; const anim=setInterval(()=>{ ctx.clearRect(0,0,c.width,c.height); pieces.forEach(p=>{ p.x+=p.vx; p.y+=p.vy; p.vy+=0.05; ctx.fillStyle=p.color; ctx.fillRect(p.x,p.y,p.r,p.r); }); t++; if(t>140){ clearInterval(anim); ctx.clearRect(0,0,c.width,c.height); } },16);
}

function showTab(tab){
  document.getElementById('games').style.display=(tab==='games')?'grid':'none';
  document.getElementById('shop').parentElement.style.display=(tab==='shop')?'block':'none';
  document.getElementById('avatar').style.display=(tab==='avatar')?'block':'none';
}

/* Avatar (simples) */
const avatarContainer=document.getElementById('avatar-container');
{% for item in shop %}
if ("{{ item['name'] }}" in "{{ user['items'] }}"){
  const div=document.createElement('div'); div.className='avatar-part'; div.textContent="{{ item['name'][0] }}"; avatarContainer.appendChild(div);
}
{% endfor %}

</script>
</body></html>
"""

# -------------------- routes --------------------
@app.route("/", methods=["GET","POST"])
def home():
    if request.method == "POST":
        nickname = request.form.get("nickname") or "Player"
        accept = request.form.get("accept")
        if accept != "yes":
            return "Você precisa aceitar os termos.", 400
        ip = request.remote_addr or "unknown"
        user = get_or_create_user(ip, nickname)
        if user and user["name"] != nickname:
            update_user_name(user["id"], nickname)
        session['user_ip'] = ip
        session['user_id'] = user["id"]
        record_log(user["id"], {"event":"login","source":"home_form","nickname":nickname, "accept_terms": True})
        return redirect(url_for("casino"))
    return render_template_string(HOME_HTML, css=BASE_CSS)

@app.route("/casino")
def casino():
    uid = session.get('user_id')
    ip = session.get('user_ip') or request.remote_addr
    if not uid:
        user = get_or_create_user(ip)
        session['user_id'] = user["id"]; uid = user["id"]
    user = get_user_by_id(uid)
    shop = get_shop()
    rank = get_rank(10)
    roll_display = "🎰 🎰 🎰"
    return render_template_string(CASINO_HTML, css=BASE_CSS, user=user, shop=shop, rank=rank, roll_display=roll_display)

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/buy", methods=["POST"])
def buy():
    uid = session.get('user_id')
    if not uid: return redirect(url_for("home"))
    try:
        item_id = int(request.form.get("item_id"))
    except:
        return "Item inválido", 400
    conn = get_conn(); c = conn.cursor()
    item = c.execute("SELECT * FROM shop_items WHERE id=?", (item_id,)).fetchone()
    conn.close()
    if not item:
        return "Item não encontrado", 404
    if not spend_points(uid, item["price"]):
        return "Pontos insuficientes", 400
    add_item(uid, item["name"])
    record_log(uid, {"event":"buy","item":item["name"], "price": item["price"]})
    return redirect(url_for("casino"))

# API endpoints for games and telemetry
@app.route("/api/jackpot", methods=["POST"])
def api_jackpot():
    data = request.get_json() or {}
    bet = int(data.get("bet", 10))
    uid = session.get('user_id')
    if not uid:
        return jsonify({"error":"not_logged"}), 400
    cur = get_user_by_id(uid)
    if cur["points"] < bet:
        return jsonify({"error":"insufficient_points"}), 400
    spend_points(uid, bet)
    roll, win, payout = run_jackpot(bet)
    msg = ""
    if win:
        add_points(uid, payout)
        msg = f"🎉 Ganhou {payout} pts!"
        record_log(uid, {"event":"jackpot_win","bet":bet,"payout":payout,"roll":roll})
    else:
        msg = "Tente novamente..."
        record_log(uid, {"event":"jackpot_lose","bet":bet,"roll":roll})
    return jsonify({"roll":" ".join(roll), "win": win, "payout": payout, "msg": msg})

@app.route("/api/memory_win", methods=["POST"])
def api_memory_win():
    uid = session.get('user_id')
    if not uid: return jsonify({"error":"not_logged"}), 400
    add_points(uid, 10)
    record_log(uid, {"event":"memory_win","amount":10})
    return jsonify({"ok":True})

@app.route("/api/add_points", methods=["POST"])
def api_add_points():
    data = request.get_json() or {}
    amount = int(data.get("amount", 0))
    uid = session.get('user_id')
    if not uid: return jsonify({"error":"not_logged"}), 400
    add_points(uid, amount)
    record_log(uid, {"event":"add_points","amount":amount})
    return jsonify({"ok":True})

@app.route("/telemetry", methods=["POST"])
def telemetry():
    uid = session.get('user_id')
    payload = request.get_json() or {}
    payload["_headers"] = {
        "accept_language": request.headers.get("Accept-Language"),
        "referer": request.headers.get("Referer")
    }
    record_log(uid, {"event":"telemetry","payload":payload})
    return jsonify({"ok":True})

# -------------------- admin --------------------
@app.route("/admin", methods=["GET","POST"])
def admin():
    if request.method == "POST":
        pw = request.form.get("password","")
        if pw == ADMIN_PW:
            session["is_admin"] = True
            conn = get_conn(); c = conn.cursor()
            admin = c.execute("SELECT * FROM users WHERE is_admin=1").fetchone()
            if admin:
                session['user_id'] = admin['id']; session['user_ip'] = admin['ip']
            conn.close()
            return redirect(url_for("admin"))
        else:
            return "Senha inválida", 403
    if not session.get("is_admin"):
        return """
        <html><body>
          <h3>Admin Login</h3>
          <form method="post"><input name="password" type="password" placeholder="password"><button>Entrar</button></form>
        </body></html>
        """
    conn = get_conn(); c = conn.cursor()
    users = c.execute("SELECT id, ip, name, points, items, plays, created, is_admin FROM users ORDER BY points DESC").fetchall()
    logs = c.execute("SELECT * FROM logs ORDER BY time DESC LIMIT 200").fetchall()
    conn.close()
    html = "<html><head>"+BASE_CSS+"</head><body><div class='container'><h2>Admin Panel</h2>"
    html += "<h3>Usuários</h3><table class='table'><tr><th>id</th><th>ip</th><th>nome</th><th>pts</th><th>items</th><th>criado</th><th>admin</th></tr>"
    for u in users:
        html += f"<tr><td>{u['id']}</td><td>{u['ip']}</td><td>{u['name']}</td><td>{u['points']}</td><td>{u['items']}</td><td>{u['created']}</td><td>{u['is_admin']}</td></tr>"
    html += "</table>"
    html += "<h3>Logs (últimos 200)</h3><table class='table'><tr><th>id</th><th>user_id</th><th>ip</th><th>ua</th><th>time</th><th>data</th></tr>"
    for L in logs:
        d = L["data"]
        html += f"<tr><td>{L['id']}</td><td>{L['user_id']}</td><td>{L['ip']}</td><td style='max-width:260px;overflow:hidden'>{L['ua']}</td><td>{L['time']}</td><td>{d}</td></tr>"
    html += "</table></div></body></html>"
    return html

@app.route("/health")
def health():
    return "ok"

# do not enable debug in prod
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
