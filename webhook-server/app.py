import base64
import hashlib
import hmac
import json
import os
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, request


load_dotenv()

app = Flask(__name__)

QUEUE_LOCK = threading.Lock()
EVENT_ORDER = deque()
EVENTS = {}


def now_ts() -> float:
    return time.time()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_consumer_secret() -> str:
    return get_required_env("X_CONSUMER_SECRET")


def get_worker_token() -> str:
    return get_required_env("WORKER_TOKEN")


def get_lease_seconds() -> int:
    raw = os.getenv("LEASE_SECONDS", "300").strip()
    try:
        return max(30, int(raw))
    except ValueError:
        return 300


def is_authorized_worker() -> bool:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return False
    token = auth_header.removeprefix("Bearer ").strip()
    return hmac.compare_digest(token, get_worker_token())


def build_crc_response_token(crc_token: str) -> str:
    digest = hmac.new(
        get_consumer_secret().encode("utf-8"),
        crc_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return "sha256=" + base64.b64encode(digest).decode("utf-8")


def verify_x_signature(raw_body: bytes) -> bool:
    expected_header = request.headers.get("x-twitter-webhooks-signature", "")
    if not expected_header:
        return False

    digest = hmac.new(
        get_consumer_secret().encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).digest()
    expected_value = "sha256=" + base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected_header, expected_value)


def summarize_follow_user(user: dict) -> tuple[str, str]:
    """follow_events の user オブジェクトから (user_id, username) を取り出す。

    legacy AAA 形式 (id_str / screen_name) と v2 形式 (id / username) の両方を許容する。
    """
    user = user or {}
    user_id = str(user.get("id_str") or user.get("id") or "")
    username = str(user.get("screen_name") or user.get("username") or "")
    return user_id, username


def summarize_payload(payload: dict) -> dict:
    follow_events = payload.get("follow_events") or []
    if follow_events:
        event = follow_events[0]
        follow_type = str(event.get("type") or "")
        source_id, source_username = summarize_follow_user(event.get("source"))
        target_id, target_username = summarize_follow_user(event.get("target"))
        return {
            "event_type": "follow_events",
            "follow_type": follow_type,
            "tweet_id": "",
            "conversation_id": "",
            "user_id": source_id,
            "username": source_username,
            "target_user_id": target_id,
            "target_username": target_username,
            "text": "",
            "source_created_at": str(event.get("created_timestamp") or event.get("created_at") or ""),
        }

    tweet_events = payload.get("tweet_create_events") or []
    if tweet_events:
        event = tweet_events[0]
        user = event.get("user") or {}
        text = event.get("text") or ""
        # 素のリツイート（リポスト）は返信対象外。legacy AAA は retweeted_status を持ち、
        # 本文は "RT @..." で始まる。引用RT(quoted_status)は対象なので除外しない。
        # これを queue に入れて返信すると自己リプ事故になる（2026-06-13）。
        is_retweet = bool(event.get("retweeted_status")) or text.startswith("RT @")
        return {
            "event_type": "tweet_create_events",
            "is_retweet": is_retweet,
            "tweet_id": event.get("id_str") or event.get("id") or "",
            "conversation_id": event.get("conversation_id_str") or "",
            "user_id": user.get("id_str") or "",
            "username": user.get("screen_name") or "",
            "text": text,
            "source_created_at": event.get("created_at") or "",
        }

    data = payload.get("data") or {}
    includes = payload.get("includes") or {}
    users = includes.get("users") or []
    first_user = users[0] if users else {}
    if data:
        return {
            "event_type": "data",
            "tweet_id": data.get("id") or "",
            "conversation_id": data.get("conversation_id") or "",
            "user_id": data.get("author_id") or "",
            "username": first_user.get("username") or "",
            "text": data.get("text") or "",
            "source_created_at": data.get("created_at") or "",
        }

    keys = list(payload.keys())
    return {
        "event_type": keys[0] if keys else "unknown",
        "tweet_id": "",
        "conversation_id": "",
        "user_id": "",
        "username": "",
        "text": "",
        "source_created_at": "",
    }


def event_dedupe_key(summary: dict) -> str:
    parts = [
        summary.get("event_type", ""),
        summary.get("tweet_id", ""),
        summary.get("conversation_id", ""),
        summary.get("user_id", ""),
        # follow_events: フォロー→即アンフォローの連続を別イベントとして扱う
        summary.get("follow_type", ""),
        summary.get("source_created_at", "") if summary.get("event_type") == "follow_events" else "",
    ]
    return "|".join(parts)


def is_leased(event: dict) -> bool:
    leased_until = event.get("leased_until")
    return bool(leased_until and leased_until > now_ts())


def enqueue_event(summary: dict, payload: dict) -> dict:
    dedupe_key = event_dedupe_key(summary)

    with QUEUE_LOCK:
        for event_id in EVENT_ORDER:
            event = EVENTS.get(event_id)
            if not event:
                continue
            if event["dedupe_key"] == dedupe_key and event["status"] in {"pending", "leased"}:
                event["duplicate_count"] += 1
                event["last_seen_at"] = now_iso()
                return event

        event_id = str(uuid.uuid4())
        event = {
            "event_id": event_id,
            "dedupe_key": dedupe_key,
            "received_at": now_iso(),
            "last_seen_at": now_iso(),
            "duplicate_count": 0,
            "status": "pending",
            "leased_until": None,
            "summary": summary,
            "raw_payload": payload,
        }
        EVENTS[event_id] = event
        EVENT_ORDER.append(event_id)
        return event


def pull_events(limit: int) -> list[dict]:
    lease_seconds = get_lease_seconds()
    items = []

    with QUEUE_LOCK:
        for event_id in list(EVENT_ORDER):
            if len(items) >= limit:
                break

            event = EVENTS.get(event_id)
            if not event:
                continue

            if event["status"] == "done":
                continue

            if event["status"] == "leased" and is_leased(event):
                continue

            event["status"] = "leased"
            event["leased_until"] = now_ts() + lease_seconds
            event["lease_started_at"] = now_iso()
            items.append(
                {
                    "event_id": event["event_id"],
                    "received_at": event["received_at"],
                    "status": event["status"],
                    "duplicate_count": event["duplicate_count"],
                    **event["summary"],
                }
            )

    return items


def ack_events(event_ids: list[str], status: str) -> dict:
    updated = 0
    removed = 0

    with QUEUE_LOCK:
        for event_id in event_ids:
            event = EVENTS.get(event_id)
            if not event:
                continue

            if status == "done":
                EVENTS.pop(event_id, None)
                try:
                    EVENT_ORDER.remove(event_id)
                except ValueError:
                    pass
                removed += 1
                continue

            event["status"] = status
            event["leased_until"] = None
            event["updated_at"] = now_iso()
            updated += 1

    return {
        "updated": updated,
        "removed": removed,
    }


@app.get("/")
def root():
    with QUEUE_LOCK:
        pending_count = sum(1 for event_id in EVENT_ORDER if EVENTS.get(event_id))

    return jsonify(
        {
            "ok": True,
            "service": "x-webhook-queue",
            "mode": "in-memory",
            "pending_count": pending_count,
            "now": now_iso(),
        }
    )


@app.get("/webhook")
def webhook_crc():
    crc_token = request.args.get("crc_token", "").strip()
    if not crc_token:
        return jsonify({"ok": False, "error": "crc_token_required"}), 400
    return jsonify({"response_token": build_crc_response_token(crc_token)})


@app.post("/webhook")
def webhook():
    raw_body = request.get_data()

    if not verify_x_signature(raw_body):
        return jsonify({"ok": False, "error": "invalid_signature"}), 401

    try:
        payload = request.get_json(force=True, silent=False) or {}
    except Exception as error:
        return jsonify({"ok": False, "error": "invalid_json", "detail": str(error)}), 400

    summary = summarize_payload(payload)
    is_follow_event = summary.get("event_type") == "follow_events"
    if is_follow_event:
        # follow_events に tweet_id はない。user_id が取れていれば有効イベント
        if not summary.get("user_id"):
            return jsonify(
                {
                    "ok": True,
                    "ignored": True,
                    "reason": "missing_user_id",
                    "event_type": "follow_events",
                }
            )
    elif not summary.get("tweet_id"):
        return jsonify(
            {
                "ok": True,
                "ignored": True,
                "reason": "missing_tweet_id",
                "event_type": summary.get("event_type", "unknown"),
            }
        )
    elif summary.get("is_retweet"):
        # 素のリツイート（リポスト）は queue に入れない。返信すると自己リプ事故になる（2026-06-13）
        return jsonify(
            {
                "ok": True,
                "ignored": True,
                "reason": "retweet_not_target",
                "event_type": summary.get("event_type", "unknown"),
                "tweet_id": summary.get("tweet_id", ""),
            }
        )

    event = enqueue_event(summary, payload)

    return jsonify(
        {
            "ok": True,
            "event_id": event["event_id"],
            "event_type": summary["event_type"],
            "tweet_id": summary["tweet_id"],
        }
    )


@app.get("/pull")
def pull():
    if not is_authorized_worker():
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    try:
        limit = max(1, min(50, int(request.args.get("limit", "20"))))
    except ValueError:
        limit = 20

    items = pull_events(limit)
    return jsonify(
        {
            "ok": True,
            "count": len(items),
            "items": items,
        }
    )


@app.post("/ack")
def ack():
    if not is_authorized_worker():
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    body = request.get_json(force=True, silent=True) or {}
    event_ids = body.get("event_ids") or []
    status = (body.get("status") or "done").strip()

    if not isinstance(event_ids, list) or not event_ids:
        return jsonify({"ok": False, "error": "event_ids_required"}), 400

    if status not in {"done", "pending", "failed"}:
        return jsonify({"ok": False, "error": "invalid_status"}), 400

    result = ack_events(event_ids, status)
    return jsonify({"ok": True, **result})


@app.get("/debug/events")
def debug_events():
    if not is_authorized_worker():
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    with QUEUE_LOCK:
        items = []
        for event_id in list(EVENT_ORDER):
            event = EVENTS.get(event_id)
            if not event:
                continue
            items.append(
                {
                    "event_id": event["event_id"],
                    "status": event["status"],
                    "received_at": event["received_at"],
                    "leased_until": event["leased_until"],
                    "duplicate_count": event["duplicate_count"],
                    **event["summary"],
                }
            )

    return jsonify({"ok": True, "count": len(items), "items": items})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=True)
