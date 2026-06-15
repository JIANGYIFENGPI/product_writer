from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass
import json
import os
from pathlib import Path

from product_writer.cleaner import clean_model_output
from product_writer.config import load_project_config, project_dir
from product_writer.filenames import safe_filename
from product_writer.generator import GenerationError, generate_article, humanize_article
from product_writer.image_assets import (
    load_image_paths,
    load_image_slots,
    select_article_images,
    select_article_slot_images,
    validate_image_slots,
)
from product_writer.prompt_loader import (
    choose_prompt,
    config_with_expected_promoted_order,
    config_with_prompt_promoted_order,
    extract_fixed_top10,
    load_prompts,
    load_terms,
    load_titles,
    render_prompt,
)
from product_writer.quality import (
    build_report,
    docx_article_char_count,
    docx_body_text,
    docx_illustration_warnings,
    write_report,
)
from product_writer.renderer import render_docx
from product_writer.state import mark_title


@dataclass
class PipelineOptions:
    project_id: str
    dry_run: bool = False
    limit: int | None = None
    skip_existing: bool = True
    overwrite: bool = False
    workers: int = 3
    repair_existing: bool = False


def remove_completed_titles(titles_file: Path, completed_titles: set[str]) -> None:
    if not completed_titles or not titles_file.exists():
        return
    lines = titles_file.read_text(encoding="utf-8-sig").splitlines()
    remaining = [line for line in lines if line.strip().lstrip("\ufeff") not in completed_titles]
    titles_file.write_text("\n".join(remaining).rstrip() + ("\n" if remaining else ""), encoding="utf-8")


def remove_disabled_raw_text(root: Path, project_id: str, config: dict) -> None:
    if config.get("features", {}).get("save_raw_text", False):
        return
    raw_dir = root / "runs" / project_id / "raw"
    if not raw_dir.exists():
        return
    expected = (root / "runs" / project_id).resolve()
    if raw_dir.resolve().parent != expected or raw_dir.name != "raw":
        raise ValueError(f"拒绝清理非预期目录：{raw_dir}")
    for path in raw_dir.iterdir():
        if not path.is_file():
            raise ValueError(f"raw 目录包含非文件项目，已停止清理：{path}")
        path.unlink()
    raw_dir.rmdir()


def process_title(
    *,
    root: Path,
    project_id: str,
    title: str,
    config: dict,
    prompts: list[tuple[Path, str]],
    terms: list[str],
    image_paths: list[Path] | None = None,
    image_slots: dict[str, list[Path]] | None = None,
    state_path: Path,
    options: PipelineOptions,
) -> dict:
    basename = safe_filename(title)
    docx_path = root / "output" / project_id / f"{basename}.docx"
    raw_path = root / "runs" / project_id / "raw" / f"{basename}.txt"
    humanized_path = root / "runs" / project_id / "humanized" / f"{basename}.txt"
    prompt_used_path = root / "runs" / project_id / "prompts_used" / f"{basename}.txt"
    report_path = root / "runs" / project_id / "reports" / f"{basename}.json"
    pending_path = docx_path.with_name(f".{docx_path.stem}.pending.docx")
    if pending_path.exists():
        pending_path.unlink()
    prompt_path, template = choose_prompt(prompts, title, config)
    article_config = config_with_prompt_promoted_order(template, config)

    previous_report: dict = {}
    if report_path.exists():
        try:
            previous_report = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            previous_report = {}

    if options.skip_existing and not options.overwrite and docx_path.exists() and not options.dry_run:
        try:
            existing_text = docx_body_text(docx_path)
        except Exception:  # noqa: BLE001
            existing_text = ""
        expected_existing = previous_report.get("expected_top10") or []
        existing_config = config_with_expected_promoted_order(expected_existing, article_config)
        previous_prompt = previous_report.get("prompt_template")
        prompt_existing = Path(previous_prompt) if previous_prompt else prompt_path
        existing_images = select_article_slot_images(
            image_slots or {},
            title,
            existing_config,
            existing_text,
        )
        if existing_images.neutral is None and not existing_images.by_rank:
            existing_images = select_article_images(image_paths or [], title)
        existing_report = build_report(
            title=title,
            docx_path=docx_path,
            raw_text=existing_text,
            cleaned_text=existing_text,
            prompt_path=prompt_existing,
            config=existing_config,
            expected_top10=expected_existing,
            humanized=bool(previous_report.get("humanized")),
            dry_run=False,
        )
        if existing_report["success"]:
            report = {
                **existing_report,
                "skipped": True,
                "reason": "docx 已存在且通过完整质检，已按 skip-existing 跳过",
            }
            write_report(report_path, report)
            mark_title(state_path, title, "skipped", report_path)
            return report

        humanizer_settings = existing_config.get("humanizer") or {}
        if (
            existing_text
            and humanizer_settings.get("enabled", True)
            and humanizer_settings.get("auto_rewrite", True)
        ):
            repair_error = ""
            try:
                repaired_text = humanize_article(
                    root,
                    existing_text,
                    existing_config,
                    expected_existing,
                    title,
                )
            except GenerationError as exc:
                repaired_text = existing_text
                repair_error = str(exc)
            if repaired_text != existing_text:
                render_docx(
                    title,
                    repaired_text,
                    pending_path,
                    existing_config,
                    terms,
                    image_paths=existing_images,
                )
                repaired_report = build_report(
                    title=title,
                    docx_path=pending_path,
                    raw_text=existing_text,
                    cleaned_text=repaired_text,
                    prompt_path=prompt_existing,
                    config=existing_config,
                    expected_top10=expected_existing,
                    humanized=True,
                    dry_run=False,
                )
                if repaired_report["success"]:
                    os.replace(pending_path, docx_path)
                    repaired_report["docx_path"] = str(docx_path)
                    repaired_report["repaired_existing"] = True
                    repaired_report["reason"] = "已有正文命中AI痕迹规则，已自然化重写并重新排版"
                    humanized_path.parent.mkdir(parents=True, exist_ok=True)
                    humanized_path.write_text(repaired_text, encoding="utf-8")
                    write_report(report_path, repaired_report)
                    mark_title(state_path, title, "completed", report_path)
                    return repaired_report
                pending_path.unlink(missing_ok=True)
            elif repair_error and options.repair_existing:
                raise GenerationError(
                    "已有文章自然化修复失败，原 Word 未修改：" + repair_error
                )

        text_only_config = deepcopy(existing_config)
        text_only_config.setdefault("features", {})["images"] = False
        text_only_report = build_report(
            title=title,
            docx_path=docx_path,
            raw_text=existing_text,
            cleaned_text=existing_text,
            prompt_path=prompt_existing,
            config=text_only_config,
            expected_top10=expected_existing,
            humanized=bool(previous_report.get("humanized")),
            dry_run=False,
        )
        if text_only_report["success"] and docx_illustration_warnings(docx_path, existing_config):
            render_docx(
                title,
                existing_text,
                pending_path,
                existing_config,
                terms,
                image_paths=existing_images,
            )
            repaired_report = build_report(
                title=title,
                docx_path=pending_path,
                raw_text=existing_text,
                cleaned_text=existing_text,
                prompt_path=prompt_existing,
                config=existing_config,
                expected_top10=expected_existing,
                humanized=bool(previous_report.get("humanized")),
                dry_run=False,
            )
            if repaired_report["success"]:
                os.replace(pending_path, docx_path)
                repaired_report["docx_path"] = str(docx_path)
                repaired_report["repaired_existing"] = True
                repaired_report["reason"] = "正文通过质检，仅重新排版并补齐插图"
                write_report(report_path, repaired_report)
                mark_title(state_path, title, "completed", report_path)
                return repaired_report
            pending_path.unlink(missing_ok=True)

    prompt = render_prompt(template, title, article_config)
    expected_top10 = extract_fixed_top10(prompt)
    prompt_used_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_used_path.write_text(prompt, encoding="utf-8")

    if options.dry_run:
        report = build_report(
            title=title,
            docx_path=None,
            raw_text="",
            cleaned_text="",
            prompt_path=prompt_path,
            config=article_config,
            expected_top10=expected_top10,
            dry_run=True,
        )
        write_report(report_path, report)
        mark_title(state_path, title, "dry-run", report_path)
        return report

    raw_text = generate_article(root, prompt, article_config, expected_top10, title)
    cleaned_text = clean_model_output(raw_text)
    humanized_text = humanize_article(
        root,
        cleaned_text,
        article_config,
        expected_top10,
        title,
    )
    was_humanized = humanized_text != cleaned_text
    cleaned_text = clean_model_output(humanized_text)
    article_images = select_article_slot_images(
        image_slots or {},
        title,
        article_config,
        cleaned_text,
    )
    if article_images.neutral is None and not article_images.by_rank:
        article_images = select_article_images(image_paths or [], title)

    if article_config.get("features", {}).get("save_raw_text", False):
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(raw_text, encoding="utf-8")
    elif raw_path.exists():
        raw_path.unlink()
    if was_humanized:
        humanized_path.parent.mkdir(parents=True, exist_ok=True)
        humanized_path.write_text(cleaned_text, encoding="utf-8")
    elif humanized_path.exists():
        humanized_path.unlink()

    render_docx(title, cleaned_text, pending_path, article_config, terms, image_paths=article_images)
    report = build_report(
        title=title,
        docx_path=pending_path,
        raw_text=humanized_text,
        cleaned_text=cleaned_text,
        prompt_path=prompt_path,
        config=article_config,
        expected_top10=expected_top10,
        humanized=was_humanized,
        dry_run=False,
    )
    if report["success"]:
        os.replace(pending_path, docx_path)
        report["docx_path"] = str(docx_path)
    else:
        pending_path.unlink(missing_ok=True)
        report["docx_path"] = str(docx_path) if docx_path.exists() else None
        report["candidate_rejected"] = True
    write_report(report_path, report)
    mark_title(state_path, title, "completed" if report["success"] else "warning", report_path)
    return report


def run_pipeline(root: Path, options: PipelineOptions) -> list[dict]:
    config = load_project_config(root, options.project_id)
    remove_disabled_raw_text(root, options.project_id, config)
    product_path = project_dir(root, options.project_id)
    titles = load_titles(product_path, config)
    if options.repair_existing:
        output_dir = root / "output" / options.project_id
        titles = [path.stem for path in sorted(output_dir.glob("*.docx"))]
    prompts = load_prompts(product_path, config)
    terms = load_terms(product_path, config)
    image_paths = load_image_paths(product_path, config)
    image_slots = load_image_slots(product_path, config)
    if not options.dry_run:
        validate_image_slots(image_slots, config)

    if not titles and options.repair_existing:
        raise ValueError(f"没有可修复的 Word：{root / 'output' / options.project_id}")
    if not titles:
        raise ValueError(f"标题列表为空：{product_path / config['project']['titles_file']}")

    selected_titles = titles[: options.limit] if options.limit else titles
    reports: list[dict] = []
    completed_titles: set[str] = set()
    state_path = root / "runs" / options.project_id / "state.json"
    titles_file = product_path / config["project"]["titles_file"]
    workers = max(1, options.workers)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                process_title,
                root=root,
                project_id=options.project_id,
                title=title,
                config=config,
                prompts=prompts,
                terms=terms,
                image_paths=image_paths,
                image_slots=image_slots,
                state_path=state_path,
                options=options,
            ): index
            for index, title in enumerate(selected_titles)
        }
        ordered_reports: list[dict | None] = [None] * len(selected_titles)
        for future in as_completed(futures):
            index = futures[future]
            title = selected_titles[index]
            try:
                report = future.result()
            except Exception as exc:  # noqa: BLE001
                basename = safe_filename(title)
                report_path = root / "runs" / options.project_id / "reports" / f"{basename}.json"
                report = {
                    "title": title,
                    "success": False,
                    "error": str(exc),
                    "warnings": [f"处理异常：{exc}"],
                }
                write_report(report_path, report)
                mark_title(state_path, title, "failed", report_path)
            ordered_reports[index] = report
            if report.get("success") and not options.dry_run:
                completed_titles.add(report["title"])
        reports = [report for report in ordered_reports if report is not None]

    if (
        not options.dry_run
        and not options.repair_existing
        and not config["project"].get("preserve_titles", False)
    ):
        remove_completed_titles(titles_file, completed_titles)
    return reports
