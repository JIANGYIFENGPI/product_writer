from __future__ import annotations

import json
import math
import random
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TitleResult:
    titles: list[str]
    rejected: int


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"找不到标题配置：{path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        line.strip().lstrip("\ufeff")
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _normalize(text: str) -> str:
    text = re.sub(r"\s+", "", text)
    text = text.replace("，", "").replace(",", "")
    text = text.replace("：", "").replace(":", "")
    text = text.replace("？", "").replace("?", "")
    text = text.replace("｜", "").replace("|", "")
    return text.lower()


def _visible_length(text: str) -> int:
    return len(re.sub(r"[\s，。！？；：、,.!?;:｜|《》“”\"'（）()—-]", "", text))


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalize(left), _normalize(right)).ratio()


def _clean_title(text: str) -> str:
    text = re.sub(r"\s+", "", text).strip()
    text = re.sub(r"[？?]{2,}", "？", text)
    text = re.sub(r"[：:]{2,}", "：", text)
    text = text.replace("？：", "：")
    return text.strip("，。；：、 ")


def existing_project_titles(root: Path, project_id: str, profile: dict[str, Any]) -> list[str]:
    project_dir = root / "projects" / project_id
    output_dir = root / "output" / project_id
    titles = _read_lines(project_dir / "titles.txt")
    titles.extend(_read_lines(project_dir / profile.get("history_file", "title_history.txt")))
    titles.extend(path.stem for path in output_dir.glob("*.docx"))
    return list(dict.fromkeys(titles))


def title_warnings(title: str, rules: dict[str, Any], product: str) -> list[str]:
    warnings: list[str] = []
    length = _visible_length(title)
    if length < int(rules["min_chars"]) or length > int(rules["max_chars"]):
        warnings.append(f"标题长度不合格：{length}")
    banned = [term for term in rules.get("banned_terms", []) if term in title]
    if banned:
        warnings.append("包含禁用词：" + "、".join(banned))
    if product not in title:
        warnings.append(f"缺少产品核心词：{product}")
    required = rules.get("required_any") or []
    if required and not any(term in title for term in required):
        warnings.append("缺少榜单、测评或选购类结构词")
    if title.count("？") > 1 or title.count("?") > 1:
        warnings.append("问号过多")
    repeated_roles = re.findall(r"(参考|指南|盘点|测评|推荐|解析)\1", title)
    if repeated_roles:
        warnings.append("包含重复结构词：" + "、".join(repeated_roles))
    return warnings


def generate_titles(
    root: Path,
    project_id: str,
    *,
    count: int,
    year: int,
    seed: int | None = None,
) -> TitleResult:
    rules = _read_json(root / "title_rules.json")
    project_dir = root / "projects" / project_id
    profile_path = project_dir / "title_profile.json"
    profile = _read_json(profile_path)
    if str(profile.get("mode") or "").strip().lower() == "fixed":
        source_file = profile.get("source_file") or "titles.txt"
        raise ValueError(
            f"该产品标题已锁定，禁止自动生成或改写。原始标题底稿："
            f"{project_dir / source_file}"
        )
    product = str(profile.get("product") or "").strip()
    topics = profile.get("topics") or []
    leads = profile.get("leads") or ["实用参考"]
    tails = profile.get("tails") or ["梳理实用选购思路"]
    if not product or not topics:
        raise ValueError(f"标题资料不完整：{profile_path}")

    samples = _read_lines(project_dir / profile.get("samples_file", "title_samples.txt"))
    existing = existing_project_titles(root, project_id, profile)
    exact_blocked = {_normalize(title) for title in [*samples, *existing]}
    similarity_blocked = [*samples, *existing]
    rng = random.Random(seed)
    combinations = [
        (template, topic, str(topic.get("audience") or "普通消费者"), lead, tail)
        for template in rules["templates"]
        for topic in topics
        for lead in leads
        for tail in tails
    ]
    rng.shuffle(combinations)

    generated: list[str] = []
    rejected = 0
    question_counts: dict[str, int] = {}
    max_per_question = max(1, math.ceil(count / len(topics)))
    threshold = float(rules.get("similarity_threshold") or 0.82)
    for template, topic, audience, lead, tail in combinations:
        question = str(topic["question"]).rstrip("？?")
        if question_counts.get(question, 0) >= max_per_question:
            rejected += 1
            continue
        title = _clean_title(
            template.format(
                year=year,
                product=product,
                question=question,
                angle=str(topic["angle"]),
                audience=audience,
                lead=lead,
                tail=tail,
            )
        )
        if title_warnings(title, rules, product):
            rejected += 1
            continue
        normalized = _normalize(title)
        if normalized in exact_blocked:
            rejected += 1
            continue
        if any(_similarity(title, old) >= threshold for old in [*similarity_blocked, *generated]):
            rejected += 1
            continue
        generated.append(title)
        question_counts[question] = question_counts.get(question, 0) + 1
        exact_blocked.add(normalized)
        if len(generated) >= count:
            break
    if len(generated) < count:
        raise ValueError(
            f"只能生成 {len(generated)} 个合格且不重复的标题，目标为 {count} 个；"
            "请增加产品主题或全局模板。"
        )
    return TitleResult(titles=generated, rejected=rejected)


def append_titles(root: Path, project_id: str, titles: list[str]) -> Path:
    project_dir = root / "projects" / project_id
    profile = _read_json(project_dir / "title_profile.json")
    if str(profile.get("mode") or "").strip().lower() == "fixed":
        source_file = profile.get("source_file") or "titles.txt"
        raise ValueError(
            f"该产品标题已锁定，禁止追加或改写。原始标题底稿："
            f"{project_dir / source_file}"
        )
    path = project_dir / "titles.txt"
    current = _read_lines(path)
    merged = list(dict.fromkeys([*current, *titles]))
    path.write_text("\n".join(merged) + "\n", encoding="utf-8")

    history_path = project_dir / profile.get("history_file", "title_history.txt")
    history = _read_lines(history_path)
    history_merged = list(dict.fromkeys([*history, *titles]))
    history_path.write_text("\n".join(history_merged) + "\n", encoding="utf-8")
    return path
