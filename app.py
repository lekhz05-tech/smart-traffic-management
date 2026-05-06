import streamlit as st
import mysql.connector
import time
import random
import threading
import json

# ─────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────
st.set_page_config(
    page_title="Smart Traffic Management",
    layout="wide",
    page_icon="🚦"
)

# ─────────────────────────────────────────
# DATABASE CONNECTION
# ─────────────────────────────────────────
def get_db():
    try:
        db = mysql.connector.connect(
            host="trolley.proxy.rlwy.net",
            port=41829,
            user="root",
            password="pskpxuaQLNOcrvaXVwzKvAfmtWOSfwQc",
            database="railway",
            connection_timeout=5
        )
        return db
    except:
        return None

def fetch_signal_data():
    db = get_db()
    if not db:
        # Fallback data
        return [
            {"signal_id": i, "vehicle_count": random.randint(10, 80), "green_time": 30 if i == 1 else 0}
            for i in range(1, 5)
        ]
    try:
        cur = db.cursor(dictionary=True)
        cur.execute("""
            SELECT s.signal_id,
                   COALESCE(t.vehicle_count, 20) AS vehicle_count,
                   COALESCE(st.green_time, 0) AS green_time
            FROM signals s
            LEFT JOIN traffic_data t ON s.signal_id = t.signal_id
            LEFT JOIN signal_timing st ON s.signal_id = st.signal_id
            ORDER BY s.signal_id
        """)
        rows = cur.fetchall()
        return rows if rows else [
            {"signal_id": i, "vehicle_count": random.randint(10, 80), "green_time": 30 if i == 1 else 0}
            for i in range(1, 5)
        ]
    except Exception as e:
        st.warning(f"DB Error: {e}")
        return [
            {"signal_id": i, "vehicle_count": random.randint(10, 80), "green_time": 30 if i == 1 else 0}
            for i in range(1, 5)
        ]
    finally:
        if db:
            db.close()

# ─────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────
if "emergency_queue" not in st.session_state:
    st.session_state.emergency_queue = []
if "sim_started" not in st.session_state:
    st.session_state.sim_started = False

# ─────────────────────────────────────────
# BACKGROUND SIMULATOR
# ─────────────────────────────────────────
def background_simulator():
    while True:
        db = get_db()
        if db:
            try:
                cur = db.cursor()
                # Simple cycling + emergency handling
                cur.execute("SELECT signal_id FROM signal_timing WHERE green_time = 999 LIMIT 1")
                emg = cur.fetchone()
                if not emg:
                    # Basic cycle
                    cur.execute("SELECT signal_id FROM signals ORDER BY signal_id")
                    sids = [r[0] for r in cur.fetchall()]
                    # You can enhance cycling logic later
                db.commit()
            except:
                pass
            finally:
                db.close()
        time.sleep(3)

if not st.session_state.sim_started:
    st.session_state.sim_started = True
    threading.Thread(target=background_simulator, daemon=True).start()

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────
DIRECTIONS = {1: "North", 2: "East", 3: "South", 4: "West"}

def trigger_emergency(sid):
    if sid not in st.session_state.emergency_queue:
        st.session_state.emergency_queue.append(sid)
        db = get_db()
        if db:
            try:
                cur = db.cursor()
                cur.execute("UPDATE signal_timing SET green_time=999 WHERE signal_id=%s", (sid,))
                cur.execute("INSERT INTO emergency_log (signal_id, event_type) VALUES (%s, 'TRIGGERED')", (sid,))
                db.commit()
            except:
                pass
            finally:
                db.close()
    st.rerun()

def clear_emergency():
    if st.session_state.emergency_queue:
        sid = st.session_state.emergency_queue.pop(0)
        db = get_db()
        if db:
            try:
                cur = db.cursor()
                cur.execute("UPDATE signal_timing SET green_time=0 WHERE signal_id=%s", (sid,))
                db.commit()
            except:
                pass
            finally:
                db.close()
    st.rerun()

# ─────────────────────────────────────────
# MAIN LOGIC
# ─────────────────────────────────────────
db_ok = get_db() is not None
rows = fetch_signal_data()
sig_data = {r["signal_id"]: r for r in rows}

emq = st.session_state.emergency_queue
current_green_id = emq[0] if emq else next(
    (sid for sid, d in sig_data.items() if d.get("green_time", 0) > 0), 1
)

signal_states = []
for sid in range(1, 5):
    d = sig_data.get(sid, {"vehicle_count": random.randint(15, 75), "green_time": 0})
    gt = 999 if sid in emq else d.get("green_time", 0)
    
    if sid in emq:
        color = "emergency"
    elif gt > 10:
        color = "green"
    elif gt > 0:
        color = "yellow"
    else:
        color = "red"
    
    signal_states.append({
        "id": sid,
        "direction": DIRECTIONS[sid],
        "vehicles": d["vehicle_count"],
        "timer": gt if gt != 999 else 999,
        "color": color,
        "emergency": sid in emq
    })

sig_json = json.dumps(signal_states)
emq_json = json.dumps(emq)
green_dir = DIRECTIONS.get(current_green_id, "North")

# ─────────────────────────────────────────
# UI
# ─────────────────────────────────────────
st.markdown("# 🚦 Smart Traffic Management System")
col1, col2 = st.columns([5, 1])
with col2:
    if db_ok:
        st.success("MySQL Connected ✅")
    else:
        st.warning("Offline Simulation")

st.divider()

# Emergency Controls
st.subheader("🚨 Emergency Override")
ecols = st.columns(5)
for i in range(1, 5):
    with ecols[i-1]:
        if i in emq:
            st.error(f"🚑 S{i} ACTIVE", icon="🚨")
        else:
            if st.button(f"Signal {i} — {DIRECTIONS[i]}", key=f"emg_{i}", use_container_width=True):
                trigger_emergency(i)

if emq:
    if st.button("✅ Clear Oldest Emergency", type="primary", use_container_width=True):
        clear_emergency()

st.divider()

# Live Dashboard
# ==================== LIVE DASHBOARD ====================
st.subheader("📡 Live Intersection Dashboard")

# Prepare JSON safely
emg_json_safe = emq_json if emq_json != "[]" else "[]"

html_code = f"""
<!DOCTYPE html>
<html>
<head>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;600&display=swap');
    
    body {{
        font-family: 'Inter', sans-serif;
        background: #0a0c14;
        color: #e0e0e0;
        margin: 0;
        padding: 15px;
    }}
    .dashboard {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
    .panel {{
        background: #111827;
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }}
    .signal-row {{
        display: flex;
        align-items: center;
        gap: 15px;
        padding: 14px 0;
        border-bottom: 1px solid #1f2937;
    }}
    .signal-row:last-child {{ border-bottom: none; }}
    .dot {{
        width: 18px; height: 18px; border-radius: 50%; flex-shrink: 0;
    }}
    .dot-emergency {{ background: #c026d3; box-shadow: 0 0 20px #c026d3; animation: pulse 1.2s infinite; }}
    .dot-green {{ background: #22c55e; box-shadow: 0 0 15px #22c55e; }}
    .dot-yellow {{ background: #eab308; box-shadow: 0 0 15px #eab308; }}
    .dot-red {{ background: #ef4444; box-shadow: 0 0 12px #ef4444; }}
    @keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} }}
    .timer {{ font-family: 'Space Grotesk', monospace; font-size: 1.45em; font-weight: 600; }}
</style>
</head>
<body>
<div class="dashboard">
  <div class="panel">
    <h3 style="margin:0 0 18px 0; color:#a5b4fc;">📊 Signal Status</h3>
    <div id="signalList"></div>
  </div>

  <div class="panel">
    <h3 style="margin:0 0 18px 0; color:#a5b4fc;">🗺 Intersection View</h3>
    <canvas id="canvas" width="440" height="440" style="background:#0f172a; border-radius:12px; display:block; margin:0 auto;"></canvas>
    <div id="emgStatus" style="text-align:center; margin-top:15px; font-size:1.1em; font-weight:500; min-height:32px;"></div>
  </div>
</div>

<script>
const signals = {sig_json};
const emgQueue = {emg_json_safe};

let signalStates = signals.map(s => ({{
  id: s.id,
  direction: s.direction,
  vehicles: s.vehicles,
  color: s.emergency ? 'emergency' : s.color,
  timer: s.emergency ? 999 : Math.max(15, parseInt(s.timer) || 30),
  phase: s.emergency ? 'green' : s.color
}}));

let ambulanceProgress = 0;

function updateList() {{
  let html = '';
  signalStates.forEach(s => {{
    let dotClass = 'dot-red';
    if (s.color === 'emergency') dotClass = 'dot-emergency';
    else if (s.color === 'green') dotClass = 'dot-green';
    else if (s.color === 'yellow') dotClass = 'dot-yellow';

    const timerText = s.timer === 999 ? '∞' : s.timer + 's';
    const colorText = s.color === 'green' ? '#22c55e' : s.color === 'yellow' ? '#eab308' : '#ef4444';

    html += `
      <div class="signal-row">
        <span class="dot ${{dotClass}}"></span>
        <strong>S${{s.id}} ${{s.direction}}</strong>
        <div style="flex:1; height:10px; background:#1f2937; border-radius:999px; overflow:hidden; margin:0 12px;">
          <div style="width:${{Math.min(100, (s.vehicles/1.25))}}%; height:100%; background:linear-gradient(90deg, #f87171, #4ade80);"></div>
        </div>
        <span style="width:65px; text-align:right;">${{s.vehicles}} veh</span>
        <span class="timer" style="color:${{colorText}};">${{timerText}}</span>
      </div>`;
  }});
  document.getElementById('signalList').innerHTML = html;
}}

const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');

function draw() {{
  ctx.clearRect(0, 0, 440, 440);

  ctx.fillStyle = '#1e2937';
  ctx.fillRect(0, 180, 440, 80);
  ctx.fillRect(180, 0, 80, 440);
  ctx.fillStyle = '#111827';
  ctx.fillRect(180, 180, 80, 80);

  const positions = {{1:[220, 130], 2:[320, 220], 3:[220, 310], 4:[130, 220]}};

  signalStates.forEach(s => {{
    const [x, y] = positions[s.id];
    let color = '#ef4444';
    if (s.color === 'green') color = '#22c55e';
    else if (s.color === 'yellow') color = '#eab308';
    else if (s.color === 'emergency') color = '#c026d3';

    ctx.shadowBlur = s.color === 'emergency' ? 40 : 25;
    ctx.shadowColor = color;
    ctx.beginPath();
    ctx.arc(x, y, 36, 0, Math.PI*2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.shadowBlur = 0;

    ctx.fillStyle = '#000';
    ctx.font = 'bold 22px Space Grotesk';
    ctx.textAlign = 'center';
    ctx.fillText('S' + s.id, x, y + 8);
  }});

  if (emgQueue.length > 0) {{
    ambulanceProgress += 7;
    if (ambulanceProgress > 700) ambulanceProgress = -100;

    const sid = emgQueue[0];
    let x = 220, y = 220, rot = 0;

    if (sid === 1) y = 440 - (ambulanceProgress % 580);
    else if (sid === 2) x = ambulanceProgress % 580;
    else if (sid === 3) y = ambulanceProgress % 580;
    else if (sid === 4) {{ x = 440 - (ambulanceProgress % 580); rot = Math.PI; }}

    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(rot);
    ctx.fillStyle = '#f8fafc';
    ctx.fillRect(-32, -16, 64, 32);
    ctx.fillStyle = '#ef4444';
    ctx.fillRect(-14, -13, 28, 8);
    ctx.fillRect(-7, -24, 14, 26);

    const flash = Math.sin(Date.now() / 50) > 0;
    ctx.fillStyle = flash ? '#ef4444' : '#3b82f6';
    ctx.fillRect(-24, -20, 10, 7);
    ctx.fillStyle = flash ? '#3b82f6' : '#ef4444';
    ctx.fillRect(14, -20, 10, 7);
    ctx.restore();
  }}
}}

setInterval(() => {{
  signalStates.forEach(sig => {{
    if (sig.timer === 999) return;
    if (sig.timer > 0) {{
      sig.timer--;
    }} else {{
      if (sig.phase === 'green') {{
        sig.phase = 'yellow'; sig.color = 'yellow'; sig.timer = 5;
      }} else if (sig.phase === 'yellow') {{
        sig.phase = 'red'; sig.color = 'red'; sig.timer = 25;
      }} else if (sig.phase === 'red') {{
        const next = (signalStates.findIndex(s => s.phase === 'green') + 1) % 4;
        signalStates.forEach(s => {{ if(s.timer !== 999) s.phase = 'red'; }});
        signalStates[next].phase = 'green';
        signalStates[next].color = 'green';
        signalStates[next].timer = 40;
      }}
    }}
  }});

  updateList();
  draw();

  const statusEl = document.getElementById('emgStatus');
  if (emgQueue.length > 0) {{
    statusEl.innerHTML = `🚑 <strong>EMERGENCY ACTIVE — Signal ${{emgQueue[0]}} has priority</strong>`;
    statusEl.style.color = '#c026d3';
  }} else {{
    statusEl.innerHTML = 'Normal Operation • Cycle Running';
    statusEl.style.color = '#64748b';
  }}
}}, 850);

updateList();
draw();
</script>
</body>
</html>
"""

import streamlit.components.v1 as components
components.html(html_code, height=680, scrolling=False)


# ─────────────────────────────────────────
# STATS
# ─────────────────────────────────────────
st.divider()
total_veh = sum(s["vehicles"] for s in signal_states)
c1, c2, c3, c4 = st.columns(4)
c1.metric("🚗 Total Vehicles", total_veh)
c2.metric("🟢 Current Green", f"S{current_green_id} — {green_dir}")
c3.metric("⏱ Timer", "∞" if emq else f"{signal_states[current_green_id-1]['timer']}s")
c4.metric("Status", "🚨 EMERGENCY MODE" if emq else "Normal Operation")