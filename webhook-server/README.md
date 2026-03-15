# webhook-server

X webhook を受けて、一時的にイベントを保持し、ローカル worker が `pull / ack` できるようにする Flask サーバーです。

## できること

- X webhook の CRC 応答
- `x-twitter-webhooks-signature` の検証
- イベントの受信と in-memory queue への格納
- ローカル worker 向けの `pull` API
- ローカル worker 向けの `ack` API
- queue 状態の確認用 `debug` API

## エンドポイント

### `GET /`

- healthcheck を返します

### `GET /webhook`

- `crc_token` を受けて `response_token` を返します

### `POST /webhook`

- X からの webhook を受けます
- 署名検証に通った payload だけ queue に積みます

### `GET /pull`

- Bearer token 認証が必要です
- pending なイベントを leased 状態で返します
- ローカル worker がここから新着を取得します

### `POST /ack`

- Bearer token 認証が必要です
- 処理済みイベントを `done` にするか、再試行用に戻します

### `GET /debug/events`

- Bearer token 認証が必要です
- queue に入っているイベント一覧を返します

## queue の仕様

- queue は **process memory** に保存されます
- そのため、deploy / restart / crash が起きると内容は消えます
- まずは最小構成として割り切る前提です

## 動作前提

- `Railway` を使う場合は **single replica**
- `Railway Serverless` は使わない
- `WORKER_TOKEN` を知っているローカル worker だけが `pull / ack` できます

## 環境変数

| 変数名 | 用途 |
| --- | --- |
| `X_CONSUMER_SECRET` | X webhook の CRC と署名検証に使う secret |
| `WORKER_TOKEN` | `pull / ack` API を叩く worker 用 Bearer token |
| `LEASE_SECONDS` | `pull` 後に lease する秒数 |

## ローカル実行

```bash
cd program/20260315_x-reply-webhook-kit/webhook-server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

## 確認コマンド

### CRC

```bash
curl "http://127.0.0.1:8080/webhook?crc_token=test123"
```

### pull

```bash
curl -H "Authorization: Bearer YOUR_WORKER_TOKEN" \
  "http://127.0.0.1:8080/pull?limit=10"
```

### ack

```bash
curl -X POST "http://127.0.0.1:8080/ack" \
  -H "Authorization: Bearer YOUR_WORKER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"event_ids":["EVENT_ID"],"status":"done"}'
```

## デプロイ

このディレクトリを `Railway` にデプロイし、次の環境変数を設定してください。

- `X_CONSUMER_SECRET`
- `WORKER_TOKEN`
- `LEASE_SECONDS`

デプロイ後は、X Console の webhook URL をこの公開 URL の `/webhook` に向けます。
