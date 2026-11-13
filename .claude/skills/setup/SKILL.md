---
name: setup
description: 新しいセッションを開いた直後に、1コマンドでメール通知の仕組み(mail-notifier)の環境を整える。取り込み、引き継ぎ書の読み込み、セッション名の設定、Remote Control、Python・gh の確認、テスト、GitHub Actions の定期実行と Secrets の確認を行い、直近のタスクを提示する。「/setup」「環境構築」「セッションの再開」と言われたときに使う。
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, ToolSearch, PowerShell, mcp__ccd_session_mgmt__get_session, mcp__ccd_session_mgmt__set_session_title, mcp__ccd_session_mgmt__set_remote_control, Bash(date:*), Bash(ls:*), Bash(cat:*), Bash(test:*), Bash(python -X utf8:*), Bash(python --version:*), Bash(gh auth status:*), Bash(gh workflow list:*), Bash(gh run list:*), Bash(gh secret list:*), Bash(git status:*), Bash(git log:*), Bash(git pull:*), Bash(git -C:*)
---

# /setup — 新しいセッションの環境確認と、文脈の同期

新しいセッションの直後に実行する。**取り込みと読み取り・確認だけ**を行い、コード・設定・Secrets は変更しない(インストールも、通知も、Actions の手動実行もしない。変えるのは、取り込みの結果と、このセッションの名前と Remote Control だけ)。
makeDoc・translateGmail の `/setup` を、このフォルダ(`C:\MyFolder\MyProjects\name.Com`。お名前.com のメールの新着を Discord に知らせる仕組み)向けに直したもの(2026-11-13)。

このフォルダの約束(`/handoff` と同じ):
- リポジトリは**公開**(`supertwins036-commits/mail-notifier`)。秘密・メールアドレス・見張る差出人の指定はリポジトリに書かない。
- 引き継ぎ書は非公開の `~/.claude` 側にある: `C:\Users\user\.claude\projects\C--MyFolder-MyProjects-name-Com\memory\handoff.md`。
- パスワードと Webhook URL は本人が GitHub の Secrets に入れる(Claude は入力しない)。

## 手順(この順に、最後まで実行する。失敗しても止まらず、結果を集めて最後に報告する)

### 0a. 取り込み(2台の PC で続けるため)
- このリポジトリと `~/.claude` のそれぞれで、`git status --short`(`~/.claude` は `git -C /c/Users/user/.claude status --short`)を見る。
  - 空なら `git pull --ff-only -q`(`~/.claude` は `git -C /c/Users/user/.claude pull --ff-only -q`)で取り込む。このリポジトリは Actions が `state.json` を書き戻すので、ほぼ毎回新しいコミットがある。
  - 未コミットの変更があるとき・取り込みが失敗したとき(食い違い・ネットワーク)は取り込まず、手元の版で続け、完了報告の表に「取り込み: 要対応(理由)」と書く。`--force`・`reset`・`stash` はしない。

### 1. 引き継ぎ書の確認
- 上の置き場所に `handoff.md` と、別名の `handoff_*.md` があるか確認する(`ls`)。
  - 別名のファイルもあれば、それも読み、各ファイルの「作成日時」を比べて、どれが新しいかを報告する(新しいほうを主に使う)。
  - **あれば**: 全文を読む。作成日時、いまの設定、既知のエラー、**本人が決めたこと**を控える。節は、全フォルダ共通の見出しの言葉「到達点」「判断待ち」「最初にやること」で探す(番号は見ない)。
  - **なければ**: 「引き継ぎ書がありません。前のセッションで `/handoff` を実行すると作られます」と報告し、記憶・README・`git log` から文脈を組み立てて続ける。
- このフォルダの `CLAUDE.md` があれば読む(ルールは引き継ぎ書より CLAUDE.md が優先)。全体の指示 `~/.claude/CLAUDE.md` と記憶の `MEMORY.md` は、起動時に読み込まれているので、読み直さない(その内容を前提にする)。
- **決まっていることを、選択肢として出し直さない。** 判断を仰ぐ前に、引き継ぎ書の「本人が決めたこと」と記憶を調べる。

### 1.5 セッション名の設定
- 引き継ぎ書の「セッション名(最初の"("まで)」の行から、バッククォートの中の文字列を取り出す(**空白も含めて、そのまま**)。
  - 行がない、または `(取得できませんでした)` なら、名前は変えず、「セッション名の記録がないため、変更しません」と報告する。
- 現在の日本時間を取得する: `date -u -d '+9 hours' '+%y/%m/%d %H:%M'`。
- 新しい名前 = **取り出した文字列 + `(` + 上の日時 + `)`**。間に何も足さない。
- `mcp__ccd_session_mgmt__set_session_title`(`session_id` は `"self"`)で設定する。ツールが未読み込みなら、先に `ToolSearch`(`select:mcp__ccd_session_mgmt__set_session_title`)で読み込む。
  - 承認されなかった・変更できなかったときは、新しい名前を報告するだけにして、続行する。

### 1.6 Remote Control をオンにする
- `mcp__ccd_session_mgmt__set_remote_control` を `session_id` は `"self"`・`enabled` は `true` で呼ぶ。未読み込みなら先に `ToolSearch`(`select:mcp__ccd_session_mgmt__set_remote_control`)。
- 理由: Remote Control がつながったセッションだけが、ほかの PC やスマホのアプリに出るため。
- 結果(on / connecting / unavailable)を完了報告の表に1行で書く。拒否・失敗したら回避せず、「画面上の Remote Control のスイッチをオンにしてください」と報告して、残りの手順を続ける。

### 2. 道具の確認(インストールはしない)
- **Python**: `python --version`(標準の部品だけで動くので、追加の部品は要らない)。
- **gh**: `gh auth status`。ログインしていなければ、`gh auth login` を本人に案内する(Claude はログインしない)。

### 3. スキル・記憶・設定の確認
- `.claude/skills/*/SKILL.md`、`.claude/commands/*.md` を一覧する。
- 記憶: 起動時に読み込まれた `MEMORY.md` の内容と引き継ぎ書が食い違っていないか見る(ファイルは読み直さない)。
- `.claude/settings.json`・`.claude/settings.local.json` があれば読む。値に秘密が含まれていたら書かない。

### 4. 見張りの確認(読み取りだけ)
1. **テスト**: `python -X utf8 -m unittest -q test_check_mail`(できた `__pycache__` は消してよい)。
2. **定期実行**: `gh workflow list -a -R supertwins036-commits/mail-notifier`。`active` でなければ要対応。`disabled_inactivity` は「60日の休止」で、本人が Actions の画面で有効にし直す(Claude は勝手に有効にしない)。
3. **最近の実行**: `gh run list -R supertwins036-commits/mail-notifier -w check-mail -L 10`。`failure` があれば、その時刻と番号を報告する。失敗が続いていれば、パスワードの変更・サーバー名の変更・Webhook の削除を疑う。
4. **Secrets**: `gh secret list -R supertwins036-commits/mail-notifier` で、`IMAP_HOST`・`IMAP_USER`・`IMAP_PASSWORD`・`WATCH_FROM`・`DISCORD_WEBHOOK_URL` がそろっているか(値は読めない)。
5. 失敗があれば、**直さずに**要点を報告する(引き継ぎ書の「既知のエラー」と同じか比べる)。

### 5. 完了報告
次の形式で報告して終わる。

1. **環境チェックの表**: 項目(取り込み(このリポジトリ・`~/.claude`)/ 引き継ぎ書 / セッション名 / Remote Control(on・connecting・unavailable)/ Python / gh のログイン / スキル・記憶 / テスト / 定期実行 / 最近の実行 / Secrets)と結果(OK・不要・要対応)。
2. すべて OK(または「不要」)のとき:
   > 環境構築とコンテキストの同期が完了しました。いつでも作業を再開できます!
3. 要対応があるときは、上の一文の代わりに、要対応の項目と対処を先に示す。
4. **直近のタスク**: 引き継ぎ書の「最初にやること」の節を、要点だけ提示する。引き継ぎ書がなければ、記憶・README・`git log` から推測できる予定を、推測であると断って示す。
4.5 **判断待ち**: 引き継ぎ書の「判断待ち」の節にある項目を、**省かず1行ずつすべて**出す。無ければ「判断待ち: なし」と書く。
5. **本人が決めたこと**のうち、これからの作業に関わるものを1〜3行で添える(選択肢として出し直さないための確認)。
6. 処理が数分以上かかったときだけ、「長い処理の終了」の音を鳴らす(全体の指示 `~/.claude/CLAUDE.md` の「音で知らせる」の1)。

## 注意
- 手動で呼び出す(`/setup`)。自動では動かさない。
- ファイルの作成・編集、インストール、通知の送信、Actions の手動実行(`gh workflow run`)、定期実行の有効/無効の切り替え、Secrets の変更は行わない(変えるのは、取り込みの結果と、このセッションの名前と Remote Control だけ)。
