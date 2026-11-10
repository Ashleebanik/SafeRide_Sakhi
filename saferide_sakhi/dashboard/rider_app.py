"""
SafeRide Sakhi – Rider App
Entry point: streamlit run saferide_sakhi/dashboard/rider_app.py

Pages:
  - Login / Sign-up
  - Dashboard (home, book ride wizard, AI assistant, my trips, safety tips)
"""
from __future__ import annotations

import sys
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from saferide_sakhi.dashboard.auth import login, register
from saferide_sakhi.llm_gateway import call as llm_call

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SafeRide Sakhi",
    page_icon="🛡️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* Hide Streamlit default chrome */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

/* Primary button */
.stButton > button[kind="primary"] {
    background: #1a6b3c !important;
    color: #fff !important;
    border-radius: 24px !important;
    font-weight: 600 !important;
    height: 44px;
    width: 100%;
}
.stButton > button[kind="secondary"] {
    border-radius: 24px !important;
    height: 44px;
    width: 100%;
}

/* Step wizard bar */
.wizard-bar {
    display: flex; justify-content: space-between;
    align-items: center; margin-bottom: 24px;
    border-bottom: 1px solid #e5e7eb;
    padding-bottom: 12px;
}
.wstep { text-align: center; font-size: 11px; color: #9ca3af; font-weight: 500; }
.wstep.active { color: #1a6b3c; font-weight: 700; }
.wstep.done { color: #6b7280; }
.wicon {
    width: 32px; height: 32px; border-radius: 50%;
    background: #f3f4f6; display: flex; align-items: center;
    justify-content: center; margin: 0 auto 4px;
    font-size: 14px; border: 2px solid #e5e7eb;
}
.wicon.active { background: #1a6b3c; border-color: #1a6b3c; color: #fff; }
.wicon.done   { background: #d1fae5; border-color: #6ee7b7; }

/* Card */
.safecard {
    background: #fff; border: 1px solid #e5e7eb;
    border-radius: 12px; padding: 16px 20px; margin-bottom: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,.06);
}

/* Chat bubble */
.chat-user { background:#1a6b3c; color:#fff; border-radius:16px 16px 4px 16px;
             padding:10px 14px; margin:8px 0 8px 40px; font-size:14px; }
.chat-ai   { background:#f3f4f6; color:#111; border-radius:16px 16px 16px 4px;
             padding:10px 14px; margin:8px 40px 8px 0; font-size:14px; }
.chat-label { font-size:11px; color:#9ca3af; margin-bottom:2px; }

/* Bottom nav */
.bottom-nav {
    position: fixed; bottom: 0; left: 0; right: 0;
    background: #fff; border-top: 1px solid #e5e7eb;
    display: flex; justify-content: space-around;
    padding: 8px 0 10px; z-index: 100;
}
.nav-item { text-align: center; font-size: 10px; color: #6b7280; cursor: pointer; }
.nav-item.active { color: #1a6b3c; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# ── Session state defaults ────────────────────────────────────────────────────
for key, default in [
    ("user", None),
    ("page", "home"),
    ("wizard_step", 0),
    ("booking", {}),
    ("chat_history", []),
    ("trip_type", "One Way"),
    ("direction", "Going To Provider"),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ══════════════════════════════════════════════════════════════════════════════
# LOGIN / SIGNUP PAGE
# ══════════════════════════════════════════════════════════════════════════════

def page_login() -> None:
    st.markdown("""
    <div style="text-align:center;padding:32px 0 8px;">
      <div style="font-size:52px;">🛡️</div>
      <h1 style="font-size:26px;font-weight:700;margin:8px 0 4px;">SafeRide Sakhi</h1>
      <p style="color:#6b7280;font-size:14px;margin:0;">Women's Night-Travel Safety Platform</p>
    </div>
    """, unsafe_allow_html=True)

    tab_login, tab_signup = st.tabs(["Sign In", "Create Account"])

    # ── Sign In ───────────────────────────────────────────────────────────────
    with tab_login:
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        email    = st.text_input("Email address", placeholder="you@example.com",
                                  key="login_email")
        password = st.text_input("Password", type="password",
                                  placeholder="Enter your password", key="login_pw")

        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        if st.button("Sign In", type="primary", key="btn_login"):
            if not email or not password:
                st.error("Please enter your email and password.")
            else:
                user = login(email, password)
                if user:
                    st.session_state.user = user
                    st.session_state.page = "home"
                    st.rerun()
                else:
                    st.error("Incorrect email or password.")

        st.markdown("""
        <div style="text-align:center;margin-top:16px;font-size:13px;color:#6b7280;">
          Demo accounts:<br>
          <code>priya@saferide.in</code> / <code>rider123</code> (Rider)<br>
          <code>kavitha@saferide.in</code> / <code>driver123</code> (Driver)<br>
          <code>operator@saferide.in</code> / <code>operator123</code> (Operator)
        </div>
        """, unsafe_allow_html=True)

    # ── Sign Up ───────────────────────────────────────────────────────────────
    with tab_signup:
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        name     = st.text_input("Full name", placeholder="Your name", key="su_name")
        email_su = st.text_input("Email address", placeholder="you@example.com",
                                  key="su_email")
        role_su  = st.selectbox("I am a", ["Rider", "Driver"], key="su_role")
        pw_su    = st.text_input("Password", type="password",
                                  placeholder="Choose a password", key="su_pw")
        pw_su2   = st.text_input("Confirm password", type="password",
                                  placeholder="Repeat password", key="su_pw2")

        if st.button("Create Account", type="primary", key="btn_signup"):
            if not all([name, email_su, pw_su, pw_su2]):
                st.error("Please fill in all fields.")
            elif pw_su != pw_su2:
                st.error("Passwords do not match.")
            elif len(pw_su) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                user = register(name, email_su, pw_su, role_su.lower())
                if user is None:
                    st.error("An account with this email already exists.")
                else:
                    st.session_state.user = user
                    st.session_state.page = "home"
                    st.success(f"Welcome, {name}! 🎉")
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# SHARED: TOP BAR
# ══════════════════════════════════════════════════════════════════════════════

def _top_bar(title: str) -> None:
    user = st.session_state.user
    col_l, col_m, col_r = st.columns([1, 4, 1])
    col_m.markdown(
        f"<h3 style='text-align:center;margin:0;padding:8px 0;font-size:18px;'>{title}</h3>",
        unsafe_allow_html=True,
    )
    if col_r.button("⏻", help="Sign out", key="signout_btn"):
        for k in ["user", "page", "wizard_step", "booking", "chat_history"]:
            st.session_state[k] = None if k == "user" else (
                {} if k == "booking" else ([] if k == "chat_history" else "home"))
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: HOME DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

def page_home() -> None:
    user = st.session_state.user
    _top_bar("SafeRide Sakhi")

    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#1a6b3c,#25a25a);
         border-radius:16px;padding:20px 24px;color:#fff;margin-bottom:20px;">
      <div style="font-size:22px;">{user['avatar']}</div>
      <div style="font-size:20px;font-weight:700;margin-top:4px;">
        Hello, {user['name'].split()[0]}!</div>
      <div style="font-size:13px;opacity:.85;margin-top:2px;">
        Stay safe tonight. Your safety agents are active.</div>
    </div>
    """, unsafe_allow_html=True)

    # Quick action buttons
    st.markdown("#### Quick Actions")
    c1, c2, c3 = st.columns(3)
    if c1.button("🚗\nBook Ride", use_container_width=True):
        st.session_state.page = "book"
        st.session_state.wizard_step = 0
        st.session_state.booking = {}
        st.rerun()
    if c2.button("🤖\nAsk AI", use_container_width=True):
        st.session_state.page = "ai"
        st.rerun()
    if c3.button("📍\nMy Trips", use_container_width=True):
        st.session_state.page = "trips"
        st.rerun()

    st.markdown("---")

    # Safety status card
    st.markdown("#### 🛡️ Safety Status")
    st.markdown("""
    <div class="safecard">
      <div style="display:flex;align-items:center;gap:10px;">
        <div style="font-size:24px;">✅</div>
        <div>
          <div style="font-weight:600;">All agents active</div>
          <div style="font-size:12px;color:#6b7280;">
            Route monitoring · Chauffeur verification · Emergency escalation
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Safety tips
    st.markdown("#### 💡 Safety Tips")
    tips = [
        ("📱", "Share your live trip with a trusted contact before boarding."),
        ("🔍", "Always verify your driver photo matches the app before getting in."),
        ("📞", "If you feel unsafe, press the SOS button – help arrives in seconds."),
        ("🌙", "Prefer lit pickup points like malls or police stations at night."),
    ]
    for icon, tip in tips:
        st.markdown(
            f'<div class="safecard" style="display:flex;gap:12px;align-items:flex-start;">'
            f'<span style="font-size:20px;">{icon}</span>'
            f'<span style="font-size:13px;color:#374151;">{tip}</span></div>',
            unsafe_allow_html=True,
        )

    _bottom_nav()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: BOOK RIDE WIZARD (matches the screenshot exactly)
# Steps: INFO → ROUTE → SCHEDULE → DETAILS → REVIEW
# ══════════════════════════════════════════════════════════════════════════════

STEPS = ["INFO", "ROUTE", "SCHEDULE", "DETAILS", "REVIEW"]
STEP_ICONS = ["📋", "📍", "📅", "🚗", "✅"]


def _wizard_bar(current: int) -> None:
    cols = st.columns(len(STEPS))
    for i, (label, icon) in enumerate(zip(STEPS, STEP_ICONS)):
        cls = "active" if i == current else ("done" if i < current else "wstep")
        icon_cls = "active" if i == current else ("done" if i < current else "")
        cols[i].markdown(
            f'<div class="wstep {cls}">'
            f'<div class="wicon {icon_cls}">{icon}</div>'
            f'{label}</div>',
            unsafe_allow_html=True,
        )


def _next_step() -> None:
    st.session_state.wizard_step += 1
    st.rerun()


def _prev_step() -> None:
    st.session_state.wizard_step -= 1
    st.rerun()


def _step_info() -> None:
    st.markdown("### Where would you like to go?")
    # One Way / Round Trip toggle
    col1, col2 = st.columns(2)
    one_way = col1.button("One Way",
        type="primary" if st.session_state.booking.get("trip_type","One Way") == "One Way" else "secondary")
    round_trip = col2.button("Round Trip",
        type="primary" if st.session_state.booking.get("trip_type") == "Round Trip" else "secondary")
    if one_way:
        st.session_state.booking["trip_type"] = "One Way"
    if round_trip:
        st.session_state.booking["trip_type"] = "Round Trip"

    st.markdown("---")
    st.markdown("**Tell us about yourself**")
    name = st.text_input("Your name", value=st.session_state.user["name"],
                          key="info_name")
    phone = st.text_input("Mobile number", placeholder="+91 9XXXXXXXXX", key="info_phone")
    trusted = st.text_input("Trusted contact number (will receive trip updates)",
                             placeholder="+91 9XXXXXXXXX", key="info_trusted")
    consent = st.checkbox("I consent to sharing my location during the trip",
                           value=True, key="info_consent")

    st.session_state.booking.update({
        "name": name, "phone": phone,
        "trusted_contact": trusted, "consent": consent,
    })

    st.markdown("<div style='height:60px'></div>", unsafe_allow_html=True)
    if st.button("Next: Route  →", type="primary"):
        if not phone:
            st.error("Please enter your mobile number.")
        else:
            _next_step()


def _step_route() -> None:
    st.markdown("### 📍 Pickup")

    miles = st.session_state.booking.get("distance_miles", 0.0)
    col_l, col_r = st.columns([3, 1])
    col_l.markdown("**Are you going to your provider or leaving from your provider?**")
    col_r.markdown(
        f'<div style="background:#f3f4f6;border-radius:8px;padding:4px 10px;'
        f'text-align:center;font-size:13px;font-weight:600;">{miles:.2f} Miles</div>',
        unsafe_allow_html=True,
    )

    direction = st.radio(
        "Direction",
        ["Going To Provider", "Leaving From Provider"],
        index=0 if st.session_state.booking.get("direction","Going To Provider") == "Going To Provider" else 1,
        key="direction_radio",
        label_visibility="collapsed",
    )
    st.session_state.booking["direction"] = direction

    st.markdown("**Pickup Location** *")
    pickup = st.text_input("", placeholder="🔍  Search pickup location",
                            key="pickup_loc", label_visibility="collapsed")

    st.markdown("**Care Provider / Drop-Off Location** *")
    dropoff = st.text_input("", placeholder="🔍  Search provider / destination",
                             key="dropoff_loc", label_visibility="collapsed")
    st.caption("Call (800) 123-4567 if your provider is not listed")

    # Simulate distance calculation
    if pickup and dropoff:
        dist = round(random.uniform(1.5, 18.5), 2)
        st.session_state.booking["distance_miles"] = dist
        st.session_state.booking["pickup"]  = pickup
        st.session_state.booking["dropoff"] = dropoff
        st.info(f"📏 Estimated distance: **{dist} miles**")

    st.markdown("<div style='height:60px'></div>", unsafe_allow_html=True)
    col_back, col_next = st.columns(2)
    if col_back.button("← Back", type="secondary"):
        _prev_step()
    if col_next.button("Next: Schedule  →", type="primary"):
        if not pickup or not dropoff:
            st.error("Please enter both pickup and drop-off locations.")
        else:
            _next_step()


def _step_schedule() -> None:
    st.markdown("### 📅 Schedule Your Ride")

    ride_date = st.date_input("Pickup date",
                               value=datetime.now().date() + timedelta(days=1),
                               key="sched_date")
    ride_time = st.time_input("Pickup time",
                               value=datetime.now().replace(hour=22, minute=0).time(),
                               key="sched_time")

    st.markdown("**Recurring ride?**")
    recurring = st.selectbox("Frequency",
                              ["One-time", "Daily", "Weekly (Mon–Fri)", "Custom"],
                              key="sched_freq")

    notes = st.text_area("Special instructions (optional)",
                          placeholder="e.g. Meet me at the main gate",
                          key="sched_notes", height=80)

    st.session_state.booking.update({
        "ride_date": str(ride_date),
        "ride_time": str(ride_time),
        "recurring": recurring,
        "notes": notes,
    })

    st.markdown("<div style='height:60px'></div>", unsafe_allow_html=True)
    col_back, col_next = st.columns(2)
    if col_back.button("← Back", type="secondary"):
        _prev_step()
    if col_next.button("Next: Details  →", type="primary"):
        _next_step()


def _step_details() -> None:
    st.markdown("### 🚗 Ride Details")

    vehicle = st.selectbox("Vehicle preference",
                            ["Any available", "Sedan", "SUV", "Auto-rickshaw"],
                            key="det_vehicle")
    women_driver = st.checkbox("Women driver preferred", value=True, key="det_women")
    sos_contacts = st.text_input("SOS contact (auto-alerted on emergency)",
                                  value=st.session_state.booking.get("trusted_contact", ""),
                                  key="det_sos")
    share_trip = st.checkbox("Share live trip with trusted contact", value=True,
                              key="det_share")
    record = st.checkbox("Enable audio safety recording (opt-in)", value=False,
                          key="det_record")

    st.markdown("**Payment method**")
    payment = st.radio("", ["Cash", "UPI", "Card"], horizontal=True,
                        key="det_payment", label_visibility="collapsed")

    st.session_state.booking.update({
        "vehicle": vehicle,
        "women_driver": women_driver,
        "sos_contact": sos_contacts,
        "share_trip": share_trip,
        "record": record,
        "payment": payment,
    })

    st.markdown("<div style='height:60px'></div>", unsafe_allow_html=True)
    col_back, col_next = st.columns(2)
    if col_back.button("← Back", type="secondary"):
        _prev_step()
    if col_next.button("Next: Review  →", type="primary"):
        _next_step()


def _step_review() -> None:
    st.markdown("### ✅ Review & Confirm")
    b = st.session_state.booking

    details = [
        ("👤 Rider",        b.get("name", "")),
        ("📱 Phone",        b.get("phone", "")),
        ("🗺️ Trip type",   b.get("trip_type", "One Way")),
        ("📍 From",         b.get("pickup", "")),
        ("🏥 To",           b.get("dropoff", "")),
        ("📏 Distance",     f"{b.get('distance_miles', 0):.2f} miles"),
        ("📅 Date & Time",  f"{b.get('ride_date','')}  {b.get('ride_time','')}"),
        ("🔁 Recurring",    b.get("recurring", "One-time")),
        ("🚗 Vehicle",      b.get("vehicle", "Any")),
        ("👩 Women driver", "Yes ✅" if b.get("women_driver") else "No"),
        ("💳 Payment",      b.get("payment", "Cash")),
        ("📡 Share trip",   "Yes ✅" if b.get("share_trip") else "No"),
    ]

    st.markdown('<div class="safecard">', unsafe_allow_html=True)
    for label, value in details:
        if value:
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;'
                f'padding:6px 0;border-bottom:1px solid #f3f4f6;font-size:13px;">'
                f'<span style="color:#6b7280;">{label}</span>'
                f'<span style="font-weight:500;">{value}</span></div>',
                unsafe_allow_html=True,
            )
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    st.markdown("**SafeRide Safety Agents will:**")
    st.markdown("""
    - ✅ Verify your driver's ID and police clearance
    - ✅ Monitor your route in real time
    - ✅ Alert your trusted contact if anything unusual is detected
    - ✅ Confirm your safe arrival automatically
    """)

    col_back, col_confirm = st.columns(2)
    if col_back.button("← Back", type="secondary"):
        _prev_step()
    if col_confirm.button("🚗 Confirm Booking", type="primary"):
        st.balloons()
        st.success("🎉 Ride booked! Your safety agents are activated.")
        st.markdown(
            '<div class="safecard" style="text-align:center;">'
            '<div style="font-size:32px;">🛡️</div>'
            '<div style="font-weight:700;font-size:16px;margin:8px 0 4px;">'
            'Booking Confirmed</div>'
            '<div style="font-size:13px;color:#6b7280;">'
            'Driver will arrive at your pickup point.<br>'
            'Your trusted contact has been notified.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        if st.button("Back to Home"):
            st.session_state.page = "home"
            st.session_state.wizard_step = 0
            st.session_state.booking = {}
            st.rerun()


def page_book() -> None:
    _top_bar("Book a Ride")
    step = st.session_state.wizard_step
    _wizard_bar(step)
    st.markdown("---")

    steps = [_step_info, _step_route, _step_schedule, _step_details, _step_review]
    steps[min(step, len(steps) - 1)]()
    _bottom_nav()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: AI ASSISTANT
# ══════════════════════════════════════════════════════════════════════════════

_AI_SYSTEM = """You are Sakhi, the friendly AI safety assistant for SafeRide Sakhi,
a women's night-travel safety platform in India. You help riders with:
- Booking rides and understanding the process
- Safety tips for night travel
- What to do in an emergency
- Understanding how the AI safety agents work
- General questions about women's safety

Be warm, concise and empowering. Never be alarmist. Reply in 2-3 sentences max.
Always end with a practical action the user can take."""


def _ai_reply(user_msg: str) -> str:
    """Get a reply from the AI assistant via the LLM gateway."""
    history = st.session_state.chat_history[-6:]  # last 3 exchanges
    context = "\n".join(
        f"{'User' if m['role']=='user' else 'Sakhi'}: {m['content']}"
        for m in history
    )
    prompt = f"{_AI_SYSTEM}\n\nConversation so far:\n{context}\n\nUser: {user_msg}\nSakhi:"

    # Try Groq first (fastest), fall back to rule-based
    resp = llm_call("groq", prompt, max_tokens=150, agent="ai_assistant")
    if resp.success and resp.text:
        return resp.text.strip()

    # Rule-based fallback responses
    msg = user_msg.lower()
    if any(w in msg for w in ["book", "ride", "cab", "auto"]):
        return ("To book a ride, tap **Book Ride** on the home screen and follow the "
                "5-step wizard. Your driver will be verified before arrival! 🚗")
    if any(w in msg for w in ["safe", "safety", "danger", "scared", "unsafe"]):
        return ("Press the **SOS button** in the app immediately — the system will alert "
                "your trusted contact and the control room within seconds. "
                "You are never alone with SafeRide Sakhi. 🛡️")
    if any(w in msg for w in ["driver", "verify", "check"]):
        return ("Every driver is verified before each trip — ID, police clearance and "
                "a live face match. If anything doesn't match, the ride is blocked. ✅")
    if any(w in msg for w in ["emergency", "police", "112", "help"]):
        return ("In any emergency, press SOS in the app. The system contacts your "
                "trusted person and the operator who can call 112. "
                "You can also call 112 directly at any time. 📞")
    return ("I'm here to help! You can ask me about booking rides, driver safety checks, "
            "what to do in an emergency, or how the safety agents protect your journey. 😊")


def page_ai() -> None:
    _top_bar("🤖 Sakhi AI Assistant")

    st.markdown("""
    <div class="safecard" style="text-align:center;background:#f0fdf4;border-color:#86efac;">
      <div style="font-size:28px;">🤖</div>
      <div style="font-weight:600;margin:4px 0;">Hi! I'm Sakhi</div>
      <div style="font-size:13px;color:#6b7280;">
        Ask me anything about your ride, safety or emergencies.
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Suggestion chips
    suggestions = [
        "How do I book a safe night ride?",
        "What happens if I press SOS?",
        "How is my driver verified?",
        "What should I do if I feel unsafe?",
        "How does the AI monitor my trip?",
    ]
    st.markdown("**Quick questions:**")
    chip_cols = st.columns(len(suggestions[:3]))
    for i, sugg in enumerate(suggestions[:3]):
        if chip_cols[i].button(sugg, key=f"chip_{i}", use_container_width=True):
            st.session_state.chat_history.append({"role": "user", "content": sugg})
            reply = _ai_reply(sugg)
            st.session_state.chat_history.append({"role": "assistant", "content": reply})
            st.rerun()

    chip_cols2 = st.columns(2)
    for i, sugg in enumerate(suggestions[3:]):
        if chip_cols2[i].button(sugg, key=f"chip2_{i}", use_container_width=True):
            st.session_state.chat_history.append({"role": "user", "content": sugg})
            reply = _ai_reply(sugg)
            st.session_state.chat_history.append({"role": "assistant", "content": reply})
            st.rerun()

    st.markdown("---")

    # Chat history
    if st.session_state.chat_history:
        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                st.markdown(
                    f'<div class="chat-label" style="text-align:right;">You</div>'
                    f'<div class="chat-user">{msg["content"]}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="chat-label">🤖 Sakhi</div>'
                    f'<div class="chat-ai">{msg["content"]}</div>',
                    unsafe_allow_html=True,
                )
    else:
        st.markdown(
            '<div style="text-align:center;color:#9ca3af;font-size:13px;padding:20px;">'
            'No messages yet. Ask me anything! 👆</div>',
            unsafe_allow_html=True,
        )

    # Input box
    st.markdown("<div style='height:70px'></div>", unsafe_allow_html=True)
    with st.form("chat_form", clear_on_submit=True):
        col_in, col_send = st.columns([5, 1])
        user_input = col_in.text_input("", placeholder="Type your question…",
                                        label_visibility="collapsed", key="chat_input")
        submitted = col_send.form_submit_button("➤", use_container_width=True)
        if submitted and user_input.strip():
            st.session_state.chat_history.append(
                {"role": "user", "content": user_input.strip()})
            reply = _ai_reply(user_input.strip())
            st.session_state.chat_history.append(
                {"role": "assistant", "content": reply})
            st.rerun()

    if st.session_state.chat_history:
        if st.button("🗑️ Clear chat", key="clear_chat"):
            st.session_state.chat_history = []
            st.rerun()

    _bottom_nav()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: MY TRIPS
# ══════════════════════════════════════════════════════════════════════════════

_MOCK_TRIPS = [
    {"date": "2026-11-10", "from": "Indiranagar", "to": "Whitefield", "status": "Completed ✅", "risk": "Safe"},
    {"date": "2026-11-09", "from": "Koramangala", "to": "Marathahalli", "status": "Completed ✅", "risk": "Safe"},
    {"date": "2026-11-08", "from": "MG Road", "to": "Electronic City", "status": "Completed ✅", "risk": "⚠️ Nudge sent"},
]


def page_trips() -> None:
    _top_bar("📍 My Trips")
    st.markdown("#### Recent trips")
    for t in _MOCK_TRIPS:
        st.markdown(
            f'<div class="safecard">'
            f'<div style="display:flex;justify-content:space-between;'
            f'align-items:center;">'
            f'<div>'
            f'<div style="font-weight:600;font-size:14px;">{t["from"]} → {t["to"]}</div>'
            f'<div style="font-size:12px;color:#6b7280;">{t["date"]}</div>'
            f'</div>'
            f'<div style="text-align:right;">'
            f'<div style="font-size:12px;">{t["status"]}</div>'
            f'<div style="font-size:11px;color:#6b7280;">{t["risk"]}</div>'
            f'</div></div></div>',
            unsafe_allow_html=True,
        )
    _bottom_nav()


# ══════════════════════════════════════════════════════════════════════════════
# BOTTOM NAVIGATION BAR
# ══════════════════════════════════════════════════════════════════════════════

def _bottom_nav() -> None:
    st.markdown("<div style='height:72px'></div>", unsafe_allow_html=True)
    nav_items = [
        ("🏠", "Home",    "home"),
        ("🚗", "Book",    "book"),
        ("🤖", "Ask AI",  "ai"),
        ("📍", "My Trips","trips"),
    ]
    cols = st.columns(len(nav_items))
    for col, (icon, label, pg) in zip(cols, nav_items):
        active = st.session_state.page == pg
        style = "color:#1a6b3c;font-weight:700;" if active else "color:#6b7280;"
        if col.button(
            f"{icon}\n{label}",
            key=f"nav_{pg}",
            use_container_width=True,
            help=label,
        ):
            st.session_state.page = pg
            if pg == "book":
                st.session_state.wizard_step = 0
                st.session_state.booking = {}
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# ROUTER
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    if not st.session_state.user:
        page_login()
        return

    page = st.session_state.page
    if page == "home":
        page_home()
    elif page == "book":
        page_book()
    elif page == "ai":
        page_ai()
    elif page == "trips":
        page_trips()
    else:
        page_home()


if __name__ == "__main__":
    main()
