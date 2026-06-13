# product_writer Notes

Use only inside `C:\Users\haixiang\Projects\product_writer`.

## Important Files

- `pipeline.py`
- `product_writer/pipeline_core.py`
- `product_writer/cleaner.py`
- `product_writer/renderer.py`
- `product_writer/quality.py`
- `product_writer/prompt_loader.py`
- `product_writer/image_assets.py`
- `projects/<product_id>/project.yaml`
- `projects/<product_id>/brands.txt`
- `projects/<product_id>/titles.txt`
- `runs/<product_id>/raw/`
- `runs/<product_id>/reports/`
- `output/<product_id>/`

## Safe Re-render Pattern

1. Load project config.
2. Read existing raw text.
3. Run `clean_model_output`.
4. Select images.
5. Run `render_docx`.
6. Run `build_report` with the existing expected TOP10 list.
7. Write the report.

Back up raw text under `tmp/` before editing generated content.

## Commands

Set UTF-8 output when running scripts:

```powershell
$env:PYTHONIOENCODING='utf-8'
```

Run generation only when explicitly requested:

```powershell
C:\Users\haixiang\python-sdk\python3.13.2\python.exe pipeline.py --project tuonaifen --workers 3 --overwrite
```

For analysis and re-render scripts, use existing raw text and avoid external API calls.

## Boundaries

- Do not modify prompts unless asked.
- Do not delete Word files unless asked.
- Do not remove titles manually unless accepted or reports pass.
- Do not introduce product or brand content into Python.
- Do not touch `C:\Users\haixiang\Desktop\batchword`.
