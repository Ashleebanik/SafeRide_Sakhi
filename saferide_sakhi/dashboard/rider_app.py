"""
SafeRide Sakhi – Rider App  (v3)
- Blue AI palette from the shield-woman image
- Floating chat icon opens a real working modal (HTML/JS overlay)
- Chat sends messages via Streamlit query params trick (st.query_params)
- Control Room removed
- Avatar is the AI shield-woman image
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

# ── AI avatar – the shield-woman image stored as a data URL would be huge,
#    so we reference the local file path via a Streamlit static serve trick.
#    For portability we embed a high-quality base64 thumbnail or use the
#    uploaded file path directly.
AI_AVATAR_PATH = (
    r"c:\Users\Ashlee Banik\OneDrive\Pictures\Screenshots"
    r"\Screenshot 2026-11-11 011823.png"
)

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
    ("pending_msg", ""),
]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── Colour palette extracted from the image ───────────────────────────────────
# Deep navy bg, electric blue accent, cyan glow, indigo surface
DARK = st.session_state.dark_mode

# Light mode: white bg but blue accent family
# Dark mode: deep navy bg with blue/cyan accents
_P = dict(
    bg       = "#0a0e1a" if DARK else "#f0f4ff",
    surface  = "#111827" if DARK else "#ffffff",
    border   = "#1e3a5f" if DARK else "#c7d7f5",
    text     = "#e2eaff" if DARK else "#0d1b3e",
    muted    = "#6b83b0" if DARK else "#4a6fa5",
    accent   = "#2563eb",           # electric blue (same both modes)
    accent_h = "#1d4ed8",           # darker blue hover
    cyan     = "#06b6d4",           # cyan glow
    glow     = "#1e40af",           # deep indigo
    hero1    = "#1e3a8a",           # hero gradient start
    hero2    = "#0e7490",           # hero gradient end (teal)
    shadow   = "0 4px 20px rgba(37,99,235,.35)" if DARK else "0 2px 12px rgba(37,99,235,.15)",
    ai_bg    = "#0f172a" if DARK else "#eff6ff",
)

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {{
  --bg:       {bg};
  --surface:  {surface};
  --border:   {border};
  --text:     {text};
  --muted:    {muted};
  --accent:   {accent};
  --accent-h: {accent_h};
  --cyan:     {cyan};
  --glow:     {glow};
  --hero1:    {hero1};
  --hero2:    {hero2};
  --shadow:   {shadow};
  --ai-bg:    {ai_bg};
}}

html, body, [class*="css"] {{
  font-family: 'Inter', sans-serif !important;
  background: var(--bg) !important;
  color: var(--text) !important;
}}

#MainMenu, footer {{ visibility: hidden; }}
.block-container {{ padding: 1rem 1.5rem 5rem !important; max-width: 900px; }}
section[data-testid="stSidebar"] {{ background: var(--surface) !important; border-right: 1px solid var(--border); }}
section[data-testid="stSidebar"] * {{ color: var(--text) !important; }}

input, textarea, select {{
  background: var(--surface) !important;
  color: var(--text) !important;
  border-color: var(--border) !important;
  border-radius: 10px !important;
}}

.stButton > button[kind="primary"] {{
  background: linear-gradient(135deg, var(--accent), var(--glow)) !important;
  color: #fff !important; border: none !important;
  border-radius: 24px !important; font-weight: 600 !important; height: 44px;
  box-shadow: 0 2px 10px rgba(37,99,235,.4);
}}
.stButton > button[kind="secondary"] {{
  background: var(--surface) !important; color: var(--text) !important;
  border: 1px solid var(--border) !important;
  border-radius: 24px !important; height: 44px;
}}
.stButton > button:hover {{ opacity: .9; }}

.safecard {{
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 14px; padding: 16px 20px; margin-bottom: 12px;
  box-shadow: var(--shadow);
}}

.hero {{
  background: linear-gradient(135deg, var(--hero1) 0%, var(--hero2) 100%);
  border-radius: 18px; padding: 24px 28px; color: #fff;
  margin-bottom: 20px; position: relative; overflow: hidden;
  border: 1px solid rgba(6,182,212,.3);
  box-shadow: 0 0 40px rgba(6,182,212,.15);
}}

.wstep {{ text-align:center; font-size:11px; color:var(--muted); font-weight:500; flex:1; }}
.wstep.active {{ color:var(--accent); font-weight:700; }}
.wicon {{
  width:32px; height:32px; border-radius:50%;
  background:var(--border); margin:0 auto 4px;
  display:flex; align-items:center; justify-content:center;
  font-size:15px; border:2px solid var(--border);
}}
.wicon.active {{ background:var(--accent); border-color:var(--accent); }}
.wicon.done   {{ background:var(--glow); border-color:var(--glow); }}

/* Chat bubble colours use the blue palette */
.chat-user {{
  background: linear-gradient(135deg, var(--accent), var(--glow));
  color: #fff; border-radius: 18px 18px 4px 18px;
  padding: 10px 14px; margin: 6px 0 6px 52px; font-size:14px; line-height:1.5;
}}
.chat-ai {{
  background: var(--ai-bg); color: var(--text);
  border: 1px solid var(--border);
  border-radius: 18px 18px 18px 4px;
  padding: 10px 14px; margin: 6px 52px 6px 0; font-size:14px; line-height:1.5;
}}
.chat-lbl {{ font-size:11px; color:var(--muted); margin-bottom:2px; }}

/* Floating button – real clickable Streamlit button restyled */
div[data-testid="stButton"].float-btn > button {{
  position: fixed !important;
  bottom: 24px !important;
  right: 24px !important;
  width: 68px !important;
  height: 68px !important;
  border-radius: 50% !important;
  padding: 0 !important;
  background: transparent !important;
  border: none !important;
  box-shadow: 0 0 24px rgba(6,182,212,.6), 0 4px 16px rgba(0,0,0,.4) !important;
  z-index: 9999 !important;
  overflow: hidden !important;
}}
</style>
""".format(**_P)

st.markdown(_CSS, unsafe_allow_html=True)

# ── Load and encode AI avatar image ──────────────────────────────────────────
import base64

def _avatar_b64() -> str:
    """Return the shield-woman image as a base64 data URI."""
    try:
        with open(AI_AVATAR_PATH, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        return f"data:image/png;base64,{data}"
    except Exception:
        # Fallback: blue robot emoji rendered as SVG placeholder
        return "https://api.dicebear.com/7.x/bottts/svg?seed=Sakhi&backgroundColor=1e3a8a&primaryColor=2563eb"

AI_AVATAR = _avatar_b64()

# ══════════════════════════════════════════════════════════════════════════════
# AI REPLY
# ══════════════════════════════════════════════════════════════════════════════

_AI_SYSTEM = (
    "You are Sakhi, the AI safety companion for SafeRide Sakhi, "
    "a women's night-travel safety platform in India. "
    "Help with ride booking, safety tips, emergency guidance, and the AI agents. "
    "Be concise (2-3 sentences), empowering, never alarmist. "
    "End with one practical action."
)


def _ai_reply(msg: str) -> str:
    hist = st.session_state.chat_history[-6:]
    ctx  = "\n".join(f"{'User' if m['role']=='user' else 'Sakhi'}: {m['content']}" for m in hist)
    prompt = f"{_AI_SYSTEM}\n\n{ctx}\nUser: {msg}\nSakhi:"
    resp = llm_call("groq", prompt, max_tokens=150, agent="sakhi_chat")
    if resp.success and resp.text.strip():
        return resp.text.strip()
    m = msg.lower()
    if any(w in m for w in ["book","ride","cab","auto"]):
        return "Go to **Book a Ride** in the sidebar and follow the 5-step wizard. A verified woman driver will be matched to you. 🚗"
    if any(w in m for w in ["safe","danger","scared","unsafe","threat"]):
        return "Press **SOS** immediately — the system alerts your trusted contact and the safety team in seconds. You are never alone. 🛡️"
    if any(w in m for w in ["driver","verify","check","id"]):
        return "Every driver's ID, police clearance and face are verified before each trip. A mismatch blocks the ride automatically. ✅"
    if any(w in m for w in ["emergency","police","112","help"]):
        return "Call **112** directly, or press SOS — our agents coordinate with emergency services on your behalf. 📞"
    return "I can help with bookings, safety tips, driver checks or emergencies. What would you like to know? 😊"


# ══════════════════════════════════════════════════════════════════════════════
# FLOATING CHAT – proper working implementation
# Strategy: render a full-page overlay HTML+JS component that:
#   1. Shows the avatar button fixed bottom-right (always visible)
#   2. On click, opens a slide-up chat modal inside the iframe
#   3. Uses st.query_params to pass messages back to Python
# ══════════════════════════════════════════════════════════════════════════════

def _build_chat_html() -> str:
    """
    Self-contained chat modal.
    The send button posts to the parent Streamlit page via
    window.parent.postMessage so Streamlit can read it through
    a hidden text_input that captures the value.
    """
    # Build message history HTML
    msgs_html = ""
    for m in st.session_state.chat_history[-20:]:
        if m["role"] == "user":
            msgs_html += (
                f'<div class="msg-row user">'
                f'<div class="bubble user">{m["content"]}</div>'
                f'</div>'
            )
        else:
            msgs_html += (
                f'<div class="msg-row ai">'
                f'<img class="av-sm" src="{AI_AVATAR}" />'
                f'<div class="bubble ai">{m["content"]}</div>'
                f'</div>'
            )

    surface  = _P["surface"]
    border   = _P["border"]
    text_col = _P["text"]
    accent   = _P["accent"]
    glow     = _P["glow"]
    cyan     = _P["cyan"]
    ai_bg    = _P["ai_bg"]
    bg       = _P["bg"]

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
* {{ margin:0;padding:0;box-sizing:border-box; }}
body {{ background:transparent; font-family:'Inter',system-ui,sans-serif; overflow:hidden; }}

/* ── Float button ── */
#fab {{
  position:fixed; bottom:20px; right:20px;
  width:68px; height:68px; border-radius:50%;
  cursor:pointer; z-index:9999;
  box-shadow: 0 0 0 3px {cyan}44, 0 0 28px {cyan}88, 0 4px 16px rgba(0,0,0,.5);
  border:3px solid {cyan};
  overflow:hidden; transition:transform .2s;
  animation: pulse 2.5s infinite;
}}
#fab:hover {{ transform:scale(1.08); }}
#fab img {{ width:100%;height:100%;object-fit:cover; }}

@keyframes pulse {{
  0%   {{ box-shadow: 0 0 0 0 {cyan}66, 0 4px 16px rgba(0,0,0,.5); }}
  70%  {{ box-shadow: 0 0 0 12px {cyan}00, 0 4px 16px rgba(0,0,0,.5); }}
  100% {{ box-shadow: 0 0 0 0 {cyan}00, 0 4px 16px rgba(0,0,0,.5); }}
}}

/* ── Modal overlay ── */
#overlay {{
  display:none; position:fixed; inset:0; z-index:9998;
  background:rgba(0,0,0,.55); backdrop-filter:blur(4px);
}}
#modal {{
  display:none; position:fixed;
  bottom:100px; right:16px;
  width:360px; max-height:560px;
  background:{surface}; border:1px solid {border};
  border-radius:20px; z-index:9999;
  box-shadow: 0 0 40px {cyan}44, 0 8px 40px rgba(0,0,0,.5);
  flex-direction:column; overflow:hidden;
  animation:slideUp .25s ease;
}}
@keyframes slideUp {{ from{{ transform:translateY(30px);opacity:0 }} to{{ transform:translateY(0);opacity:1 }} }}

/* ── Modal header ── */
.mhead {{
  background:linear-gradient(135deg,{glow},{accent});
  padding:14px 16px; display:flex; align-items:center; gap:12px; flex-shrink:0;
}}
.mhead img {{ width:44px;height:44px;border-radius:50%;border:2px solid {cyan};flex-shrink:0; }}
.mhead-text .title {{ font-size:15px;font-weight:700;color:#fff; }}
.mhead-text .sub {{ font-size:11px;color:rgba(255,255,255,.7); }}
.close-btn {{
  margin-left:auto; background:rgba(255,255,255,.15);
  border:none; color:#fff; width:28px; height:28px;
  border-radius:50%; cursor:pointer; font-size:16px;
  display:flex;align-items:center;justify-content:center;
}}
.close-btn:hover {{ background:rgba(255,255,255,.3); }}

/* ── Chips ── */
.chips {{ padding:10px 12px 4px; display:flex; flex-wrap:wrap; gap:6px; flex-shrink:0; }}
.chip {{
  background:{ai_bg}; border:1px solid {border};
  color:{text_col}; border-radius:20px;
  padding:5px 12px; font-size:11px; cursor:pointer; white-space:nowrap;
}}
.chip:hover {{ background:{accent}22; border-color:{accent}; color:{accent}; }}

/* ── Messages ── */
#msgs {{
  flex:1; overflow-y:auto; padding:12px;
  display:flex; flex-direction:column; gap:8px;
  scrollbar-width:thin; scrollbar-color:{border} transparent;
}}
.msg-row {{ display:flex; align-items:flex-end; gap:8px; }}
.msg-row.user {{ flex-direction:row-reverse; }}
.bubble {{
  max-width:76%; padding:9px 13px; font-size:13px; line-height:1.5;
  border-radius:16px;
}}
.bubble.user {{
  background:linear-gradient(135deg,{accent},{glow});
  color:#fff; border-radius:16px 16px 4px 16px;
}}
.bubble.ai {{
  background:{ai_bg}; color:{text_col};
  border:1px solid {border}; border-radius:16px 16px 16px 4px;
}}
.av-sm {{ width:28px;height:28px;border-radius:50%;flex-shrink:0;border:1px solid {cyan}; }}

/* Typing indicator */
.typing {{ display:flex;gap:4px;padding:8px 12px; }}
.typing span {{
  width:7px;height:7px;border-radius:50%;background:{accent};
  animation:blink 1.2s infinite; display:inline-block;
}}
.typing span:nth-child(2){{ animation-delay:.2s; }}
.typing span:nth-child(3){{ animation-delay:.4s; }}
@keyframes blink{{ 0%,80%,100%{{opacity:.2}} 40%{{opacity:1}} }}

/* ── Input row ── */
.input-row {{
  display:flex; gap:8px; padding:10px 12px;
  border-top:1px solid {border}; flex-shrink:0;
  background:{surface};
}}
#chat-input {{
  flex:1; background:{ai_bg}; color:{text_col};
  border:1px solid {border}; border-radius:20px;
  padding:8px 14px; font-size:13px; outline:none;
}}
#chat-input:focus {{ border-color:{accent}; }}
#send-btn {{
  width:38px;height:38px;border-radius:50%;
  background:linear-gradient(135deg,{accent},{glow});
  border:none; color:#fff; font-size:16px; cursor:pointer;
  display:flex;align-items:center;justify-content:center;
  flex-shrink:0; box-shadow:0 2px 8px {accent}66;
}}
#send-btn:hover {{ opacity:.85; }}
</style>
</head>
<body>

<!-- Floating button -->
<div id="fab" onclick="openChat()" title="Ask Sakhi AI">
  <img src="{AI_AVATAR}" alt="Sakhi AI" />
</div>

<!-- Overlay -->
<div id="overlay" onclick="closeChat()"></div>

<!-- Modal -->
<div id="modal">
  <!-- Header -->
  <div class="mhead">
    <img src="{AI_AVATAR}" alt="Sakhi" />
    <div class="mhead-text">
      <div class="title">Sakhi AI Assistant</div>
      <div class="sub">🟢 Online · Your safety companion</div>
    </div>
    <button class="close-btn" onclick="closeChat()">✕</button>
  </div>

  <!-- Quick chips -->
  <div class="chips">
    <div class="chip" onclick="sendChip('How do I book a safe ride?')">Book a ride</div>
    <div class="chip" onclick="sendChip('What happens if I press SOS?')">SOS help</div>
    <div class="chip" onclick="sendChip('How is my driver verified?')">Driver check</div>
    <div class="chip" onclick="sendChip('Safety tips for night travel')">Night safety</div>
  </div>

  <!-- Messages -->
  <div id="msgs">
    {msgs_html}
    {"" if st.session_state.chat_history else
     f'<div class="bubble ai" style="align-self:flex-start;">Hi! I\'m Sakhi 👋 — your AI safety companion. How can I help you today?</div>'}
  </div>

  <!-- Input -->
  <div class="input-row">
    <input id="chat-input" type="text" placeholder="Ask anything about your safety…"
           onkeydown="if(event.key==='Enter')sendMsg()" autocomplete="off" />
    <button id="send-btn" onclick="sendMsg()">➤</button>
  </div>
</div>

<script>
const modal   = document.getElementById('modal');
const overlay = document.getElementById('overlay');
const msgs    = document.getElementById('msgs');
const inp     = document.getElementById('chat-input');

function openChat() {{
  modal.style.display   = 'flex';
  overlay.style.display = 'block';
  scrollBottom();
  inp.focus();
}}
function closeChat() {{
  modal.style.display   = 'none';
  overlay.style.display = 'none';
}}

function scrollBottom() {{
  msgs.scrollTop = msgs.scrollHeight;
}}

function addBubble(text, role) {{
  const row = document.createElement('div');
  row.className = 'msg-row ' + role;
  if (role === 'ai') {{
    const av = document.createElement('img');
    av.className = 'av-sm';
    av.src = "{AI_AVATAR}";
    row.appendChild(av);
  }}
  const b = document.createElement('div');
  b.className = 'bubble ' + role;
  b.textContent = text;
  row.appendChild(b);
  msgs.appendChild(row);
  scrollBottom();
}}

function showTyping() {{
  const d = document.createElement('div');
  d.className = 'typing'; d.id = 'typing';
  d.innerHTML = '<span></span><span></span><span></span>';
  msgs.appendChild(d);
  scrollBottom();
  return d;
}}

function sendMsg() {{
  const text = inp.value.trim();
  if (!text) return;
  inp.value = '';
  _dispatch(text);
}}

function sendChip(text) {{
  _dispatch(text);
}}

function _dispatch(text) {{
  addBubble(text, 'user');
  const t = showTyping();
  // Send to Streamlit parent via postMessage
  window.parent.postMessage({{type:'sakhi_msg', text: text}}, '*');
  // After a brief delay remove typing (reply comes via re-render)
  setTimeout(() => {{ if (t.parentNode) t.parentNode.removeChild(t); }}, 800);
}}

// Auto-open if flagged by Streamlit
{"openChat();" if st.session_state.show_chat else ""}

scrollBottom();
</script>
</body>
</html>"""


def _render_float_chat() -> None:
    if not st.session_state.user:
        return

    # Check for a pending message set by the JS postMessage listener below
    pending = st.session_state.get("pending_msg", "")
    if pending:
        reply = _ai_reply(pending)
        st.session_state.chat_history.append({"role": "user",    "content": pending})
        st.session_state.chat_history.append({"role": "assistant","content": reply})
        st.session_state.pending_msg = ""
        st.session_state.show_chat = True
        st.rerun()

    # Render the floating button + modal as an always-visible full-page iframe
    # height=1 so it doesn't take layout space; the fixed positioning makes it overlay
    components.html(_build_chat_html(), height=1, scrolling=False)

    # ── Hidden Streamlit listener for postMessage ───────────────────────────
    # We inject a parent-level script that listens for messages from the iframe
    st.markdown("""
    <script>
    (function() {
      if (window._sakhiListener) return;
      window._sakhiListener = true;
      window.addEventListener('message', function(e) {
        if (e.data && e.data.type === 'sakhi_msg') {
          // Write the message into a hidden input and trigger Streamlit
          const inp = window.parent.document.querySelector(
            'input[data-testid="stTextInput"][aria-label="__sakhi_hidden__"]'
          );
          if (inp) {
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
              window.HTMLInputElement.prototype, 'value').set;
            nativeInputValueSetter.call(inp, e.data.text);
            inp.dispatchEvent(new Event('input', { bubbles: true }));
          }
        }
      });
    })();
    </script>
    """, unsafe_allow_html=True)

    # Hidden text input that receives the postMessage value
    hidden_val = st.text_input("__sakhi_hidden__", value="",
                                label_visibility="collapsed",
                                key="sakhi_hidden_input")
    if hidden_val and hidden_val != st.session_state.get("_last_hidden", ""):
        st.session_state._last_hidden = hidden_val
        st.session_state.pending_msg  = hidden_val
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

def _sidebar() -> None:
    with st.sidebar:
        st.markdown(f"""
        <div style="text-align:center;padding:16px 0 12px;">
          <img src="{AI_AVATAR}"
               style="width:72px;height:72px;border-radius:50%;
                      border:3px solid {_P['cyan']};
                      box-shadow:0 0 20px {_P['cyan']}66;
                      margin-bottom:8px;" />
          <div style="font-size:18px;font-weight:800;letter-spacing:.5px;">SafeRide Sakhi</div>
          <div style="font-size:11px;color:var(--muted);">Women's Night-Travel Safety</div>
        </div>
        """, unsafe_allow_html=True)

        if st.session_state.user:
            u = st.session_state.user
            st.markdown(f"""
            <div class="safecard" style="text-align:center;padding:10px;">
              <div style="font-weight:600;">{u['name']}</div>
              <div style="font-size:11px;color:var(--muted);text-transform:capitalize;">{u['role']}</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("---")

        pages = [
            ("🏠", "Home",         "home"),
            ("🚗", "Book a Ride",  "book"),
            ("📍", "My Trips",     "trips"),
            ("🛡️", "Safety Tips", "safety"),
        ]
        for icon, label, pg in pages:
            active = st.session_state.page == pg
            if st.button(f"{icon}  {label}", key=f"nav_{pg}",
                         use_container_width=True,
                         type="primary" if active else "secondary"):
                st.session_state.page = pg
                if pg == "book":
                    st.session_state.wizard_step = 0
                    st.session_state.booking = {}
                st.rerun()

        st.markdown("---")

        # Chat toggle
        show = st.session_state.show_chat
        if st.button("💬 Close Sakhi" if show else "💬 Ask Sakhi AI",
                     key="chat_toggle", use_container_width=True):
            st.session_state.show_chat = not show
            st.rerun()

        st.markdown("---")

        dm = st.session_state.dark_mode
        if st.button("☀️  Light Mode" if dm else "🌙  Dark Mode",
                     key="theme_toggle", use_container_width=True):
            st.session_state.dark_mode = not dm
            st.rerun()

        st.markdown("---")

        if st.session_state.user:
            if st.button("⏻  Sign Out", key="signout", use_container_width=True):
                for k in ["user","page","wizard_step","booking","chat_history",
                          "show_chat","pending_msg"]:
                    st.session_state[k] = (
                        None  if k=="user" else
                        {}    if k=="booking" else
                        []    if k=="chat_history" else
                        ""    if k=="pending_msg" else
                        False if k=="show_chat" else "home")
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# LOGIN PAGE
# ══════════════════════════════════════════════════════════════════════════════

def page_login() -> None:
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown(f"""
        <div style="text-align:center;padding:32px 0 20px;">
          <img src="{AI_AVATAR}"
               style="width:90px;height:90px;border-radius:50%;
                      border:3px solid {_P['cyan']};
                      box-shadow:0 0 30px {_P['cyan']}77;
                      margin-bottom:12px;" />
          <h1 style="font-size:28px;font-weight:800;margin:0;color:var(--text);">
            SafeRide Sakhi</h1>
          <p style="color:var(--muted);font-size:14px;margin:4px 0 0;">
            Women's Night-Travel Safety Platform</p>
        </div>
        """, unsafe_allow_html=True)

        tab_in, tab_up = st.tabs(["Sign In", "Create Account"])

        with tab_in:
            st.markdown("<br>", unsafe_allow_html=True)
            email = st.text_input("Email", placeholder="you@example.com", key="li_email")
            pw    = st.text_input("Password", type="password", key="li_pw")
            if st.button("Sign In →", type="primary", key="btn_li",
                          use_container_width=True):
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
            st.markdown(f"""
            <div style="text-align:center;font-size:12px;color:var(--muted);
                        margin-top:16px;line-height:1.9;">
              Demo accounts:<br>
              <code>priya@saferide.in</code> / <code>rider123</code><br>
              <code>kavitha@saferide.in</code> / <code>driver123</code><br>
              <code>operator@saferide.in</code> / <code>operator123</code>
            </div>""", unsafe_allow_html=True)

        with tab_up:
            st.markdown("<br>", unsafe_allow_html=True)
            name  = st.text_input("Full name", key="su_name")
            email2= st.text_input("Email", key="su_email")
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

        st.markdown("<br>", unsafe_allow_html=True)
        dm = st.session_state.dark_mode
        if st.button("🌙 Dark Mode" if not dm else "☀️ Light Mode",
                      key="login_theme", use_container_width=True):
            st.session_state.dark_mode = not dm
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# HOME
# ══════════════════════════════════════════════════════════════════════════════

def _live_map_html(api_key: str, height: int = 320) -> str:
    maps_src = (
        f"https://maps.googleapis.com/maps/api/js"
        f"?key={api_key}&callback=initMap&v=weekly"
        f"&solution_channel=GMP_CCS_geolocation_v2"
    )
    no_key = "" if api_key else (
        '<div style="position:absolute;top:8px;left:50%;transform:translateX(-50%);'
        'background:#fef2f2;border:1px solid #fca5a5;border-radius:6px;'
        'padding:6px 14px;font-size:12px;color:#991b1b;z-index:10;">'
        '⚠️ Add GOOGLE_MAPS_API_KEY to .env for full Google Maps</div>'
    )
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/>
<style>
  *{{margin:0;padding:0;box-sizing:border-box;}}
  html,body,#map{{width:100%;height:{height}px;}}
  .loc-btn{{background:#fff;border:0;border-radius:4px;
    box-shadow:0 1px 4px -1px rgba(0,0,0,.4);
    margin:10px;padding:0 12px;font:500 13px Roboto,sans-serif;
    height:36px;cursor:pointer;color:#1e3a8a;}}
  .loc-btn:hover{{background:#eff6ff;}}
  #mtype{{position:absolute;bottom:28px;right:8px;z-index:5;
    background:#fff;border:1px solid #c7d7f5;border-radius:8px;
    padding:6px 10px;font:400 12px Roboto,sans-serif;}}
</style></head><body>
{no_key}
<div id="map"></div>
<div id="mtype">
  <label><input type="radio" name="mt" value="roadmap" checked onchange="setT(this.value)"> Map</label>&nbsp;
  <label><input type="radio" name="mt" value="satellite" onchange="setT(this.value)"> Satellite</label>
</div>
<script>
let map,iw,pin;
function initMap(){{
  map=new google.maps.Map(document.getElementById("map"),{{
    center:{{lat:12.9716,lng:77.5946}},zoom:14,
    mapTypeId:"roadmap",mapTypeControl:false,
    streetViewControl:false,fullscreenControl:true,
  }});
  iw=new google.maps.InfoWindow();
  const btn=document.createElement("button");
  btn.textContent="📍 My Location"; btn.className="loc-btn";
  map.controls[google.maps.ControlPosition.TOP_CENTER].push(btn);
  btn.addEventListener("click",()=>{{
    if(!navigator.geolocation){{iw.setPosition(map.getCenter());iw.setContent("Geolocation not supported.");iw.open(map);return;}}
    navigator.geolocation.getCurrentPosition(p=>{{
      const loc={{lat:p.coords.latitude,lng:p.coords.longitude}};
      if(pin) pin.setPosition(loc);
      else pin=new google.maps.Marker({{position:loc,map,
        icon:{{path:google.maps.SymbolPath.CIRCLE,
          fillColor:"#2563eb",fillOpacity:1,
          strokeColor:"#06b6d4",strokeWeight:3,scale:11}},
        title:"You are here"}});
      iw.setContent("<b>You are here</b><br>"+loc.lat.toFixed(5)+", "+loc.lng.toFixed(5));
      iw.open(map,pin); map.panTo(loc); map.setZoom(15);
    }},()=>{{iw.setPosition(map.getCenter());iw.setContent("Could not get location.");iw.open(map);}});
  }});
}}
window.setT=t=>map&&map.setMapTypeId(t);
window.initMap=initMap;
</script>
<script src="{maps_src}" defer></script>
</body></html>"""


def page_home() -> None:
    user = st.session_state.user
    name = user["name"].split()[0]
    st.markdown(f"""
    <div class="hero">
      <div style="display:flex;align-items:center;gap:18px;">
        <img src="{AI_AVATAR}"
             style="width:68px;height:68px;border-radius:50%;
                    border:3px solid {_P['cyan']};
                    box-shadow:0 0 20px {_P['cyan']}66;" />
        <div>
          <div style="font-size:22px;font-weight:800;">Hello, {name}! 👋</div>
          <div style="font-size:13px;opacity:.85;margin-top:3px;">
            Your AI safety agents are active and watching over you.</div>
          <span style="background:rgba(6,182,212,.2);border:1px solid {_P['cyan']}66;
                border-radius:20px;padding:3px 12px;font-size:11px;
                font-weight:600;margin-top:8px;display:inline-block;color:{_P['cyan']};">
            🛡️ All systems operational</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("#### Quick Actions")
    c1, c2, c3 = st.columns(3)
    for col, (icon, label, pg) in zip(
        [c1, c2, c3],
        [("🚗","Book Ride","book"),("📍","My Trips","trips"),("🛡️","Safety Tips","safety")]
    ):
        with col:
            st.markdown(
                f'<div class="safecard" style="text-align:center;padding:20px 8px;">'
                f'<div style="font-size:30px;">{icon}</div>'
                f'<div style="font-size:13px;font-weight:600;margin-top:8px;">{label}</div>'
                f'</div>', unsafe_allow_html=True)
            if st.button(label, key=f"qa_{pg}", use_container_width=True):
                st.session_state.page = pg
                if pg == "book": st.session_state.wizard_step = 0; st.session_state.booking = {}
                st.rerun()

    st.markdown("---")
    st.markdown("#### 📍 Your Current Location")
    st.caption("Click **My Location** to centre the map on your real position.")
    components.html(_live_map_html(GOOGLE_MAPS_API_KEY, height=300), height=300)

    st.markdown("---")
    ca, cb = st.columns(2)
    with ca:
        st.markdown("#### 🛡️ Agent Status")
        for ico, nm, st_ in [
            ("✅","Route Monitor","Active"),("✅","Driver Verifier","Active"),
            ("✅","Risk Scorer","Active"),("✅","Escalation","Standby"),
        ]:
            st.markdown(
                f'<div class="safecard" style="display:flex;justify-content:space-between;'
                f'align-items:center;padding:10px 14px;">'
                f'<span style="font-size:13px;">{ico} {nm}</span>'
                f'<span style="font-size:11px;font-weight:600;color:var(--accent);">{st_}</span>'
                f'</div>', unsafe_allow_html=True)
    with cb:
        st.markdown("#### 💡 Night Safety")
        for ico, tip in [
            ("📱","Share your trip before boarding."),
            ("🔍","Verify driver photo matches the app."),
            ("🌙","Prefer lit pickup points after 10 pm."),
            ("📞","SOS alerts your contacts instantly."),
        ]:
            st.markdown(
                f'<div class="safecard" style="display:flex;gap:10px;padding:10px 14px;">'
                f'<span style="font-size:18px;">{ico}</span>'
                f'<span style="font-size:13px;color:var(--muted);">{tip}</span></div>',
                unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# BOOK RIDE WIZARD
# ══════════════════════════════════════════════════════════════════════════════

STEPS      = ["INFO","ROUTE","SCHEDULE","DETAILS","REVIEW"]
STEP_ICONS = ["📋","📍","📅","🚗","✅"]


def _wizard_bar(step: int) -> None:
    cols = st.columns(len(STEPS))
    for i,(lbl,ico) in enumerate(zip(STEPS,STEP_ICONS)):
        cls  = "active" if i==step else ("done" if i<step else "wstep")
        icls = "active" if i==step else ("done"  if i<step else "")
        cols[i].markdown(
            f'<div class="wstep {cls}"><div class="wicon {icls}">{ico}</div>{lbl}</div>',
            unsafe_allow_html=True)


def page_book() -> None:
    st.markdown("## 🚗 Book a Ride")
    step = st.session_state.wizard_step
    _wizard_bar(step)
    st.markdown("---")
    [_step_info,_step_route,_step_schedule,_step_details,_step_review][min(step,4)]()


def _step_info() -> None:
    st.markdown("### Where would you like to go?")
    c1,c2 = st.columns(2)
    if c1.button("One Way", type="primary" if st.session_state.booking.get("trip_type","One Way")=="One Way" else "secondary"):
        st.session_state.booking["trip_type"]="One Way"; st.rerun()
    if c2.button("Round Trip", type="primary" if st.session_state.booking.get("trip_type")=="Round Trip" else "secondary"):
        st.session_state.booking["trip_type"]="Round Trip"; st.rerun()
    st.markdown("---")
    name  = st.text_input("Your name", value=st.session_state.user["name"])
    phone = st.text_input("Mobile number", placeholder="+91 9XXXXXXXXX")
    tc    = st.text_input("Trusted contact number")
    cons  = st.checkbox("I consent to sharing my location during the trip", value=True)
    st.session_state.booking.update({"name":name,"phone":phone,"trusted_contact":tc,"consent":cons})
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Next: Route →", type="primary"):
        if not phone: st.error("Mobile number is required.")
        else: st.session_state.wizard_step+=1; st.rerun()


def _step_route() -> None:
    st.markdown("### 📍 Set Your Route")
    b = st.session_state.booking
    miles = b.get("distance_miles",0.0)
    cl,cr = st.columns([3,1])
    cl.radio("Direction",["Going To Provider","Leaving From Provider"],key="dir_r")
    cr.markdown(
        f'<div class="safecard" style="text-align:center;padding:8px;">'
        f'<div style="font-size:18px;font-weight:700;">{miles:.1f}</div>'
        f'<div style="font-size:11px;color:var(--muted);">Miles</div></div>',
        unsafe_allow_html=True)
    pickup  = st.text_input("🔍 Pickup Location *", placeholder="Search pickup…")
    dropoff = st.text_input("🔍 Drop-Off Location *", placeholder="Search destination…")
    st.caption("Call (800) 123-4567 if your provider is not listed")
    if pickup and dropoff:
        d = round(random.uniform(1.5,18.5),2)
        st.session_state.booking.update({"pickup":pickup,"dropoff":dropoff,"distance_miles":d})
        st.info(f"📏 Estimated distance: **{d} miles**")
    st.markdown("<br>", unsafe_allow_html=True)
    c1,c2 = st.columns(2)
    if c1.button("← Back",type="secondary"): st.session_state.wizard_step-=1; st.rerun()
    if c2.button("Next: Schedule →",type="primary"):
        if not pickup or not dropoff: st.error("Please enter both locations.")
        else: st.session_state.wizard_step+=1; st.rerun()


def _step_schedule() -> None:
    st.markdown("### 📅 Schedule Your Ride")
    ride_date = st.date_input("Pickup date", value=datetime.now().date()+timedelta(days=1))
    ride_time = st.time_input("Pickup time", value=datetime.now().replace(hour=22,minute=0).time())
    recur     = st.selectbox("Frequency",["One-time","Daily","Weekly (Mon–Fri)","Custom"])
    notes     = st.text_area("Special instructions", placeholder="e.g. Meet at main gate", height=80)
    st.session_state.booking.update({"ride_date":str(ride_date),"ride_time":str(ride_time),"recurring":recur,"notes":notes})
    st.markdown("<br>", unsafe_allow_html=True)
    c1,c2 = st.columns(2)
    if c1.button("← Back",type="secondary"): st.session_state.wizard_step-=1; st.rerun()
    if c2.button("Next: Details →",type="primary"): st.session_state.wizard_step+=1; st.rerun()


def _step_details() -> None:
    st.markdown("### 🚗 Ride Preferences")
    vehicle      = st.selectbox("Vehicle",["Any available","Sedan","SUV","Auto-rickshaw"])
    women_driver = st.checkbox("Women driver preferred", value=True)
    share_trip   = st.checkbox("Share live trip with trusted contact", value=True)
    record       = st.checkbox("Enable audio safety recording (opt-in)", value=False)
    payment      = st.radio("Payment",["Cash","UPI","Card"],horizontal=True)
    st.session_state.booking.update({"vehicle":vehicle,"women_driver":women_driver,"share_trip":share_trip,"record":record,"payment":payment})
    st.markdown("<br>", unsafe_allow_html=True)
    c1,c2 = st.columns(2)
    if c1.button("← Back",type="secondary"): st.session_state.wizard_step-=1; st.rerun()
    if c2.button("Next: Review →",type="primary"): st.session_state.wizard_step+=1; st.rerun()


def _step_review() -> None:
    st.markdown("### ✅ Review & Confirm")
    b = st.session_state.booking
    rows = [
        ("👤 Rider",b.get("name","")),("📱 Phone",b.get("phone","")),
        ("🗺️ Trip type",b.get("trip_type","One Way")),
        ("📍 From",b.get("pickup","")),("🏥 To",b.get("dropoff","")),
        ("📏 Distance",f"{b.get('distance_miles',0):.1f} miles"),
        ("📅 Date",f"{b.get('ride_date','')} {b.get('ride_time','')}"),
        ("🔁 Recurring",b.get("recurring","One-time")),
        ("🚗 Vehicle",b.get("vehicle","Any")),
        ("👩 Women driver","Yes ✅" if b.get("women_driver") else "No"),
        ("💳 Payment",b.get("payment","Cash")),
        ("📡 Share trip","Yes ✅" if b.get("share_trip") else "No"),
    ]
    st.markdown('<div class="safecard">', unsafe_allow_html=True)
    for lbl,val in rows:
        if val:
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;padding:6px 0;'
                f'border-bottom:1px solid var(--border);font-size:13px;">'
                f'<span style="color:var(--muted);">{lbl}</span>'
                f'<span style="font-weight:600;">{val}</span></div>',
                unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown("**Safety agents will:** verify driver · monitor route · alert contacts · confirm arrival")
    c1,c2 = st.columns(2)
    if c1.button("← Back",type="secondary"): st.session_state.wizard_step-=1; st.rerun()
    if c2.button("🚗 Confirm Booking",type="primary"):
        st.balloons()
        st.success("🎉 Ride booked! Safety agents are activated.")
        st.markdown(f"""
        <div class="safecard" style="text-align:center;padding:24px;">
          <img src="{AI_AVATAR}" style="width:60px;height:60px;border-radius:50%;border:3px solid {_P['cyan']};" />
          <div style="font-size:17px;font-weight:700;margin:10px 0 6px;">Booking Confirmed</div>
          <div style="font-size:13px;color:var(--muted);">
            Driver arriving soon · Trusted contact notified</div>
        </div>""", unsafe_allow_html=True)
        if st.button("← Back to Home"):
            st.session_state.page="home"; st.session_state.wizard_step=0
            st.session_state.booking={}; st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# MY TRIPS
# ══════════════════════════════════════════════════════════════════════════════

def page_trips() -> None:
    st.markdown("## 📍 My Trips")
    for t in [
        {"date":"2026-11-10","from":"Indiranagar","to":"Whitefield","status":"✅ Completed","risk":"Safe"},
        {"date":"2026-11-09","from":"Koramangala","to":"Marathahalli","status":"✅ Completed","risk":"Safe"},
        {"date":"2026-11-08","from":"MG Road","to":"Electronic City","status":"✅ Completed","risk":"⚠️ Nudge sent"},
    ]:
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
    for icon, title, body in [
        ("📱","Before Boarding","Verify driver name, photo and vehicle number match the app before getting in."),
        ("🔍","During the Ride","Share your live trip with a trusted contact. Keep your phone charged."),
        ("🌙","Night Travel","Choose lit, busy pickup points. Prefer verified women drivers after 10 pm."),
        ("🆘","In an Emergency","Press SOS — the system contacts your trusted person and the safety team instantly."),
        ("📞","Call 112","You can always call 112 directly. Our agents can also coordinate with emergency services."),
        ("🚫","Red Flags","Driver doesn't match photo · Asks to cancel and rebook · Behaves aggressively — exit safely."),
    ]:
        st.markdown(
            f'<div class="safecard"><div style="display:flex;gap:14px;">'
            f'<div style="font-size:28px;flex-shrink:0;">{icon}</div>'
            f'<div><div style="font-weight:700;margin-bottom:4px;">{title}</div>'
            f'<div style="font-size:13px;color:var(--muted);">{body}</div>'
            f'</div></div></div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# ROUTER
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    if not st.session_state.user:
        page_login()
        return

    _sidebar()

    page = st.session_state.page
    if   page == "home":   page_home()
    elif page == "book":   page_book()
    elif page == "trips":  page_trips()
    elif page == "safety": page_safety()
    else:                  page_home()

    _render_float_chat()


if __name__ == "__main__":
    main()
