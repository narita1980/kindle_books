"""ページ送り方向の自動判定（--key auto）の回帰テスト。

実機を動かさずに、撮影済みのスクリーンショットを仮想の本として
`detect_turn_key()` を動かす。キー入力と画面キャプチャだけ差し替えれば、
判定ロジックそのものは本番と同じコードが走る。

    python3 test_detect_direction.py

要点は「誤答を出さないこと」。判定できずに None を返す（棄権）のは
撮影を始めずに停止するだけなので安全だが、向きを取り違えると
本が丸ごと逆順で撮れてしまい、枚数を見ても気づけない。
"""
import glob
import os
import shutil
import sys
import time

import capture_kindle as ck

# 撮影済みフォルダと、その本の正解（縦書き＝右綴じ＝left 送り）
CORPUS = {
    "2026-05-26": "vertical",
    "2026-06-17": "horizontal",
    "2026-07-03": "horizontal",
    "2026-07-19": "vertical",
}
FORWARD_KEY = {"vertical": "left", "horizontal": "right"}


def books():
    """(フォルダ名, 正解の向き, ページ画像のリスト) を返す。"""
    for d in sorted(glob.glob("kindle_screenshots/*/")):
        name = os.path.basename(d.rstrip("/"))
        orient = CORPUS.get(name[:10])
        pics = sorted(glob.glob(os.path.join(d, "*.png")))
        if orient and len(pics) >= 40:
            yield name, orient, pics


class FakeKindle:
    """指定ページを表示している Kindle のふりをする。"""

    def __init__(self, pages, forward_key, pos):
        self.pages, self.forward_key, self.pos = pages, forward_key, pos

    def press(self, key):
        step = 1 if key == self.forward_key else -1
        self.pos = max(0, min(len(self.pages) - 1, self.pos + step))

    def grab(self, owner, app, settle, path):
        shutil.copyfile(self.pages[self.pos], path)


def detect_from(pages, orient, pos, tmp):
    fake = FakeKindle(pages, FORWARD_KEY[orient], pos)
    ck.pyautogui.press = fake.press
    ck._grab = fake.grab
    verdict = ck.detect_turn_key(0, None, None, 0, tmp)
    return verdict, fake.pos


def main():
    corpus = list(books())
    if not corpus:
        print("kindle_screenshots に判定対象の撮影フォルダがありません。スキップします。")
        return 0

    time.sleep = lambda s: None  # 待機は不要
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".test_probe")
    os.makedirs(tmp, exist_ok=True)

    wrong = correct = abstain = 0
    drift = []
    quiet = open(os.devnull, "w")
    real_stdout = sys.stdout

    for name, orient, pages in corpus:
        want = FORWARD_KEY[orient]
        # 先頭・巻末・途中の3か所から判定させる
        spots = [("先頭", 0), ("巻末", len(pages) - 1), ("途中", int(len(pages) * 0.17))]
        results = []
        for label, pos in spots:
            sys.stdout = quiet  # 判定の実況は抑制する
            try:
                verdict, end_pos = detect_from(pages, orient, pos, tmp)
            finally:
                sys.stdout = real_stdout
            if verdict is None:
                abstain += 1
                results.append(f"{label}:棄権")
            elif verdict == want:
                correct += 1
                results.append(f"{label}:OK")
            else:
                wrong += 1
                results.append(f"{label}:誤答({verdict})")
            # 先頭で開始したら表紙(0)に戻っていること＝表紙を撮り逃さない
            if label == "先頭" and end_pos != 0:
                drift.append(f"{name} 先頭判定後に {end_pos} ページ目へずれた")

        print(f"{name} ({orient}/{want}送り): " + "  ".join(results))

    quiet.close()
    shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n正解 {correct} / 棄権 {abstain} / 誤答 {wrong}")
    for d in drift:
        print(f"[NG] {d}")
    if wrong or drift:
        print("失敗: 向きの取り違え、または開始位置のずれがあります。")
        return 1
    print("成功: 誤った向きを返したケースはありません（棄権は安全side）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
