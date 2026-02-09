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

[📄Documentation](https://menghuan1918.github.io/pdfdeal-docs/guide/)

<br>

🗺️ ENGLISH | [简体中文](README_CN.md)

</div>

Handle PDF more easily and simply, utilizing Doc2X's powerful document conversion capabilities for retained format file conversion/RAG enhancement.

<div align=center>
<img src="https://github.com/user-attachments/assets/3db3c682-84f1-4712-bd70-47422616f393" width="500px">
</div>

## Introduction

### Doc2X Support

[Doc2X](https://doc2x.com/) is a new universal document OCR tool that can convert images or PDF files into Markdown/LaTeX text with formulas and text formatting. It performs better than similar tools in most scenarios. `pdfdeal` provides abstract packaged classes to use Doc2X for requests.

### Processing PDFs

Use various OCR or PDF recognition tools to identify images and add them to the original text. You can set the output format to use PDF, which will ensure that the recognized text retains the same page numbers as the original in the new PDF. It also offers various practical file processing tools.

After conversion and pre-processing of PDF using Doc2X, you can achieve better recognition rates when used with knowledge base applications such as [graphrag](https://github.com/microsoft/graphrag), [Dify](https://github.com/langgenius/dify), and [FastGPT](https://github.com/labring/FastGPT).

### Markdown Document Processing Features

`pdfdeal` also provides a series of powerful tools to handle Markdown documents:

- **Convert HTML tables to Markdown format**: Allows conversion of HTML formatted tables to Markdown format for easy use in Markdown documents.
- **Upload images to remote storage services**: Supports uploading local or online images in Markdown documents to remote storage services to ensure image persistence and accessibility.
- **Convert online images to local images**: Allows downloading and converting online images in Markdown documents to local images for offline use.
- **Document splitting and separator addition**: Supports splitting Markdown documents by headings or adding separators within documents for better organization and management.

For detailed feature introduction and usage, please refer to the [documentation link](https://menghuan1918.github.io/pdfdeal-docs/guide/Tools/).


## Cases

### graphrag

See [how to use it with graphrag](https://menghuan1918.github.io/pdfdeal-docs/demo/graphrag.html), [its not supported to recognize pdf](https://github.com/microsoft/graphrag), but you can use the CLI tool `doc2x` to convert it to a txt document for use.

<div align=center>
<img src="https://github.com/user-attachments/assets/f9e8408b-9a4b-42b9-9aee-0d1229065a91" width="600px">
</div>

### Fastgpt/Dify or other RAG system

Or for knowledge base applications, you can use `pdfdeal`'s built-in variety of enhancements to documents, such as uploading images to remote storage services, adding breaks by paragraph, etc. See [Integration with RAG applications](https://menghuan1918.github.io/pdfdeal-docs/demo/RAG_pre.html).

<div align=center>
<img src="https://github.com/user-attachments/assets/034d3eb0-d77e-4f7d-a707-9be08a092a9a" width="450px">
<img src="https://github.com/user-attachments/assets/6078e585-7c06-485f-bcd3-9fac84eb7301" width="450px">
</div>

## Documentation

For details, please refer to the [documentation](https://menghuan1918.github.io/pdfdeal-docs/)

Or check out the [documentation repository pdfdeal-docs](https://github.com/Menghuan1918/pdfdeal-docs).

## Quick Start

For details, please refer to the [documentation](https://menghuan1918.github.io/pdfdeal-docs/)

### Installation

Install using pip:

```bash
pip install --upgrade pdfdeal
```

If you need [document processing tools](https://menghuan1918.github.io/pdfdeal-docs/guide/Tools/):

```bash
pip install --upgrade "pdfdeal[rag]"
```

### Use the Doc2X PDF API to process all PDF files in a specified folder

```python
from pdfdeal import Doc2X

client = Doc2X(apikey="Your API key",debug=True)
success, failed, flag = client.pdf2file(
    pdf_file="tests/pdf",
    output_path="./Output",
    output_format="docx",
    model="v3-2026",  # optional, default is server-side v2
)
print(success)
print(failed)
print(flag)
```

### Use the Doc2X PDF API to process the specified PDF file and specify the name of the exported file

```python
from pdfdeal import Doc2X

client = Doc2X(apikey="Your API key",debug=True)
success, failed, flag = client.pdf2file(
    pdf_file="tests/pdf/sample.pdf",
    output_path="./Output/test/single/pdf2file",
    output_names=["sample1.zip"],
    output_format="md_dollar",
)
print(success)
print(failed)
print(flag)
```

See the online documentation for details.
