import argparse
import json
import os
from typing import Any

from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session
import requests


load_dotenv()

API_BASE = "https://api.x.com/2"


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_bearer_headers() -> dict[str, str]:
    token = get_required_env("X_BEARER_TOKEN")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def get_oauth1_session() -> OAuth1Session:
    return OAuth1Session(
        get_required_env("X_API_KEY"),
        client_secret=get_required_env("X_API_SECRET"),
        resource_owner_key=get_required_env("X_ACCESS_TOKEN"),
        resource_owner_secret=get_required_env("X_ACCESS_TOKEN_SECRET"),
    )


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def handle_response(response) -> Any:
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}

    if response.status_code >= 400:
        raise RuntimeError(
            f"HTTP {response.status_code}\n{json.dumps(body, ensure_ascii=False, indent=2)}"
        )

    return body


def list_webhooks() -> Any:
    response = requests.get(
        f"{API_BASE}/webhooks",
        headers=get_bearer_headers(),
        timeout=30,
    )
    return handle_response(response)


def create_webhook(url: str) -> Any:
    response = requests.post(
        f"{API_BASE}/webhooks",
        headers=get_bearer_headers(),
        json={"url": url},
        timeout=30,
    )
    return handle_response(response)


def list_subscriptions(webhook_id: str) -> Any:
    response = requests.get(
        f"{API_BASE}/account_activity/webhooks/{webhook_id}/subscriptions/all/list",
        headers=get_bearer_headers(),
        timeout=30,
    )
    return handle_response(response)


def subscribe_user(webhook_id: str) -> Any:
    session = get_oauth1_session()
    response = session.post(
        f"{API_BASE}/account_activity/webhooks/{webhook_id}/subscriptions/all",
        timeout=30,
    )
    return handle_response(response)


def find_webhook_id_by_url(target_url: str) -> str:
    body = list_webhooks()
    webhooks = body.get("data") or []
    for webhook in webhooks:
        if webhook.get("url") == target_url:
            return webhook["id"]
    raise RuntimeError(f"Webhook not found for url: {target_url}")


def ensure_subscription(target_url: str) -> Any:
    webhook_id = find_webhook_id_by_url(target_url)
    return {
        "webhook_id": webhook_id,
        "subscribe_result": subscribe_user(webhook_id),
        "subscriptions": list_subscriptions(webhook_id),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage X Account Activity webhooks and subscriptions"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-webhooks", help="List registered webhooks")

    create_parser = subparsers.add_parser("create-webhook", help="Create a webhook")
    create_parser.add_argument("--url", required=True, help="Public webhook URL")

    subs_parser = subparsers.add_parser("list-subscriptions", help="List subscriptions")
    subs_parser.add_argument("--webhook-id", required=True, help="Webhook ID")

    subscribe_parser = subparsers.add_parser(
        "subscribe", help="Subscribe the authenticating user to a webhook"
    )
    subscribe_parser.add_argument("--webhook-id", required=True, help="Webhook ID")

    ensure_parser = subparsers.add_parser(
        "ensure-subscription",
        help="Find a webhook by URL, subscribe the current user, and show subscriptions",
    )
    ensure_parser.add_argument("--url", required=True, help="Registered webhook URL")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "list-webhooks":
        print_json(list_webhooks())
        return

    if args.command == "create-webhook":
        print_json(create_webhook(args.url))
        return

    if args.command == "list-subscriptions":
        print_json(list_subscriptions(args.webhook_id))
        return

    if args.command == "subscribe":
        print_json(subscribe_user(args.webhook_id))
        return

    if args.command == "ensure-subscription":
        print_json(ensure_subscription(args.url))
        return

    raise RuntimeError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
