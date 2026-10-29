# 论文翻译与 HTML 阅读

一个可复用的 Codex 技能：将本地学术 PDF 完整逐句翻译成中文，提取图件，并生成可离线阅读、可对照原页的 HTML 资料库。

## 功能

- 默认附四部分导读：解决的问题、相对已有工作的创新与效果、方法简介、实验汇总表；结论附原文证据位置。
- 支持 DOI／论文链接的全文查找；仅获取摘要时明确标记部分完成，不虚构正文与实验。

- 逐页翻译正文、附录、图注、表格、参考文献题名和提示词，保留公式、编号及数值。
- 截取独立图件和全部原页，提供页码导航、可折叠原页对照和图集。
- 使用本地 KaTeX 与字体显示公式，整个输出目录可复制后离线阅读。
- 检查页码覆盖、截图数量、代码围栏、本地资源链接及裁图来源。
- 支持单篇、多篇论文，以及从已有译文重建 HTML。

翻译由 Codex 按技能要求完成。辅助脚本负责 PDF 提取、裁图、呈现和结构检查，不会自行调用翻译 API，也不能代替逐句语义校对。

## 安装到 Codex

在 Codex 中输入：

```text
使用 $skill-installer 安装这个技能：
https://github.com/Yulia2233/translator_paper/tree/main/skills/paper-translate-html
```

也可使用 `gh` 克隆仓库，把 `skills/paper-translate-html` 整个文件夹复制到个人技能目录 `$CODEX_HOME/skills/`（未设置时通常为 `~/.codex/skills/`）。

辅助脚本需要 Python 3.11 或更新版本。克隆仓库后安装依赖：

```bash
gh repo clone Yulia2233/translator_paper
cd translator_paper
python -m pip install -r skills/paper-translate-html/requirements.txt
```

## 使用

在包含论文的工作区中，向 Codex 发出请求：

```text
使用 $paper-translate-html，将工作区论文完整逐句翻译成中文，
提取所有图片，并在 out/ 中生成离线 HTML 阅读版。
```

如需并行处理，可在请求中明确说明“创建子智能体，分篇翻译”。译文完成后，打开 `out/index.html` 阅读。

```text
out/
├── index.html
├── assets/                  # 离线样式、公式显示资源和字体
├── 翻译清单.json
├── 完整性检查.json
└── <论文ID>/
    ├── paper.json
    ├── 中文逐句翻译.md
    ├── 中文阅读版.html
    ├── 原文提取.txt
    ├── pages/               # 原文逐页截图
    └── figures/             # 独立图件与裁图清单
```

## 辅助脚本

从仓库根目录运行：

```bash
python skills/paper-translate-html/scripts/paper_bundle.py --help
python skills/paper-translate-html/scripts/paper_bundle.py prepare --input ./papers --out ./out
```

完成逐页译文并填写裁图清单后：

```bash
python skills/paper-translate-html/scripts/paper_bundle.py crop --pdf ./papers/example.pdf --paper ./out/example --manifest ./crops.json
python skills/paper-translate-html/scripts/paper_bundle.py build --out ./out --title "论文中文译文"
python skills/paper-translate-html/scripts/paper_bundle.py check --out ./out
```

已有资料包缺少 `paper.json` 时，可用 `adopt --pdf <原文.pdf> --paper <已有论文目录>` 注册来源。完整工作流见 [SKILL.md](skills/paper-translate-html/SKILL.md)，译文格式及裁图坐标约定见 [format.md](skills/paper-translate-html/references/format.md)。

## 校验范围

`check` 通过代表结构条件通过，不代表翻译语义完整。仍需对照原文检查全部段落、图内文字、长提示词、表格和公式，并实际打开 HTML 检查显示。原文自身矛盾的数值应保留，并单独注明。

仓库提供技能与工具，不附带用户论文、译文、原页截图或任务临时文件。KaTeX 资源的许可文件位于 [KATEX-LICENSE.txt](skills/paper-translate-html/assets/KATEX-LICENSE.txt)。

## 选中文本提问

阅读版提供“选文提问”面板。先通过本地服务打开资料库：

```bash
python skills/paper-translate-html/scripts/question_server.py --out ./out
```

打开终端输出的网址，再进入论文。选中正文或导读文字，点击“标注问题”，填写并提交，然后在 Codex 聊天中说“回答问题”。agent 读取 `out/问题标注.json` 并结合原文回答；写回答案后，阅读页点击“刷新问题与回答”即可显示。页面本身不调用模型或自动发送聊天。

双击离线 HTML 时可导出问题 JSON，将文件保存到工作区或发给 agent 后再说“回答问题”。问题草稿只存在浏览器时，agent 无法读取。服务关闭后可重启，问题文件仍保留。
