# local-worker

ローカル PC で動かす worker 用ディレクトリです。

## 想定役割

- `webhook-server` の `GET /pull` を定期的に叩く
- 新着イベントを console や OS 通知に出す
- 必要なら既存の返信フローにつなぐ
- 処理後に `POST /ack` を返す

## 今後追加するもの

- `worker.py`
- `.env.example`
- 通知サンプル
- 常駐実行のメモ

## 想定フロー

```text
1. pull
2. 新着イベントを表示
3. 返信するか判断
4. done / failed を ack
```
