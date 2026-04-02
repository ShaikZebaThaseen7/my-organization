from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from werkzeug.exceptions import BadRequest

from ..config import Config
from ..db import get_db
from ..models import Campaign, Donation, Post, Transaction
from ..utils import amount_to_cents, build_upi_payment_uri, cents_to_amount_str, format_datetime

public_bp = Blueprint("public", __name__)


def _parse_amount_cents(amount_str: str) -> int:
    try:
        cents = amount_to_cents(amount_str)
    except ValueError:
        raise BadRequest("Invalid amount.")
    if cents <= 0:
        raise BadRequest("Amount must be greater than 0.")
    return cents


def _simple_email_valid(email: str) -> bool:
    return "@" in email and "." in email.split("@", 1)[1]


@public_bp.route("/", methods=["GET"])
def home():
    db = get_db()
    recent_posts = db.query(Post).order_by(Post.created_at.desc()).limit(3).all()
    recent_transactions = db.query(Transaction).order_by(Transaction.created_at.desc()).limit(6).all()
    return render_template("public/home.html", recent_posts=recent_posts, recent_transactions=recent_transactions)


@public_bp.route("/transparency", methods=["GET"])
def transparency():
    db = get_db()
    page = max(1, int(request.args.get("page", 1)))
    page_size = int(request.args.get("page_size", Config.DEFAULT_PAGE_SIZE))
    page_size = max(5, min(50, page_size))

    total_income = db.query(func.coalesce(func.sum(Transaction.amount_cents), 0)).filter(Transaction.type == "income").scalar()  # type: ignore[assignment]
    total_expense = db.query(func.coalesce(func.sum(Transaction.amount_cents), 0)).filter(Transaction.type == "expense").scalar()  # type: ignore[assignment]
    remaining = int(total_income) - int(total_expense)

    q = db.query(Transaction).order_by(Transaction.created_at.desc())
    total_count = q.count()
    transactions = q.offset((page - 1) * page_size).limit(page_size).all()

    return render_template(
        "public/transparency.html",
        total_income_cents=total_income,
        total_expense_cents=total_expense,
        remaining_cents=remaining,
        transactions=transactions,
        page=page,
        page_size=page_size,
        total_count=total_count,
        cents_to_amount_str=cents_to_amount_str,
        format_datetime=format_datetime,
    )


@public_bp.route("/campaigns", methods=["GET"])
def campaigns():
    db = get_db()
    active_campaigns = (
        db.query(Campaign).filter(Campaign.status == "active").order_by(Campaign.created_at.desc()).all()
    )
    return render_template("public/campaigns.html", campaigns=active_campaigns, cents_to_amount_str=cents_to_amount_str)


@public_bp.route("/donate", methods=["GET", "POST"])
def donate():
    db = get_db()
    campaigns = db.query(Campaign).filter(Campaign.status == "active").order_by(Campaign.title.asc()).all()

    if request.method == "GET":
        return render_template("public/donate.html", campaigns=campaigns)

    # POST: create pending donation
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()
    amount_str = (request.form.get("amount") or "").strip()
    campaign_id_raw = request.form.get("campaign_id") or ""
    campaign_id = int(campaign_id_raw) if campaign_id_raw else None

    if not name or len(name) < 2:
        flash("Please enter your name.", "danger")
        return redirect(url_for("public.donate"))
    if not email or not _simple_email_valid(email):
        flash("Please enter a valid email address.", "danger")
        return redirect(url_for("public.donate"))

    try:
        amount_cents = _parse_amount_cents(amount_str)
    except BadRequest as e:
        flash(str(e), "danger")
        return redirect(url_for("public.donate"))

    donation = Donation(
        name=name,
        email=email,
        amount_cents=amount_cents,
        campaign_id=campaign_id,
        status="pending",
    )
    db.add(donation)
    db.commit()

    flash("Donation created. Scan the QR code to pay, then submit the UTR.", "success")
    return redirect(url_for("public.donate_qr", donation_id=donation.id))


@public_bp.route("/donate/qr/<int:donation_id>", methods=["GET"])
def donate_qr(donation_id: int):
    db = get_db()
    donation = db.query(Donation).options(selectinload(Donation.campaign)).filter(Donation.id == donation_id).first()
    if not donation:
        flash("Donation not found.", "danger")
        return redirect(url_for("public.donate"))

    trx_ref = f"DON-{donation.id}"
    qr_payload = build_upi_payment_uri(
        payee=Config.UPI_PAYEE,
        payer_name=Config.UPI_PAYER_NAME,
        amount_cents=donation.amount_cents,
        transaction_ref=trx_ref,
        purpose=f"{Config.UPI_PURPOSE_PREFIX} #{donation.id}",
    )

    return render_template(
        "public/donate_qr.html",
        donation=donation,
        qr_payload=qr_payload,
        cents_to_amount_str=cents_to_amount_str,
    )


@public_bp.route("/donate/verify/<int:donation_id>", methods=["GET", "POST"])
def donate_verify(donation_id: int):
    db = get_db()
    donation = db.query(Donation).filter(Donation.id == donation_id).first()
    if not donation:
        flash("Donation not found.", "danger")
        return redirect(url_for("public.donate"))

    if request.method == "GET":
        return render_template("public/donate_verify.html", donation=donation, cents_to_amount_str=cents_to_amount_str)

    # POST: submit UTR
    utr = (request.form.get("utr") or "").strip()
    if not utr or len(utr) < 6:
        flash("Please enter a valid UTR number.", "danger")
        return redirect(url_for("public.donate_verify", donation_id=donation.id))

    # Update donation but keep it pending until admin verification.
    # If donation was already awaiting verification, allow update.
    donation.utr = utr
    donation.utr_submitted_at = datetime.utcnow()
    donation.status = "awaiting_verification"
    db.commit()

    flash("UTR submitted. The admin team will verify and record your donation.", "success")
    return redirect(url_for("public.thank_you"))


@public_bp.route("/thank-you", methods=["GET"])
def thank_you():
    return render_template("public/thank_you.html")


@public_bp.route("/posts", methods=["GET"])
def posts_list():
    db = get_db()
    q = (db.query(Post).order_by(Post.created_at.desc()))
    posts = q.all()
    return render_template("public/posts_list.html", posts=posts, cents_to_amount_str=cents_to_amount_str)


@public_bp.route("/posts/<int:post_id>", methods=["GET"])
def post_detail(post_id: int):
    db = get_db()
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        flash("Post not found.", "danger")
        return redirect(url_for("public.posts_list"))
    return render_template("public/post_detail.html", post=post)

