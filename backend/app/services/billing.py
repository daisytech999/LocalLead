"""Stripe billing integration for Pro/Agency plan subscriptions."""

import stripe

from ..config import get_settings
from ..models import User

settings = get_settings()

PLAN_TO_PRICE = {
    "pro": lambda: settings.stripe_price_pro,
    "agency": lambda: settings.stripe_price_agency,
}


class BillingConfigError(RuntimeError):
    pass


def _require_stripe() -> None:
    if not settings.stripe_secret_key:
        raise BillingConfigError("STRIPE_SECRET_KEY is not configured")
    stripe.api_key = settings.stripe_secret_key


def ensure_customer(user: User) -> str:
    _require_stripe()
    if user.stripe_customer_id:
        return user.stripe_customer_id
    customer = stripe.Customer.create(email=user.email, name=user.name, metadata={"user_id": str(user.id)})
    user.stripe_customer_id = customer.id
    return customer.id


def create_checkout_session(user: User, plan: str) -> str:
    _require_stripe()
    if plan not in PLAN_TO_PRICE:
        raise BillingConfigError(f"Plan '{plan}' is not purchasable")
    price_id = PLAN_TO_PRICE[plan]()
    if not price_id:
        raise BillingConfigError(f"Stripe price for '{plan}' is not configured")

    customer_id = ensure_customer(user)
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=settings.checkout_success_url,
        cancel_url=settings.checkout_cancel_url,
        metadata={"user_id": str(user.id), "plan": plan},
        subscription_data={"metadata": {"user_id": str(user.id), "plan": plan}},
    )
    return session.url


def verify_webhook(payload: bytes, sig_header: str | None):
    _require_stripe()
    if not settings.stripe_webhook_secret:
        raise BillingConfigError("STRIPE_WEBHOOK_SECRET is not configured")
    return stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)


def plan_for_price(price_id: str | None) -> str | None:
    if price_id and price_id == settings.stripe_price_pro:
        return "pro"
    if price_id and price_id == settings.stripe_price_agency:
        return "agency"
    return None
