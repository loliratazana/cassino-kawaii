from flask import Flask, request, session, redirect, jsonify, render_template_string, url_for
import sqlite3, random, time, os
import requests

app = Flask(__name__)
app.secret_key = os.environ.get("KAWAII_SECRET", "kawaii-casino-secret")
DB = "casino.db"

# ======================================================
# DB & INIT
# ======================================================
def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        points INTEGER DEFAULT 100,
        last_tick INTEGER,
        consent_ip INTEGER DEFAULT 0
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        ip TEXT,
        action TEXT,
        timestamp INTEGER
    )""")
    cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "consent_ip" not in cols:
        try:
            conn.execute("ALTER TABLE users ADD COLUMN consent_ip INTEGER DEFAULT 0")
        except Exception:
            pass
    conn.commit()
    conn.close()


init_db()

# ======================================================
# HELPERS
# ======================================================

def get_user():
    uid = session.get("uid")
    if not uid:
        return None
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    finally:
        conn.close()


def get_user_by_username(username):
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    finally:
        conn.close()


def tick_points(user):
    now = int(time.time())
    last = user["last_tick"] or now
    diff = now - last
    if diff >= 60:
        gain = (diff // 60) * 2
        conn = get_conn()
        try:
            conn.execute(
                "UPDATE users SET points=points+?, last_tick=? WHERE id=?",
                (gain, now, user["id"])
            )
            conn.commit()
        finally:
            conn.close()


def safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default


# ======================================================
# IP VIA SITES EXTERNOS (NOVO)
# ======================================================

def get_ip_from_sites():
    """
    Busca IP público real usando serviços externos.
    Fallback automático se falhar.
    """
    try:
        ip = requests.get(
            "https://api.ipify.org?format=json",
            timeout=2
        ).json().get("ip")
        if not ip:
            raise Exception("ip vazio")

        geo = requests.get(
            f"https://ipapi.co/{ip}/json/",
            timeout=2
        ).json()

        return {
            "ip": ip,
            "country": geo.get("country_name", geo.get("country", "NA")),
            "org": geo.get("org", "NA"),
            "asn": geo.get("asn", "NA")
        }
    except Exception:
        # fallback local
        return {
            "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
            "country": "NA",
            "org": "NA",
            "asn": "NA"
        }


def log_action(username, action):
    """
    Loga ações respeitando consentimento.
    IP vem de SITE EXTERNO se possível.
    """
    data = get_ip_from_sites()

    ip_to_store = "unknown"
    try:
        u = get_user_by_username(username)
        if u is None:
            ip_to_store = data["ip"]
        else:
            if u["consent_ip"]:
                ip_to_store = data["ip"]
            else:
                ip_to_store = "consent_no"
    except Exception:
        ip_to_store = "unknown"

    action_full = f"{action} | cc:{data['country']} asn:{data['asn']} isp:{data['org']}"

    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO logs(username, ip, action, timestamp) VALUES(?,?,?,?)",
            (username, ip_to_store, action_full, int(time.time()))
        )
        conn.commit()
    finally:
        conn.close()


# ======================================================
# CSS
# ======================================================
CSS = """
<style>
:root{--pink:#ff69b4;--light:#fff4f8;--card-shadow:0 12px 30px rgba(0,0,0,0.12)}
body{ background:linear-gradient(135deg,#ffd6e8,#c7f0ff); font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; text-align:center; margin:0; padding:20px; }
.container{max-width:1100px;margin:0 auto}
.card{ background:white; padding:20px; margin:20px auto; border-radius:18px; box-shadow:var(--card-shadow); }
button,input,select{ padding:10px 16px; border-radius:14px; border:none; margin:5px; font-size:15px; }
button{background:linear-gradient(45deg,var(--pink),#ff3d7f);color:white;cursor:pointer}
#play-btn{padding:14px 36px;font-size:20px;border-radius:34px}
#play-btn:disabled{opacity:0.6;cursor:not-allowed}
.memory-card{ width:100px;height:100px;background:#fff;border-radius:12px;margin:8px;display:inline-flex;justify-content:center;align-items:center;font-size:44px;cursor:pointer; box-shadow:0 6px 18px rgba(0,0,0,.12); transition:transform .18s ease, background .18s; }
.memory-card:hover{ transform:translateY(-6px) }
.memory-card.matched{ background:#ffdce6; cursor:default }
.memory-container{display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:12px;justify-items:center;align-items:center;max-width:720px;margin:12px auto}
.header-row{display:flex;justify-content:space-between;align-items:center}
.small{font-size:13px;color:#333}
.leaderboard{display:flex;gap:10px;justify-content:center;flex-wrap:wrap}
.leader{background:#fff1f6;padding:10px;border-radius:10px;min-width:140px}
#slot-container{display:flex;justify-content:center;gap:30px;margin:24px 0;font-size:96px}
.slot-emoji{display:inline-block;font-size:96px;line-height:1}
.result{font-weight:700; margin-top:10px}
</style>
"""


# ======================================================
# ROUTES
# ======================================================
@app.route('/', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('user', '').strip()
        p = request.form.get('pw', '')
        if not u or not p:
            return CSS + "<div class=card><b>Usuário e senha precisam ser preenchidos</b><br><a href=/>Voltar</a></div>"
        conn = get_conn()
        try:
            user = conn.execute('SELECT * FROM users WHERE username=?', (u,)).fetchone()
            if user:
                # login normal
                if user['password'] != p:
                    return CSS + "<div class=card><b>Senha incorreta</b><br><a href=/>Voltar</a></div>"
            else:
                # cria usuário novo já aceitando termos
                conn.execute(
                    'INSERT INTO users(username,password,last_tick,consent_ip) VALUES(?,?,?,?)',
                    (u, p, int(time.time()), 1)
                )
                conn.commit()
                user = conn.execute('SELECT * FROM users WHERE username=?', (u,)).fetchone()
        finally:
            conn.close()
        session['uid'] = user['id']
        log_action(u, 'login')
        return redirect('/casino')

    return render_template_string(CSS + """
<div class="container">
  <div class="card">
    <h2>🎀 Kawaii Casino 🎀</h2>
    <form method=post>
      <input name=user placeholder="Usuário" required><br>
      <input name=pw type=password placeholder="Senha" required><br>
      <button>Entrar / Registrar</button>
    </form>
    <p><a href="/terms" class="small">📜 Termos de Uso</a></p>
  </div>
</div>
""")

@app.route('/logout')
def logout():
    session.pop('uid', None)
    return redirect('/')

@app.route('/terms')
def terms():
    user = get_user()
    checked = ''
    if user:
        try:
            checked = 'checked' if user['consent_ip'] else ''
        except Exception:
            checked = ''
    # Consent is now handled here (separate aba) as requested
    return render_template_string(CSS + """
<div class="container">
  <div class="card">
    <h2>📜 Termos de Uso</h2>
    <p>Bem-vindo ao Kawaii Casino! Use com responsabilidade. Este é um jogo fictício de entretenimento.</p>
    <p>Nenhum ponto ou prêmio tem valor real. Não compartilhe sua senha. Divirta-se!</p>
    {% if user %}
    <div style="margin-top:12px">
      <label><input type="checkbox" id="consent-checkbox" {{checked}}> Eu concordo em compartilhar meu IP nos logs (consentimento)</label>
    </div>
    {% else %}
    <p class="small">Faça login para ajustar o consentimento de IP.</p>
    {% endif %}
    <p style="margin-top:12px"><a href="/">⬅ Voltar</a></p>
  </div>
</div>

<script>
const cb = document.getElementById('consent-checkbox');
if(cb){
  cb.addEventListener('change', ()=>{
    fetch('/api/consent', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({consent: cb.checked?1:0})})
      .then(r=>r.json()).then(d=>{ if(!d.ok) alert('Erro ao salvar consentimento'); else alert('Consentimento atualizado'); })
      .catch(()=>alert('Erro de rede'))
  })
}
</script>
""", user=user, checked=checked)

@app.route('/casino')
def casino():
    user = get_user()
    if not user:
        return redirect('/')
    tick_points(user)
    user = get_user()
    is_admin = (user['username'] == 'admin')
    return render_template_string("""
<!doctype html>
<html>
<head>
{{css|safe}}
</head>
<body>
<div class="container">
  <div class="card header-row">
    <div>
      <h2>🎰 Slots Kawaii 🎀</h2>
      <div class="small">Olá <strong>{{u['username']}}</strong> — pontos: <strong id="points">{{u['points']}}</strong></div>
    </div>
    <div>
      <a href="/leaderboard" class="small">🏆 Leaderboard</a> |
      <a href="/logout" class="small">🚪 Logout</a>
      <!-- termos removidos daqui conforme pedido -->
    </div>
  </div>

  <div class="card">
    <label for="bet">Quanto quer apostar?</label><br>
    <input id="bet" type="number" value="10" min="1" max="{{u['points']}}" /><br>
    <div id="slot-container">
      <span class="slot-emoji">❔</span>
      <span class="slot-emoji">❔</span>
      <span class="slot-emoji">❔</span>
      <span class="slot-emoji">❔</span>
    </div>
    <button id="play-btn">🎲 Jogar</button>
    <div id="result-msg" class="result"></div>
  </div>

  <div class="card">
    <h3>🧠 Jogo da Memória</h3>
    <div class="memory-container" id="memory-container"></div>
  </div>

  {% if is_admin %}
  <div class="card">
    <h3>Admin Panel - Logs</h3>
    <button id="admin-load-btn">Ver Usuários / Logs</button>
    <div id="user-list"></div>
  </div>
  {% endif %}
</div>

<script>
document.addEventListener('DOMContentLoaded', ()=>{
  const emojis = ['🐱','🦄','🐭','🐰','🍓','🌸','🍬'];
  const slots = document.querySelectorAll('.slot-emoji');
  const playBtn = document.getElementById('play-btn');
  const betInput = document.getElementById('bet');
  const resultMsg = document.getElementById('result-msg');
  const pointsEl = document.getElementById('points');
  let spinning=false; let spinInterval=null;

  function startSpin(){ 
    spinInterval = setInterval(()=>{
      slots.forEach(s=>{
        s.textContent = emojis[Math.floor(Math.random()*emojis.length)];
      });
    }, 90);
  }
  function stopSpin(){ if(spinInterval){ clearInterval(spinInterval); spinInterval=null; } }
  function allEqual(arr){ return arr.length>0 && arr.every(v=>v===arr[0]); }

  playBtn.addEventListener('click', ()=>{
    let bet = parseInt(betInput.value);
    let maxBet = parseInt(pointsEl.textContent);
    if(isNaN(bet)||bet<1){ alert('Digite um valor válido!'); return; }
    if(bet>maxBet){ alert('Você não tem pontos suficientes!'); betInput.value = maxBet; return; }
    if(spinning) return;
    spinning = true; playBtn.disabled=true; resultMsg.textContent=''; startSpin();
    setTimeout(()=>{
      stopSpin();
      let result = [];
      if(Math.random()<0.2){ let w = emojis[Math.floor(Math.random()*emojis.length)]; result = [w,w,w,w]; }
      else{ for(let i=0;i<4;i++) result.push(emojis[Math.floor(Math.random()*emojis.length)]); }
      slots.forEach((s,i)=>s.textContent = result[i]);
      let won = allEqual(result);
      fetch('/api/slots', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({bet:bet, win: won})})
        .then(r=>r.json()).then(data=>{
          if(data.error) alert(data.error);
          if(won) resultMsg.innerHTML = `🎉 Parabéns! Você ganhou <span style="color:#ff1493;">+${data.win_amount}</span> pontos!`;
          else resultMsg.innerHTML = `😿 Que pena, você perdeu <span style="color:#ff1493;">${bet}</span> pontos.`;
          if(typeof data.new_points !== 'undefined'){
            pointsEl.textContent = data.new_points; betInput.max = data.new_points; betInput.value = Math.min(bet, data.new_points);
          }
        }).catch(()=>alert('Erro no servidor'))
        .finally(()=>{ spinning=false; playBtn.disabled=false; });
    }, 2500);
  });

  // Memory game (Fisher-Yates shuffle)
  function shuffle(array){ for(let i=array.length-1;i>0;i--){ const j=Math.floor(Math.random()*(i+1)); [array[i],array[j]]=[array[j],array[i]]; } }
  const memoryContainer = document.getElementById('memory-container');
  function buildMemory(){
    memoryContainer.innerHTML='';
    let pairs = [...emojis];
    if(pairs.length>8) pairs = pairs.slice(0,8);
    let memoryEmojis = [...pairs, ...pairs];
    shuffle(memoryEmojis);
    let firstCard = null; let lock=false;
    memoryEmojis.forEach(val=>{
      const card = document.createElement('div');
      card.className = 'memory-card'; card.textContent='?'; card.dataset.value = val;
      card.addEventListener('click', ()=>{
        if(card.classList.contains('matched') || lock) return;
        card.textContent = val;
        if(!firstCard){ firstCard = card; return; }
        lock = true;
        if(firstCard.dataset.value === card.dataset.value){
          card.classList.add('matched'); firstCard.classList.add('matched');
          fetch('/api/memory', {method:'POST'}).then(r=>r.json()).then(d=>{ if(d.new_points) pointsEl.textContent = d.new_points; }).finally(()=>{ firstCard=null; lock=false; });
        } else {
          setTimeout(()=>{ if(firstCard) firstCard.textContent='?'; card.textContent='?'; firstCard=null; lock=false; }, 500);
        }
      });
      memoryContainer.appendChild(card);
    });
  }
  buildMemory();

  // Admin panel loader
  const adminBtn = document.getElementById('admin-load-btn');
  if(adminBtn){
    adminBtn.addEventListener('click', ()=>{
      fetch('/api/admin/users').then(r=>{
        if(r.status===403){ alert('Acesso negado: você não é admin'); return []; }
        return r.json();
      }).then(data=>{
        const list = document.getElementById('user-list'); list.innerHTML='';
        data.forEach(u=>{
          const div = document.createElement('div');
          div.textContent = `${u.username} - IP: ${u.ip} - ${new Date(u.timestamp*1000).toLocaleString()} - ${u.action}`;
          list.appendChild(div);
        });
      }).catch(()=>alert('Erro ao carregar logs'));
    });
  }

});
</script>
</body>
</html>
""", css=CSS, u=user, is_admin=is_admin)


# ======================================================
# APIs
# ======================================================
@app.route('/api/slots', methods=['POST'])
def api_slots():
    user = get_user()
    if not user:
        return jsonify(error='Usuário não logado'), 403
    data = request.get_json(silent=True) or {}
    bet = safe_int(data.get('bet', 0))
    win = bool(data.get('win', False))
    if bet <= 0:
        return jsonify(error='Aposta inválida')
    conn = get_conn()
    try:
        cur = conn.execute('SELECT points FROM users WHERE id=?', (user['id'],)).fetchone()
        cur_points = cur['points'] if cur else 0
        if cur_points < bet:
            return jsonify(error='Sem pontos suficientes')
        if win:
            win_amount = bet * 5
            conn.execute('UPDATE users SET points=points+? WHERE id=?', (win_amount, user['id']))
        else:
            win_amount = 0
            conn.execute('UPDATE users SET points=points-? WHERE id=?', (bet, user['id']))
        conn.commit()
        new_points = conn.execute('SELECT points FROM users WHERE id=?', (user['id'],)).fetchone()['points']
    finally:
        conn.close()
    log_action(user['username'], f"slots {'win' if win else 'lose'} {bet}")
    return jsonify(ok=True, win_amount=win_amount, new_points=new_points)


@app.route('/api/memory', methods=['POST'])
def api_memory():
    user = get_user()
    if not user:
        return jsonify(msg='Usuário não logado'), 403
    conn = get_conn()
    try:
        conn.execute('UPDATE users SET points=points+2 WHERE id=?', (user['id'],))
        conn.commit()
        new_points = conn.execute('SELECT points FROM users WHERE id=?', (user['id'],)).fetchone()['points']
    finally:
        conn.close()
    log_action(user['username'], 'memory win +2')
    return jsonify(new_points=new_points)


@app.route('/api/consent', methods=['POST'])
def api_consent():
    user = get_user()
    if not user:
        return jsonify(ok=False, error='Usuário não logado'), 403
    data = request.get_json(silent=True) or {}
    consent = 1 if safe_int(data.get('consent', 0)) else 0
    conn = get_conn()
    try:
        conn.execute('UPDATE users SET consent_ip=? WHERE id=?', (consent, user['id']))
        conn.commit()
    finally:
        conn.close()
    return jsonify(ok=True, consent=consent)


@app.route('/api/admin/users')
def api_admin_users():
    user = get_user()
    if not user or user['username'] != 'admin':
        return jsonify([]), 403
    conn = get_conn()
    try:
        users = conn.execute('SELECT * FROM logs ORDER BY timestamp DESC LIMIT 200').fetchall()
        return jsonify([dict(u) for u in users])
    finally:
        conn.close()


@app.route('/leaderboard')
def leaderboard():
    conn = get_conn()
    try:
        top = conn.execute('SELECT username, points FROM users ORDER BY points DESC LIMIT 10').fetchall()
    finally:
        conn.close()
    html = CSS + '<div class="container"><div class="card"><h2>🏆 Top 10</h2><div class="leaderboard">'
    for u in top:
        html += f"<div class=leader><strong>{u['username']}</strong><br>{u['points']} pts</div>"
    html += '</div><p><a href="/">Voltar</a></p></div></div>'
    return html


# ======================================================
if __name__ == '__main__':
    app.run(port=3000, debug=True)
