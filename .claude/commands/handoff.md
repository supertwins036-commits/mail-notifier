---
description: 見張りの仕組み(GitHub Actions)の健全性チェック → 環境情報の収集 → 引き継ぎ書の作成(非公開の ~/.claude 側)→ コミットと push、までを自動で行う
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Write, ToolSearch, PowerShell, mcp__ccd_session_mgmt__get_session, mcp__ccd_session_mgmt__list_sessions, Bash(ls:*), Bash(date:*), Bash(cat:*), Bash(python -X utf8:*), Bash(python --version:*), Bash(gh auth status:*), Bash(gh workflow list:*), Bash(gh run list:*), Bash(gh secret list:*), Bash(git status:*), Bash(git log:*), Bash(git pull:*), Bash(git -C:*), Bash(mkdir:*)
---

# /handoff — 引き継ぎ(見張りの点検 → 引き継ぎ書)

長いセッションで精度が落ちる前に、見張りの仕組みの状態を確かめ、新しいセッションに渡す引き継ぎ書を作る。
makeDoc の `/handoff` を、このフォルダ(`C:\MyFolder\MyProjects\name.Com`。お名前.com のメールの新着を Discord に知らせる仕組み)向けに直したもの(2026-11-13)。

このフォルダの約束:
- **リポジトリは公開(`supertwins036-commits/mail-notifier`)。** 中身は誰でも読める。メールアドレス・見張る差出人の指定・パスワード・Webhook URL は、リポジトリのファイルに書かない。
- **そのため、引き継ぎ書はリポジトリに入れない。** 非公開の `~/.claude`(claude-config)の、このプロジェクトの記憶のフォルダに置く:
  `C:\Users\user\.claude\projects\C--MyFolder-MyProjects-name-Com\memory\handoff.md`(本人の決定、2026-11-13)。
- GitHub Actions が `state.json` を書き戻すので、手元はいつも遅れている。**push の前に必ず `git pull --ff-only`。**
- Secrets(`IMAP_HOST`・`IMAP_USER`・`IMAP_PASSWORD`・`WATCH_FROM`・`DISCORD_WEBHOOK_URL`)の値は、GitHub からは読めない。名前と更新日時だけを見る。

## 現在の状態(実行時に取得済み)
- フォルダの中身: !`ls -la --time-style=+%Y-%m-%d_%H:%M`

## 手順(この順に、止まらず最後まで実行する)

### 0. 取り込み
- `git status --short` が空なら `git pull --ff-only -q`。食い違った・失敗したら取り込まず、そのことを控える(`--force`・`reset`・`stash` はしない)。

### 1. 見張りの健全性チェック(読み取りだけ)
1. **テスト**: `python -X utf8 -m unittest -q test_check_mail`。件数と結果を控える(実行後に `__pycache__` ができたら、それは消してよい)。
2. **定期実行の状態**: `gh workflow list -a -R supertwins036-commits/mail-notifier`。`active` 以外(`disabled_manually`・`disabled_inactivity`)なら控える。`disabled_inactivity` は公開リポジトリの「60日の休止」。
3. **最近の実行**: `gh run list -R supertwins036-commits/mail-notifier -w check-mail -L 10`。失敗(`failure`)があれば、その番号を控える(ログの中身は、秘密が伏せ字でも引き継ぎ書に貼らない)。
4. **Secrets**: `gh secret list -R supertwins036-commits/mail-notifier` で、上の5つの名前がそろっているか。値は読めない・書かない。
5. **記録**: `cat state.json`(UIDVALIDITY と、最後に見たメールの番号だけ)。
6. 失敗やエラーがあれば、**直さずに**「既知のエラー」として控える(この段階は引き継ぎが目的で、修正はしない)。
- **「実行が成功」は、Discord に通知が届いた意味ではない。** このセッションで実際に通知が届いたのを本人に確かめていなければ、「Discord への到着: 未確認」と書く。

### 1.5 セッション名の記録
- 実行しているセッションの名前を取得する: `mcp__ccd_session_mgmt__get_session`(`session_id` は `"self"`)の `title`。ツールが未読み込みなら、先に `ToolSearch`(`select:mcp__ccd_session_mgmt__get_session`)で読み込む。
- **タイトルの最初の `(`(半角)より前の文字列**を切り出す。`(` がなければ、タイトル全体。空白は削らず、そのまま。
- 引き継ぎ書の先頭の項目に、**バッククォートで囲んで**記録する(末尾の空白が消えないように)。`/setup` がこの行を読んで、新しいセッションの名前にする。
- 取得できなかった場合は `(取得できませんでした)` とし、`/setup` が名前を変えないようにする。

### 2. 環境情報の収集(読み取りだけ)
- スキル・コマンド: `.claude/skills/*/SKILL.md`、`.claude/commands/*.md`。
- 記憶: `C:\Users\user\.claude\projects\C--MyFolder-MyProjects-name-Com\memory\MEMORY.md` と、そこから指される記憶(無ければ「なし」)。今回の作業の結果と食い違っていれば報告する(自動では書き換えない)。
- 設定: `.claude/settings.json`、`.claude/settings.local.json`、`CLAUDE.md` があれば読む(**値に秘密が含まれていたら書かない**)。
- 外部の道具: `python --version`、`gh auth status`(ログインしているアカウント名だけ控える。トークンは書かない)。
- **作業用スクリプトの置き場所**: セッションの一時フォルダ(scratchpad)は、次のセッションからは見えない。次も使う道具がそこにあれば、リポジトリへ移すよう引き継ぎ書に書く(ここでは移さない)。

### 3. 引き継ぎ書を書き出す
置き場所: `C:\Users\user\.claude\projects\C--MyFolder-MyProjects-name-Com\memory\handoff.md`(フォルダが無ければ `mkdir -p` で作る)。
**リポジトリ(`C:\MyFolder\MyProjects\name.Com`)の中には書かない。**

**上書きの確認(書き出す前に必ず行う)**:
1. 既存の `handoff.md` があれば、その「作成日時」と「セッション名」の行を読む。
2. `mcp__ccd_session_mgmt__list_sessions` で、同じフォルダ(`C:\MyFolder\MyProjects\name.Com`)に、このセッション以外の処理中のセッションがあるかを確かめる。ツールが未読み込みなら、先に `ToolSearch`(`select:mcp__ccd_session_mgmt__list_sessions`)で読み込む。
3. 次のどれかに当てはまれば、**上書きせず**、同じフォルダに `handoff_<YYYYMMDD_HHMM>.md`(作成日時の JST)の別名で書き、そのことを最後の案内で報告する。
   - このセッション以外の処理中のセッションが、同じフォルダにある。
   - 既存の `handoff.md` の作成日時が、このセッションの開始より後。
   - 上の確認ができなかった(ツールが使えない・作成日時が読めないなど)。**迷ったら上書きしない側に倒す。**
4. どれにも当てはまらなければ、`handoff.md` を上書きする。
- 事実は上の手順で**実際に確認したもの**だけを書く。会話の記憶だけで書かない。確かめていないことは「未確認」と書く。
- 日付は絶対日付(YYYY-MM-DD)。
- **書かないもの**: パスワード、Webhook URL、トークン、本人のメールアドレス(`IMAP_USER` の値)。
- **書いてよいもの**: `WATCH_FROM` に入れた指定(Secrets は読み戻せないので、次に足すときに要る)。置き場所が非公開の `~/.claude` だから書ける。リポジトリには書かない。
- 「**本人が決めたこと**」は、日付と理由つきで書く。「やめる」と決めたことも書く。**決まったことを、新しいセッションが選択肢として出し直さないため。**

```markdown
# 引き継ぎ(handoff)

- 作成日時: YYYY-MM-DD HH:MM(JST)
- セッション名(最初の"("まで): `<切り出した文字列>`
- リポジトリ: supertwins036-commits/mail-notifier(公開)/ 最新のコミット: <番号と題名>

## 1. このセッションの目的と到達点
## 2. 確定した内容
### 本人が決めたこと(日付・理由つき。「やめる」と決めたことも)
### いまの設定
| 項目 | 値 |
(確かめる間隔(cron)/ WATCH_FROM の指定 / IMAP_HOST / Secrets の名前と更新日時 / state.json の番号)
## 3. 確認の結果
| 項目 | 結果 |
(テスト / 定期実行の状態 / 最近の実行(失敗の有無)/ Secrets がそろっているか / Discord への到着(本人が確かめたか。未なら「未確認」))
### 既知のエラー
## 4. 環境
(スキル・コマンド / 記憶 / Python / gh のログイン / scratchpad に残った道具)
## 5. 残っている課題と判断待ち
(本人の判断待ちは1行ずつ書く。無ければ「判断待ち: なし」)
## 6. 最初にやること(優先順、具体的な最初の一手つき)
## 7. 作業ルール(要点)
(例: チャットは日本語 / 公開リポジトリに秘密や見張る相手を書かない / パスワード・Webhook URL は本人が Secrets に入れる / push の前に pull / 決まったことを選択肢にしない / 確認は grilling 形式)
```

### 3.5 コミットと push(2台の PC で続けるため)
失敗したら、そこで止めて報告する。`--force`・`reset`・マージの食い違いの解消は行わない。
1. **このリポジトリ**:
   - `git pull --ff-only -q`。食い違った(早送りできない)ら、コミット・push はせず、「取り込みが食い違いました。本人の確認が要ります」と報告する。
   - `git status --short` で、思わぬ変更がないか見る。秘密(パスワード・Webhook URL・メールアドレス)や引き継ぎ書がリポジトリに入っていないか確かめる。
   - 本人が頼んだ作業の変更が残っていれば、内容のわかるメッセージでコミットして push する。引き継ぎ書はここに無いので、ふつうは変更なし。
2. **このプロジェクトの記憶と引き継ぎ書**(`~/.claude` の claude-config。非公開):
   - `git -C /c/Users/user/.claude pull --ff-only -q`
   - `git -C /c/Users/user/.claude add projects/C--MyFolder-MyProjects-name-Com/memory`
   - 変更があれば(`git -C /c/Users/user/.claude diff --cached --quiet` が失敗したら)、`git -C /c/Users/user/.claude commit -q -m "name.Com の引き継ぎ書と記憶を更新する"` → `git -C /c/Users/user/.claude push -q`。
   - `~/.claude` のほかのファイルは add しない(このプロジェクトの記憶だけ)。
3. 結果(コミットの番号・push できたか)を、最後の案内に1行ずつ書く。

### 4. 案内して終了する
次の内容だけを表示して終わる(続けて作業を始めない)。

> 見張りの点検と引き継ぎ書の作成が完了しました(テスト: <N 件 合格/不合格>、定期実行: <active など>、最近の失敗: <なし/あり>)。
> コミットと push: このリポジトリ <済/変更なし/要対応(理由)>、引き継ぎ書と記憶 <済/変更なし/要対応(理由)>。
> 新しいセッションを開いて `/setup` を実行してください(引き継ぎ書を読んで、その続きから進められます)。

上書きの確認で別名(`handoff_<YYYYMMDD_HHMM>.md`)にした場合は、そのファイル名と理由(処理中の別のセッションがある、など)を1行添える。
テストが不合格、または定期実行が止まっている・失敗が続いている場合は、上の一文の代わりに、その要点と「新しいセッションで最初に直してください」を表示する。
処理が数分以上かかったときだけ、終了の合図に「長い処理の終了」の音を鳴らす(全体の指示 `~/.claude/CLAUDE.md` の「音で知らせる」の1)。

## 注意
- 手動で呼び出す(`/handoff`)。自動では動かさない。
- 書き換えるのは引き継ぎ書(`handoff.md` または別名)だけ。コード・設定・Secrets・定期実行の有効/無効は変更しない(直すのは新しいセッションの仕事)。
- 外部への送信(Discord など)は行わない。Actions を手で動かすこともしない(`gh workflow run` は使わない)。GitHub への push は手順 3.5 のとおり行う。
