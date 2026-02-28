from pdfdeal import Doc2X
from pdfdeal.Doc2X.Types import FormulaLevel, V2ParseModel
import os
import pytest
from typing import Optional


def _require_apikey() -> str:
    apikey = os.getenv("DOC2X_APIKEY")
    if not apikey:
        pytest.skip("DOC2X_APIKEY is required for integration tests")
    return apikey


def _build_client(apikey: Optional[str] = None) -> Doc2X:
    return Doc2X(apikey=apikey or _require_apikey(), debug=True, thread=1)


def _skip_if_doc2x_internal_error(flag, failed):
    if not flag or not failed:
        return
    first_error = failed[0].get("error", "") if isinstance(failed[0], dict) else ""
    if "internal_error" in first_error:
        pytest.skip(f"Doc2X service internal_error: {first_error}")


def _skip_if_transient_integration_error(flag, failed):
    if not flag or not failed:
        return
    error_texts = []
    for item in failed:
        if isinstance(item, dict):
            error_texts.append(str(item.get("error", "")))
        else:
            error_texts.append(str(item))
    combined = " | ".join(error_texts).lower()
    transient_markers = (
        "internal_error",
        "connecterror",
        "all connection attempts failed",
        "name or service not known",
        "nodename nor servname provided",
        "temporary failure in name resolution",
        "timed out",
    )
    if any(marker in combined for marker in transient_markers):
        pytest.skip(f"Transient integration error: {combined}")


def _count_pdf_files(path: str) -> int:
    return sum(
        1
        for root, _, files in os.walk(path)
        for file in files
        if file.lower().endswith(".pdf")
    )


def _assert_multiple_pdf2file_result(output_path, failed, expected_count: int) -> None:
    assert len(output_path) == expected_count
    assert len(failed) == expected_count
    for file_path, fail in zip(output_path, failed):
        if isinstance(file_path, str):
            if file_path == "":
                assert fail["error"] != ""
            else:
                assert os.path.isfile(file_path)
                assert fail["error"] == ""


def test_pdf2file_v3_model_example():
    client = _build_client()
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
    client = _build_client()

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


def test_pdf2file_v3_model_formula_level_enum_example():
    client = _build_client()
    output_path = "./Output/test/single/formula_level_enum"
    success, failed, flag = client.pdf2file(
        pdf_file="tests/pdf/formula_level.pdf",
        output_path=output_path,
        output_format="md",
        model=V2ParseModel.V3_2026,
        formula_level=FormulaLevel.INLINE_TO_TEXT,
    )

    print(success)
    print(failed)
    print(flag)
    _skip_if_doc2x_internal_error(flag, failed)
    assert flag is False
    assert isinstance(success[0], str)
    assert success[0] != ""
    assert os.path.isfile(success[0])
    assert failed[0]["error"] == ""


def test_pdf2file_v3_model_formula_level_all_to_text_example():
    client = _build_client()
    output_path = "./Output/test/single/formula_level_all_to_text"
    success, failed, flag = client.pdf2file(
        pdf_file="tests/pdf/formula_level.pdf",
        output_path=output_path,
        output_format="md",
        model=V2ParseModel.V3_2026,
        formula_level=FormulaLevel.ALL_TO_TEXT,
    )

    print(success)
    print(failed)
    print(flag)
    _skip_if_doc2x_internal_error(flag, failed)
    assert flag is False
    assert isinstance(success[0], str)
    assert success[0] != ""
    assert os.path.isfile(success[0])
    assert failed[0]["error"] == ""


def test_pdf2file_invalid_formula_level():
    client = _build_client(apikey="test_apikey")
    with pytest.raises(ValueError, match="formula_level must be one of 0, 1, 2"):
        client.pdf2file(
            pdf_file="tests/pdf/formula_level.pdf",
            output_path="./Output/test/single/pdf2file",
            output_format="md",
            formula_level=3,
        )


# 测试一个文件,output_format为json
def test_pdf2json():
    client = _build_client()
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
    client = _build_client()
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
    _skip_if_transient_integration_error(flag, failed)
    assert flag == False
    assert os.path.dirname(filepath[0][0]) == output_path
    assert os.path.dirname(filepath[0][1]) == output_path
    assert os.path.dirname(filepath[0][2]) == output_path

# 测试一个文件,output_format为md_dollar,tex,docx，同时保存到子文件夹下
def test_single_pdf2file_with_subdir():
    client = _build_client()
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
    _skip_if_transient_integration_error(flag, failed)
    assert flag == False
    assert os.path.dirname(filepath[0][0]) == os.path.join(output_path, "sample")
    assert os.path.dirname(filepath[0][1]) == os.path.join(output_path, "sample")
    assert os.path.dirname(filepath[0][2]) == os.path.join(output_path, "sample")

# 测试非法的输出格式
def test_error_input_pdf2file():
    client = _build_client()
    with pytest.raises(ValueError):
        client.pdf2file(
            pdf_file="tests/pdf/sample.pdf",
            output_path="./Output/test/single/pdf2file",
            output_names=["sample1.zip"],
            output_format="md_dallar",
        )

@pytest.mark.parametrize("save_subdir", [False, True], ids=["flat", "with_subdir"])
def test_multiple_pdf2file(save_subdir: bool):
    client = _build_client()
    expected_count = _count_pdf_files("tests/pdf")
    output_path, failed, flag = client.pdf2file(
        pdf_file="tests/pdf",
        output_path="./Output/test/multiple/pdf2file",
        output_format="docx",
        save_subdir=save_subdir,
    )
    print(output_path)
    print(failed)
    print(flag)
    assert flag
    _assert_multiple_pdf2file_result(output_path, failed, expected_count)

# 测试格式错误或者损坏的pdf文件
def test_all_fail_pdf2file():
    client = _build_client()
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
    client = _build_client()
    output_path, failed, flag = client.pdf2file(
        pdf_file="tests/pdf",
        output_path="./Output/",
        output_format="md",
        export_history="./Output/history/history.csv",
    )
