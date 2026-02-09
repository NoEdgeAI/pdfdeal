from pdfdeal import Doc2X
from pdfdeal.Doc2X.Types import V2ParseModel
import os
import pytest


def _require_apikey() -> str:
    apikey = os.getenv("DOC2X_APIKEY")
    if not apikey:
        pytest.skip("DOC2X_APIKEY is required for integration tests")
    return apikey


def test_pdf2file_v3_model_example():
    client = Doc2X(apikey=_require_apikey(), debug=True, thread=1)
    success, failed, flag = client.pdf2file(
        pdf_file="tests/pdf/sample.pdf",
        output_format="text",
        model=V2ParseModel.V3_2026,
    )

    print(success)
    print(failed)
    print(flag)
    assert flag is False
    assert isinstance(success[0], str)
    assert success[0] != ""
    assert failed[0]["error"] == ""


def test_pdf2file_mixed_v3_and_v2_models():
    client = Doc2X(apikey=_require_apikey(), debug=True, thread=1)

    success_v3, failed_v3, flag_v3 = client.pdf2file(
        pdf_file="tests/pdf/sample.pdf",
        output_format="text",
        model=V2ParseModel.V3_2026,
    )
    success_v2, failed_v2, flag_v2 = client.pdf2file(
        pdf_file="tests/pdf/sample.pdf",
        output_format="text",
    )

    print(success_v3)
    print(failed_v3)
    print(flag_v3)
    print(success_v2)
    print(failed_v2)
    print(flag_v2)
    assert flag_v3 is False
    assert flag_v2 is False
    assert isinstance(success_v3[0], str)
    assert isinstance(success_v2[0], str)
    assert success_v3[0] != ""
    assert success_v2[0] != ""
    assert failed_v3[0]["error"] == ""
    assert failed_v2[0]["error"] == ""


# 测试一个文件,output_format为json
def test_pdf2json():
    client = Doc2X(debug=True, thread=1)
    output_path = "./Output/test/single/pdf2file"
    filepath, failed, flag = client.pdf2file(
        pdf_file="tests/pdf",
        output_path=output_path,
        output_format="json",
        save_subdir=False,
    )
    print(filepath)
    print(failed)
    print(flag)
    assert flag

# 测试一个文件,output_format为md_dollar,tex,docx
def test_single_pdf2file():
    client = Doc2X(debug=True, thread=1)
    output_path = "./Output/test/single/pdf2file"
    filepath, failed, flag = client.pdf2file(
        pdf_file="tests/pdf/sample.pdf",
        output_path=output_path,
        output_format="md_dollar,tex,docx",
        save_subdir=False,
    )
    print(filepath)
    print(failed)
    print(flag)
    assert flag == False
    assert os.path.dirname(filepath[0][0]) == output_path
    assert os.path.dirname(filepath[0][1]) == output_path
    assert os.path.dirname(filepath[0][2]) == output_path

# 测试一个文件,output_format为md_dollar,tex,docx，同时保存到子文件夹下
def test_single_pdf2file_with_subdir():
    client = Doc2X(debug=True, thread=1)
    output_path = "./Output/test/single/pdf2file"
    filepath, failed, flag = client.pdf2file(
        pdf_file="tests/pdf/sample.pdf",
        output_path=output_path,
        output_format="md_dollar,tex,docx",
        save_subdir=True,
    )
    print(filepath)
    print(failed)
    print(flag)
    assert flag == False
    assert os.path.dirname(filepath[0][0]) == os.path.join(output_path, "sample")
    assert os.path.dirname(filepath[0][1]) == os.path.join(output_path, "sample")
    assert os.path.dirname(filepath[0][2]) == os.path.join(output_path, "sample")

# 测试非法的输出格式
def test_error_input_pdf2file():
    client = Doc2X(debug=True, thread=1)
    with pytest.raises(ValueError):
        client.pdf2file(
            pdf_file="tests/pdf/sample.pdf",
            output_path="./Output/test/single/pdf2file",
            output_names=["sample1.zip"],
            output_format="md_dallar",
        )

# 测试一个文件夹下的多个文件，output_format
def test_multiple_pdf2file():
    client = Doc2X(debug=True, thread=1)
    output_path, failed, flag = client.pdf2file(
        pdf_file="tests/pdf",
        output_path="./Output/test/multiple/pdf2file",
        output_format="docx",
        save_subdir=False,
    )
    print(output_path)
    print(failed)
    print(flag)
    assert flag
    assert len(output_path) == 3
    for idx, file_path in enumerate(output_path):
        if isinstance(file_path, str):
            if file_path == '':
               assert failed[idx]['error'] != ""
            else:
                assert os.path.isfile(file_path)
                assert failed[idx]['error'] == ""

# 测试一个文件夹下的多个pdf文件转化（包含其子文件夹下的pdf文件）
def test_multiple_pdf2file_with_subdir():
    client = Doc2X(debug=True, thread=1)
    output_path, failed, flag = client.pdf2file(
        pdf_file="tests/pdf",
        output_path="./Output/test/multiple/pdf2file",
        output_format="docx",
        save_subdir=True,
    )
    print(output_path)
    print(failed)
    print(flag)
    assert flag
    assert len(output_path) == 3
    for idx, file_path in enumerate(output_path):
        if isinstance(file_path, str):
            if file_path == '':
                assert failed[idx]['error'] != ""
            else:
                assert os.path.isfile(file_path)
                assert failed[idx]['error'] == ""

# 测试格式错误或者损坏的pdf文件
def test_all_fail_pdf2file():
    client = Doc2X(debug=True, thread=1)
    output_path, failed, flag = client.pdf2file(
        pdf_file="tests/pdf/sample_bad.pdf",
        output_path="./Output/test/allfail/pdf2file",
        output_format="md",
    )
    print(output_path)
    print(failed)
    print(flag)
    assert flag


def test_export_history():
    client = Doc2X(debug=True, thread=1)
    output_path, failed, flag = client.pdf2file(
        pdf_file="tests/pdf",
        output_path="./Output/",
        output_format="md",
        export_history="./Output/history/history.csv",
    )
