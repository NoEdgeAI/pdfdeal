<div align=center>
<h1 aligh="center">
<img src="https://github.com/Menghuan1918/pdfdeal/assets/122662527/837cfd7f-4546-4b44-a199-d826d78784fc" width="45">  pdfdeal
</h1>
<a href="https://github.com/Menghuan1918/pdfdeal/actions/workflows/python-test.yml">
  <img src="https://github.com/Menghuan1918/pdfdeal/actions/workflows/python-test.yml/badge.svg" 
  alt="Package Testing on Python 3.8-3.13 on Win/Linux/macOS">
</a>
<br>

<br>

[![Downloads](https://static.pepy.tech/badge/pdfdeal)](https://pepy.tech/project/pdfdeal) ![GitHub License](https://img.shields.io/github/license/Menghuan1918/pdfdeal) ![PyPI - Version](https://img.shields.io/pypi/v/pdfdeal) ![GitHub Repo stars](https://img.shields.io/github/stars/Menghuan1918/pdfdeal)

<br>

[📄 在线文档](https://menghuan1918.github.io/pdfdeal-docs/zh/guide/)

<br>

[ENGLISH](README.md) | 🗺️ 简体中文

</div>

更轻松简单地处理 PDF，利用 Doc2X 强大的文档转换能力，进行保留格式文件转换/RAG 增强。

<div align=center>
<img src="https://github.com/user-attachments/assets/3db3c682-84f1-4712-bd70-47422616f393" width="500px">
</div>

## 简介

### Doc2X 支持

[Doc2X](https://doc2x.com/)是一款新型的通用的文档 OCR 工具，可将图像或 pdf 文件转换为带有公式和文本格式的 Markdown/LaTeX 文本，并且效果在大部分场景下优于同类型工具。`pdfdeal`提供了抽象包装好的类以使用 Doc2X 发起请求。

### 对 PDF 进行处理

使用多种 OCR 或者 PDF 识别工具来识别图像并将其添加到原始文本中。可以设置输出格式使用 pdf 格式，这将确保识别后的文本在新 PDF 中的页数与原始文本相同。同时提供了多种实用的文件处理工具。

对 PDF 使用 Doc2X 转换并预处理后，与知识库应用程序（例如[graphrag](https://github.com/microsoft/graphrag)，[Dify](https://github.com/langgenius/dify)，[FastGPT](https://github.com/labring/FastGPT)），可以显著提升召回率。

### Markdown 文档处理功能

`pdfdeal` 也提供了一系列强大的工具来处理 Markdown 文档：

- **HTML 表格转换为 Markdown 格式**：可以将 HTML 格式的表格转换为 Markdown 格式，方便在 Markdown 文档中使用。
- **图片上传到远端储存服务**：支持将 Markdown 文档中的本地或在线图片上传到远端储存服务，确保图片的持久性和可访问性。
- **在线图片转换为本地图片**：可以将 Markdown 文档中的在线图片下载并转换为本地图片，便于离线使用。
- **文档拆分与分隔符添加**：支持按照标题拆分 Markdown 文档或在文档中添加分隔符，以便于文档的组织和管理。

详细功能介绍和使用方法请参见[文档链接](https://menghuan1918.github.io/pdfdeal-docs/zh/guide/Tools/)。

## 案例

### graphrag

参见[如何与 graphrag 结合使用](https://menghuan1918.github.io/pdfdeal-docs/zh/demo/graphrag.html)，[其不支持识别 pdf](https://github.com/microsoft/graphrag)，但你可以使用 CLI 工具`doc2x`将其转换为 txt 文档进行使用。

<div align=center>
<img src="https://github.com/user-attachments/assets/f9e8408b-9a4b-42b9-9aee-0d1229065a91" width="600px">
</div>

### FastGPT/Dify 或其他 RAG 应用

或者对于知识库应用，你也可以使用`pdfdeal`内置的多种对文档进行增强，例如图片上传到远端储存服务，按段落添加分割符等。请参见[与 RAG 应用集成](https://menghuan1918.github.io/pdfdeal-docs/zh/demo/RAG_pre.html)

<div align=center>
<img src="https://github.com/user-attachments/assets/034d3eb0-d77e-4f7d-a707-9be08a092a9a" width="450px">
<img src="https://github.com/user-attachments/assets/6078e585-7c06-485f-bcd3-9fac84eb7301" width="450px">
</div>

## 文档

详细请查看[在线文档](https://menghuan1918.github.io/pdfdeal-docs/zh/)。

你可以找到在线文档的开源[储存库 pdfdeal-docs](https://github.com/Menghuan1918/pdfdeal-docs)。

## 快速开始

### 安装

使用 pip 安装：

```bash
pip install --upgrade pdfdeal
```

如你还需要使用[文本预处理功能](https://menghuan1918.github.io/pdfdeal-docs/zh/guide/Tools/)：

```bash
pip install --upgrade "pdfdeal[rag]"
```

### 使用 Doc2X PDF API 处理指定文件夹中所有 PDF 文件

```python
from pdfdeal import Doc2X

client = Doc2X(apikey="Your API key",debug=True)
success, failed, flag = client.pdf2file(
    pdf_file="tests/pdf",
    output_path="./Output",
    output_format="docx",
    model="v3-2026",  # 可选，不填则使用服务端默认 v2
    formula_level=1,  # 可选：0（默认，推荐）不降级；1 仅降级行内公式（\(...\)、$...$）；2 降级所有公式（含 \[...\]、$$...$$）
)
print(success)
print(failed)
print(flag)
```

### 使用 Doc2X PDF API 处理指定的 PDF 文件并指定导出的文件名

```python
from pdfdeal import Doc2X

client = Doc2X(apikey="Your API key",debug=True)
success, failed, flag = client.pdf2file(
    pdf_file="tests/pdf/sample.pdf",
    output_path="./Output/test/single/pdf2file",
    output_names=["NAME.zip"],
    output_format="md_dollar",
)
print(success)
print(failed)
print(flag)
```

### V3 JSON 更新

当 `model="v3-2026"` 时：

- `output_format="json"` 现在会保存 Doc2X 原始 v3 JSON（`result.pages...`），不再保存旧的简化 `[{text, location}]` 结构。
- 即使 `output_format` 不包含 `json`（例如 `text`、`detailed`、`md`、`docx`），也会额外保存一份 sidecar `.json`。
- 如果 `output_format` 包含 `json`，sidecar JSON 的命名会跟随 `output_names` 里 `json` 这一槽位。
- 如果 `output_format` 不包含 `json`，sidecar JSON 的命名会跟随 `output_names` 里第一个非空名字。
- 如果没有传 `output_names`，sidecar JSON 会回退到原 PDF 文件名。
- 已不再使用过期的小文件直传。`oss_choose="always"` 和 `oss_choose="auto"` 都会走 preupload；`oss_choose="never"` / `oss_choose="none"` 会直接报错。

示例：

```python
from pdfdeal import Doc2X

client = Doc2X(apikey="Your API key", debug=True)
success, failed, flag = client.pdf2file(
    pdf_file="tests/pdf/sample.pdf",
    output_path="./Output/test/v3",
    output_format="text,json",
    output_names=[["plain.txt", "viz.data"]],
    model="v3-2026",
)
print(success)  # ["页面文本...", "./Output/test/v3/viz.json"]
print(failed)
print(flag)
```

### V3 figure/table 裁剪辅助脚本

在 [`scripts/`](/Users/cc/work/NoEdgeAI/pdfdeal/scripts) 下新增了两个辅助脚本：

- [`extract_v3_figures.py`](/Users/cc/work/NoEdgeAI/pdfdeal/scripts/extract_v3_figures.py)：基于 Doc2X v3 JSON 从 PDF 中裁剪 figure 图片
- [`extract_v3_tables.py`](/Users/cc/work/NoEdgeAI/pdfdeal/scripts/extract_v3_tables.py)：基于 Doc2X v3 JSON 从 PDF 中裁剪 table 图片

这两个脚本都会：

- 先校验 v3 JSON 是否符合裁剪规则
- 用 `fitz` 按指定 `dpi` 只渲染包含目标 block 的页面
- 将整页 PNG 保存到 `_pages/`
- 根据 v3 JSON 中的 block `bbox/xyxy` 和 page 坐标裁剪出目标区域
- 输出带裁剪元数据的 `manifest.json`

示例：

```bash
python scripts/extract_v3_figures.py \
  --pdf /path/to/input.pdf \
  --v3-json /path/to/input_v3.json \
  --dpi 200 \
  --output-dir ./Output/figures
```

```bash
python scripts/extract_v3_tables.py \
  --pdf /path/to/input.pdf \
  --v3-json /path/to/input_v3.json \
  --dpi 200 \
  --output-dir ./Output/tables
```

