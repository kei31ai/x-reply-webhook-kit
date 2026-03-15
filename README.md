# x-reply-webhook-kit

X のメンション・リプライ・引用リポストを webhook で受け取り、ローカルの worker が取り出して **Claude Code で返信判断・返信送信まで行う** 仕組みです。

このリポジトリは次の 2 つで構成されています（2026-06-12 更新: 旧 `local-worker/` ひな形は削除済み。現役は `local-worker2/` のみ）。

- `webhook-server/`
  - 公開側の受信サーバー（Railway にデプロイ）
  - X webhook の CRC 応答・署名検証
  - in-memory queue + `pull / ack / debug` API
- `local-worker2/`
  - 手元 PC（Windows マシン）側の本命 worker
  - 1分ごとに `pull` → イベント判定 → `post/` に YAML 保存 → Claude Code で返信判断 → 返信送信 → `ack`

## アーキテクチャ

```text
X Webhook（メンション / リプライ / 引用リポスト / フォロー・アンフォロー）
  -> webhook-server（Railway・署名検証・queue 保持）
  -> local-worker2 が 1分ごとに pull
  ├─ tweet 系イベント
  │    -> post/{post_tweet_id}.yaml に保存（会話履歴つき）
  │    -> Claude Code CLI を起動して action を判断
  │         __REPLY_ACTION__ / __QUOTE_REPOST_ACTION__ / __NOOP_ACTION__
  │         （オーナー投稿のみ + __TASK_REGISTER_ACTION__）
  │    -> reply は task-x-api の資産で送信、結果を worker_result に記録
  │    -> positive=true かつ相手がフォロワーならフォローバック
  └─ follow_events
       -> followers.json をローカル更新（API 呼び出しゼロ）
       -> アンフォローされたら unfollow_queue に積む（日次バッチで返す）
  -> ack（done）
```

## 各ディレクトリ

### `webhook-server/`

Railway などの公開環境に置く Flask サーバーです。

- X webhook の CRC 応答と `x-twitter-webhooks-signature` 検証
- イベントを in-memory queue に格納（restart で消える割り切り構成・single replica 前提）
- `GET /pull`（Bearer 認証・lease 方式）/ `POST /ack` / `GET /debug/events`
- Account Activity subscription は `scripts/account_activity.py` で API から作成

詳細は `webhook-server/README.md` を参照してください。

### `local-worker2/`

ローカル PC 側の本命 worker です。日常運用前提で、現在も常駐稼働しています。

- **実行環境**: Windows マシン（`venv_win/` + `run_worker_win.bat`）。コードは Mac/Windows 両対応（`os.name` で task-x-api の python を切り替え）
- **イベント判定**: `referenced_tweets[].type` を正本に reply / quote / mention を判定。自分自身の投稿はスキップ
- **保存形式**: `post/{post_tweet_id}.yaml` 単一ファイル運用（入力保存 + 処理結果更新）。reply は root post まで最大10件遡って `conversation_history`（古い→新しい・order付き）を全文保存
- **返信判断**: Claude Code CLI を read/write 権限なしで起動。IDENTITY / SOUL / USER / persona / 相手の people データをインライン展開した長文プロンプトを渡し、標準出力の action を parse
- **action の種類**:
  - 通常ユーザー投稿: `__REPLY_ACTION__` / `__QUOTE_REPOST_ACTION__` / `__NOOP_ACTION__` の3択
  - タスク登録オーナー投稿: 上記 + `__TASK_REGISTER_ACTION__` の4択（external-task-inbox へ登録 + 受付リプライ）
  - reply / quote_repost には **`positive`（bool）** を含める（2026-06-12追加）: 相手の投稿が友好的なら true。「こちらから相手をフォローするか」の判断材料として `worker_result.positive` に記録される。フォロー関係の確認は `get_user.py` の `connection_status`（followed_by / following）で取得可能
- **返信送信**: `.claude/skills/task-x-api` のスクリプト資産を流用して worker 自身が送信
- **状態管理**: `worker_result.status`（`replied` / `quote_reposted` / `task_registered` / `noop` / `failed` / `pending`）を正本に再処理を防止
- **連携**: people record（`task-people-record`）、external task inbox（`20260227_discord` のモジュールを import）
- **ログ**: `logs/worker-YYYYMMDD.log` に標準出力・標準エラーを保存
- **実行モード**: `--once`（1回実行）/ 常駐ループ。`--interval` `--limit` `--no-ack` `--claude-timeout` 等で調整可

仕様の正本は `local-worker2/REQUIREMENTS.md` を参照してください（FR-1〜FR-18 / NFR / post_id.yaml フォーマット）。

## フォロワー管理（2026-06-12 追加・FR-15〜FR-18）

API 費用をかけずにフォロー関係を管理する仕組みです。

- **followers.json**（`local-worker2/` 直下・gitignore 推奨）: `followers` / `following` / `unfollow_queue` / `last_unfollow_batch_date` を保持するローカルキャッシュ。処理時の API 呼び出しはゼロ
  - 初期構築: `python worker.py --bootstrap`（`get_followers.py --all` で followers / following を全件取得して保存）
  - 以降は webhook の `follow_events`（follow / unfollow）で差分更新。自分発のフォロー操作も following に同期
- **フォローバック**（FR-16）: 無条件フォロバはしない。**「相手がフォロワー」AND「リプ等で positive=true」** のときだけフォローする。こちらから先に自発フォローはしない。結果は `worker_result.followed_back` に記録（`followed` / `skipped_not_follower` / `already_following` / `skipped_cooldown` / `error_cooldown_started`）
- **フォローエラー時クールダウン**（FR-16a）: フォロー API エラー = レート制限と判断し、**24時間 in-memory でフォロー停止**。ファイルには保存しない（worker 再起動後の初回エラーで再アーム）
- **アンフォロー返し**(FR-17): アンフォローされても即返しはしない（bot 感排除）。unfollow_queue に積み、**1日1回・最大10人**の日次バッチで `unfollow.py` 実行。キュー方式なのは、ブートストラップ取込済みの既存フォロー（けいすけ本人等）を機械判定で誤切りしないため
- **is_follower**: post yaml の `current_post.is_follower` にキャッシュ参照で記録（Claude の返信判断の参考情報）
- 新規 API スクリプト: `task-x-api/scripts/unfollow.py`（DELETE following）/ `get_followers.py`（followers / following ページネーション取得）

## 環境変数

### webhook-server

| 変数名 | 用途 |
| --- | --- |
| `X_CONSUMER_SECRET` | CRC と署名検証 |
| `WORKER_TOKEN` | `pull / ack` 用 Bearer token |
| `LEASE_SECONDS` | pull 後の lease 秒数 |

### local-worker2（.env）

| 変数名 | 用途 |
| --- | --- |
| `WEBHOOK_SERVER_URL` | webhook-server の公開 URL |
| `WORKER_TOKEN` | webhook-server と共有する Bearer token |
| その他 | `.env.example` を参照（polling 間隔、Claude CLI パス、タスク登録オーナー指定等） |

## 運用メモ

- 旧 `local-worker/` は 2026-03-15 の初期ひな形のまま使われておらず、**2026-06-12 にけいすけが削除**（現役は `local-worker2/` のみ）
- queue は in-memory のため、webhook-server を再デプロイするとイベントが消える。取りこぼしは通知チェック系のスキルで補完する
- `__QUOTE_REPOST_ACTION__` は**通知起点（自分宛てのメンション・リプライ）の引用リポスト**なのでルール上OK（2026-06-12 けいすけ確認。禁止なのは「こちらから他人のポストへ自発的に引用しに行く」場合のみ。CLAUDE.md も同日修正済み）

## スタート地点

1. `webhook-server/README.md` を読んで Railway にデプロイする
2. X Console / Account Activity API で webhook URL を登録する
3. `local-worker2/.env` を設定する
4. `python worker.py --bootstrap` で followers.json を初期構築する
5. Windows マシンで `run_worker_win.bat` を起動（または `python worker.py --once` で単発確認）

### フォロワー管理デプロイ手順（2026-06-12 変更分の反映）

1. **webhook-server を Railway に再デプロイ**（follow_events 受信対応）
2. デプロイ後、実際のフォローイベントを発生させて `GET /debug/events` で raw_payload の形式を確認（legacy / v2 両対応済みだが実形式は要確認）
3. Windows 側で `python worker.py --bootstrap` を実行して followers.json を作成
4. worker を再起動（`run_worker_win.bat`）して新コードを反映
