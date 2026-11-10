"""
SafeRide Sakhi – Rider App  (v2)
Changes vs v1:
  - Dark / Light mode toggle (CSS custom properties)
  - Sidebar navigation replacing bottom nav
  - Dashboard has Google Maps current-location component
  - Floating AI chat button (bottom-right) with female avatar
  - Refined typography and card design throughout
Run: streamlit run saferide_sakhi/dashboard/rider_app.py --server.port 8502
"""
from __future__ import annotations

import sys
import random
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import streamlit.components.v1 as components

from saferide_sakhi.dashboard.auth import login, register
from saferide_sakhi.llm_gateway import call as llm_call
from saferide_sakhi.config import GOOGLE_MAPS_API_KEY

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SafeRide Sakhi",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session defaults ──────────────────────────────────────────────────────────
for k, v in [
    ("user", None), ("page", "home"), ("dark_mode", False),
    ("wizard_step", 0), ("booking", {}),
    ("chat_history", []), ("show_chat", False),
]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── Theme CSS ─────────────────────────────────────────────────────────────────
DARK = st.session_state.dark_mode

_THEME = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {{
  --bg:        {bg};
  --surface:   {surface};
  --border:    {border};
  --text:      {text};
  --muted:     {muted};
  --accent:    {accent};
  --accent2:   {accent2};
  --card-shadow: {shadow};
}}

html, body, [class*="css"] {{
  font-family: 'Inter', sans-serif;
  background: var(--bg) !important;
  color: var(--text) !important;
}}

/* Streamlit chrome cleanup */
#MainMenu, footer {{ visibility: hidden; }}
.block-container {{ padding: 1rem 1.5rem 6rem !important; max-width: 900px; }}
section[data-testid="stSidebar"] {{ background: var(--surface) !important; }}
section[data-testid="stSidebar"] * {{ color: var(--text) !important; }}

/* Inputs */
input, textarea, select {{
  background: var(--surface) !important;
  color: var(--text) !important;
  border-color: var(--border) !important;
  border-radius: 10px !important;
}}

/* Primary button */
.stButton > button[kind="primary"] {{
  background: var(--accent) !important;
  color: #fff !important;
  border: none !important;
  border-radius: 24px !important;
  font-weight: 600 !important;
  height: 44px;
}}
.stButton > button[kind="secondary"] {{
  background: var(--surface) !important;
  color: var(--text) !important;
  border: 1px solid var(--border) !important;
  border-radius: 24px !important;
  height: 44px;
}}
.stButton > button:hover {{ opacity: 0.9; }}

/* Cards */
.safecard {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 16px 20px;
  margin-bottom: 12px;
  box-shadow: var(--card-shadow);
}}

/* Wizard steps */
.wizard-wrap {{
  display: flex; justify-content: space-between;
  padding: 12px 0 16px; margin-bottom: 8px;
  border-bottom: 1px solid var(--border);
}}
.wstep {{ text-align: center; font-size: 11px; color: var(--muted); font-weight: 500; flex:1; }}
.wstep.active {{ color: var(--accent); font-weight: 700; }}
.wstep.done   {{ color: var(--muted); }}
.wicon {{
  width: 32px; height: 32px; border-radius: 50%;
  background: var(--border); margin: 0 auto 4px;
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; border: 2px solid var(--border);
}}
.wicon.active {{ background: var(--accent); border-color: var(--accent); }}
.wicon.done   {{ background: var(--accent2); border-color: var(--accent2); }}

/* Chat bubbles */
.chat-user {{
  background: var(--accent); color: #fff;
  border-radius: 18px 18px 4px 18px;
  padding: 10px 14px; margin: 6px 0 6px 60px;
  font-size: 14px; line-height: 1.5;
}}
.chat-ai {{
  background: var(--surface); color: var(--text);
  border: 1px solid var(--border);
  border-radius: 18px 18px 18px 4px;
  padding: 10px 14px; margin: 6px 60px 6px 0;
  font-size: 14px; line-height: 1.5;
}}
.chat-lbl {{ font-size: 11px; color: var(--muted); margin-bottom: 2px; }}

/* Floating chat button */
.float-chat {{
  position: fixed; bottom: 24px; right: 24px; z-index: 9999;
  width: 64px; height: 64px; border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 4px 16px rgba(0,0,0,.3);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; font-size: 28px;
  border: 3px solid #fff;
  transition: transform .15s;
}}
.float-chat:hover {{ transform: scale(1.08); }}

/* Badge */
.badge {{
  display: inline-block; padding: 3px 10px; border-radius: 20px;
  font-size: 11px; font-weight: 600;
  background: var(--accent2); color: var(--accent);
}}

/* Hero gradient */
.hero {{
  background: linear-gradient(135deg, var(--accent) 0%, {hero2} 100%);
  border-radius: 18px; padding: 24px 28px; color: #fff;
  margin-bottom: 20px; position: relative; overflow: hidden;
}}
</style>
""".format(
    bg       ="#0f1117" if DARK else "#f8f9fb",
    surface  ="#1e2130" if DARK else "#ffffff",
    border   ="#2d3246" if DARK else "#e5e7eb",
    text     ="#f1f5f9" if DARK else "#111827",
    muted    ="#8892a4" if DARK else "#6b7280",
    accent   ="#2f855a" if DARK else "#1a6b3c",
    accent2  ="#1a3a2a" if DARK else "#d1fae5",
    shadow   ="0 2px 8px rgba(0,0,0,.4)" if DARK else "0 1px 4px rgba(0,0,0,.07)",
    hero2    ="#276749" if DARK else "#276749",
)

st.markdown(_THEME, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# FLOATING AI CHAT WIDGET
# ══════════════════════════════════════════════════════════════════════════════

_AI_SYSTEM = (
    "You are Sakhi, the warm and practical AI safety companion for SafeRide Sakhi, "
    "a women's night-travel safety platform in India. Help with ride booking, "
    "safety tips, emergency guidance, and how the AI agents protect the journey. "
    "Be concise (2-3 sentences), empowering, never alarmist. "
    "End with one practical action."
)


def _ai_reply(msg: str) -> str:
    hist = st.session_state.chat_history[-6:]
    ctx  = "\n".join(
        f"{'User' if m['role']=='user' else 'Sakhi'}: {m['content']}" for m in hist
    )
    prompt = f"{_AI_SYSTEM}\n\n{ctx}\nUser: {msg}\nSakhi:"
    resp = llm_call("groq", prompt, max_tokens=150, agent="sakhi_chat")
    if resp.success and resp.text.strip():
        return resp.text.strip()
    # Rule-based fallback
    m = msg.lower()
    if any(w in m for w in ["book","ride","cab","auto"]):
        return "Tap **Book Ride** in the sidebar → follow the 5-step wizard. A verified woman driver will be matched to you. 🚗"
    if any(w in m for w in ["safe","danger","scared","unsafe","threat"]):
        return "Press **SOS** immediately — the system alerts your trusted contact and control room in seconds. You are never alone. 🛡️"
    if any(w in m for w in ["driver","verify","check","id"]):
        return "Every driver's ID, police clearance and face are verified before each trip. If anything doesn't match, the ride is blocked. ✅"
    if any(w in m for w in ["emergency","police","112","help"]):
        return "Press SOS in the app or call **112** directly. Our control room can coordinate with emergency services on your behalf. 📞"
    return "I'm here to help with bookings, safety tips, driver checks or emergencies. What would you like to know? 😊"


def _render_float_chat() -> None:
    """Floating chat button + expandable panel."""
    if not st.session_state.user:
        return

    # Toggle button rendered as an HTML element (purely visual)
    # The actual toggle is a Streamlit button below it
    st.markdown("""
    <div class="float-chat" id="floatbtn" title="Ask Sakhi AI">
      <img src="https://api.dicebear.com/7.x/adventurer/svg?seed=Sakhi&backgroundColor=2f855a"
           style="width:52px;height:52px;border-radius:50%;object-fit:cover;" />
    </div>
    """, unsafe_allow_html=True)

    # Invisible Streamlit button overlaid on the float bubble
    # (Streamlit can't absolutely position buttons, so we show chat in sidebar toggle)
    with st.sidebar:
        st.markdown("---")
        show = st.session_state.show_chat
        label = "💬 Close Sakhi Chat" if show else "💬 Ask Sakhi AI"
        if st.button(label, key="float_toggle", use_container_width=True):
            st.session_state.show_chat = not st.session_state.show_chat
            st.rerun()

    if st.session_state.show_chat:
        _render_chat_panel()


def _render_chat_panel() -> None:
    """Inline chat panel rendered below main content."""
    st.markdown("---")
    # Female avatar header
    st.markdown("""
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:16px;">
      <img src="https://api.dicebear.com/7.x/adventurer/svg?seed=Sakhi&backgroundColor=2f855a"
           style="width:56px;height:56px;border-radius:50%;border:3px solid var(--accent);" />
      <div>
        <div style="font-size:18px;font-weight:700;">Sakhi AI Assistant</div>
        <div style="font-size:12px;color:var(--muted);">
          🟢 Online · Your safety companion
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Suggestion chips
    chips = ["How do I book a ride?", "What happens if I press SOS?",
             "How is my driver verified?", "Safety tips for night travel"]
    cols = st.columns(2)
    for i, chip in enumerate(chips):
        if cols[i % 2].button(chip, key=f"chip_{i}", use_container_width=True):
            st.session_state.chat_history.append({"role": "user", "content": chip})
            st.session_state.chat_history.append(
                {"role": "assistant", "content": _ai_reply(chip)})
            st.rerun()

    # Chat history
    for msg in st.session_state.chat_history[-12:]:
        if msg["role"] == "user":
            st.markdown(
                f'<div class="chat-lbl" style="text-align:right;">You</div>'
                f'<div class="chat-user">{msg["content"]}</div>',
                unsafe_allow_html=True)
        else:
            st.markdown(
                '<div style="display:flex;align-items:flex-start;gap:8px;">'
                '<img src="https://api.dicebear.com/7.x/adventurer/svg?seed=Sakhi&backgroundColor=2f855a"'
                ' style="width:28px;height:28px;border-radius:50%;flex-shrink:0;margin-top:4px;" />'
                f'<div><div class="chat-lbl">Sakhi</div>'
                f'<div class="chat-ai">{msg["content"]}</div></div></div>',
                unsafe_allow_html=True)

    # Input
    with st.form("chatform", clear_on_submit=True):
        ci, cs = st.columns([5, 1])
        user_in = ci.text_input("", placeholder="Ask Sakhi anything…",
                                 label_visibility="collapsed", key="chat_in")
        if cs.form_submit_button("➤") and user_in.strip():
            st.session_state.chat_history.append({"role": "user", "content": user_in.strip()})
            st.session_state.chat_history.append(
                {"role": "assistant", "content": _ai_reply(user_in.strip())})
            st.rerun()

    if st.session_state.chat_history:
        if st.button("🗑️ Clear chat", key="clearchat"):
            st.session_state.chat_history = []
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

def _sidebar() -> None:
    with st.sidebar:
        # Logo + app name
        st.markdown("""
        <div style="text-align:center;padding:16px 0 8px;">
          <div style="font-size:40px;">🛡️</div>
          <div style="font-size:18px;font-weight:800;letter-spacing:.5px;">
            SafeRide Sakhi</div>
          <div style="font-size:11px;color:var(--muted);">
            Women's Night-Travel Safety</div>
        </div>
        """, unsafe_allow_html=True)

        # User card
        if st.session_state.user:
            u = st.session_state.user
            st.markdown(f"""
            <div class="safecard" style="text-align:center;padding:12px;">
              <img src="https://api.dicebear.com/7.x/adventurer/svg?seed={u['name']}&backgroundColor=2f855a"
                   style="width:52px;height:52px;border-radius:50%;border:2px solid var(--accent);" />
              <div style="font-weight:600;margin-top:6px;">{u['name']}</div>
              <div style="font-size:11px;color:var(--muted);text-transform:capitalize;">
                {u['role']}</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("---")

        # Navigation
        pages = [
            ("🏠", "Home",          "home"),
            ("🚗", "Book a Ride",   "book"),
            ("📍", "My Trips",      "trips"),
            ("🛡️", "Safety Tips",  "safety"),
            ("📊", "Control Room",  "control"),
        ]
        for icon, label, pg in pages:
            active = st.session_state.page == pg
            btn_type = "primary" if active else "secondary"
            if st.button(f"{icon}  {label}", key=f"nav_{pg}",
                         use_container_width=True, type=btn_type):
                st.session_state.page = pg
                if pg == "book":
                    st.session_state.wizard_step = 0
                    st.session_state.booking = {}
                st.rerun()

        st.markdown("---")

        # Dark / Light toggle
        dm = st.session_state.dark_mode
        toggle_label = "☀️  Light Mode" if dm else "🌙  Dark Mode"
        if st.button(toggle_label, key="theme_toggle", use_container_width=True):
            st.session_state.dark_mode = not dm
            st.rerun()

        st.markdown("---")

        # Sign-out
        if st.session_state.user:
            if st.button("⏻  Sign Out", key="signout", use_container_width=True):
                for k in ["user","page","wizard_step","booking","chat_history","show_chat"]:
                    st.session_state[k] = (None if k=="user" else
                                            {} if k=="booking" else
                                            [] if k=="chat_history" else
                                            False if k=="show_chat" else "home")
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# LOGIN PAGE
# ══════════════════════════════════════════════════════════════════════════════

def page_login() -> None:
    # Centre the login form
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("""
        <div style="text-align:center;padding:32px 0 16px;">
          <img src="https://api.dicebear.com/7.x/adventurer/svg?seed=Sakhi&backgroundColor=2f855a"
               style="width:80px;height:80px;border-radius:50%;
                      border:3px solid var(--accent);margin-bottom:8px;" />
          <h1 style="font-size:28px;font-weight:800;margin:0;">SafeRide Sakhi</h1>
          <p style="color:var(--muted);font-size:14px;margin:4px 0 0;">
            Women's Night-Travel Safety Platform</p>
        </div>
        """, unsafe_allow_html=True)

        tab_in, tab_up = st.tabs(["Sign In", "Create Account"])

        with tab_in:
            st.markdown("<br>", unsafe_allow_html=True)
            email = st.text_input("Email", placeholder="you@example.com", key="li_email")
            pw    = st.text_input("Password", type="password",
                                   placeholder="Your password", key="li_pw")
            if st.button("Sign In →", type="primary", key="btn_li", use_container_width=True):
                if not email or not pw:
                    st.error("Please fill in both fields.")
                else:
                    user = login(email, pw)
                    if user:
                        st.session_state.user = user
                        st.session_state.page = "home"
                        st.rerun()
                    else:
                        st.error("Incorrect email or password.")
            st.markdown("""
            <div style="text-align:center;font-size:12px;color:var(--muted);
                        margin-top:16px;line-height:1.8;">
              Demo accounts:<br>
              <code>priya@saferide.in</code> / <code>rider123</code><br>
              <code>kavitha@saferide.in</code> / <code>driver123</code><br>
              <code>operator@saferide.in</code> / <code>operator123</code>
            </div>""", unsafe_allow_html=True)

        with tab_up:
            st.markdown("<br>", unsafe_allow_html=True)
            name  = st.text_input("Full name", key="su_name")
            email2= st.text_input("Email", placeholder="you@example.com", key="su_email")
            role  = st.selectbox("I am a", ["Rider", "Driver"], key="su_role")
            pw2   = st.text_input("Password", type="password", key="su_pw")
            pw2c  = st.text_input("Confirm password", type="password", key="su_pw2")
            if st.button("Create Account →", type="primary", key="btn_su",
                          use_container_width=True):
                if not all([name, email2, pw2, pw2c]):
                    st.error("Please fill in all fields.")
                elif pw2 != pw2c:
                    st.error("Passwords do not match.")
                elif len(pw2) < 6:
                    st.error("Password must be at least 6 characters.")
                else:
                    user = register(name, email2, pw2, role.lower())
                    if user is None:
                        st.error("Email already registered.")
                    else:
                        st.session_state.user = user
                        st.session_state.page = "home"
                        st.rerun()

        # Dark mode toggle on login page
        st.markdown("<br>", unsafe_allow_html=True)
        dm = st.session_state.dark_mode
        if st.button("🌙 Dark Mode" if not dm else "☀️ Light Mode",
                      key="login_theme", use_container_width=True):
            st.session_state.dark_mode = not dm
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# HOME PAGE  —  hero + live location map + quick actions
# ══════════════════════════════════════════════════════════════════════════════

def _live_map_html(api_key: str, height: int = 320) -> str:
    """Google Maps iframe that centres on browser geolocation."""
    maps_src = (
        f"https://maps.googleapis.com/maps/api/js"
        f"?key={api_key}&callback=initMap&v=weekly"
        f"&solution_channel=GMP_CCS_geolocation_v2"
    )
    no_key = "" if api_key else (
        '<div style="position:absolute;top:8px;left:50%;transform:translateX(-50%);'
        'background:#fef2f2;border:1px solid #fca5a5;border-radius:6px;'
        'padding:6px 14px;font-size:12px;color:#991b1b;z-index:10;">'
        '⚠️ Add GOOGLE_MAPS_API_KEY to .env for full maps</div>'
    )
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  * {{ margin:0;padding:0;box-sizing:border-box; }}
  html,body,#map {{ width:100%;height:{height}px; }}
  .custom-map-control-button {{
    background:#fff;border:0;border-radius:2px;
    box-shadow:0 1px 4px -1px rgba(0,0,0,.3);
    margin:10px;padding:0 .5em;
    font:400 14px Roboto,Arial,sans-serif;
    overflow:hidden;height:36px;cursor:pointer;
  }}
  .custom-map-control-button:hover {{ background:#ebebeb; }}
  #mtype {{
    position:absolute;bottom:32px;right:10px;z-index:5;
    background:#fff;border:1px solid #e5e7eb;border-radius:8px;
    padding:6px 10px;font:400 12px Roboto,Arial,sans-serif;
    box-shadow:0 1px 4px rgba(0,0,0,.12);
  }}
</style>
</head>
<body>
{no_key}
<div id="map"></div>
<div id="mtype">
  <label><input type="radio" name="mt" value="roadmap" checked onchange="setT(this.value)"> Map</label>&nbsp;
  <label><input type="radio" name="mt" value="satellite" onchange="setT(this.value)"> Satellite</label>
</div>
<script>
let map, iw, myMarker;
function initMap() {{
  map = new google.maps.Map(document.getElementById("map"), {{
    center: {{lat:12.9716,lng:77.5946}}, zoom:14,
    mapTypeId:"roadmap", mapTypeControl:false,
    streetViewControl:false, fullscreenControl:true,
  }});
  iw = new google.maps.InfoWindow();

  const btn = document.createElement("button");
  btn.textContent = "📍 My Location";
  btn.className = "custom-map-control-button";
  map.controls[google.maps.ControlPosition.TOP_CENTER].push(btn);

  btn.addEventListener("click", () => {{
    if (!navigator.geolocation) {{
      iw.setPosition(map.getCenter());
      iw.setContent("Geolocation not supported by your browser.");
      iw.open(map); return;
    }}
    navigator.geolocation.getCurrentPosition(pos => {{
      const loc = {{lat: pos.coords.latitude, lng: pos.coords.longitude}};
      if (myMarker) myMarker.setPosition(loc);
      else myMarker = new google.maps.Marker({{
        position: loc, map,
        icon: {{
          path: google.maps.SymbolPath.CIRCLE,
          fillColor:"#2f855a",fillOpacity:1,
          strokeColor:"#fff",strokeWeight:3,scale:10,
        }},
        title:"You are here",
      }});
      iw.setContent('<b>You are here</b><br>Lat: ' + loc.lat.toFixed(5) + ', Lng: ' + loc.lng.toFixed(5));
      iw.open(map, myMarker);
      map.panTo(loc);
      map.setZoom(15);
    }}, () => {{
      iw.setPosition(map.getCenter());
      iw.setContent("Could not get location. Please allow location access.");
      iw.open(map);
    }});
  }});
}}
window.setT = t => map && map.setMapTypeId(t);
window.initMap = initMap;
</script>
<script src="{maps_src}" defer></script>
</body></html>"""


def page_home() -> None:
    user = st.session_state.user
    name = user["name"].split()[0]

    # Hero banner
    st.markdown(f"""
    <div class="hero">
      <div style="display:flex;align-items:center;gap:16px;">
        <img src="https://api.dicebear.com/7.x/adventurer/svg?seed={user['name']}&backgroundColor=276749"
             style="width:64px;height:64px;border-radius:50%;border:3px solid rgba(255,255,255,.6);" />
        <div>
          <div style="font-size:22px;font-weight:800;">Hello, {name}! 👋</div>
          <div style="font-size:13px;opacity:.85;margin-top:2px;">
            Your safety agents are active and watching over you.</div>
          <span style="background:rgba(255,255,255,.25);border-radius:20px;
                padding:3px 10px;font-size:11px;font-weight:600;margin-top:6px;
                display:inline-block;">🛡️ All systems operational</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Quick action cards
    st.markdown("#### Quick Actions")
    c1, c2, c3, c4 = st.columns(4)
    actions = [
        ("🚗", "Book Ride",   "book"),
        ("📍", "My Trips",    "trips"),
        ("🛡️", "Safety Tips","safety"),
        ("📊", "Control Room","control"),
    ]
    for col, (icon, label, pg) in zip([c1,c2,c3,c4], actions):
        with col:
            st.markdown(f"""
            <div class="safecard" style="text-align:center;cursor:pointer;padding:18px 8px;">
              <div style="font-size:28px;">{icon}</div>
              <div style="font-size:13px;font-weight:600;margin-top:6px;">{label}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(label, key=f"qa_{pg}", use_container_width=True):
                st.session_state.page = pg
                if pg == "book":
                    st.session_state.wizard_step = 0
                    st.session_state.booking = {}
                st.rerun()

    st.markdown("---")

    # Live location map
    st.markdown("#### 📍 Your Current Location")
    st.caption("Click **My Location** on the map to centre on your real position.")
    components.html(_live_map_html(GOOGLE_MAPS_API_KEY, height=320), height=320)

    st.markdown("---")

    # Safety status
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("#### 🛡️ Agent Status")
        agents = [
            ("✅", "Route Monitor",       "Active"),
            ("✅", "Driver Verifier",     "Active"),
            ("✅", "Risk Scorer",         "Active"),
            ("✅", "Escalation Agent",    "Standby"),
        ]
        for ico, name_, state in agents:
            st.markdown(
                f'<div class="safecard" style="display:flex;justify-content:space-between;'
                f'align-items:center;padding:10px 14px;">'
                f'<span style="font-size:13px;">{ico} {name_}</span>'
                f'<span style="font-size:11px;font-weight:600;color:var(--accent);">{state}</span>'
                f'</div>', unsafe_allow_html=True)
    with col_b:
        st.markdown("#### 💡 Safety Tips")
        tips = [
            ("📱", "Share your trip before boarding."),
            ("🔍", "Verify your driver's photo matches the app."),
            ("🌙", "Prefer lit pickup points at night."),
            ("📞", "SOS alerts contacts instantly."),
        ]
        for icon, tip in tips:
            st.markdown(
                f'<div class="safecard" style="display:flex;gap:10px;align-items:flex-start;'
                f'padding:10px 14px;">'
                f'<span style="font-size:18px;">{icon}</span>'
                f'<span style="font-size:13px;color:var(--muted);">{tip}</span></div>',
                unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# BOOK RIDE WIZARD
# ══════════════════════════════════════════════════════════════════════════════

STEPS      = ["INFO", "ROUTE", "SCHEDULE", "DETAILS", "REVIEW"]
STEP_ICONS = ["📋",   "📍",    "📅",       "🚗",      "✅"]


def _wizard_bar(step: int) -> None:
    cols = st.columns(len(STEPS))
    for i, (lbl, ico) in enumerate(zip(STEPS, STEP_ICONS)):
        cls  = "active" if i == step else ("done" if i < step else "wstep")
        icls = "active" if i == step else ("done"  if i < step else "")
        cols[i].markdown(
            f'<div class="wstep {cls}">'
            f'<div class="wicon {icls}">{ico}</div>{lbl}</div>',
            unsafe_allow_html=True)


def page_book() -> None:
    st.markdown("## 🚗 Book a Ride")
    step = st.session_state.wizard_step
    _wizard_bar(step)
    st.markdown("---")

    [_step_info, _step_route, _step_schedule, _step_details, _step_review][min(step,4)]()


def _step_info() -> None:
    st.markdown("### Where would you like to go?")
    c1, c2 = st.columns(2)
    if c1.button("One Way",
                  type="primary" if st.session_state.booking.get("trip_type","One Way")=="One Way" else "secondary"):
        st.session_state.booking["trip_type"] = "One Way"; st.rerun()
    if c2.button("Round Trip",
                  type="primary" if st.session_state.booking.get("trip_type")=="Round Trip" else "secondary"):
        st.session_state.booking["trip_type"] = "Round Trip"; st.rerun()

    st.markdown("---")
    name  = st.text_input("Your name", value=st.session_state.user["name"])
    phone = st.text_input("Mobile number", placeholder="+91 9XXXXXXXXX")
    tc    = st.text_input("Trusted contact number")
    cons  = st.checkbox("I consent to sharing my location during the trip", value=True)
    st.session_state.booking.update({"name":name,"phone":phone,"trusted_contact":tc,"consent":cons})
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Next: Route →", type="primary"):
        if not phone: st.error("Mobile number is required.")
        else: st.session_state.wizard_step += 1; st.rerun()


def _step_route() -> None:
    st.markdown("### 📍 Set Your Route")
    b = st.session_state.booking
    miles = b.get("distance_miles", 0.0)
    col_l, col_r = st.columns([3,1])
    col_l.radio("Direction",["Going To Provider","Leaving From Provider"],
                key="dir_r",label_visibility="visible")
    col_r.markdown(
        f'<div class="safecard" style="text-align:center;padding:8px;">'
        f'<div style="font-size:18px;font-weight:700;">{miles:.1f}</div>'
        f'<div style="font-size:11px;color:var(--muted);">Miles</div></div>',
        unsafe_allow_html=True)

    pickup  = st.text_input("🔍 Pickup Location *", placeholder="Search pickup…")
    dropoff = st.text_input("🔍 Drop-Off / Provider Location *", placeholder="Search destination…")
    st.caption("Call (800) 123-4567 if your provider is not listed")

    if pickup and dropoff:
        d = round(random.uniform(1.5, 18.5), 2)
        st.session_state.booking.update({"pickup":pickup,"dropoff":dropoff,"distance_miles":d,"direction":st.session_state.get("dir_r","Going To Provider")})
        st.info(f"📏 Estimated distance: **{d} miles**")

    st.markdown("<br>", unsafe_allow_html=True)
    c1,c2 = st.columns(2)
    if c1.button("← Back", type="secondary"):
        st.session_state.wizard_step -= 1; st.rerun()
    if c2.button("Next: Schedule →", type="primary"):
        if not pickup or not dropoff: st.error("Please enter both locations.")
        else: st.session_state.wizard_step += 1; st.rerun()


def _step_schedule() -> None:
    st.markdown("### 📅 Schedule Your Ride")
    ride_date = st.date_input("Pickup date", value=datetime.now().date()+timedelta(days=1))
    ride_time = st.time_input("Pickup time", value=datetime.now().replace(hour=22,minute=0).time())
    recur     = st.selectbox("Frequency", ["One-time","Daily","Weekly (Mon–Fri)","Custom"])
    notes     = st.text_area("Special instructions", placeholder="e.g. Meet at main gate", height=80)
    st.session_state.booking.update({"ride_date":str(ride_date),"ride_time":str(ride_time),"recurring":recur,"notes":notes})
    st.markdown("<br>", unsafe_allow_html=True)
    c1,c2 = st.columns(2)
    if c1.button("← Back", type="secondary"):
        st.session_state.wizard_step -= 1; st.rerun()
    if c2.button("Next: Details →", type="primary"):
        st.session_state.wizard_step += 1; st.rerun()


def _step_details() -> None:
    st.markdown("### 🚗 Ride Preferences")
    vehicle      = st.selectbox("Vehicle", ["Any available","Sedan","SUV","Auto-rickshaw"])
    women_driver = st.checkbox("Women driver preferred", value=True)
    share_trip   = st.checkbox("Share live trip with trusted contact", value=True)
    record       = st.checkbox("Enable audio safety recording (opt-in)", value=False)
    payment      = st.radio("Payment", ["Cash","UPI","Card"], horizontal=True)
    st.session_state.booking.update({"vehicle":vehicle,"women_driver":women_driver,"share_trip":share_trip,"record":record,"payment":payment})
    st.markdown("<br>", unsafe_allow_html=True)
    c1,c2 = st.columns(2)
    if c1.button("← Back", type="secondary"):
        st.session_state.wizard_step -= 1; st.rerun()
    if c2.button("Next: Review →", type="primary"):
        st.session_state.wizard_step += 1; st.rerun()


def _step_review() -> None:
    st.markdown("### ✅ Review & Confirm")
    b = st.session_state.booking
    rows = [
        ("👤 Rider",        b.get("name","")),
        ("📱 Phone",        b.get("phone","")),
        ("🗺️ Trip type",   b.get("trip_type","One Way")),
        ("📍 From",         b.get("pickup","")),
        ("🏥 To",           b.get("dropoff","")),
        ("📏 Distance",     f"{b.get('distance_miles',0):.1f} miles"),
        ("📅 Date",         f"{b.get('ride_date','')} {b.get('ride_time','')}"),
        ("🔁 Recurring",    b.get("recurring","One-time")),
        ("🚗 Vehicle",      b.get("vehicle","Any")),
        ("👩 Women driver", "Yes ✅" if b.get("women_driver") else "No"),
        ("💳 Payment",      b.get("payment","Cash")),
        ("📡 Share trip",   "Yes ✅" if b.get("share_trip") else "No"),
    ]
    st.markdown('<div class="safecard">', unsafe_allow_html=True)
    for lbl, val in rows:
        if val:
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;padding:6px 0;'
                f'border-bottom:1px solid var(--border);font-size:13px;">'
                f'<span style="color:var(--muted);">{lbl}</span>'
                f'<span style="font-weight:600;">{val}</span></div>',
                unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("**Your safety agents will automatically:**")
    st.markdown("- ✅ Verify driver ID, police clearance and face\n"
                "- ✅ Monitor your route in real time\n"
                "- ✅ Alert your trusted contact if any anomaly is detected\n"
                "- ✅ Confirm your safe arrival")

    c1, c2 = st.columns(2)
    if c1.button("← Back", type="secondary"):
        st.session_state.wizard_step -= 1; st.rerun()
    if c2.button("🚗 Confirm Booking", type="primary"):
        st.balloons()
        st.success("🎉 Ride booked! Safety agents are activated.")
        st.markdown("""
        <div class="safecard" style="text-align:center;padding:24px;">
          <div style="font-size:40px;">🛡️</div>
          <div style="font-size:18px;font-weight:700;margin:8px 0 6px;">
            Booking Confirmed</div>
          <div style="font-size:13px;color:var(--muted);">
            Your driver will arrive at the pickup point.<br>
            Your trusted contact has been notified.
          </div>
        </div>""", unsafe_allow_html=True)
        if st.button("← Back to Home"):
            st.session_state.page = "home"
            st.session_state.wizard_step = 0
            st.session_state.booking = {}
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# MY TRIPS
# ══════════════════════════════════════════════════════════════════════════════

def page_trips() -> None:
    st.markdown("## 📍 My Trips")
    trips = [
        {"date":"2026-11-10","from":"Indiranagar","to":"Whitefield","status":"✅ Completed","risk":"Safe"},
        {"date":"2026-11-09","from":"Koramangala","to":"Marathahalli","status":"✅ Completed","risk":"Safe"},
        {"date":"2026-11-08","from":"MG Road","to":"Electronic City","status":"✅ Completed","risk":"⚠️ Nudge sent"},
    ]
    for t in trips:
        st.markdown(
            f'<div class="safecard"><div style="display:flex;justify-content:space-between;">'
            f'<div><div style="font-weight:600;">{t["from"]} → {t["to"]}</div>'
            f'<div style="font-size:12px;color:var(--muted);">{t["date"]}</div></div>'
            f'<div style="text-align:right;font-size:13px;">{t["status"]}<br>'
            f'<span style="font-size:11px;color:var(--muted);">{t["risk"]}</span></div>'
            f'</div></div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SAFETY TIPS
# ══════════════════════════════════════════════════════════════════════════════

def page_safety() -> None:
    st.markdown("## 🛡️ Safety Tips & Guidelines")
    tips = [
        ("📱","Before Boarding","Always verify the driver's name, photo and vehicle number match the app before getting in."),
        ("🔍","During the Ride","Share your live trip with a trusted contact. Keep your phone charged."),
        ("🌙","Night Travel","Choose lit, busy pickup points. Prefer verified women drivers after 10 pm."),
        ("🆘","In an Emergency","Press the SOS button — the system contacts your trusted person and the control room in seconds."),
        ("📞","112","You can always call 112 directly. Our agents can also coordinate with emergency services on your behalf."),
        ("🚫","Red Flags","Driver doesn't match the photo · Asks you to cancel and rebook · Behaves aggressively — exit safely immediately."),
    ]
    for icon, title, body in tips:
        st.markdown(
            f'<div class="safecard"><div style="display:flex;gap:14px;">'
            f'<div style="font-size:28px;flex-shrink:0;">{icon}</div>'
            f'<div><div style="font-weight:700;margin-bottom:4px;">{title}</div>'
            f'<div style="font-size:13px;color:var(--muted);">{body}</div>'
            f'</div></div></div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# CONTROL ROOM (link through to operator dashboard)
# ══════════════════════════════════════════════════════════════════════════════

def page_control() -> None:
    st.markdown("## 📊 Operator Control Room")
    st.info("The full operator dashboard (live trip map, alert queue, case detail, metrics) runs on port 8501.")
    st.markdown("""
    <div class="safecard" style="text-align:center;padding:28px;">
      <div style="font-size:40px;">🖥️</div>
      <div style="font-size:16px;font-weight:700;margin:10px 0 6px;">
        Open the Operator Dashboard</div>
      <div style="font-size:13px;color:var(--muted);margin-bottom:16px;">
        Live trips on Google Maps · Alert queue · Case detail · Metrics</div>
      <a href="http://localhost:8501" target="_blank"
         style="background:var(--accent);color:#fff;border-radius:24px;
                padding:10px 28px;font-weight:600;text-decoration:none;font-size:14px;">
        Open Control Room →
      </a>
    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# ROUTER
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    if not st.session_state.user:
        page_login()
        return

    _sidebar()

    page = st.session_state.page
    if   page == "home":    page_home()
    elif page == "book":    page_book()
    elif page == "trips":   page_trips()
    elif page == "safety":  page_safety()
    elif page == "control": page_control()
    else:                   page_home()

    _render_float_chat()


if __name__ == "__main__":
    main()
