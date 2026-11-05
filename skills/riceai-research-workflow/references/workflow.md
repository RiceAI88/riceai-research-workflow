# 本地命令与搭建

`<skill>` 是本SKILL.md所在目录；`<vault>` 使用绝对路径。Python 3.10+。脚本本身除PDF提取外只用标准库；不调用付费模型API。精读使用当前Codex会话，模型使用成本由用户当前产品/订阅决定。

## 1. 准备目录

```bash
python3 <skill>/scripts/paperflow.py doctor
python3 <skill>/scripts/paperflow.py init --vault /absolute/path/ResearchVault
```

在Obsidian中把同一个ResearchVault文件夹作为vault打开；在Codex中打开同目录。可先不用Obsidian应用，写出的md文件之后也能打开。结构：

```text
ResearchVault/
  papers/                 # 复制的PDF，原文件不动
  notes/                  # Codex按统一模板写的笔记
  topics/                 # Codex维护的主题比较和索引
  templates/paper-note.md
  .paperflow/library.json # 本地元数据、哈希和路径，包含私人资料
  .paperflow/text/         # 带物理PDF页码的提取文本
```

首次只初始化目录与元数据，不自动处理论文、不覆盖已有文件。

## 2A. Zotero本地API（只读）

需要用户自己安装并打开支持本地API的Zotero。设置 → 高级 → 其他中启用本机应用访问API（界面名称以实际版本为准）。没有连接时优先用2B；脚本不改Zotero配置。

```bash
python3 <skill>/scripts/paperflow.py collections --vault <vault>
python3 <skill>/scripts/paperflow.py sync-zotero --vault <vault> --collection ABCD1234 --limit 3
# 或按关键词搜索；仅导入元数据
python3 <skill>/scripts/paperflow.py sync-zotero --vault <vault> --query transformer --limit 3
python3 <skill>/scripts/paperflow.py children --vault <vault> --id z0-ABCD1234
python3 <skill>/scripts/paperflow.py import-attachment --vault <vault> --id z0-ABCD1234 --attachment PDFKEY12
```

实际paper ID以命令输出为准，前缀中的library ID来自Zotero响应，并不总是0。sync导入题录和摘要，不自动导入PDF；显式import-attachment会读取所选论文PDF附件路径并复制入vault。群组附件暂不自动导入，用add-pdf手动关联即可。分页按limit拉取；元数据更新保留PDF注册信息，不更新旧笔记分析。

连接是 `http://127.0.0.1:23119/api/users/0`；只用本机GET、不使用API key、不通过环境代理。附件只允许所选父条目的本地PDF，外部链接不下载。

## 2B. 导出元数据或直接使用PDF

在Zotero导出所选分类为Zotero JSON（不是CSL JSON）：

```bash
python3 <skill>/scripts/paperflow.py import-json --vault <vault> --file /absolute/path/export.json
python3 <skill>/scripts/paperflow.py add-pdf --vault <vault> --id z0-ABCD1234 --file /absolute/path/paper.pdf
# 无Zotero：省略id，以PDF内容哈希建立稳定ID
python3 <skill>/scripts/paperflow.py add-pdf --vault <vault> --file /absolute/path/paper.pdf --title '论文原始标题'
```

导出JSON中的附件路径不自动跟随复制，避免误读用户未选择的文件。没有Zotero key的题录使用元数据哈希ID；同标题不当作同一篇。add-pdf同ID不同内容会拒绝覆盖；新增版本用新的id。

## 3. 提取全文、精读和写笔记

```bash
# 有pypdf的Python环境
python3 <skill>/scripts/paperflow.py extract --vault <vault> --id PAPER_ID
# 或复用uv的隔离依赖（需事先安装uv；首次需网络下载pypdf）
uv run --with pypdf python <skill>/scripts/paperflow.py extract --vault <vault> --id PAPER_ID
```

也支持PATH里的pdftotext。不处理扫描件OCR；空页会列出，页中图像/公式仍需看原PDF。页码从1开始对应PDF物理页，不是期刊印刷页。提取文本不是笔记，也不代表论文已精读。

给Codex：

> 使用 $riceai-research-workflow。只处理当前vault中这3篇论文，关注我的研究问题：……。阅读全文并核对关键图表，按templates/paper-note.md写到notes/<paper-id>.md，保存paper_id和source_sha256，每条关键结论标PDF页码与章节或图表。区分事实、作者解释和推断。缺失的材料注明，不补写；最后更新topics/index.md。

## 4. 检索与来源核对

```bash
python3 <skill>/scripts/paperflow.py search --vault <vault> --query 'knowledge distillation' --top 10
python3 <skill>/scripts/paperflow.py search --vault <vault> --query '知识蒸馏' --top 10
python3 <skill>/scripts/paperflow.py check --vault <vault>
```

search是字面关键词排序，返回文件、章节与摘录，不自动回答，不是向量索引。Codex要读取候选上下文并回原PDF核对。notes文件名按paper ID；另有人工笔记时由Codex读索引定位，不会自动被此脚本收录。check只验证存在性、哈希与笔记来源哈希，不能保证文献真实性、引用语义或结论正确。

给Codex：

> 只依据这个库比较……。先列出检索关键词与实际读取来源，再比较方法、实验条件和结果；每条判断标论文ID、原文PDF页码和笔记链接。证据不足明确说不足。把比较保存到topics，不改原笔记。

## 官方接口与数据存储说明

- Zotero本地API：https://www.zotero.org/support/dev/web_api/v3/basics#local_api
- Obsidian的vault是本地Markdown目录：https://help.obsidian.md/Files+and+folders/How+Obsidian+stores+data
- 本库不提供双向同步、Zotero题录写回、自动跨设备同步、向量数据库或无人值守批量科研。
