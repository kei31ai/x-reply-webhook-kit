import argparse
import json
import os
import subprocess
import time
from dataclasses import dataclass

import requests
from dotenv import load_dotenv


load_dotenv()


@dataclass
class WorkerConfig:
    server_url: str
    worker_token: str
    poll_interval_seconds: int
    pull_limit: int
    auto_ack: bool
    ack_status: str
    enable_macos_notification: bool


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def get_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw.strip())


def load_config(args: argparse.Namespace) -> WorkerConfig:
    server_url = (args.server_url or os.getenv("WEBHOOK_SERVER_URL", "")).strip().rstrip("/")
    if not server_url:
        raise RuntimeError("Missing WEBHOOK_SERVER_URL")

    return WorkerConfig(
        server_url=server_url,
        worker_token=(args.worker_token or os.getenv("WORKER_TOKEN", "")).strip() or get_required_env("WORKER_TOKEN"),
        poll_interval_seconds=args.interval or get_int_env("POLL_INTERVAL_SECONDS", 60),
        pull_limit=args.limit or get_int_env("PULL_LIMIT", 10),
        auto_ack=not args.no_ack if args.no_ack else get_bool_env("AUTO_ACK", True),
        ack_status=(args.ack_status or os.getenv("ACK_STATUS", "done")).strip() or "done",
        enable_macos_notification=not args.no_notify if args.no_notify else get_bool_env("ENABLE_MACOS_NOTIFICATION", True),
    )


def build_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def pull_events(config: WorkerConfig) -> list[dict]:
    response = requests.get(
        f"{config.server_url}/pull",
        headers=build_headers(config.worker_token),
        params={"limit": config.pull_limit},
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    return body.get("items") or []


def ack_events(config: WorkerConfig, event_ids: list[str]) -> dict:
    response = requests.post(
        f"{config.server_url}/ack",
        headers=build_headers(config.worker_token),
        json={"event_ids": event_ids, "status": config.ack_status},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def format_event(event: dict) -> str:
    username = event.get("username") or "unknown"
    text = (event.get("text") or "").replace("\n", " ").strip()
    tweet_id = event.get("tweet_id") or ""
    return f"@{username} | {text} | tweet_id={tweet_id}"


def notify_macos(event: dict) -> None:
    title = f"X reply from @{event.get('username') or 'unknown'}"
    message = (event.get("text") or "").replace('"', "'").replace("\n", " ").strip()
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], check=False)


def print_event(event: dict) -> None:
    print(json.dumps(event, ensure_ascii=False, indent=2))


def handle_items(config: WorkerConfig, items: list[dict]) -> None:
    if not items:
        print("No new events.")
        return

    event_ids = []
    for item in items:
        print("-" * 80)
        print(format_event(item))
        print_event(item)
        if config.enable_macos_notification:
            notify_macos(item)
        event_ids.append(item["event_id"])

    if config.auto_ack:
        result = ack_events(config, event_ids)
        print("-" * 80)
        print(f"Acked events: {json.dumps(result, ensure_ascii=False)}")


def run_once(config: WorkerConfig) -> None:
    items = pull_events(config)
    handle_items(config, items)


def run_loop(config: WorkerConfig) -> None:
    print(f"Polling {config.server_url} every {config.poll_interval_seconds}s")
    while True:
        try:
            run_once(config)
        except KeyboardInterrupt:
            print("Stopped.")
            return
        except Exception as error:
            print(f"Worker error: {error}")

        time.sleep(config.poll_interval_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local worker for x-reply-webhook-kit")
    parser.add_argument("--once", action="store_true", help="Run one pull cycle and exit")
    parser.add_argument("--server-url", help="Override WEBHOOK_SERVER_URL")
    parser.add_argument("--worker-token", help="Override WORKER_TOKEN")
    parser.add_argument("--interval", type=int, help="Polling interval in seconds")
    parser.add_argument("--limit", type=int, help="Pull limit")
    parser.add_argument("--ack-status", choices=["done", "pending", "failed"], help="Ack status")
    parser.add_argument("--no-ack", action="store_true", help="Do not ack after printing events")
    parser.add_argument("--no-notify", action="store_true", help="Disable macOS notifications")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = load_config(args)

    if args.once:
        run_once(config)
        return

    run_loop(config)


if __name__ == "__main__":
    main()
