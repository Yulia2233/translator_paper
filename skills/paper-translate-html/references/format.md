# 资料包约定

```text
out/
  index.html
  assets/                    # CSS、KaTeX、字体及许可证
  翻译清单.json
  完整性检查.json
  .work/<paper-id>/           # 逐页文本、块坐标、候选图注
  <paper-id>/
    paper.json               # 来源文件名、SHA256、真实页数
    中文逐句翻译.md
    中文阅读版.html
    原文提取.txt
    pages/page-001.png
    figures/figure-01.png
    figures/manifest.json
```

论文 ID 默认是 PDF 文件名的主干。不同来源同名时先取不冲突的 ID，再通过 `adopt --id ...` 注册；不能把两篇同名来源写进一个目录。

## 译文

```markdown
# 论文中文标题

原文标题、版本、日期及必要翻译说明。

## 原文第 1 页

完整译文，保留章节与编号。

![图 1](figures/figure-01.png)

**图 1：** 完整中文图注。图内英文另附中文对应。

## 原文第 2 页

继续逐句翻译。
```

每页代码围栏必须闭合；提示词示例中的章节标题保持在围栏内或使用更低级标题，避免误识别为真实页码标题。跨页句子可以按页续接，但不要省略内容。空白页仍保留页标题并写“本页为空白”；只有图片的页须翻译图注和图内文字。

## 裁图清单

输入为 JSON 数组。页码从 1 开始，`bbox` 为原始 PDF 中 `[x0, y0, x1, y1]`，单位为点。不要使用截图像素作为坐标；有旋转页面先检查 `blocks.json` 与原页。

```json
[
  {"kind": "figure", "id": "01", "page": 1, "bbox": [50, 80, 550, 360], "label": "图 1"},
  {"kind": "table", "id": "07", "page": 14, "bbox": [90, 60, 510, 530], "label": "表 7 连接示意"},
  {"kind": "equation", "id": "A1", "page": 19, "bbox": [80, 250, 510, 340], "label": "式 A.1"}
]
```

`kind` 可选 `figure`、`table`、`equation`；`id` 允许字母、数字、短横线及下划线，输出名是 `kind-id.png`。例如多页图可用 `12-part1`、`12-part2`。清单可分批提交，按输出文件名更新合并；移除错误裁图时同时更新最终 `figures/manifest.json`，不要保留未引用的旧图冒充完成数量。

## 只重建已有资料包

当原目录没有 `paper.json` 时，用以下命令注册真实页数和来源指纹，不覆盖译文或图片：

```text
python "<skill-dir>/scripts/paper_bundle.py" adopt --pdf "<original.pdf>" --paper "<existing-paper-dir>"
```

然后运行 `build` 和 `check`。未生成原页截图时，先对临时输出执行 `prepare` 再复制所需资源，或在确认来源一致后向同一目录执行 `prepare`。`prepare` 不覆盖译文或裁图；不同来源指纹会报错。

`--pdf`、`--paper`、`--out` 等参数均接受绝对路径。辅助脚本只处理提取、裁图、呈现及结构验证，正文翻译仍须由智能体完成。`check` 通过只代表这些结构条件通过，不代表逐句语义核对已完成。
