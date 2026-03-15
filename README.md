# x-reply-webhook-kit

X の返信やメンションを webhook で受け取り、ローカルの worker から取り出して処理するための最小構成です。

このリポジトリは次の 2 つで構成されています。

- `webhook-server/`
  - 公開側の受信サーバー
  - X webhook を受ける
  - `pull / ack` API を提供する
- `local-worker/`
  - 手元 PC 側の worker
  - `webhook-server` からイベントを取得して通知・返信処理を行う

## 想定アーキテクチャ

```text
X Webhook
  -> webhook-server
  -> local-worker が pull
  -> ローカルで通知 / 返信
  -> ack
```

## いま入っているもの

- `webhook-server/` に Flask ベースの最小実装
- X webhook の CRC 応答
- X 署名検証
- in-memory queue
- `pull / ack / debug` API
- `local-worker/` のひな形 README

## 各ディレクトリ

### `webhook-server/`

`Railway` などの公開環境に置くサーバーです。  
詳細は `program/20260315_x-reply-webhook-kit/webhook-server/README.md:1` を参照してください。

### `local-worker/`

ローカル PC 側の worker 置き場です。  
詳細は `program/20260315_x-reply-webhook-kit/local-worker/README.md:1` を参照してください。

## スタート地点

最初に触るならこの順番です。

1. `webhook-server/README.md` を読む
2. `webhook-server/.env.example` をもとに環境変数を設定する
3. Railway などに `webhook-server` をデプロイする
4. X Console で webhook URL を登録する
5. `local-worker` を実装して `pull / ack` する
