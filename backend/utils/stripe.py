import os
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import stripe

import logging

logger = logging.getLogger(__name__)

stripe.api_key = os.getenv('STRIPE_API_KEY')
endpoint_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
base_url = os.getenv('BASE_API_URL')
if base_url and not base_url.startswith(('http://', 'https://')):
    base_url = 'https://' + base_url


def create_subscription_checkout_session(
    uid: str,
    price_id: str,
    idempotency_key: Optional[str] = None,
    customer_id: Optional[str] = None,
    promotion_code_id: Optional[str] = None,
):
    """Create a Stripe Checkout session for a subscription."""
    try:
        success_url = urljoin(base_url, 'v1/payments/success?session_id={CHECKOUT_SESSION_ID}')  # type: ignore[reportArgumentType]  # base_url validated at runtime
        cancel_url = urljoin(base_url, 'v1/payments/cancel')  # type: ignore[reportArgumentType]  # base_url validated at runtime

        # session creation parameters
        session_params: Dict[str, Any] = {
            'client_reference_id': uid,
            'payment_method_types': ['card'],
            'line_items': [
                {
                    'price': price_id,
                    'quantity': 1,
                },
            ],
            'mode': 'subscription',
            'success_url': success_url,
            'cancel_url': cancel_url,
            'metadata': {
                'uid': uid,
                'sub_type': 'unlimited',
            },
            'subscription_data': {
                'metadata': {
                    'uid': uid,
                    'sub_type': 'unlimited',
                }
            },
        }

        if promotion_code_id:
            session_params['discounts'] = [{'promotion_code': promotion_code_id}]
        else:
            session_params['allow_promotion_codes'] = True

        if customer_id:
            session_params['customer'] = customer_id
            session_params['customer_update'] = {'name': 'auto', 'address': 'auto'}

        if idempotency_key:
            session_params['idempotency_key'] = idempotency_key

        checkout_session = stripe.checkout.Session.create(**session_params)
        return checkout_session
    except stripe.error.InvalidRequestError:  # type: ignore[reportAttributeAccessIssue,reportUnknownMemberType]  # stripe.error exposed dynamically at runtime
        raise
    except Exception as e:
        logger.error(f"Error creating checkout session: {e}")
        return None


def cancel_subscription(subscription_id: str):
    """Cancel a Stripe subscription at the end of the current period."""
    try:
        return stripe.Subscription.modify(
            subscription_id,
            cancel_at_period_end=True,
        )
    except Exception as e:
        logger.error(f"Error canceling subscription: {e}")
        return None


# Stripe statuses in which a subscription can no longer bill the customer. Stripe rejects
# `cancel_at_period_end` on these ("A canceled subscription can only update its
# cancellation_details and metadata"), so callers that only need the goal state — the
# subscription is not billing — must ask Stripe rather than treat that 400 as a failure.
TERMINAL_SUBSCRIPTION_STATUSES = frozenset({'canceled', 'incomplete_expired'})


def cancel_subscription_for_account_deletion(subscription_id: str) -> None:
    """Cancel now for erasure; absent/terminal subscriptions already satisfy it.

    Unlike period-end cancellation, transport/rate-limit/server errors propagate
    so the deletion task can retry without mistaking an outage for success.
    """
    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
        if subscription.get('status') in TERMINAL_SUBSCRIPTION_STATUSES:
            return
        canceled = subscription.delete()
        if canceled.get('status') not in TERMINAL_SUBSCRIPTION_STATUSES:
            raise RuntimeError('Stripe immediate cancellation did not reach a terminal status')
    except stripe.InvalidRequestError as error:
        if error.code == 'resource_missing' or 'no such subscription' in str(error).lower():
            return
        # A concurrent cancellation can win between retrieve and delete. Verify
        # the goal state rather than accepting an arbitrary Stripe 400.
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
        except stripe.InvalidRequestError as read_error:
            if read_error.code == 'resource_missing' or 'no such subscription' in str(read_error).lower():
                return
            raise
        if subscription.get('status') not in TERMINAL_SUBSCRIPTION_STATUSES:
            raise error


def is_subscription_terminal(subscription_id: str) -> bool:
    """Whether Stripe currently reports the subscription in a terminal, non-billing state.

    Fails closed: an unreadable subscription or any non-terminal status returns False, so a
    caller never mistakes a transport error for a subscription that is already canceled. A
    subscription that does not exist at all (Stripe ``resource_missing``) is terminal: nothing
    can bill through an id Stripe does not know.
    """
    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
    except stripe.InvalidRequestError as e:
        if getattr(e, 'code', None) == 'resource_missing' or getattr(e, 'http_status', None) == 404:
            # A subscription id Stripe has never heard of (a stale or synthetic id stored on the
            # user) cannot bill anyone, so the billing goal state is already met. Treating it as a
            # failure left account-deletion wipes retrying forever behind the auth fence.
            logger.warning(f"Subscription {subscription_id} does not exist in Stripe; treating as terminal")
            return True
        logger.error(f"Error retrieving subscription: {e}")
        return False
    except Exception as e:
        logger.error(f"Error retrieving subscription: {e}")
        return False
    return subscription.get('status') in TERMINAL_SUBSCRIPTION_STATUSES


def find_billable_app_subscription_ids(uid: str) -> list[str]:
    if not stripe.api_key:
        return []
    subscriptions = stripe.Subscription.search(query=f"metadata['uid']:'{uid}'")
    return [
        subscription.id
        for subscription in subscriptions.auto_paging_iter()
        if subscription.get('metadata', {}).get('app_id')
        and subscription.get('status') not in TERMINAL_SUBSCRIPTION_STATUSES
    ]


def parse_event(payload: Any, sig_header: Any) -> Any:
    """Parse the Stripe event."""
    return stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)  # type: ignore[reportUnknownMemberType]  # stripe Webhook.construct_event partially typed
