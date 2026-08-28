"""Stripe billing: a one-time $5 paywall in front of the chatbot.

Kept separate from routes (app.py) and from persistence (src.store) so
each layer has one job, matching the rest of this codebase. stripe is
imported inside _client(), not at module top level, consistent with
the other heavy/optional imports lazy-loaded elsewhere in this app.
"""

import os
import sys

PRICE_USD_CENTS = 500
CURRENCY = "usd"
PRODUCT_NAME = "Discovr chatbot access"


class BillingError(Exception):
    """Raised whenever a Stripe call fails. The message is written to be
    shown to the user as-is; the real stripe.error.StripeError is always
    logged to stderr first, so app.py can catch just this one exception
    type without importing the stripe SDK itself -- it never needs to
    know Stripe was involved, only that billing failed."""


def _client():
    import stripe

    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    return stripe


def _fail(log_context, user_message, error):
    print(f"Stripe error ({log_context}): {error}", file=sys.stderr)
    raise BillingError(user_message) from error


def create_checkout_session(user_id, user_email, success_url, cancel_url):
    """Creates a one-time $5 Checkout Session for user_id and returns its
    hosted URL. client_reference_id carries the user id so
    confirm_checkout_session can verify it later against Stripe's own
    record, not a client-supplied value.

    Raises BillingError (never a raw stripe.error.StripeError) on
    failure -- most commonly an invalid customer_email, which Stripe
    rejects with a 400 rather than silently ignoring."""
    stripe = _client()
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": CURRENCY,
                        "product_data": {"name": PRODUCT_NAME},
                        "unit_amount": PRICE_USD_CENTS,
                    },
                    "quantity": 1,
                }
            ],
            client_reference_id=user_id,
            customer_email=user_email,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except stripe.error.StripeError as error:
        _fail(
            "create_checkout_session",
            "We couldn't start checkout — please check your email address on your account.",
            error,
        )
    return session.url


def confirm_checkout_session(session_id, expected_user_id):
    """Retrieves the session from Stripe -- never trusts client-supplied
    query params -- and returns the payment_intent id if payment
    actually succeeded for expected_user_id, else None. Raises
    BillingError if Stripe itself can't be reached."""
    stripe = _client()
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError as error:
        _fail(
            "confirm_checkout_session",
            "We couldn't confirm your payment — please try again or contact support.",
            error,
        )
    if session.client_reference_id != expected_user_id:
        return None
    if session.payment_status != "paid":
        return None
    return session.payment_intent


def refund_payment(payment_intent_id):
    """Issues a full refund for a payment_intent. Raises BillingError on
    failure (e.g. already refunded, or Stripe unreachable) -- callers
    decide how to surface that."""
    stripe = _client()
    try:
        stripe.Refund.create(payment_intent=payment_intent_id)
    except stripe.error.StripeError as error:
        _fail(
            "refund_payment",
            "We couldn't process the refund — please try again or contact support.",
            error,
        )
