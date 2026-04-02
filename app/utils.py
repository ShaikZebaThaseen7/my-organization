from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import quote


def amount_to_cents(amount: str | Decimal | int | float) -> int:
    if isinstance(amount, int):
        return amount
    if isinstance(amount, float):
        amount = Decimal(str(amount))
    if isinstance(amount, Decimal):
        val = amount
    else:
        try:
            val = Decimal(str(amount).strip())
        except (InvalidOperation, AttributeError) as e:
            raise ValueError("Invalid amount") from e

    if val < 0:
        raise ValueError("Amount must be >= 0")

    # Normalize to cents
    return int((val * 100).quantize(Decimal("1")))


def cents_to_amount_str(cents: int) -> str:
    return f"{Decimal(cents) / Decimal(100):.2f}"


def format_datetime(dt: datetime | None) -> str:
    if dt is None:
        return "-"
    # Use local display format (simple and readable)
    return dt.strftime("%Y-%m-%d %H:%M")


def format_date(d: date | None) -> str:
    if d is None:
        return "-"
    return d.strftime("%Y-%m-%d")


def build_upi_payment_uri(
    *,
    payee: str,
    payer_name: str,
    amount_cents: int,
    transaction_ref: str,
    purpose: str,
) -> str:
    """
    Build a simple UPI payment URI for QR generation.
    Example: upi://pay?pa=<payee>&pn=<name>&am=<amount>&tr=<ref>&tn=<purpose>
    """
    amount = f"{Decimal(amount_cents) / Decimal(100):.2f}"
    # UPI parameters are query-string values
    return (
        "upi://pay?"
        f"pa={quote(payee)}&pn={quote(payer_name)}&am={quote(amount)}&tr={quote(transaction_ref)}&tn={quote(purpose)}"
    )

