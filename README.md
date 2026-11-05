# riceAI Research Workflow

**Zotero 管文献，Obsidian 存知识，Codex 做精读和问答。**

一套开源 Codex Skill，把论文整理成带原文位置的精读笔记，再基于自己的文献做检索与比较。支持 Zotero 本地只读 API、Zotero JSON 导出和直接导入 PDF。MIT · Python 3.10+ · 本地 Markdown。

## 能做什么

- 按关键词或分类读取 Zotero 题录，显式选择要导入的 PDF 附件。
- 使用统一模板整理研究问题、方法、实验、结果、局限和课题关联。
- 为关键结论记录物理 PDF 页码、章节/图表号，分清事实、解释和推断。
- 将笔记写入 Obsidian vault，保留人工笔记与已有模板。
- 搜索提取文本和笔记，再由 Codex 回原文核对、比较研究方法和整理主题。
- 通过稳定 ID 和文件哈希检测来源变化，避免同标题混淆和覆盖 PDF。

**精读与回答由 Codex 完成。** Python 脚本负责导入、文本提取、字面检索和文件完整性检查；没有“脚本自动读懂论文”或自动验证科学结论的承诺。

## 安装 Skill

下载或克隆本仓库，将 `skills/riceai-research-workflow` 文件夹放进你的 Codex Skills 目录。以已配置扫描 `~/.agents/skills` 的环境为例：

```bash
git clone https://github.com/RiceAI88/riceai-research-workflow.git
mkdir -p ~/.agents/skills
cp -R riceai-research-workflow/skills/riceai-research-workflow ~/.agents/skills/
```

刷新技能列表或开启新会话，显式调用 `$riceai-research-workflow`。已有同名 Skill 时先比较，不直接覆盖。不同宿主的技能目录以其当前设置为准。

## 最快跑通：先用 1–3 篇本地 PDF

在仓库根目录运行，将示例路径换成真实绝对路径：

```bash
python3 skills/riceai-research-workflow/scripts/paperflow.py doctor
python3 skills/riceai-research-workflow/scripts/paperflow.py init --vault /absolute/path/ResearchVault
python3 skills/riceai-research-workflow/scripts/paperflow.py add-pdf --vault /absolute/path/ResearchVault --file /absolute/path/paper.pdf
```

记下 `add-pdf` 返回的 ID，再提取文本。可选依赖二选一：已有 `pdftotext`，或 Python 环境安装 `pypdf`。已装 uv 的用户可以隔离运行：

```bash
uv run --with pypdf python skills/riceai-research-workflow/scripts/paperflow.py extract --vault /absolute/path/ResearchVault --id PAPER_ID
```

在 Obsidian 中打开 `ResearchVault` 作为 vault，在 Codex 中打开同一个目录，然后说：

> 使用 $riceai-research-workflow，精读这个库里的论文，关注我的研究问题：……。按统一模板写笔记，关键结论标出原文物理 PDF 页码与图表位置，保留来源哈希，不覆盖人工笔记，最后更新主题索引。

再问：

> 只依据这个库，比较这些论文使用的方法和实验条件。每条判断给出论文 ID、PDF 页码和笔记链接，库内证据不足就明确说明。

## 连接 Zotero

需要安装并启动支持本地 API 的 Zotero，启用“允许本机其他应用访问”相关设置。无需 Zotero 云端 API key。元数据导入与 PDF 导入是两个显式动作；不会读写 Zotero 的 SQLite 数据库。

```bash
python3 skills/riceai-research-workflow/scripts/paperflow.py collections --vault /absolute/path/ResearchVault
python3 skills/riceai-research-workflow/scripts/paperflow.py sync-zotero --vault /absolute/path/ResearchVault --query transformer --limit 3
```

附件导入、离线 JSON、分页及完整提示词见 [工作流文档](skills/riceai-research-workflow/references/workflow.md)。笔记字段见 [精读模板](skills/riceai-research-workflow/assets/paper-note.md)。

## 数据与边界

- PDF、题录、提取文本和笔记写在自己的 vault；不放到这个开源仓库、不自动上传。
- 会话中的资料仍遵循当前 Codex 服务的数据处理方式，“本地文件”不表示模型离线运行。
- 脚本不调用外部模型 API；提取全文的依赖首次安装可能需要网络。
- Zotero 只读；不导入新题录、不改原库、不默认扫描全库。
- 搜索为字面关键词检索，尚无向量索引、双向同步、扫描件 OCR 或后台自动运行。
- 提取不到的图表/公式需回原 PDF 查看；检索未命中不等于论文不存在；完整性检查不等于结论验证。

## 验证

```bash
uv run --with pypdf python -m unittest discover -s tests -v
python3 skills/riceai-research-workflow/scripts/paperflow.py check --vault /absolute/path/ResearchVault
```

自动测试覆盖文件保护、同标题不同论文、分页、附件范围、页码检索以及 PDF 文本提取。真实 Zotero 桌面连接与真实论文精读需要在自己的环境验证，不能用这些测试替代。

## License

[MIT](LICENSE)。独立实现；不包含参考视频作者的私有 Skill 源码，也不捆绑 Zotero、Obsidian 或 Codex。
