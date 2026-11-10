"""
Auth helpers – simple in-memory user store for the prototype.
In production this would use a real DB + bcrypt + JWT.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

# Synthetic demo accounts (name, email, password_hash, role)
# Passwords are sha256 hashed. Never store plaintext in production.
def _h(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

_USERS: dict[str, dict] = {
    "priya@saferide.in": {
        "name": "Priya Sharma",
        "email": "priya@saferide.in",
        "password_hash": _h("rider123"),
        "role": "rider",
        "avatar": "👩",
    },
    "kavitha@saferide.in": {
        "name": "Kavitha Reddy",
        "email": "kavitha@saferide.in",
        "password_hash": _h("driver123"),
        "role": "driver",
        "avatar": "🚗",
    },
    "operator@saferide.in": {
        "name": "Control Room",
        "email": "operator@saferide.in",
        "password_hash": _h("operator123"),
        "role": "operator",
        "avatar": "🛡️",
    },
}


def login(email: str, password: str) -> dict | None:
    """Return user dict on success, None on failure."""
    user = _USERS.get(email.strip().lower())
    if user and user["password_hash"] == _h(password):
        return {**user, "logged_in_at": datetime.utcnow().isoformat()}
    return None


def register(name: str, email: str, password: str, role: str = "rider") -> dict | None:
    """Register a new user. Returns user dict or None if email taken."""
    email = email.strip().lower()
    if email in _USERS:
        return None
    user = {
        "name": name.strip(),
        "email": email,
        "password_hash": _h(password),
        "role": role,
        "avatar": "👩" if role == "rider" else "🚗",
    }
    _USERS[email] = user
    return {**user, "logged_in_at": datetime.utcnow().isoformat()}
