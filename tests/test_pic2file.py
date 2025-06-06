import time
from pdfdeal import Doc2X
from pdfdeal.file_tools import get_files
import logging

httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO)

def test_single_pic2file():
    client = Doc2X()
    results, errors, has_error = client.piclayout(
        pic_file="tests/image/sample.png",
        zip_path="./Output/test/single/",
    )
    print(results)
    print(errors)
    print(has_error)
    assert not has_error
    assert isinstance(results, list)  # 返回值应该是列表类型
    assert len(errors) == 1
    assert isinstance(errors[0], dict)
    assert "error" in errors[0]
    assert "path" in errors[0]

def test_multiple_pic2file():
    client = Doc2X()
    file_list, rename = get_files("tests/image", "img", "docx")
    results, errors, has_error = client.piclayout(
        pic_file=file_list,
        zip_path="./Output/test/multiple/",
    )
    assert isinstance(results, list)  # 返回值应该是列表类型
    assert len(errors) == 3
    assert isinstance(errors[0], dict)
    assert "error" in errors[0]
    assert "path" in errors[0]


def test_multiple_high_rpm():
    client = Doc2X()
    time.sleep(30)
    file_list = ["tests/image/sample.png" for _ in range(31)] #测试处理上限是否为30s/30 req
    results, errors, has_error = client.piclayout(
        pic_file=file_list,
        zip_path="./Output/test/highrpm/",
    )
    assert not has_error
    assert isinstance(results, list)  # 返回值应该是列表类型
    assert isinstance(errors[0], dict)
    assert "error" in errors[0]
    assert "path" in errors[0]


def test_piclayout():
    client = Doc2X()
    # Test single file layout analysis
    results, errors, has_error = client.piclayout("tests/image/sample.png")
    assert not has_error
    assert isinstance(results, list)  # 返回值应该是列表类型
    assert isinstance(errors[0], dict)
    assert "error" in errors[0]
    assert "path" in errors[0]
