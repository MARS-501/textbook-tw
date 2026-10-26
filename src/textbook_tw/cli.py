"""指令列入口：uv run textbook-tw translate <PDF>"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from textbook_tw.config import DUAL_MODES, FONTS, list_profiles, load_profile, load_settings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="textbook-tw", description="保留原版面，把英文 PDF 翻成台灣繁體中文"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    tr = sub.add_parser("translate", help="翻譯一份 PDF")
    tr.add_argument("pdf", type=Path, help="要翻譯的 PDF")
    tr.add_argument("-p", "--pages", help="只翻部分頁面，例如 1-5,8（1 起算）")
    tr.add_argument(
        "--dual",
        choices=DUAL_MODES,
        help="對照版格式：side_by_side 左右並排、alternating 交替頁、both 兩種、none 不要",
    )
    tr.add_argument("--profile", choices=list_profiles(), help="科目設定")
    tr.add_argument("--font", choices=FONTS, help="譯文字型：auto、serif 明體、sans-serif 黑體")
    tr.add_argument("--model", help="Ollama 模型名稱，例如 qwen3.5:4b")
    tr.add_argument("--output", type=Path, help="輸出資料夾")
    tr.add_argument("--no-mono", action="store_true", help="不輸出純譯文版")
    tr.add_argument("--translated-first", action="store_true", help="對照版譯文放前面")
    tr.add_argument("--no-glossary", action="store_true", help="不使用術語表")
    tr.add_argument("-v", "--verbose", action="store_true", help="顯示 BabelDOC 的詳細紀錄")

    sub.add_parser("profiles", help="列出科目設定")

    gl = sub.add_parser("glossary", help="術語表").add_subparsers(
        dest="glossary_command", required=True
    )
    scan = gl.add_parser("scan", help="掃描 PDF，建立這本書的術語表")
    scan.add_argument("pdf", type=Path, help="要掃描的 PDF")
    scan.add_argument("--profile", choices=list_profiles(), help="科目設定")
    scan.add_argument("--force", action="store_true", help="覆蓋已有的術語表（你的修改會遺失）")
    gl.add_parser("update", help="重新下載國家教育研究院的名詞庫")
    return parser


def _quiet_logs(verbose: bool) -> None:
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, format="%(message)s")
    for name in ("httpx", "httpcore", "openai", "peewee", "pdfminer"):
        logging.getLogger(name).setLevel(logging.ERROR)


def _make_progress_printer():
    last = {"line": ""}

    def on_progress(stage: str, overall: float) -> None:
        line = f"\r{overall:5.1f}%  {stage[:60]:<60}"
        if line != last["line"]:
            print(line, end="", flush=True)
            last["line"] = line

    return on_progress


def _translate(args: argparse.Namespace) -> int:
    from textbook_tw import pipeline

    settings = load_settings().with_overrides(
        dual=args.dual,
        profile=args.profile,
        font=args.font,
        model=args.model,
        output_dir=args.output.resolve() if args.output else None,
        mono=False if args.no_mono else None,
        translated_first=True if args.translated_first else None,
        glossary=False if args.no_glossary else None,
    )
    if not args.pdf.is_file():
        print(f"找不到檔案：{args.pdf}", file=sys.stderr)
        return 1

    print(f"翻譯 {args.pdf.name}（{settings.profile.name}，模型 {settings.model}）")
    try:
        outputs = pipeline.translate(
            args.pdf,
            settings,
            pages=args.pages,
            on_progress=_make_progress_printer(),
            on_message=print,
        )
    except (pipeline.SetupError, ValueError) as e:
        print(f"\n{e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已中斷。已翻好的段落有快取，下次重跑會接著翻。", file=sys.stderr)
        return 130

    minutes, seconds = divmod(int(outputs.seconds), 60)
    print(f"\n完成，花了 {minutes} 分 {seconds} 秒：")
    for label, path in (
        ("純譯文", outputs.mono),
        ("對照-並排", outputs.side_by_side),
        ("對照-交替", outputs.alternating),
    ):
        if path:
            print(f"  {label}：{path}")
    return 0


def _glossary(args: argparse.Namespace) -> int:
    from textbook_tw.glossary import book
    from textbook_tw.glossary.fetch import fetch_missing, load_sources
    from textbook_tw.pipeline import describe_book_glossary

    if args.glossary_command == "update":
        fetch_missing(load_sources(), force=True, on_fetch=lambda s: print(f"下載 {s.id}"))
        print("名詞庫已更新。已建立的術語表不會自動更新，需要的話請用 glossary scan 重建。")
        return 0

    if not args.pdf.is_file():
        print(f"找不到檔案：{args.pdf}", file=sys.stderr)
        return 1
    existing = book.book_path(args.pdf)
    if existing.exists() and not args.force:
        print(
            f"已經有術語表 {existing}。要重新掃描請加 --force（你在裡面的修改會遺失）。",
            file=sys.stderr,
        )
        return 1
    settings = load_settings().with_overrides(profile=args.profile)
    print(f"掃描 {args.pdf.name}（{settings.profile.name}）…")
    path, terms = book.create_book_glossary(args.pdf.resolve(), settings.profile)
    print("已建立" + describe_book_glossary(path, terms))
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(errors="replace")
    args = _build_parser().parse_args(argv)
    if args.command == "profiles":
        for profile_id in list_profiles():
            profile = load_profile(profile_id)
            print(f"{profile_id:<18} {profile.name}：{profile.description}")
        return 0
    if args.command == "glossary":
        return _glossary(args)

    _quiet_logs(args.verbose)
    return _translate(args)


if __name__ == "__main__":
    sys.exit(main())
