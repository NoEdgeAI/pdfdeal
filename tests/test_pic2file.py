from pdfdeal import Doc2X
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


def test_single_pic2file():
    client = _build_client()
    success, failed, flag = client.piclayout(
        pic_file="tests/image/sample.png",
        output_path="./Output/test/single/pic2file",
    )
    print(success)
    print(failed)
    print(flag)
    assert flag is False
    assert isinstance(success, list)
    assert len(success) == 1
    assert isinstance(success[0], list)
    assert len(success[0]) == 1
    assert isinstance(success[0][0], list)
    assert len(success[0][0]) > 0
    assert isinstance(success[0][0][0], dict)
    assert "md" in success[0][0][0]
    assert "zip_path" in success[0][0][0]
    assert "path" in success[0][0][0]
    assert failed[0]["error"] == ""


def test_multiple_pic2file():
    client = _build_client()
    success, failed, flag = client.piclayout(
        pic_file="tests/image",
        output_path="./Output/test/multiple/pic2file",
    )
    print(success)
    print(failed)
    print(flag)
    assert flag
    assert isinstance(success, list)
    assert len(success) == 3
    assert len(failed) == 3
    for idx, result in enumerate(success):
        if not result:
            assert failed[idx]["error"] != ""
            assert failed[idx]["path"] != ""
        else:
            assert failed[idx]["error"] == ""


def test_multiple_high_rpm():
    client = _build_client()
    file_list = ["tests/image/sample.png" for _ in range(30)]
    success, failed, flag = client.piclayout(
        pic_file=file_list,
        output_path="./Output/test/highrpm/pic2file",
    )
    print(success)
    print(failed)
    print(flag)
    assert flag is False
    assert isinstance(success, list)
    assert len(success) == 30
    assert all(isinstance(item, list) and item for item in success)
    assert all(item["error"] == "" for item in failed)


def test_piclayout():
    client = _build_client()
    success, failed, flag = client.piclayout(
        pic_file="tests/image/sample.png",
    )
    print(success)
    print(failed)
    print(flag)
    assert flag is False
    assert isinstance(success, list)
    assert len(success) == 1
    assert isinstance(success[0], list)
    assert len(success[0]) == 1
    assert isinstance(success[0][0], list)
    assert len(success[0][0]) > 0
    assert isinstance(success[0][0][0], dict)
    assert "md" in success[0][0][0]
    assert "zip_path" in success[0][0][0]
    assert "path" in success[0][0][0]
    assert failed[0]["error"] == ""
