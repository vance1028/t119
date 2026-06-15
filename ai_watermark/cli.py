from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .processors import scan_directory, detect_file_type
from .models import ComplianceStatus
from .marker import MarkConfig, mark_directory
from .verifier import VerifyConfig, verify_directory


DEFAULT_KEY_ENV = "AI_WATERMARK_KEY"


_STATUS_LABELS = {
    ComplianceStatus.COMPLIANT: "合规",
    ComplianceStatus.MISSING_BOTH: "缺标(两层都缺)",
    ComplianceStatus.MISSING_EXPLICIT: "缺标(缺显式)",
    ComplianceStatus.MISSING_IMPLICIT: "缺标(缺隐式)",
    ComplianceStatus.MISMATCH: "显隐不一致",
    ComplianceStatus.HMAC_INVALID: "HMAC校验失败(疑似伪造)",
    ComplianceStatus.FINGERPRINT_MISMATCH: "指纹不匹配(疑似篡改)",
    ComplianceStatus.ERROR: "处理错误",
    ComplianceStatus.SKIPPED: "跳过",
}


def _resolve_secret_key(cli_key: str | None, cli_key_file: str | None) -> bytes:
    if cli_key:
        return cli_key.encode("utf-8")
    if cli_key_file:
        with open(cli_key_file, "rb") as f:
            return f.read().strip()
    env_val = os.environ.get(DEFAULT_KEY_ENV)
    if env_val:
        return env_val.encode("utf-8")
    raise SystemExit(
        "错误: 未提供密钥。请通过 --key 或 --key-file 或环境变量 "
        f"{DEFAULT_KEY_ENV} 指定密钥。"
    )


def _make_progress_printer(verbose: bool):
    if not verbose:
        return None
    def _cb(idx: int, total: int, p: Path):
        pct = (idx / total * 100) if total > 0 else 100
        print(f"  [{idx}/{total} {pct:5.1f}%] {p}", file=sys.stderr)
    return _cb


def _print_human_report(
    summary: dict[str, Any],
    groups: dict[str, list[str]],
    cmd: str,
    extra_counts: dict[str, int] | None = None,
):
    if cmd == "scan":
        print()
        print("=== 扫描结果 ===")
        print(f"共发现文件: {summary['total']}")
        by_type = summary.get("by_type", {})
        for t, c in by_type.items():
            print(f"  {t:10s}: {c}")
        return
    if cmd == "mark":
        counts = extra_counts or {}
        print()
        print("=== 打标报告 ===")
        print(f"总文件: {summary['total']}")
        print(f"  新增打标: {counts.get('marked', 0)}")
        print(f"  已打标跳过: {counts.get('already_marked', 0)}")
        print(f"  Dry-run: {counts.get('dry_run', 0)}")
        print(f"  跳过(不支持): {counts.get('skipped', 0)}")
        print(f"  失败: {counts.get('failed', 0)}")
        if counts.get('dry_run', 0) > 0:
            print("（说明: dry-run 模式下没有实际修改文件）")
        return
    if cmd == "verify":
        label_keys = [
            ("compliant", "合规"),
            ("missing_both", "缺标(两层都缺)"),
            ("missing_explicit", "缺标(缺显式)"),
            ("missing_implicit", "缺标(缺隐式)"),
            ("mismatch", "显隐不一致"),
            ("hmac_invalid", "HMAC校验失败(疑似伪造)"),
            ("fingerprint_mismatch", "指纹不匹配(疑似篡改)"),
            ("error", "处理错误"),
            ("skipped", "跳过"),
        ]
        print()
        print("=== 核验分组报告 ===")
        total = summary["total"]
        print(f"文件总数: {total}")
        s = summary
        for key, label in label_keys:
            c = s.get(key, 0)
            if c:
                pct = c / total * 100 if total > 0 else 0
                print(f"  {label:24s}: {c:5d} ({pct:5.1f}%)")
        issues = (
            s.get("missing_both", 0) + s.get("missing_explicit", 0)
            + s.get("missing_implicit", 0) + s.get("mismatch", 0)
            + s.get("hmac_invalid", 0) + s.get("fingerprint_mismatch", 0)
            + s.get("error", 0)
        )
        print(f"  {'问题合计':24s}: {issues:5d}")
        print()
        print("=== 各分组文件列表 ===")
        for key, label in label_keys:
            files = groups.get(key, [])
            if files:
                print(f"\n[{label}] 共 {len(files)} 个:")
                for f in files:
                    print(f"  - {f}")
        return


def _json_dump(obj: Any, out_file: str | None):
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if out_file:
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        print(text)


def _build_output_dict(cmd: str, **kwargs) -> dict:
    out = {"command": cmd, "version": __version__}
    out.update(kwargs)
    return out


def cmd_scan(args: argparse.Namespace) -> int:
    directory = Path(args.directory).resolve()
    if not directory.is_dir():
        print(f"错误: 目录不存在: {directory}", file=sys.stderr)
        return 2
    files = scan_directory(directory)
    by_type: dict[str, int] = {}
    file_list = []
    for p, ft in files:
        by_type[ft] = by_type.get(ft, 0) + 1
        file_list.append({"path": str(p), "type": ft})
    summary = {"total": len(files), "by_type": by_type}
    if args.format == "json":
        out = _build_output_dict(
            "scan",
            directory=str(directory),
            summary=summary,
            files=file_list,
        )
        _json_dump(out, args.output)
    else:
        _print_human_report(summary, {}, "scan")
        if args.output:
            out = _build_output_dict(
                "scan",
                directory=str(directory),
                summary=summary,
                files=file_list,
            )
            _json_dump(out, args.output)
    return 0


def cmd_mark(args: argparse.Namespace) -> int:
    directory = Path(args.directory).resolve()
    if not directory.is_dir():
        print(f"错误: 目录不存在: {directory}", file=sys.stderr)
        return 2
    try:
        secret_key = _resolve_secret_key(args.key, args.key_file)
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 2
    progress_cb = _make_progress_printer(args.verbose or (args.format != "json"))
    config = MarkConfig(
        secret_key=secret_key,
        ai_tool=args.tool,
        is_ai_generated=not args.not_ai,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
        progress_cb=progress_cb,
    )
    files = scan_directory(directory)
    result = mark_directory(directory, config, files=files)
    counts = result.summary_counts()
    file_list = [fr.to_dict() for fr in result.file_results]
    summary = {
        "total": len(result.file_results),
        "marked": counts["marked"],
        "already_marked": counts["already_marked"],
        "dry_run": counts["dry_run"],
        "skipped": counts["skipped"],
        "failed": counts["failed"],
        "dry_run_mode": args.dry_run,
    }
    if args.format == "json":
        out = _build_output_dict(
            "mark",
            directory=str(directory),
            dry_run=args.dry_run,
            tool=args.tool,
            not_ai=args.not_ai,
            summary=summary,
            files=file_list,
        )
        _json_dump(out, args.output)
    else:
        _print_human_report(summary, {}, "mark", extra_counts=counts)
        if args.output:
            out = _build_output_dict(
                "mark",
                directory=str(directory),
                dry_run=args.dry_run,
                tool=args.tool,
                not_ai=args.not_ai,
                summary=summary,
                files=file_list,
            )
            _json_dump(out, args.output)
    if counts.get("failed", 0) > 0:
        return 1
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    directory = Path(args.directory).resolve()
    if not directory.is_dir():
        print(f"错误: 目录不存在: {directory}", file=sys.stderr)
        return 2
    try:
        secret_key = _resolve_secret_key(args.key, args.key_file)
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 2
    progress_cb = _make_progress_printer(args.verbose or (args.format != "json"))
    config = VerifyConfig(
        secret_key=secret_key,
        progress_cb=progress_cb,
    )
    files = scan_directory(directory)
    result = verify_directory(directory, config, files=files)
    summary = result.summary().to_dict()
    groups = result.grouped()
    file_list = [fr.to_dict() for fr in result.file_results]
    if args.format == "json":
        out = _build_output_dict(
            "verify",
            directory=str(directory),
            summary=summary,
            groups=groups,
            files=file_list,
        )
        _json_dump(out, args.output)
    else:
        _print_human_report(summary, groups, "verify")
        if args.output:
            out = _build_output_dict(
                "verify",
                directory=str(directory),
                summary=summary,
                groups=groups,
                files=file_list,
            )
            _json_dump(out, args.output)
    has_issues = result.has_issues()
    if args.strict and has_issues:
        return 3
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-watermark",
        description="AI内容标识自动化工具 - 批量打标/核验，支持显式元数据+隐式水印",
    )
    parser.add_argument("--version", action="version", version=f"ai-watermark {__version__}")
    parser.add_argument(
        "--key",
        help=f"HMAC密钥，也可通过环境变量 {DEFAULT_KEY_ENV} 指定",
        default=None,
    )
    parser.add_argument(
        "--key-file",
        help="从文件读取HMAC密钥",
        default=None,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="扫描目录，列出识别到的文件及类型")
    p_scan.add_argument("directory", help="要扫描的目录")
    p_scan.add_argument("--format", choices=["text", "json"], default="text")
    p_scan.add_argument("-o", "--output", help="输出JSON结果到文件（text模式也可选存一份JSON）")
    p_scan.set_defaults(func=cmd_scan)

    p_mark = sub.add_parser("mark", help="对目录批量打标（显式+隐式），幂等")
    p_mark.add_argument("directory", help="要打标的目录")
    p_mark.add_argument("--tool", default="unknown", help="AI生成工具名称（如: GPT-4o, Midjourney 等）")
    p_mark.add_argument("--not-ai", action="store_true", help="标记为非AI生成（is_ai_generated=false）")
    p_mark.add_argument("--overwrite", action="store_true", help="覆盖已存在的标识（默认不覆盖已正确打标的文件）")
    p_mark.add_argument("--dry-run", action="store_true", help="只模拟不写文件")
    p_mark.add_argument("--format", choices=["text", "json"], default="text")
    p_mark.add_argument("-o", "--output", help="输出JSON结果到文件")
    p_mark.add_argument("-v", "--verbose", action="store_true", help="显示每个文件进度")
    p_mark.set_defaults(func=cmd_mark)

    p_verify = sub.add_parser("verify", help="对目录做合规核验，出分组报告")
    p_verify.add_argument("directory", help="要核验的目录")
    p_verify.add_argument("--strict", action="store_true", help="严格模式，有不合规则以非零退出码退出")
    p_verify.add_argument("--format", choices=["text", "json"], default="text")
    p_verify.add_argument("-o", "--output", help="输出JSON结果到文件")
    p_verify.add_argument("-v", "--verbose", action="store_true", help="显示每个文件进度")
    p_verify.set_defaults(func=cmd_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n已中断。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
