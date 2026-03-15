# x-reply-webhook-kit

X の返信検知を `webhook server` と `local worker` に分けて管理する作業フォルダです。

## 構成

- `webhook-server/`
  - 公開側
  - X webhook を受ける
  - `pull / ack` API を出す
- `local-worker/`
  - 手元 PC 側
  - `webhook-server` から event を取りに行く
  - 通知・返信処理を行う

## 公開方針

公開するなら、基本は **両方を同じリポジトリに入れた方が使う人には親切** です。

ただし以下は除外します。

- `.env`
- 個人用トークン
- macOS 専用の個別設定
- けいすけ固有の返信ロジック

つまり、
- `webhook-server/` はそのまま公開
- `local-worker/` は再利用できるテンプレートだけ公開

という形がよいです。
