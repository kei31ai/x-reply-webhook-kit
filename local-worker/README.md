# local-worker

ローカル PC で動かす worker 用ディレクトリです。

## 想定役割

- `webhook-server` の `GET /pull` を定期的に叩く
- 新着イベントを console や OS 通知に出す
- 必要なら既存の返信フローにつなぐ
- 処理後に `POST /ack` を返す

## 入っているもの

- `worker.py`
- `.env.example`
- `requirements.txt`

## 想定フロー

```text
1. pull
2. 新着イベントを表示
3. 返信するか判断
4. done / failed を ack
```

## セットアップ

```bash
cd /Users/keisukeohno/Dropbox/xPersonal/project/mp0059_program/20260113_kei31ai/program/20260315_x-reply-webhook-kit/local-worker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env.example` は公開用テンプレートです。実際の `WEBHOOK_SERVER_URL` は、Git に載せない `.env` にだけ入れます。

## 環境変数

| 変数名 | 用途 |
| --- | --- |
| `WEBHOOK_SERVER_URL` | 公開 webhook server の URL |
| `WORKER_TOKEN` | `pull / ack` 用 Bearer token |
| `POLL_INTERVAL_SECONDS` | ポーリング間隔 |
| `PULL_LIMIT` | 1回で取る件数 |
| `AUTO_ACK` | 取得後に自動 ack するか |
| `ACK_STATUS` | ack 時の status |
| `ENABLE_MACOS_NOTIFICATION` | macOS 通知を出すか |

## 実行例

1 回だけ確認:

```bash
cd /Users/keisukeohno/Dropbox/xPersonal/project/mp0059_program/20260113_kei31ai/program/20260315_x-reply-webhook-kit/local-worker
source .venv/bin/activate
python worker.py --once
```

常駐:

```bash
cd /Users/keisukeohno/Dropbox/xPersonal/project/mp0059_program/20260113_kei31ai/program/20260315_x-reply-webhook-kit/local-worker
source .venv/bin/activate
python worker.py
```

## 補足

- デフォルトでは、取得したイベントを表示したあと `done` で自動 ack します
- 通知だけ見たい場合は `--no-ack` を使います
- macOS 通知は `osascript` を使っています
