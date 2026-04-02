from __future__ import annotations

from functools import wraps

from flask import flash, redirect, render_template, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .models import User


def password_hash(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password: str, password_hash_value: str) -> bool:
    return check_password_hash(password_hash_value, password)


def ensure_default_admin(username: str, password: str) -> None:
    db = get_db()
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return
    u = User(username=username, password_hash=password_hash(password))
    db.add(u)
    db.commit()


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Please login to access the admin panel.", "warning")
            return redirect(url_for("admin.login", next=requested_next_url()))
        return view_func(*args, **kwargs)

    def requested_next_url():
        # Avoid importing request in module-level (keep things tidy)
        from flask import request

        # If none provided, fall back to admin dashboard
        return request.args.get("next") or url_for("admin.dashboard")

    return wrapper

