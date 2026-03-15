# X Webhook Queue for Railway

X webhook を `Railway` で受けて、ローカルの返信 worker が `pull/ack` できるようにする最小構成です。

## 構成

- `GET /`
  - `crc_token` があれば `response_token` を返す
  - それ以外は healthcheck
- `POST /webhook`
  - `x-twitter-webhooks-signature` を検証
  - event を in-memory queue に積む
- `GET /pull`
  - Bearer token 認証
  - pending event を leased にして返す
- `POST /ack`
  - Bearer token 認証
  - 処理済み event を削除、または状態更新
- `GET /debug/events`
  - Bearer token 認証
  - queue の中身を確認

## 前提

- `Railway` は **single replica**
- `Railway Serverless` は **使わない**
- queue は process memory だけなので、deploy / restart / crash で消えます

## 環境変数

- `X_CONSUMER_SECRET`
- `WORKER_TOKEN`
- `LEASE_SECONDS`

## ローカル実行

```bash
cd program/20260315_x-reply-webhook-kit/webhook-server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

## CRC テスト

```bash
curl "http://127.0.0.1:8080/?crc_token=test123"
```

## pull テスト

```bash
curl -H "Authorization: Bearer YOUR_WORKER_TOKEN" \
  "http://127.0.0.1:8080/pull?limit=10"
```

## ack テスト

```bash
curl -X POST "http://127.0.0.1:8080/ack" \
  -H "Authorization: Bearer YOUR_WORKER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"event_ids":["EVENT_ID"],"status":"done"}'
```

## GitHub 用メモ

このディレクトリ単体で GitHub に上げられるようにしてあります。
push 前に以下だけ入れてください。

- `.env` を作る
- Railway 側に同じ環境変数を設定する
- X Console の webhook URL を Railway の公開 URL に向ける
