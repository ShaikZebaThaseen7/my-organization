from __future__ import annotations

import os

from flask import Flask

from .auth import ensure_default_admin
from .config import Config
from .db import init_db, init_engine
from .models import Campaign, Donation, Post, Transaction, User


def _seed_dummy_data() -> None:
    """
    Seed a small consistent dataset for first-time runs.
    Safe to call repeatedly (idempotent).
    """
    from .db import get_db
    from .utils import amount_to_cents, cents_to_amount_str

    db = get_db()

    # Campaigns
    general = db.query(Campaign).filter(Campaign.title == "General Fund").first()
    if not general:
        general = Campaign(
            title="General Fund",
            description="Transparent, needs-based support for community services and urgent aid.",
            goal_cents=amount_to_cents("2000"),
            raised_cents=0,
            status="active",
        )
        db.add(general)

    edu = db.query(Campaign).filter(Campaign.title == "Student Support").first()
    if not edu:
        edu = Campaign(
            title="Student Support",
            description="Support for students through learning materials and education assistance.",
            goal_cents=amount_to_cents("500"),
            raised_cents=0,
            status="active",
        )
        db.add(edu)

    db.flush()

    # Posts
    if not db.query(Post).first():
        db.add_all(
            [
                Post(
                    title="Community meal distribution",
                    content="We delivered fresh food packets to families and ensured everyone received proper guidance.",
                    image_filename=None,
                ),
                Post(
                    title="Education assistance update",
                    content="We provided learning materials for students and worked with local coordinators to ensure fairness.",
                    image_filename=None,
                ),
            ]
        )

    db.flush()

    # Donations + transactions + campaign raised amounts
    # Only seed if no verified donation exists yet.
    has_verified = db.query(Donation).filter(Donation.status == "verified").first()
    if not has_verified:
        d1 = Donation(
            name="Asha R.",
            email="asha@example.com",
            amount_cents=amount_to_cents("150"),
            campaign_id=general.id,
            utr="UTR-DEMO-1001",
            status="verified",
        )
        d2 = Donation(
            name="Kumar S.",
            email="kumar@example.com",
            amount_cents=amount_to_cents("60"),
            campaign_id=edu.id,
            utr="UTR-DEMO-1002",
            status="verified",
        )
        db.add_all([d1, d2])
        db.flush()

        # Transactions will drive transparency totals.
        t1 = Transaction(
            type="income",
            amount_cents=d1.amount_cents,
            purpose=f"Donation verified: {d1.name}",
            campaign_id=d1.campaign_id,
            donation_id=d1.id,
        )
        t2 = Transaction(
            type="income",
            amount_cents=d2.amount_cents,
            purpose=f"Donation verified: {d2.name}",
            campaign_id=d2.campaign_id,
            donation_id=d2.id,
        )
        expense = Transaction(
            type="expense",
            amount_cents=amount_to_cents("70"),
            purpose="Food distribution supplies",
            campaign_id=None,
        )
        db.add_all([t1, t2, expense])

        # Update raised_cents based on verified donations
        general.raised_cents = general.raised_cents + d1.amount_cents
        edu.raised_cents = edu.raised_cents + d2.amount_cents

    db.commit()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    # Set up DB
    init_engine(app.config["SQLALCHEMY_DATABASE_URI"], app.config.get("SQLALCHEMY_ENGINE_OPTIONS"))
    init_db(create_tables=app.config.get("AUTO_CREATE_DB", True))

    # Ensure upload directory exists
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)

    # Ensure at least one admin user exists
    ensure_default_admin(app.config["ADMIN_USERNAME"], app.config["ADMIN_PASSWORD"])

    # Optional dummy data for first run
    if app.config.get("SEED_DUMMY_DATA", True):
        _seed_dummy_data()

    # Register blueprints
    from .routes.public import public_bp
    from .routes.admin import admin_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    # Close out DB sessions after each request (prevents connection leaks).
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        from .db import SessionLocal

        if SessionLocal is not None:
            SessionLocal.remove()

    # Ensure templates can render flashed messages
    @app.context_processor
    def inject_now():
        import datetime

        return {"now": datetime.datetime.utcnow()}

    return app

