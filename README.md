# kindle_books

macOS 上で **Kindle アプリ**を前面に置いた状態から、画面を連続でスクリーンショットし、PNG として保存するスクリプトです。紙の本のように左送り（次のページへは **左矢印**）で進むレイアウトを想定しています。

## 必要な環境

- macOS
- Python 3
- [Kindle for Mac](https://www.amazon.com/gp/browse.html?node=16571048011) など、操作対象の Kindle アプリ

## セットアップ

リポジトリのディレクトリで依存パッケージを入れます。スクリーンショット生成には **Pillow** も必要です（無いと `unable to import pyscreeze` で失敗します）。

```bash
pip install pyautogui Pillow
```

Homebrew などの「外部管理（externally-managed）」な Python で上記がエラーになる場合は、ユーザー領域に入れます。

```bash
python3 -m pip install --user --break-system-packages pyautogui Pillow
```

（仮想環境を使う場合は、先に `python -m venv venv` と `source venv/bin/activate` などで有効化してから実行してください。）

> macOS の「システム設定 → プライバシーとセキュリティ」で、実行するターミナル／アプリに **アクセシビリティ** と **画面収録** の権限を付与しておく必要があります。

## 使い方

1. **Kindle** で撮りたい本を開き、**最初に保存したいページ**を表示する。
2. Kindle ウィンドウを **最前面** にする（他のアプリに隠れないようにする）。
3. ターミナルでプロジェクトフォルダに移動し、スクリプトを実行する。

   ```bash
   cd /path/to/kindle_books
   python capture_kindle.py
   ```

4. コンソールに「5秒後に開始します」と出たら、その間に Kindle を前面に整える。
5. 開始後は **自動で** 次の動きが繰り返されます。
   - 現在画面のスクリーンショットを保存
   - **左矢印**キーで 1 ページ送り
   - 指定秒だけ待機（ページの描画待ち）
6. 指定ページ数に達するか、途中でターミナルから `Ctrl+C` で止められます（止めた時点までの画像は残り、続きから撮るための `--session-dir` / `--start-index` の例が表示されます）。

## 保存されるファイルの場所

- ベースフォルダ: スクリプト内の `SAVE_DIR`（既定は `kindle_screenshots`）
- **実行のたびに**、その直下に **日時フォルダ**が 1 つ作られます。  
  例: `kindle_screenshots/2026-04-05_14-30-45/`
- その中に `001.png`, `002.png`, … と連番で保存されます。

同じ実行では常に同じ日時フォルダにまとまるので、何度か試したときの結果が混ざりません。

## スクリプトで変えられる設定

`capture_kindle.py` 冒頭の定数を編集します。

| 変数 | 意味 |
|------|------|
| `SAVE_DIR` | スクリーンショットの親フォルダ名（相対パス可） |
| `PAGE_COUNT` | 撮影する枚数（ページ数） |
| `INTERVAL` | ページ送りのあと待つ秒数（重い端末や描画が遅いときは長めに） |

画面の **一部だけ** 切り取りたい場合は、`pyautogui.screenshot()` に `region=(left, top, width, height)` を指定する方法があります（ピクセル座標は環境ごとに調整が必要です）。

定数を書き換えずに、**コマンドライン引数**でも上書きできます（既定値は上の表のとおり）。

```bash
# 120ページを 2 秒間隔で撮影し、右送りにする例
python capture_kindle.py --pages 120 --interval 2 --key right
```

| 引数 | 意味 |
|------|------|
| `-p, --pages` | 撮影する枚数（ページ数の上限） |
| `-i, --interval` | ページ送り後の待機秒数 |
| `-d, --save-dir` | 保存先の親フォルダ |
| `--delay` | 開始までのカウントダウン秒数 |
| `--key` | ページ送りキー（`left` / `right` など） |
| `--app` | ページ送り前に最前面へ出すアプリ名（例: `"Amazon Kindle"`） |
| `--owner` | ウインドウ単位で撮影する対象の所有者名（例: `"Kindle"`）。マルチモニタ／背面でもそのウインドウだけを撮影 |
| `--session-dir` | 保存先フォルダを直接指定（続きから撮るとき用） |
| `--start-index` | 連番の開始番号（続きから撮るとき用、既定 1） |
| `--stop-repeat` | 同一ページが連続 N 回続いたら巻末とみなして自動停止し、末尾の重複を削除（0 で無効） |

詳しくは `python capture_kindle.py --help` を参照してください。

## マルチモニタ環境・確実に撮るには（推奨）

`pyautogui` の全画面撮影は **メインモニタしか撮れません**。Kindle をサブモニタに置いている場合や、撮影中に他アプリ（ターミナル等）が前面に出る場合は、**ウインドウ単位の撮影**（`--owner`）を使うと、モニタや前面状態に関係なく Kindle ウインドウだけを撮影できます。あわせて `--app` を指定すると、ページ送りキーを送る直前に毎回 Kindle をアクティブ化します。

```bash
# Kindle ウインドウだけを右送りで撮影（マルチモニタ・背面でも確実）
python capture_kindle.py --pages 254 --key right \
  --app "Amazon Kindle" --owner "Kindle"
```

### 途中から続けて撮る／巻末で自動停止

`--session-dir` と `--start-index` で、既存フォルダの続き（連番）に保存できます。`--stop-repeat` を付けると、同じページが続いた時点（＝これ以上めくれない巻末）で自動停止し、末尾の重複フレームを削除します。総ページ数が分からなくても、`--pages` を多めにして任せれば巻末で止まります。

```bash
# 既存フォルダの 219 番から続けて撮り、巻末で自動停止
python capture_kindle.py --key right --app "Amazon Kindle" --owner "Kindle" \
  --session-dir kindle_screenshots/2026-06-17_21-19-03 \
  --start-index 219 --pages 80 --stop-repeat 3
```

## PDF にまとめる

撮影したセッションフォルダの PNG を、`make_pdf.py` で 1 冊の PDF にまとめられます（macOS 標準の Quartz を使うため追加インストール不要）。

```bash
# kindle_screenshots/2026-06-17_21-19-03.pdf が作られる
python make_pdf.py kindle_screenshots/2026-06-17_21-19-03

# 出力先を指定する場合
python make_pdf.py kindle_screenshots/2026-06-17_21-19-03 -o ~/Desktop/本.pdf
```

ページは連番ファイル名（`001.png`, `002.png`, …）の順に並びます。

## スラッシュコマンド（Claude Code）

Claude Code から `/capture-book` で実行できます（定義: `.claude/commands/capture-book.md`）。

```text
/capture-book              # 既定値で撮影
/capture-book 120          # 120 ページ撮影
/capture-book 120 2        # 120 ページを 2 秒間隔で撮影
```

実行すると上記スクリプトが呼ばれ、開始前に「Kindle を最前面にする」案内が表示されます。

## 注意事項

- 既定では **画面全体（メインモニタ）** を保存します。メニューや Dock が写り込む場合は、`--owner` で **対象ウインドウだけ**を撮影するのが確実です（他モニタ・背面でも可）。
- 実行中は **マウス・キーボードがスクリプト用に使われます**。他の作業は止めるか、別ユーザーセッションで行うと安全です。
- 取得した画像の **著作権はコンテンツ提供者に帰属**します。私的利用の範囲や利用規約を守ってください。