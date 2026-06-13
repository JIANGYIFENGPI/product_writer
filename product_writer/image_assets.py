from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass(frozen=True)
class ArticleImages:
    neutral: Path | None
    by_rank: dict[int, Path]


def promoted_image_slots(config: dict[str, Any]) -> dict[int, str]:
    slots: dict[int, str] = {}
    configured_ranks = (config.get("illustrations") or {}).get("promoted_ranks")
    enabled_ranks = (
        {int(rank) for rank in configured_ranks}
        if configured_ranks is not None
        else {1, 2, 3}
    )
    for item in config.get("promoted_products") or []:
        rank = int(item.get("rank") or 0)
        if rank not in enabled_ranks:
            continue
        slot = str(item.get("image_slot") or f"top{rank}").strip()
        if slot:
            slots[rank] = slot
    return slots


def configured_image_slots(config: dict[str, Any]) -> list[str]:
    settings = config.get("illustrations") or {}
    neutral_slot = str(settings.get("neutral_slot") or "neutral").strip()
    slots = [neutral_slot, *promoted_image_slots(config).values()]
    return list(dict.fromkeys(slot for slot in slots if slot))


def load_image_paths(project_path: Path, config: dict[str, Any]) -> list[Path]:
    if not config.get("features", {}).get("images", False):
        return []
    images_dir = project_path / config["project"].get("images_dir", "images")
    if not images_dir.exists():
        return []
    return sorted(path for path in images_dir.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS)


def select_article_images(image_paths: list[Path], title: str, count: int = 4) -> list[Path]:
    if not image_paths:
        return []
    rng = random.Random(title)
    if len(image_paths) <= count:
        return image_paths[:]
    return rng.sample(image_paths, count)


def load_image_slots(project_path: Path, config: dict[str, Any]) -> dict[str, list[Path]]:
    if not config.get("features", {}).get("images", False):
        return {}
    images_dir = project_path / config["project"].get("images_dir", "images")
    settings = config.get("illustrations") or {}
    neutral_slot = str(settings.get("neutral_slot") or "neutral").strip()
    allowed_neutral = {
        str(name).strip()
        for name in settings.get("neutral_image_allowlist") or []
        if str(name).strip()
    }
    slots: dict[str, list[Path]] = {}
    for slot in configured_image_slots(config):
        slot_dir = images_dir / slot
        if slot_dir.exists():
            paths = sorted(
                path
                for path in slot_dir.iterdir()
                if path.suffix.lower() in IMAGE_EXTENSIONS
            )
            if slot == neutral_slot and allowed_neutral:
                paths = [path for path in paths if path.name in allowed_neutral]
            slots[slot] = paths
    return slots


def validate_image_slots(
    image_slots: dict[str, list[Path]],
    config: dict[str, Any],
) -> None:
    if not config.get("features", {}).get("images", False):
        return
    expected = configured_image_slots(config)
    missing = [slot for slot in expected if not image_slots.get(slot)]
    if missing:
        raise ValueError(
            "已启用自动插图，但以下图片槽位没有可用素材："
            + "、".join(missing)
        )


def select_article_slot_images(
    image_slots: dict[str, list[Path]],
    title: str,
    config: dict[str, Any],
    content: str = "",
) -> ArticleImages:
    rng = random.Random(title)
    settings = config.get("illustrations") or {}
    neutral_slot = str(settings.get("neutral_slot") or "neutral").strip()
    neutral_choices = image_slots.get(neutral_slot) or []
    neutral = select_matching_neutral_image(
        neutral_choices,
        title,
        content,
        settings.get("neutral_image_keywords") or {},
        rng,
    )
    by_rank: dict[int, Path] = {}
    for rank, slot in promoted_image_slots(config).items():
        choices = image_slots.get(slot) or []
        if choices:
            by_rank[rank] = rng.choice(choices)
    return ArticleImages(neutral=neutral, by_rank=by_rank)


def select_matching_neutral_image(
    choices: list[Path],
    title: str,
    content: str,
    keyword_map: dict[str, Any],
    rng: random.Random,
) -> Path | None:
    if not choices:
        return None

    title_lower = title.lower()
    content_lower = content.lower()
    scored: list[tuple[int, Path]] = []
    for path in choices:
        keywords = image_keywords(path, keyword_map)
        score = 0
        for keyword in keywords:
            term = keyword.strip().lower()
            if not term:
                continue
            if term in title_lower:
                score += 10
            if term in content_lower:
                score += min(content_lower.count(term), 3)
        scored.append((score, path))

    best_score = max(score for score, _ in scored)
    if best_score <= 0:
        return rng.choice(choices)
    best = [path for score, path in scored if score == best_score]
    return rng.choice(best)


def image_keywords(path: Path, keyword_map: dict[str, Any]) -> list[str]:
    configured = keyword_map.get(path.name, keyword_map.get(path.stem, []))
    if isinstance(configured, str):
        compact = configured.strip()
        if compact.startswith("[") and compact.endswith("]"):
            values = compact[1:-1].split(",")
        else:
            values = [configured]
    else:
        values = [str(keyword) for keyword in configured]
    return [value.strip() for value in values if value.strip()]
