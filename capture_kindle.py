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


def capture_kindle(page_count=PAGE_COUNT, interval=INTERVAL, save_dir=SAVE_DIR,
                   start_delay=START_DELAY, turn_key=TURN_KEY, app=APP_NAME,
                   owner=OWNER_NAME, activate_settle=ACTIVATE_SETTLE,
                   session_dir=None, start_index=START_INDEX, stop_repeat=STOP_REPEAT):
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
                        help=f"ページ送りに使うキー（left / right など、既定: {TURN_KEY}）")
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
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    capture_kindle(page_count=args.pages, interval=args.interval, save_dir=args.save_dir,
                   start_delay=args.delay, turn_key=args.key, app=args.app, owner=args.owner,
                   session_dir=args.session_dir, start_index=args.start_index,
                   stop_repeat=args.stop_repeat)
