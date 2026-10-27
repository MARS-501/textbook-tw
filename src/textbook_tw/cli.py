"""指令列入口：uv run textbook-tw translate <PDF>"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from textbook_tw.config import (
    DUAL_MODES,
    FONTS,
    Settings,
    list_profiles,
    load_profile,
    load_settings,
)


def _add_translate_options(tr: argparse.ArgumentParser) -> None:
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="textbook-tw", description="保留原版面，把英文 PDF 翻成台灣繁體中文"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    _add_translate_options(sub.add_parser("translate", help="翻譯一份 PDF"))

    sub.add_parser("profiles", help="列出科目設定")

    opt = sub.add_parser("optimize", help="讓之前翻好的 PDF 開起來不卡（畫面不變，直接覆蓋）")
    opt.add_argument("paths", type=Path, nargs="+", help="PDF 檔或資料夾（會處理裡面所有 PDF）")

    # 桌面 App 用的指令：輸出 JSON
    app = sub.add_parser("app", help="給桌面 App 呼叫（輸出 JSON）").add_subparsers(
        dest="app_command", required=True
    )
    app_gl = app.add_parser("glossary", help="沿用或建立術語表，回傳需要確認的詞")
    app_gl.add_argument("pdf", type=Path)
    app_gl.add_argument("--profile", choices=list_profiles())
    app_rs = app.add_parser("resolve", help="讓模型依上下文判斷術語譯名，每行輸出一個 JSON 事件")
    app_rs.add_argument("pdf", type=Path)
    app_rs.add_argument("--profile", choices=list_profiles())
    app.add_parser("apply", help="從標準輸入讀取選好的譯名並寫入").add_argument("pdf", type=Path)
    app_tr = app.add_parser("translate", help="翻譯，每行輸出一個 JSON 事件")
    _add_translate_options(app_tr)
    app_tr.add_argument("--out-dir", type=Path, help="輸出檔直接放在這個資料夾")

    gl = sub.add_parser("glossary", help="術語表").add_subparsers(
        dest="glossary_command", required=True
    )
    scan = gl.add_parser("scan", help="掃描 PDF，建立這本書的術語表")
    scan.add_argument("pdf", type=Path, help="要掃描的 PDF")
    scan.add_argument("--profile", choices=list_profiles(), help="科目設定")
    scan.add_argument("--force", action="store_true", help="覆蓋已有的術語表（你的修改會遺失）")
    scan.add_argument("--no-model", action="store_true", help="只掃描，不讓模型依上下文判斷譯名")
    rs = gl.add_parser("resolve", help="讓模型依文件上下文判斷術語譯名（需要 Ollama）")
    rs.add_argument("pdf", type=Path, help="已掃描過的 PDF")
    rs.add_argument("--profile", choices=list_profiles(), help="科目設定")
    rs.add_argument("--all", action="store_true", help="連已經判斷過的也重新判斷")
    gl.add_parser("update", help="重新下載國家教育研究院的名詞庫")
    return parser


def _quiet_logs(verbose: bool) -> None:
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, format="%(message)s")
    for name in ("httpx", "httpcore", "openai", "peewee", "pdfminer"):
        logging.getLogger(name).setLevel(logging.ERROR)


def _make_progress_printer():
    last = {"line": ""}

    def on_progress(stage: str, overall: float, _current: int, _total: int) -> None:
        line = f"\r{overall:5.1f}%  {stage[:60]:<60}"
        if line != last["line"]:
            print(line, end="", flush=True)
            last["line"] = line

    return on_progress


def _settings_from(args: argparse.Namespace) -> Settings:
    return load_settings().with_overrides(
        dual=args.dual,
        profile=args.profile,
        font=args.font,
        model=args.model,
        output_dir=args.output.resolve() if args.output else None,
        mono=False if args.no_mono else None,
        translated_first=True if args.translated_first else None,
        glossary=False if args.no_glossary else None,
    )


def _translate(args: argparse.Namespace) -> int:
    from textbook_tw import pipeline

    settings = _settings_from(args)
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
    if outputs.choice_usage:
        print("依段落選譯名的詞：")
        for source, counts in sorted(outputs.choice_usage.items()):
            used = "、".join(f"{zh} {n} 段" for zh, n in counts.items())
            print(f"  {source}：{used}")
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
    pdf = args.pdf.resolve()
    settings = load_settings().with_overrides(profile=args.profile)
    if args.glossary_command == "scan":
        existing = book.book_path(pdf)
        if existing.exists() and not args.force:
            print(
                f"已經有術語表 {existing}。要重新掃描請加 --force（你在裡面的修改會遺失）。",
                file=sys.stderr,
            )
            return 1
        print(f"掃描 {pdf.name}（{settings.profile.name}）…")
        path, terms = book.create_book_glossary(pdf, settings.profile)
        print("已建立" + describe_book_glossary(path, terms))
        if args.no_model:
            return 0
    return _resolve(pdf, settings, force=getattr(args, "all", False))


def _resolve(pdf: Path, settings: Settings, force: bool) -> int:
    from textbook_tw import pipeline
    from textbook_tw.glossary import book, resolve

    try:
        pipeline.check_model(settings)
        book.ensure_book_glossary(pdf, settings.profile)
        terms = resolve.resolve_book(
            pdf,
            settings,
            force=force,
            on_progress=lambda done, total: print(
                f"\r依上下文判斷術語譯名 {done}/{total}", end="", flush=True
            ),
        )
    except (pipeline.SetupError, resolve.ResolveError) as e:
        print(f"\n{e}", file=sys.stderr)
        return 1
    print()
    for status in (book.STATUS_SUGGESTED, book.STATUS_PER_PARAGRAPH, book.STATUS_SKIPPED):
        print(f"{status}：{sum(t.status == status for t in terms)} 個")
    print(f"結果寫在 {book.book_path(pdf)}，可用 Excel 檢查 status 與 note 欄")
    return 0


def _optimize(args: argparse.Namespace) -> int:
    from textbook_tw.compose.optimize import optimize_pdf

    files: list[Path] = []
    for path in args.paths:
        files += sorted(path.rglob("*.pdf")) if path.is_dir() else [path]
    if not files:
        print("沒有找到 PDF", file=sys.stderr)
        return 1
    for path in files:
        before = path.stat().st_size
        stats = optimize_pdf(path)
        if stats.glyphs:
            print(
                f"{path.name}：{stats.glyphs} 個逐字物件合併成 {stats.blocks} 個，"
                f"{before / 1e6:.1f} MB → {path.stat().st_size / 1e6:.1f} MB"
            )
        else:
            print(f"{path.name}：沒有需要合併的文字")
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(errors="replace")
    args = _build_parser().parse_args(argv)
    if args.command == "optimize":
        return _optimize(args)
    if args.command == "profiles":
        for profile_id in list_profiles():
            profile = load_profile(profile_id)
            print(f"{profile_id:<18} {profile.name}：{profile.description}")
        return 0
    if args.command == "glossary":
        return _glossary(args)
    if args.command == "app":
        return _app(args)

    _quiet_logs(args.verbose)
    return _translate(args)


def _app(args: argparse.Namespace) -> int:
    from textbook_tw import app_api

    _quiet_logs(getattr(args, "verbose", False))  # 紀錄寫到標準錯誤，不會混進 JSON
    if args.app_command == "glossary":
        return app_api.glossary(args.pdf, args.profile)
    if args.app_command == "apply":
        return app_api.apply(args.pdf)
    if args.app_command == "resolve":
        return app_api.resolve_terms(args.pdf, args.profile)
    out_dir = args.out_dir.resolve() if args.out_dir else None
    return app_api.translate(args.pdf, _settings_from(args), args.pages, out_dir)


if __name__ == "__main__":
    sys.exit(main())
