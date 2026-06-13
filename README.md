# product_writer

`product_writer` 是一个独立的多产品 Word 文章生成器。第一阶段只处理：

标题 + 提示词 -> AI 文章 -> Word 排版 -> 加粗 -> 基础质检

它不依赖也不修改 `C:\Users\haixiang\Desktop\batchword`。

## 安装依赖

优先使用本机指定 Python：

```powershell
$env:PYTHONIOENCODING="utf-8"
C:\Users\haixiang\python-sdk\python3.13.2\python.exe -m pip install -r requirements.txt
```

## 配置 DeepSeek

项目会自动保留 `.env.example` 和 `.env`。正式生成前，在 `.env` 中填写：

```text
DEEPSEEK_API_KEY=你的真实key
```

没有 key 时可以运行 `--dry-run`，正式生成会给出清晰错误。

当前 API 调用已锁定使用 `deepseek-v4-pro`。

所有项目统一执行正文长度硬门槛：有效字数不得少于 3500 字，生成目标约 4000 字。
有效字数不含空格、标点和 Markdown 格式符号。生成结果不足时会自动重新生成；
连续达到最大重试次数仍不足时，不生成 Word，也不会从标题列表移除该标题。
启用默认的 `--skip-existing` 时也会检查已有 Word；达标才跳过，不足 3500 字会自动重新生成。

所有项目默认启用保守的中文自然化处理：

- 生成提示词统一限制 AI 套话、机械连接词、无来源归因和过度整齐句式
- 默认一次生成，不额外调用模型重写
- 生成后检查 AI 套话、3500 有效字、品牌白名单和本篇 TOP10
- 如需试验自动自然化，可在项目配置中手动设置 `humanizer.auto_rewrite: true`
- 默认不保存模型初稿，生成结果直接进入质检和 Word 输出

品牌白名单是最高命令：文章中的所有品牌名和产品名必须来自 `projects/<产品id>/brands.txt`。`brands.txt` 不能为空，`promoted_products` 中的主推产品也必须完整写入该文件。白名单数量不足时改写为选购方法、避坑维度或使用建议。

驼奶粉项目单独启用排行榜规则：`promoted_products` 中的三个主推品牌占据 TOP1-TOP3；TOP4-TOP10 每篇都从 `brands.txt` 剩余品牌中重新随机抽取并随机排序。本篇选定后保持本篇顺序，下一篇再次打乱。其他产品默认不启用该规则。

## 创建新产品

```powershell
C:\Users\haixiang\python-sdk\python3.13.2\python.exe pipeline.py init --project lingzhi --name 灵芝孢子粉
```

会创建：

```text
projects/lingzhi/
├── project.yaml
├── titles.txt
├── terms.txt
└── prompts/
    └── 01_提示词.txt
```

用户通常只需要改：

- `titles.txt`：每行一个标题
- `prompts/*.txt`：一套或多套提示词，支持 `{title}`、`{project_name}`
- `terms.txt`：每行一个需要额外加粗的词，可为空
- `brands.txt`：真实品牌/产品白名单，格式为 `品牌 | 产品名`，生成和质检只允许使用这里列出的品牌

## 标题样本库

标题系统采用“全局规则 + 产品资料”的结构：

- `title_rules.json`：所有榜单、测评、选购类文章共用的标题模板、长度、禁用词和相似度规则
- `projects/<产品id>/title_profile.json`：产品关键词、搜索问题、受众和选购角度
- `projects/<产品id>/title_samples.txt`：经过筛选的合格标题样本
- `projects/<产品id>/title_history.txt`：已经采用的标题，长期用于去重
- `projects/<产品id>/titles.txt`：等待生成文章的标题队列

先预览标题，不写入队列：

```powershell
python pipeline.py titles --project tuonaifen --count 10 --year 2026
```

确认后追加到文章标题队列，并同步记录到长期历史库：

```powershell
python pipeline.py titles --project tuonaifen --count 10 --year 2026 --append
```

标题生成不调用模型。系统会过滤禁用词、长度异常、历史重复及高度相似标题。

## 插图规则

插图功能由全局程序统一执行，具体产品通过 `project.yaml` 的 `features.images` 决定是否启用。
通用图片、品牌图片、允许使用的素材和语义关键词都放在对应的 `projects/<产品id>/` 中配置，禁止把具体图片或品牌规则写死进核心 Python。
启用插图后，通用图按标题和正文内容选择，不得固定给全部文章使用同一张图，也不得紧贴标题形成封面效果；品牌图只能紧跟对应产品的正式推荐标题。
提示词禁止模型输出图片链接、图片说明、配图建议和“此处插图”等占位文字。

## 运行命令

```powershell
python pipeline.py --project test_product
python pipeline.py --project test_product --limit 1
python pipeline.py --project test_product --dry-run
python pipeline.py --project test_product --skip-existing
python pipeline.py --project test_product --overwrite
python pipeline.py --project test_product --limit 10 --workers 3
```

默认跳过已生成的 docx，只有 `--overwrite` 才覆盖。

批量生成默认并行数为 3。需要顺序生成时使用 `--workers 1`。

## 输出位置

Word 文件：

```text
output/<产品id>/<标题>.docx
```

运行记录：

```text
runs/<产品id>/
├── humanized/<标题>.txt
├── prompts_used/<标题>.txt
├── reports/<标题>.json
└── state.json
```

## Word 排版硬规则

- 全文都是普通段落，不使用 Word Heading 样式
- 全文宋体 12pt
- 中文、英文、数字统一宋体
- 同时设置 `run.font.name`、`w:ascii`、`w:hAnsi`、`w:eastAsia`
- Normal 样式也设置宋体 12pt
- 段前 0 pt，段后 0 pt
- 禁止首行缩进
- 单倍行距
- 禁止居中
- 禁止标题大字号
- 标题只允许加粗，仍是普通段落
- 结构标题、推荐一/推荐二、TOP1/TOP2、首推/次推等行自动加粗
- `terms.txt` 中的词自动加粗，长词优先
- 加粗只改变 run 的 bold，不改变字体、字号、对齐、段距
- 提示词不得要求模型自行添加星号加粗，避免模型格式与程序规则冲突
- 不使用额外空段落制造间距
- 生成后自动检查字体、字号、普通段落、对齐、段距、行距、缩进和空段落

## 提示词总体规则

每个 `prompts/*.txt` 只写该产品的内容目标、文章结构、受众、语气和真实资料要求。
品牌白名单、自然表达、字数、插图、加粗和 Word 排版由程序自动追加为全局规则，不要在产品提示词中重复。

模型只负责输出干净的纯文本正文：每个自然段单独一行，结构标题和推荐行独立成行；
不输出 Markdown 标题、项目符号、表格、HTML、图片占位符、排版说明或规则复述。

## 后续预留

`project.yaml` 已预留 `promoted_products`，以后可以扩展 1-2 个主推产品或品牌，不需要把产品资料写死进 Python。
