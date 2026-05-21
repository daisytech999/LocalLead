from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import PLANS, User
from ..schemas import CheckoutRequest, CheckoutResponse
from ..services import billing

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("/plans")
def list_plans():
    return PLANS


@router.post("/checkout", response_model=CheckoutResponse)
def checkout(payload: CheckoutRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        url = billing.create_checkout_session(user, payload.plan)
    except billing.BillingConfigError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    db.commit()  # persist stripe_customer_id set during checkout creation
    return CheckoutResponse(checkout_url=url)


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    try:
        event = billing.verify_webhook(payload, sig)
    except billing.BillingConfigError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")

    etype = event["type"]
    obj = event["data"]["object"]

    if etype == "checkout.session.completed":
        _apply_plan(db, obj.get("metadata", {}).get("user_id"), obj.get("metadata", {}).get("plan"),
                    obj.get("subscription"), obj.get("customer"))
    elif etype in ("customer.subscription.updated", "customer.subscription.created"):
        price_id = (((obj.get("items") or {}).get("data") or [{}])[0].get("price") or {}).get("id")
        plan = billing.plan_for_price(price_id) or obj.get("metadata", {}).get("plan")
        _apply_plan(db, obj.get("metadata", {}).get("user_id"), plan, obj.get("id"), obj.get("customer"))
    elif etype == "customer.subscription.deleted":
        _downgrade(db, obj.get("customer"))

    return {"received": True}


def _apply_plan(db: Session, user_id, plan, subscription_id, customer_id):
    user = None
    if user_id:
        user = db.get(User, int(user_id))
    if user is None and customer_id:
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    if user is None or plan not in PLANS:
        return
    user.plan = plan
    if subscription_id:
        user.stripe_subscription_id = subscription_id
    if customer_id:
        user.stripe_customer_id = customer_id
    db.commit()


def _downgrade(db: Session, customer_id):
    if not customer_id:
        return
    user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    if user:
        user.plan = "starter"
        user.stripe_subscription_id = None
        db.commit()
