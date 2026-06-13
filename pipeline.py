from __future__ import annotations

import argparse
import json
from pathlib import Path

from product_writer.config import init_project
from product_writer.env_utils import ensure_env_file
from product_writer.generator import GenerationError
from product_writer.pipeline_core import PipelineOptions, run_pipeline
from product_writer.title_generator import append_titles, generate_titles


ROOT = Path(__file__).resolve().parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="多产品 Word 文章生成器")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="创建产品目录和默认配置")
    init_parser.add_argument("--project", required=True, help="产品 id，例如 lingzhi")
    init_parser.add_argument("--name", required=True, help="产品名称，例如 灵芝孢子粉")
    init_parser.add_argument("--force", action="store_true", help="覆盖已存在的模板文件")

    titles_parser = subparsers.add_parser("titles", help="按全局规则和产品样本生成标题")
    titles_parser.add_argument("--project", required=True, help="产品 id，例如 tuonaifen")
    titles_parser.add_argument("--count", type=int, default=10, help="生成标题数量，默认 10")
    titles_parser.add_argument("--year", type=int, default=2026, help="标题年份")
    titles_parser.add_argument("--seed", type=int, help="固定随机种子，便于复现")
    titles_parser.add_argument(
        "--append",
        action="store_true",
        help="通过检查后追加到项目 titles.txt；默认只预览",
    )

    parser.add_argument("--project", help="产品 id，例如 test_product")
    parser.add_argument("--limit", type=int, help="最多处理多少篇")
    parser.add_argument("--dry-run", action="store_true", help="只生成实际 prompt，不调用 API")
    parser.add_argument("--skip-existing", action="store_true", default=True, help="跳过已生成 docx")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已生成 docx")
    parser.add_argument(
        "--repair-existing",
        action="store_true",
        help="遍历已有 Word，修复命中的AI痕迹并重新质检",
    )
    parser.add_argument("--workers", type=int, default=3, help="并行生成数量，默认 3；设为 1 可顺序生成")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    ensure_env_file(ROOT)

    if args.command == "init":
        path = init_project(ROOT, args.project, args.name, force=args.force)
        print(f"已创建产品目录：{path}")
        return 0

    if args.command == "titles":
        try:
            result = generate_titles(
                ROOT,
                args.project,
                count=max(1, args.count),
                year=args.year,
                seed=args.seed,
            )
        except (FileNotFoundError, ValueError) as exc:
            print(f"标题生成失败：{exc}")
            return 1
        for index, title in enumerate(result.titles, 1):
            print(f"{index}. {title}")
        print(f"已过滤不合格或相似候选：{result.rejected}")
        if args.append:
            path = append_titles(ROOT, args.project, result.titles)
            print(f"已追加到：{path}")
        else:
            print("当前仅预览，未写入 titles.txt。")
        return 0

    if not args.project:
        parser.error("请提供 --project，或使用 init 子命令。")

    options = PipelineOptions(
        project_id=args.project,
        dry_run=args.dry_run,
        limit=args.limit,
        skip_existing=not args.overwrite,
        overwrite=args.overwrite,
        workers=args.workers,
        repair_existing=args.repair_existing,
    )
    try:
        reports = run_pipeline(ROOT, options)
    except GenerationError as exc:
        print(f"生成失败：{exc}")
        return 1
    except (FileNotFoundError, ValueError) as exc:
        print(f"运行失败：{exc}")
        return 1
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 1 if any(not report.get("success") for report in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
