from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from werkzeug.datastructures import FileStorage
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

from ..config import Config
from ..db import get_db
from ..models import Campaign, Donation, Post, Transaction, User
from ..utils import amount_to_cents, cents_to_amount_str, format_datetime
from ..auth import admin_required, verify_password

admin_bp = Blueprint("admin", __name__)


def _parse_page_params():
    page = max(1, int(request.args.get("page", 1)))
    page_size = int(request.args.get("page_size", Config.DEFAULT_PAGE_SIZE))
    page_size = max(5, min(50, page_size))
    return page, page_size


def _simple_email_valid(email: str) -> bool:
    return "@" in email and "." in email.split("@", 1)[1]


def _parse_amount_cents(amount_str: str) -> int:
    cents = amount_to_cents(amount_str)
    if cents <= 0:
        raise ValueError("Amount must be greater than 0.")
    return cents


def _allowed_image(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in {"png", "jpg", "jpeg", "gif", "webp"}


def _save_post_image(file: FileStorage) -> str | None:
    if not file or not file.filename:
        return None
    if not _allowed_image(file.filename):
        raise ValueError("Unsupported image type.")

    os.makedirs(Config.UPLOAD_DIR, exist_ok=True)
    safe_name = secure_filename(file.filename)
    # Create reasonably unique name without external deps
    unique_name = f"{int(datetime.utcnow().timestamp())}-{safe_name}"
    target_path = os.path.join(Config.UPLOAD_DIR, unique_name)
    file.save(target_path)
    return unique_name


def _delete_file_if_exists(filename: str | None) -> None:
    if not filename:
        return
    path = os.path.join(Config.UPLOAD_DIR, filename)
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        # Best-effort cleanup; don't break admin UX
        pass


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("admin/login.html")

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    db = get_db()
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        flash("Invalid username or password.", "danger")
        return render_template("admin/login.html")

    session["admin_logged_in"] = True
    session["admin_username"] = user.username
    next_url = request.args.get("next") or url_for("admin.dashboard")
    flash("Welcome to the admin panel.", "success")
    return redirect(next_url)


@admin_bp.route("/logout", methods=["GET"])
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("public.home"))


@admin_bp.route("/dashboard", methods=["GET"])
@admin_required
def dashboard():
    db = get_db()
    total_income = db.query(func.coalesce(func.sum(Transaction.amount_cents), 0)).filter(Transaction.type == "income").scalar()  # type: ignore[assignment]
    total_expense = db.query(func.coalesce(func.sum(Transaction.amount_cents), 0)).filter(Transaction.type == "expense").scalar()  # type: ignore[assignment]
    remaining = int(total_income) - int(total_expense)

    campaign_stats = (
        db.query(Campaign.status, func.count(Campaign.id))
        .group_by(Campaign.status)
        .all()
    )
    active_campaigns = db.query(Campaign).filter(Campaign.status == "active").count()

    pending_donations = (
        db.query(Donation)
        .filter(Donation.status == "awaiting_verification")
        .order_by(Donation.created_at.desc())
        .limit(10)
        .all()
    )

    recent_transactions = db.query(Transaction).order_by(Transaction.created_at.desc()).limit(10).all()

    return render_template(
        "admin/dashboard.html",
        total_income_cents=int(total_income),
        total_expense_cents=int(total_expense),
        remaining_cents=remaining,
        campaign_stats=campaign_stats,
        active_campaigns=active_campaigns,
        pending_donations=pending_donations,
        recent_transactions=recent_transactions,
        cents_to_amount_str=cents_to_amount_str,
        format_datetime=format_datetime,
    )


@admin_bp.route("/campaigns", methods=["GET"])
@admin_required
def campaigns_list():
    db = get_db()
    campaigns = db.query(Campaign).order_by(Campaign.created_at.desc()).all()
    return render_template("admin/campaigns_list.html", campaigns=campaigns, cents_to_amount_str=cents_to_amount_str)


@admin_bp.route("/campaigns/create", methods=["GET", "POST"])
@admin_required
def campaigns_create():
    if request.method == "GET":
        return render_template("admin/campaign_form.html", mode="create", campaign=None)

    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()
    goal_str = (request.form.get("goal") or "").strip()
    status = (request.form.get("status") or "active").strip() or "active"

    if not title or len(title) < 3:
        flash("Please enter a campaign title (min 3 chars).", "danger")
        return render_template("admin/campaign_form.html", mode="create", campaign=None)
    if not description or len(description) < 10:
        flash("Please enter a longer description (min 10 chars).", "danger")
        return render_template("admin/campaign_form.html", mode="create", campaign=None)

    try:
        goal_cents = _parse_amount_cents(goal_str)
    except ValueError as e:
        flash(str(e), "danger")
        return render_template("admin/campaign_form.html", mode="create", campaign=None)

    db = get_db()
    campaign = Campaign(title=title, description=description, goal_cents=goal_cents, raised_cents=0, status=status)
    db.add(campaign)
    db.commit()
    flash("Campaign created.", "success")
    return redirect(url_for("admin.campaigns_list"))


@admin_bp.route("/campaigns/<int:campaign_id>/edit", methods=["GET", "POST"])
@admin_required
def campaigns_edit(campaign_id: int):
    db = get_db()
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        flash("Campaign not found.", "danger")
        return redirect(url_for("admin.campaigns_list"))

    if request.method == "GET":
        return render_template("admin/campaign_form.html", mode="edit", campaign=campaign, cents_to_amount_str=cents_to_amount_str)

    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()
    goal_str = (request.form.get("goal") or "").strip()
    status = (request.form.get("status") or "active").strip() or "active"

    if not title or len(title) < 3:
        flash("Please enter a campaign title (min 3 chars).", "danger")
        return render_template("admin/campaign_form.html", mode="edit", campaign=campaign, cents_to_amount_str=cents_to_amount_str)
    if not description or len(description) < 10:
        flash("Please enter a longer description (min 10 chars).", "danger")
        return render_template("admin/campaign_form.html", mode="edit", campaign=campaign, cents_to_amount_str=cents_to_amount_str)

    try:
        goal_cents = _parse_amount_cents(goal_str)
    except ValueError as e:
        flash(str(e), "danger")
        return render_template("admin/campaign_form.html", mode="edit", campaign=campaign, cents_to_amount_str=cents_to_amount_str)

    campaign.title = title
    campaign.description = description
    campaign.goal_cents = goal_cents
    campaign.status = status
    db.commit()

    flash("Campaign updated.", "success")
    return redirect(url_for("admin.campaigns_list"))


@admin_bp.route("/campaigns/<int:campaign_id>/delete", methods=["POST"])
@admin_required
def campaigns_delete(campaign_id: int):
    db = get_db()
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        flash("Campaign not found.", "danger")
        return redirect(url_for("admin.campaigns_list"))

    donation_count = db.query(Donation).filter(Donation.campaign_id == campaign_id).count()
    if donation_count > 0:
        flash("Cannot delete: donations are linked to this campaign.", "danger")
        return redirect(url_for("admin.campaigns_list"))

    db.delete(campaign)
    db.commit()
    flash("Campaign deleted.", "success")
    return redirect(url_for("admin.campaigns_list"))


@admin_bp.route("/posts", methods=["GET"])
@admin_required
def posts_list():
    db = get_db()
    posts = db.query(Post).order_by(Post.created_at.desc()).all()
    return render_template("admin/posts_list.html", posts=posts, cents_to_amount_str=cents_to_amount_str)


@admin_bp.route("/posts/create", methods=["GET", "POST"])
@admin_required
def posts_create():
    if request.method == "GET":
        return render_template("admin/post_form.html", mode="create", post=None)

    title = (request.form.get("title") or "").strip()
    content = (request.form.get("content") or "").strip()
    file = request.files.get("image")

    if not title or len(title) < 3:
        flash("Post title is too short.", "danger")
        return render_template("admin/post_form.html", mode="create", post=None)
    if not content or len(content) < 10:
        flash("Post content is too short.", "danger")
        return render_template("admin/post_form.html", mode="create", post=None)

    image_filename = None
    try:
        image_filename = _save_post_image(file)
    except ValueError as e:
        flash(str(e), "danger")
        return render_template("admin/post_form.html", mode="create", post=None)

    db = get_db()
    post = Post(title=title, content=content, image_filename=image_filename)
    db.add(post)
    db.commit()
    flash("Post created.", "success")
    return redirect(url_for("admin.posts_list"))


@admin_bp.route("/posts/<int:post_id>/edit", methods=["GET", "POST"])
@admin_required
def posts_edit(post_id: int):
    db = get_db()
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        flash("Post not found.", "danger")
        return redirect(url_for("admin.posts_list"))

    if request.method == "GET":
        return render_template("admin/post_form.html", mode="edit", post=post)

    title = (request.form.get("title") or "").strip()
    content = (request.form.get("content") or "").strip()
    file = request.files.get("image")

    if not title or len(title) < 3:
        flash("Post title is too short.", "danger")
        return render_template("admin/post_form.html", mode="edit", post=post)
    if not content or len(content) < 10:
        flash("Post content is too short.", "danger")
        return render_template("admin/post_form.html", mode="edit", post=post)

    # Replace image if new one provided
    if file and file.filename:
        try:
            image_filename = _save_post_image(file)
        except ValueError as e:
            flash(str(e), "danger")
            return render_template("admin/post_form.html", mode="edit", post=post)
        _delete_file_if_exists(post.image_filename)
        post.image_filename = image_filename

    post.title = title
    post.content = content
    db.commit()
    flash("Post updated.", "success")
    return redirect(url_for("admin.posts_list"))


@admin_bp.route("/posts/<int:post_id>/delete", methods=["POST"])
@admin_required
def posts_delete(post_id: int):
    db = get_db()
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        flash("Post not found.", "danger")
        return redirect(url_for("admin.posts_list"))

    _delete_file_if_exists(post.image_filename)
    db.delete(post)
    db.commit()
    flash("Post deleted.", "success")
    return redirect(url_for("admin.posts_list"))


@admin_bp.route("/donations", methods=["GET"])
@admin_required
def donations_list():
    db = get_db()
    page, page_size = _parse_page_params()

    status = (request.args.get("status") or "").strip()
    q = (request.args.get("q") or "").strip()

    query = db.query(Donation).options(selectinload(Donation.campaign))
    if status:
        query = query.filter(Donation.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter((Donation.name.ilike(like)) | (Donation.email.ilike(like)) | (Donation.utr.ilike(like)))

    query = query.order_by(Donation.created_at.desc())
    total_count = query.count()
    donations = query.offset((page - 1) * page_size).limit(page_size).all()

    return render_template(
        "admin/donations_list.html",
        donations=donations,
        page=page,
        page_size=page_size,
        total_count=total_count,
        status=status,
        q=q,
        cents_to_amount_str=cents_to_amount_str,
        format_datetime=format_datetime,
    )


@admin_bp.route("/donations/<int:donation_id>/verify", methods=["POST"])
@admin_required
def donations_verify(donation_id: int):
    db = get_db()
    donation = db.query(Donation).filter(Donation.id == donation_id).first()
    if not donation:
        flash("Donation not found.", "danger")
        return redirect(url_for("admin.donations_list"))

    if donation.status == "verified":
        flash("Donation is already verified.", "warning")
        return redirect(url_for("admin.donations_list"))
    if not donation.utr:
        flash("UTR is missing. Ask donor to submit UTR first.", "danger")
        return redirect(url_for("admin.donations_list"))

    # Only allow verification from pending/awaiting state
    if donation.status not in {"pending", "awaiting_verification"}:
        flash("Donation status cannot be verified in its current state.", "danger")
        return redirect(url_for("admin.donations_list"))

    # Create income transaction and update campaign totals.
    donation.status = "verified"

    trx = Transaction(
        type="income",
        amount_cents=donation.amount_cents,
        purpose=f"Donation verified: {donation.name}",
        campaign_id=donation.campaign_id,
        donation_id=donation.id,
    )
    db.add(trx)

    if donation.campaign_id:
        campaign = db.query(Campaign).filter(Campaign.id == donation.campaign_id).first()
        if campaign:
            campaign.raised_cents = int(campaign.raised_cents) + int(donation.amount_cents)

    db.commit()
    flash("Donation verified and recorded in transactions.", "success")
    return redirect(url_for("admin.donations_list"))


@admin_bp.route("/donations/<int:donation_id>/reject", methods=["POST"])
@admin_required
def donations_reject(donation_id: int):
    db = get_db()
    donation = db.query(Donation).filter(Donation.id == donation_id).first()
    if not donation:
        flash("Donation not found.", "danger")
        return redirect(url_for("admin.donations_list"))

    if donation.status == "verified":
        flash("Cannot reject a verified donation.", "danger")
        return redirect(url_for("admin.donations_list"))

    donation.status = "rejected"
    db.commit()
    flash("Donation rejected.", "success")
    return redirect(url_for("admin.donations_list"))


@admin_bp.route("/expenses", methods=["GET"])
@admin_required
def expenses_list():
    db = get_db()
    page, page_size = _parse_page_params()

    q = (request.args.get("q") or "").strip()
    query = db.query(Transaction).filter(Transaction.type == "expense").order_by(Transaction.created_at.desc())
    if q:
        like = f"%{q}%"
        query = query.filter(Transaction.purpose.ilike(like))

    total_count = query.count()
    expenses = query.offset((page - 1) * page_size).limit(page_size).all()

    return render_template(
        "admin/expenses_list.html",
        expenses=expenses,
        page=page,
        page_size=page_size,
        total_count=total_count,
        q=q,
        cents_to_amount_str=cents_to_amount_str,
        format_datetime=format_datetime,
    )


@admin_bp.route("/expenses/create", methods=["POST"])
@admin_required
def expenses_create():
    db = get_db()
    purpose = (request.form.get("purpose") or "").strip()
    amount_str = (request.form.get("amount") or "").strip()

    if not purpose or len(purpose) < 3:
        flash("Please enter a purpose (min 3 chars).", "danger")
        return redirect(url_for("admin.expenses_list"))

    try:
        amount_cents = _parse_amount_cents(amount_str)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("admin.expenses_list"))

    trx = Transaction(type="expense", amount_cents=amount_cents, purpose=purpose)
    db.add(trx)
    db.commit()
    flash("Expense recorded.", "success")
    return redirect(url_for("admin.expenses_list"))


@admin_bp.route("/transactions/export", methods=["GET"])
@admin_required
def transactions_export():
    """
    Export filtered transactions to CSV (admin-only).
    """
    import csv
    import io
    from flask import Response

    db = get_db()
    export_type = (request.args.get("type") or "").strip()  # income/expense/both
    q = (request.args.get("q") or "").strip()

    query = db.query(Transaction)
    if export_type in {"income", "expense"}:
        query = query.filter(Transaction.type == export_type)
    if q:
        like = f"%{q}%"
        query = query.filter(Transaction.purpose.ilike(like))

    query = query.order_by(Transaction.created_at.desc())
    rows = query.all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "type", "amount", "purpose", "campaign_id", "donation_id"])
    for t in rows:
        writer.writerow(
            [
                t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
                t.type,
                cents_to_amount_str(int(t.amount_cents)),
                t.purpose,
                t.campaign_id or "",
                t.donation_id or "",
            ]
        )

    csv_data = buf.getvalue()
    response = Response(csv_data, mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=transactions.csv"
    return response

