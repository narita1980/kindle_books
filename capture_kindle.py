import pyautogui
import time
import os
from datetime import datetime

# --- 設定項目 ---
SAVE_DIR = "kindle_screenshots"  # 保存先フォルダ名
PAGE_COUNT = 425                  # 撮影したいページ数
INTERVAL = 1.5                   # ページめくり後の待機時間（秒）
# ----------------

def capture_kindle():
    # 実行ごとに日時フォルダを作成（例: kindle_screenshots/2026-04-05_14-30-45）
    session_dir = os.path.join(SAVE_DIR, datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    os.makedirs(session_dir, exist_ok=True)
    print(f"保存先: {session_dir}")

    print("5秒後に開始します。Kindleアプリを最前面に表示し、最初のページを開いてください。")
    time.sleep(5)

    for i in range(1, PAGE_COUNT + 1):
        # ファイル名の設定（001.png, 002.png...）
        file_path = os.path.join(session_dir, f"{i:03d}.png")
        
        # スクリーンショットの撮影と保存
        # 画面全体を保存しますが、region=(x, y, width, height) で範囲指定も可能です
        screenshot = pyautogui.screenshot()
        screenshot.save(file_path)
        
        print(f"Captured: {file_path}")

        # 左矢印キーを押してページをめくる（左送り）
        pyautogui.press('left')
        
        # 描画待ち
        time.sleep(INTERVAL)

    print(f"完了しました。{session_dir} を確認してください。")

if __name__ == "__main__":
    capture_kindle()

