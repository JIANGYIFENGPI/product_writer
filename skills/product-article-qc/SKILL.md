---
name: product-article-qc
description: Product article post-generation quality-control workflow for product_writer projects. Use when the user asks to inspect, fix, optimize, validate, summarize warnings, process generated Word articles, handle batch product articles, clean AI traces, normalize ranking labels, check illustration placement, check Word formatting, or decide whether generated product articles should be accepted without blindly rerunning or changing prompts.
---

# Product Article QC

Use this skill for `product_writer` article batches after generation. The goal is to make generated product articles usable with the smallest safe intervention.

## Core Rules

- Do not modify prompts unless the user explicitly asks.
- Do not rerun DeepSeek/API generation unless the user explicitly asks to rerun or generate.
- Do not delete titles from `titles.txt` unless reports pass or the user explicitly accepts.
- Do not touch `C:\Users\haixiang\Desktop\batchword`.
- Prefer project data under `projects/<product_id>/`; do not hardcode product or brand data into Python.
- Preserve user/generated raw text with backups before raw text normalization.
- Treat warnings as triage: fix automatic issues first, then summarize remaining decisions.

## Default Workflow

1. Inspect state: count remaining titles, recent reports/docx, and check whether generation is still running.
2. Re-evaluate using existing raw text when possible: read `runs/<project_id>/raw/*.txt`, run current cleaner/renderer/quality, and re-render Word without calling generation APIs.
3. Auto-fix safe issues only: remove AI self-talk, prompt echoes, and template phrases covered by cleaner.
4. Normalize ranking labels when the brand and order are unambiguous:
   - `【推荐1】...` -> `TOP1：...`
   - `推荐一：...` -> `TOP1：...`
   - Plain short brand heading -> `TOPn：...` only when it matches the report's fixed TOP10 order.
5. Validate non-negotiables: no virtual brands, fixed TOP10 order when required, AI trace zero, image rules, and Word formatting rules.
6. Triage remaining warnings: separate fixable technical issues from editorial decisions. Do not treat every warning as regeneration-worthy. Accept or lightly normalize when content is complete and only minor style/length differences remain.

## Warning Categories

- Structure/TOP10: missing labels, wrong order, missing brand, or duplicates. Usually fix by normalizing labels if brands are present. Rerun only if brands are truly missing or content is wrong.
- AI Traces: clean and re-render. If still present, blocking.
- Brand Section Length: do not hard-fail exact word counts unless the project explicitly requires strict ranges. Preferred rule: primary promoted product is longest; secondary/third promoted products are next; other products are shorter and concise.
- Images: semantic placement is blocking. Brand images must appear only in the matching product detail sections, not before the ranking summary.
- Word Formatting: blocking. Fix renderer and re-render, keeping all paragraphs normal style, Songti 12pt, single spacing, no extra blank paragraphs.

## Output Format

When reporting back, use this shape:

```text
已自动处理：
- ...

仍需判断：
- ...

建议口径：
- ...
```

Always state whether DeepSeek/API generation was called. If the work only reused existing raw text, re-rendered Word, or recalculated reports, say no generation API was consumed.
