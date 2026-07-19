import argparse
import pyautogui
import subprocess
import time
import os
from datetime import datetime

# --- 既定値（コマンドライン引数で上書き可能） ---
SAVE_DIR = "kindle_screenshots"  # 保存先フォルダ名
PAGE_COUNT = 425                 # 撮影したいページ数
INTERVAL = 1.5                   # ページめくり後の待機時間（秒）
START_DELAY = 5                  # 開始までのカウントダウン秒数
TURN_KEY = "left"                # ページ送りに使うキー（左送りなら left）
APP_NAME = None                  # ページ送りキー送信前に最前面へ出すアプリ名（例: "Amazon Kindle"）。None で無効
OWNER_NAME = None                # ウインドウ単位で撮影する対象の所有者名（例: "Kindle"）。None なら全画面撮影
ACTIVATE_SETTLE = 0.3            # 最前面化してから撮影するまでの待機秒数
START_INDEX = 1                  # 連番の開始番号（続きから撮るとき用）
STOP_REPEAT = 0                  # 同一ページが連続 N 回続いたら終端とみなし停止（0で無効）
# ------------------------------------------------


def activate_app(app):
    """指定アプリを最前面に出す（macOS / osascript）。失敗しても撮影は継続。"""
    try:
        subprocess.run(
            ["osascript", "-e", f'tell application "{app}" to activate'],
            check=False, capture_output=True, timeout=5)
    except Exception as e:
        print(f"  [warn] {app} の前面化に失敗しました: {e}")


def find_window_id(owner):
    """所有者名が owner を含む、画面上で最大のウインドウの CGWindowID を返す。
    見つからなければ None。マルチモニタ／背面のウインドウでも特定できる。"""
    import Quartz
    wins = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID)
    best_id, best_area = None, -1
    for w in wins:
        o = str(w.get("kCGWindowOwnerName", ""))
        if owner.lower() not in o.lower():
            continue
        b = w.get("kCGWindowBounds", {})
        area = int(b.get("Width", 0)) * int(b.get("Height", 0))
        if area > best_area:
            best_area, best_id = area, int(w.get("kCGWindowNumber", 0))
    return best_id


def capture_window(window_id, file_path):
    """CGWindowID 指定でそのウインドウだけを撮影（screencapture -l）。
    最前面でなくても・別モニターでも撮影できる。"""
    subprocess.run(["screencapture", f"-l{window_id}", "-o", "-x", file_path],
                   check=False, capture_output=True, timeout=20)
    if not os.path.exists(file_path):
        raise RuntimeError(
            f"ウインドウ撮影に失敗しました（画面収録の権限を確認してください）: {file_path}")


def images_equal(path_a, path_b):
    """2画像の画素が完全一致するか（PNGメタ差を無視して画素で比較）。
    終端（これ以上ページが送れず同じ画面が続く状態）の検出に使う。"""
    try:
        from PIL import Image, ImageChops
        with Image.open(path_a) as a, Image.open(path_b) as b:
            if a.size != b.size:
                return False
            return ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox() is None
    except Exception:
        return False


def _grab(owner, app, activate_settle, path):
    """撮影を1枚だけ行うヘルパ（方向判定のプローブ用）。"""
    if app:
        activate_app(app)
        time.sleep(activate_settle)
    if owner:
        wid = find_window_id(owner)
        if wid is None:
            raise RuntimeError(f"'{owner}' のウインドウが見つかりませんでした")
        capture_window(wid, path)
    else:
        pyautogui.screenshot().save(path)


ORIENT_VOTES = 4       # 判定に必要な決定票の数
ORIENT_MARGIN = 2      # 反対票の何倍あれば確定とするか
ORIENT_MAX_PAGES = 40  # 判定のために見るページ数の上限（巻頭は図版・扉が続き票が入りにくい）


def page_orientation(path):
    """1ページの本文が縦書きか横書きかを推定し "vertical" / "horizontal" を返す。

    行と行の間には必ず余白ができるので、横書きなら「文字を含まない行」が
    行間ごとに現れ、縦書きなら「文字を含まない列」が列間ごとに現れる。
    図版ページなど自信を持てない場合は None を返す（誤判定より棄権を優先）。
    """
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        with Image.open(path) as im:
            g = im.convert("L")
            w, h = g.size
            # 上下のツールバー・進捗バーを落とす（本文でない文字が混ざるため）
            base = g.crop((0, int(h * 0.08), w, int(h * 0.92)))

            # ページがウインドウの一部にしか描かれないことがあるので、まず縮小版で
            # 文字のある領域を突き止める（探すだけなので低解像度でよい）
            s = 600.0 / max(base.size)
            small = base.resize((int(base.width * s), int(base.height * s)))
            sp = small.load()
            sw, sh = small.size
            vals = [sp[x, y] for y in range(sh) for x in range(sw)]
            thr = sum(vals) / len(vals) - 40  # これより暗ければ文字とみなす
            ink_rows = [y for y in range(sh) if any(sp[x, y] < thr for x in range(sw))]
            ink_cols = [x for x in range(sw) if any(sp[x, y] < thr for y in range(sh))]
            if not ink_rows or not ink_cols:  # 白紙ページ
                return None

            # 解析は元解像度から切り出して行う（先に全体を縮小すると行間が潰れる）
            g = base.crop((int(ink_cols[0] / s), int(ink_rows[0] / s),
                           int((ink_cols[-1] + 1) / s), int((ink_rows[-1] + 1) / s)))
            if min(g.size) < 100:
                return None  # 文字が少なすぎて判定材料にならない
            if max(g.size) > 900:  # 縦横比は保つ（正方形に潰すと行間の周期が壊れる）
                s2 = 900.0 / max(g.size)
                g = g.resize((int(g.width * s2), int(g.height * s2)))
            px = g.load()
            gw, gh = g.size
            vals = [px[x, y] for y in range(gh) for x in range(gw)]
            thr = sum(vals) / len(vals) - 40

            rows = [sum(1 for x in range(gw) if px[x, y] < thr) for y in range(gh)]
            cols = [sum(1 for y in range(gh) if px[x, y] < thr) for x in range(gw)]
            if max(rows) == 0:
                return None

            empty_rows = sum(1 for v in rows if v <= 0.02 * gw) / gh
            empty_cols = sum(1 for v in cols if v <= 0.02 * gh) / gw

            # 縦書き＝行方向に隙間が無く、列方向に隙間がある
            if empty_rows <= 0.05 and empty_cols >= 0.04:
                return "vertical"
            # 横書き＝行間にはっきり空行があり、列方向はほぼ埋まっている
            if empty_cols <= 0.20 and empty_rows >= 0.50:
                return "horizontal"
            return None
    except Exception:
        return None


def detect_orientation_by_paging(interval, app, owner, activate_settle, probe_dir, base,
                                 step_key="right"):
    """ページを送りながら本文レイアウトを多数決で判定し、元のページに戻す。

    1ページだけでは図版や扉ページに引っかかるので、送りながら投票させる。
    縦書きの本でも表組みページは「横書き」に見えるため、単に先に
    ORIENT_VOTES 集まった側を採ると誤る（実測で誤判定が出た）。
    反対票の ORIENT_MARGIN 倍を超えて初めて確定とする。

    レイアウトの判定に送り方向は関係ないので、動くと分かっているキー
    （step_key）で送り、最後に同じ回数だけ逆キーで戻せばよい。
    """
    votes = {"vertical": 0, "horizontal": 0}
    back_key = "left" if step_key == "right" else "right"
    shot = os.path.join(probe_dir, "orient.png")
    steps = 0
    verdict = None

    for i in range(ORIENT_MAX_PAGES):
        path = base if i == 0 else shot
        if i > 0:
            pyautogui.press(step_key)
            steps += 1
            time.sleep(interval)
            _grab(owner, app, activate_settle, path)

        o = page_orientation(path)
        if o:
            votes[o] += 1
            other = "horizontal" if o == "vertical" else "vertical"
            if votes[o] >= ORIENT_VOTES and votes[o] >= ORIENT_MARGIN * votes[other]:
                verdict = o
                break

    # 見た分だけ戻して開始ページに復帰
    for _ in range(steps):
        pyautogui.press(back_key)
        time.sleep(interval)
    try:
        os.remove(shot)
    except OSError:
        pass

    print(f"  {steps + 1}ページ分を確認（縦書き {votes['vertical']}票 / "
          f"横書き {votes['horizontal']}票）")
    return verdict


def detect_turn_key(interval, app, owner, activate_settle, session_dir):
    """ページ送りの向きを自動判別する。判定できなければ None を返す。

    left / right を1回ずつ試し打ちし、その結果で3つの状況に分かれる:

    - 片方だけ動く … 本の端にいる。ただし「先頭」と「巻末」は見分けが
      つかない（先頭では戻る側が、巻末では進む側が効かず、症状が鏡像になる）。
      動いたキーが送り方向とは限らないので、本文レイアウトで綴じ方向を確かめる。
    - 両方動く … 本の途中。端の情報が使えないのでレイアウトだけで判定する。
    - 両方動かない … Kindle にキーが届いていない。
    """
    probe_dir = os.path.join(session_dir, ".probe")
    os.makedirs(probe_dir, exist_ok=True)
    base = os.path.join(probe_dir, "base.png")

    print("ページ送り方向を判定中…（左右を1回ずつ試し打ちします）")
    _grab(owner, app, activate_settle, base)

    moved = {}
    for key, back in (("right", "left"), ("left", "right")):
        pyautogui.press(key)
        time.sleep(interval)
        shot = os.path.join(probe_dir, f"{key}.png")
        _grab(owner, app, activate_settle, shot)
        moved[key] = not images_equal(shot, base)
        # 動いたときだけ戻す。端で効かなかったキーの分まで押し戻すと
        # 逆方向に1ページずれ、先頭なら表紙を撮り逃す
        if moved[key]:
            pyautogui.press(back)
            time.sleep(interval)

    def cleanup():
        for name in ("base.png", "right.png", "left.png"):
            try:
                os.remove(os.path.join(probe_dir, name))
            except OSError:
                pass
        try:
            os.rmdir(probe_dir)
        except OSError:
            pass

    try:
        if not moved["right"] and not moved["left"]:
            print("  [警告] 左右どちらのキーでも画面が変化しませんでした。"
                  "Kindle が最前面か、権限設定を確認してください。")
            return None

        at_edge = moved["right"] != moved["left"]
        live_key = "right" if moved["right"] else "left"  # 動くと分かっているキー
        if at_edge:
            print(f"  {live_key} キーだけが効きました（本の端にいます）。"
                  "先頭か巻末かはこれだけでは分からないため、"
                  "本文のレイアウトで綴じ方向を確かめます…")
        else:
            print("  左右どちらでもページが動きました（本の途中）。"
                  "本文のレイアウトから綴じ方向を判定します…")

        orient = detect_orientation_by_paging(
            interval, app, owner, activate_settle, probe_dir, base, step_key=live_key)
        if orient is None:
            print("  [警告] レイアウトから判定できませんでした（図版ページなどの可能性）。")
            if at_edge:
                # ここで live_key を送り方向と決め打つと、巻末を開いていた場合に
                # 本を丸ごと逆順で撮ってしまう（枚数を見ても気づけない）。
                # 先頭にいるなら live_key が正解なので、そう伝えるに留める。
                print(f"       先頭ページを開いた状態なら --key {live_key} が送り方向です。")
            return None

        turn_key = "left" if orient == "vertical" else "right"
        binding = "右綴じ" if orient == "vertical" else "左綴じ"
        label = "縦書き" if orient == "vertical" else "横書き"
        print(f"  → {label}と判定 → {binding} → {turn_key} キーで進みます。")
        if at_edge and live_key != turn_key:
            # 効いたのが戻る側＝いま巻末にいる。ここで気づかないと本が逆順で撮れる
            print("  ※ 効いたキーは戻る側でした。いまは巻末にいます"
                  "（先頭から撮るには --rewind を付けてください）。")
        return turn_key
    finally:
        cleanup()


def rewind_to_start(back_key, interval, app, owner, activate_settle, probe_dir,
                    batch=10, max_presses=2000):
    """戻るキーを押し続けて本の先頭まで戻す。

    「先頭ではそれ以上戻れない＝画面が変化しなくなる」ことを終了条件にするので、
    総ページ数が分からなくても、メニュー構成に依存せずに先頭へ戻せる。
    """
    print(f"本の先頭まで戻します（{back_key} キー / 画面が変化しなくなるまで）…")
    paths = [os.path.join(probe_dir, "rw0.png"), os.path.join(probe_dir, "rw1.png")]
    prev = None
    pressed = 0

    while pressed < max_presses:
        cur = paths[(pressed // batch) % 2]
        _grab(owner, app, activate_settle, cur)
        if prev is not None and images_equal(cur, prev):
            print(f"  先頭に到達しました（{pressed}回戻しました）")
            break
        prev = cur
        for _ in range(batch):
            pyautogui.press(back_key)
            time.sleep(max(0.25, interval / 4))
        pressed += batch
        print(f"  {pressed}ページ戻し中…")
    else:
        print(f"  [警告] {max_presses}回戻しても先頭に到達しませんでした。そのまま撮影を続けます。")

    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass
    time.sleep(interval)


def capture_kindle(page_count=PAGE_COUNT, interval=INTERVAL, save_dir=SAVE_DIR,
                   start_delay=START_DELAY, turn_key=TURN_KEY, app=APP_NAME,
                   owner=OWNER_NAME, activate_settle=ACTIVATE_SETTLE,
                   session_dir=None, start_index=START_INDEX, stop_repeat=STOP_REPEAT,
                   rewind=False):
    # セッションフォルダ（指定があればそれを使い、続きから保存できる）
    if session_dir is None:
        session_dir = os.path.join(save_dir, datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    os.makedirs(session_dir, exist_ok=True)
    print(f"保存先: {session_dir}")
    print(f"設定: {page_count}ページ / 開始番号 {start_index} / 間隔 {interval}秒 / 送りキー {turn_key}"
          + (f" / 最前面アプリ {app}" if app else "")
          + (f" / 撮影ウインドウ {owner}" if owner else " / 全画面撮影")
          + (f" / 同一{stop_repeat}回で自動停止" if stop_repeat else ""))

    print(f"{start_delay}秒後に開始します。Kindleアプリを最前面に表示し、最初のページを開いてください。")
    time.sleep(start_delay)

    if turn_key == "auto":
        turn_key = detect_turn_key(interval, app, owner, activate_settle, session_dir)
        if turn_key is None:
            print("方向を自動判定できませんでした。--key left / --key right で明示して再実行してください。")
            return

    if rewind:
        probe_dir = os.path.join(session_dir, ".probe")
        os.makedirs(probe_dir, exist_ok=True)
        try:
            back_key = "right" if turn_key == "left" else "left"
            rewind_to_start(back_key, interval, app, owner, activate_settle, probe_dir)
        finally:
            try:
                os.rmdir(probe_dir)
            except OSError:
                pass

    try:
        _capture_loop(page_count, interval, turn_key, app, owner, activate_settle,
                      session_dir, start_index, stop_repeat)
    except KeyboardInterrupt:
        existing = sorted(f for f in os.listdir(session_dir) if f.endswith(".png"))
        print(f"\n中断しました。{len(existing)}枚を保存済み: {session_dir}")
        if existing:
            next_index = int(os.path.splitext(existing[-1])[0]) + 1
            print(f"続きから撮るには: --session-dir {session_dir} --start-index {next_index}")


def _capture_loop(page_count, interval, turn_key, app, owner, activate_settle,
                  session_dir, start_index, stop_repeat):
    prev_path = None     # 直近の「実ページ」（重複でない最後の画像）
    dup_run = 0          # 連続重複カウント
    dup_paths = []       # 末尾で削除する重複ファイル
    captured = 0

    for k in range(page_count):
        idx = start_index + k
        file_path = os.path.join(session_dir, f"{idx:03d}.png")

        # ページ送りキーを Kindle に届かせるため、対象アプリを最前面へ
        if app:
            activate_app(app)
            time.sleep(activate_settle)

        if owner:
            # 対象アプリのウインドウだけを撮影（別モニター・背面でもOK）
            wid = find_window_id(owner)
            if wid is None:
                # 取りこぼし時は前面化して再探索
                if app:
                    activate_app(app)
                time.sleep(0.5)
                wid = find_window_id(owner)
            if wid is None:
                raise RuntimeError(f"'{owner}' のウインドウが見つかりませんでした")
            capture_window(wid, file_path)
        else:
            # 全画面撮影（メインモニターのみ）
            screenshot = pyautogui.screenshot()
            screenshot.save(file_path)

        captured += 1
        print(f"Captured: {file_path}")

        # 終端検出：直前の実ページと同一が続いたら停止
        if stop_repeat and prev_path is not None and images_equal(file_path, prev_path):
            dup_run += 1
            dup_paths.append(file_path)
            if dup_run >= stop_repeat:
                for p in dup_paths:
                    try:
                        os.remove(p)
                    except OSError:
                        pass
                captured -= len(dup_paths)
                print(f"同一ページが {stop_repeat} 回続いたため終端と判断。"
                      f"末尾の重複 {len(dup_paths)} 枚を削除して停止します。")
                break
            # 閾値未満：prev_path は実ページのまま保持
        else:
            dup_run = 0
            dup_paths = []
            prev_path = file_path

        # 指定キーを押してページをめくる
        pyautogui.press(turn_key)

        # 描画待ち
        time.sleep(interval)

    print(f"完了しました。{captured}枚を保存: {session_dir}")

def parse_args():
    parser = argparse.ArgumentParser(
        description="Kindle アプリを連続スクリーンショットして PNG として保存する")
    parser.add_argument("-p", "--pages", type=int, default=PAGE_COUNT,
                        help=f"撮影するページ数（既定: {PAGE_COUNT}）")
    parser.add_argument("-i", "--interval", type=float, default=INTERVAL,
                        help=f"ページ送り後の待機秒数（既定: {INTERVAL}）")
    parser.add_argument("-d", "--save-dir", default=SAVE_DIR,
                        help=f"保存先の親フォルダ（既定: {SAVE_DIR}）")
    parser.add_argument("--delay", type=int, default=START_DELAY,
                        help=f"開始までのカウントダウン秒数（既定: {START_DELAY}）")
    parser.add_argument("--key", default=TURN_KEY,
                        help=f"ページ送りに使うキー（auto / left / right、既定: {TURN_KEY}）。"
                             "auto は本の先頭で左右を試し打ちして向きを判定する")
    parser.add_argument("--app", default=APP_NAME,
                        help='ページ送り前に最前面へ出すアプリ名（例: "Amazon Kindle"）')
    parser.add_argument("--owner", default=OWNER_NAME,
                        help='ウインドウ単位で撮影する対象の所有者名（例: "Kindle"）。'
                             '指定するとマルチモニタ／背面でもそのウインドウだけを撮影する')
    parser.add_argument("--session-dir", default=None,
                        help="保存先セッションフォルダを直接指定（続きから撮るとき用）")
    parser.add_argument("--start-index", type=int, default=START_INDEX,
                        help=f"連番の開始番号（既定: {START_INDEX}）")
    parser.add_argument("--stop-repeat", type=int, default=STOP_REPEAT,
                        help="同一ページが連続N回続いたら終端とみなし停止（0で無効）")
    parser.add_argument("--rewind", action="store_true",
                        help="撮影前に本の先頭まで戻す（途中から開いていても全ページ撮れる）")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    capture_kindle(page_count=args.pages, interval=args.interval, save_dir=args.save_dir,
                   start_delay=args.delay, turn_key=args.key, app=args.app, owner=args.owner,
                   session_dir=args.session_dir, start_index=args.start_index,
                   stop_repeat=args.stop_repeat, rewind=args.rewind)
