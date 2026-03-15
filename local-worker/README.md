# Local Worker

ローカル PC で動かす worker 用ディレクトリです。

想定役割:

- `webhook-server` の `GET /pull` を定期的に叩く
- 新着 event を console / 通知に出す
- 必要なら既存の X 返信フローにつなぐ
- 処理後に `POST /ack` を返す

## 今後入れるもの

- `worker.py`
- `.env.example`
- macOS 通知のサンプル
- `launchd` か常駐実行のメモ
