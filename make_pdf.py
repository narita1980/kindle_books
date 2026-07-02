import argparse
import os

import Quartz


def _cfurl(path):
    b = os.fsencode(os.path.abspath(path))
    return Quartz.CFURLCreateFromFileSystemRepresentation(None, b, len(b), False)


def make_pdf(session_dir, output=None):
    """セッションフォルダ内の連番 PNG を 1 冊の PDF にまとめる。
    Quartz で 1 ページずつ書き込むため、数百ページでもメモリを圧迫しない。"""
    files = sorted(
        f for f in os.listdir(session_dir)
        if f.lower().endswith(".png") and not f.startswith(".")
    )
    if not files:
        raise SystemExit(f"PNG が見つかりません: {session_dir}")
    if output is None:
        output = os.path.normpath(session_dir) + ".pdf"

    ctx = Quartz.CGPDFContextCreateWithURL(_cfurl(output), None, None)
    if ctx is None:
        raise SystemExit(f"PDF を作成できません: {output}")

    pages = 0
    for name in files:
        src = Quartz.CGImageSourceCreateWithURL(
            _cfurl(os.path.join(session_dir, name)), None)
        img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None) if src else None
        if img is None:
            print(f"  [warn] 読み込めない画像をスキップ: {name}")
            continue
        rect = Quartz.CGRectMake(
            0, 0, Quartz.CGImageGetWidth(img), Quartz.CGImageGetHeight(img))
        Quartz.CGContextBeginPage(ctx, rect)
        Quartz.CGContextDrawImage(ctx, rect, img)
        Quartz.CGContextEndPage(ctx)
        pages += 1

    Quartz.CGPDFContextClose(ctx)
    print(f"{pages}ページの PDF を作成しました: {output}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="撮影済みセッションフォルダの PNG を 1 冊の PDF にまとめる")
    parser.add_argument("session_dir",
                        help="PNG が入ったセッションフォルダ（例: kindle_screenshots/2026-06-17_21-19-03）")
    parser.add_argument("-o", "--output", default=None,
                        help="出力 PDF のパス（既定: セッションフォルダ名.pdf）")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    make_pdf(args.session_dir, args.output)
