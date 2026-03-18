import httpx
import json
import os
import re
from typing import Tuple, Literal
from .Exception import RateLimit, FileError, RequestError, async_retry
import logging
import warnings

Base_URL = "https://api.doc2x.noedgeai.com/api"

warnings.warn(
    "V1 API is deprecated and will be removed in a future version. Use V2 API instead.",
    DeprecationWarning,
    stacklevel=2,
)


@async_retry()
async def refresh_key(key: str) -> str:
    """Get the real key by the personal key

    Args:
        key (str): The personal key

    Raises:
        Exception: Failed to verify key

    Returns:
        str: The real key
    """
    url = f"{Base_URL}/token/refresh"
    timeout = httpx.Timeout(30)
    async with httpx.AsyncClient(timeout=timeout) as client:
        get_res = await client.post(url, headers={"Authorization": "Bearer " + key})
    if get_res.status_code == 200:
        try:
            return json.loads(get_res.content.decode("utf-8"))["data"]["token"]
        except Exception as e:
            raise Exception(f"Failed to verify key: {e}")
    else:
        raise Exception(f"Failed to verify key: {get_res.status_code}:{get_res.text}")


async def check_folder(path: str) -> bool:
    """Make sure the path is a folder

    Args:
        path (str): The path to check

    Raises:
        Exception: Input path already exists as a file
        Exception: Input path is not a directory
        Exception: Create folder error

    Returns:
        bool: Whether the path is a folder
    """
    try:
        os.makedirs(path, exist_ok=True)
        assert os.path.isdir(path)
    except FileExistsError:
        raise Exception("Input path already exists as a file!")
    except NotADirectoryError:
        raise Exception("Input path is not a directory!")
    except Exception as e:
        raise Exception(f"Create folder error! {e}")
    return True


@async_retry()
async def uuid2file(
        apikey: str,
        uuid: str,
        output_format: Literal["md", "md_dollar", "latex", "docx"],
        output_path: str = "./Output",
) -> str:
    """Get the file by the uuid

    Args:
        apikey (str): The key
        uuid (str): The uuid of the file
        output_format (Literal[&quot;md&quot;, &quot;md_dollar&quot;, &quot;latex&quot;, &quot;docx&quot;]): The output format
        output_path (str, optional): The output path. Defaults to "./Output".

    Raises:
        Exception: Input path is not a directory
        RateLimit: Rate limit exceeded
        Exception: Download file error

    Returns:
        str: The path of the file
    """
    await check_folder(output_path)
    url = f"{Base_URL}/export?request_id={uuid}&to={output_format}"
    download_format = output_format if output_format == "docx" else "zip"
    timeout = httpx.Timeout(120)
    async with httpx.AsyncClient(timeout=timeout) as client:
        get_res = await client.get(url, headers={"Authorization": "Bearer " + apikey})
    if get_res.status_code == 200:
        output_path = os.path.join(output_path, uuid + "." + download_format)
        try:
            with open(output_path, "wb") as f:
                f.write(get_res.content)
            return output_path
        except Exception as e:
            raise Exception(f"Dowload file error! {e}")
    else:
        if get_res.status_code == 429:
            raise RateLimit()
        elif get_res.status_code == 400:
            raise RequestError(get_res.text)
        else:
            raise Exception(
                f"Download file error! {get_res.status_code}:{get_res.text}"
            )


@async_retry()
async def get_limit(apikey: str) -> int:
    """Get the limit of the key

    Args:
        apikey (str): The key

    Raises:
        RuntimeError: The key is invalid

    Returns:
        int: The limit of the key
    """
    if apikey.startswith("sk-"):
        url = f"{Base_URL}/v1/limit"
    else:
        url = f"{Base_URL}/platform/limit"
    async with httpx.AsyncClient() as client:
        get_res = await client.get(url, headers={"Authorization": "Bearer " + apikey})
    if get_res.status_code == 200:
        try:
            return int(get_res.json()["data"]["remain"])
        except Exception as e:
            raise RuntimeError(
                f"Get limit error with {e}! {get_res.status_code}:{get_res.text}"
            )
    else:
        raise RuntimeError(f"Get limit error! {get_res.status_code}:{get_res.text}")


@async_retry()
async def upload_pdf(
        apikey: str,
        pdffile: str,
        ocr: bool = True,
        translate: bool = False,
        language: str = "zh",
        model: str = "deepseek",
) -> str:
    """Upload pdf file to server and return the uuid of the file

    Args:
        apikey (str): The key
        pdffile (str): The pdf file path
        ocr (bool, optional): Do OCR or not. Defaults to True.
        translate (bool, optional): Do translate or not. Defaults to False.
        language (str, optional): The language of the file. Defaults to "zh", only valid when translate is True.
        model (str, optional): The model of the file. Defaults to "deepseek", only valid when translate is True.

    Raises:
        FileError: Input file size is too large
        FileError: Open file error
        RateLimit: Rate limit exceeded
        Exception: Upload file error

    Returns:
        str: The uuid of the file
    """
    if apikey.startswith("sk-"):
        url = f"{Base_URL}/v1/async/pdf"
    else:
        url = f"{Base_URL}/platform/async/pdf"
    try:
        file = {"file": open(pdffile, "rb")}
        if os.path.getsize(pdffile) > 100 * 1024 * 1024:
            raise FileError("PDF dile size should be less than 100MB!")
    except Exception as e:
        raise FileError(f"Open file error! {e}")
    ocr = 1 if ocr else 0
    translate = 2 if translate else 1
    timeout = httpx.Timeout(120)
    if translate == 1:
        async with httpx.AsyncClient(timeout=timeout) as client:
            post_res = await client.post(
                url,
                headers={"Authorization": "Bearer " + apikey},
                files=file,
                data={"ocr": ocr, "parse_to": translate},
            )
    else:
        async with httpx.AsyncClient(timeout=timeout) as client:
            post_res = await client.post(
                url,
                headers={"Authorization": "Bearer " + apikey},
                files=file,
                data={
                    "ocr": ocr,
                    "parse_to": translate,
                    "lang": language,
                    "model": model,
                },
            )
    if post_res.status_code == 200:
        try:
            if (
                    "parse_task_limit_exceeded"
                    == json.loads(post_res.content.decode("utf-8"))["code"]
            ):
                raise RateLimit()
            else:
                return json.loads(post_res.content.decode("utf-8"))["data"]["uuid"]
        except RateLimit:
            raise RateLimit()
        except Exception as e:
            raise Exception(
                f"Upload file error with {e} ! {post_res.status_code}:{post_res.text}"
            )
    elif post_res.status_code == 429:
        raise RateLimit()
    elif post_res.status_code == 400:
        raise RequestError(post_res.text)
    else:
        raise Exception(f"Upload file error! {post_res.status_code}:{post_res.text}")


@async_retry()
async def upload_img(
        apikey: str,
        imgfile: str,
        formula: bool = False,
        img_correction: bool = False,
) -> str:
    """Upload image file to server and return the uuid of the file

    Args:
        apikey (str): The key
        imgfile (str): The image file path
        formula (bool, optional): Only formula or not. Defaults to False.
        img_correction (bool, optional): Do img correction or not. Defaults to False.

    Raises:
        FileError: Image file size is too large
        FileError: Open file error
        RateLimit: Rate limit exceeded
        Exception: Upload file error

    Returns:
        str: The uuid of the file
    """
    if apikey.startswith("sk-"):
        url = f"{Base_URL}/v1/async/img"
    else:
        url = f"{Base_URL}/platform/async/img"
    formula = 1 if formula else 0
    img_correction = 1 if img_correction else 0
    try:
        file = {"file": open(imgfile, "rb")}
        if os.path.getsize(imgfile) > 10 * 1024 * 1024:
            raise FileError("Image file size should be less than 10MB!")
    except Exception as e:
        raise FileError(f"Open file error! {e}")
    timeout = httpx.Timeout(120)
    async with httpx.AsyncClient(timeout=timeout) as client:
        post_res = await client.post(
            url,
            headers={"Authorization": "Bearer " + apikey},
            files=file,
            data={"equation": formula, "img_correction": img_correction},
        )
    if post_res.status_code == 200:
        try:
            if (
                    "parse_task_limit_exceeded"
                    == json.loads(post_res.content.decode("utf-8"))["code"]
            ):
                raise RateLimit()
            else:
                return json.loads(post_res.content.decode("utf-8"))["data"]["uuid"]
        except RateLimit:
            raise RateLimit()
        except Exception as e:
            raise Exception(
                f"Upload file error with {e}! {post_res.status_code}:{post_res.text}"
            )
    elif post_res.status_code == 429:
        raise RateLimit()
    elif post_res.status_code == 400:
        raise RequestError(post_res.text)
    else:
        raise Exception(f"Upload file error! {post_res.status_code}:{post_res.text}")


async def decode_data(datas: json, convert: bool) -> Tuple[list, list]:
    """Decode the data

    Args:
        datas (json): The data
        convert (bool): Convert "[" and "[[" to "$" and "$$"

    Returns:
        Tuple[list, list]: The texts and locations
    """
    texts = []
    locations = []
    if not ("result" in datas and "pages" in datas["result"]):
        logging.warning("Although parsed successfully, the content is empty!")
        return [], []
    for data in datas["result"]["pages"]:
        try:
            text = data["md"]
        except KeyError:
            text = ""
        if convert:
            text = re.sub(r"\\[()]", "$", text)
            text = re.sub(r"\\[\[\]]", "$$", text)
        try:
            url = data["url"]
        except KeyError:
            url = ""
        # When processing image, there is no page_idx
        try:
            page_id = data["page_idx"]
        except KeyError:
            page_id = 0
        location = {
            "url": url,
            "page_idx": page_id,
            "page_width": data["page_width"],
            "page_height": data["page_height"],
        }
        texts.append(text)
        locations.append(location)
    return texts, locations


async def decode_translate(datas: json, convert: bool) -> Tuple[list, list]:
    """Decode the translate data

    Args:
        datas (json): The data
        convert (bool): Convert "[" and "[[" to "$" and "$$"

    Returns:
        Tuple[list, list]: The texts and locations
    """
    texts = []
    locations = []
    Rawinput = json.loads(datas["result"])
    for data in Rawinput:
        try:
            text = data["raw"]
            translate_text = data["translated"]
            if convert:
                text = re.sub(r"\\[()]", "$", text)
                text = re.sub(r"\\[\[\]]", "$$", text)
                translate_text = re.sub(r"\\[()]", "$", translate_text)
                translate_text = re.sub(r"\\[\[\]]", "$$", translate_text)
            location = {
                "raw_text": text,
                "page_idx": data["page_idx"],
                "page_width": data["page_width"],
                "page_height": data["page_height"],
                "x": data["x"],
                "y": data["y"],
            }
            texts.append(translate_text)
            locations.append(location)
        except KeyError:
            continue
    return texts, locations


@async_retry()
async def uuid_status(
        apikey: str,
        uuid: str,
        convert: bool = False,
        translate: bool = False,
) -> Tuple[int, str, list]:
    """Get the status of the file

    Args:
        apikey (str): The key
        uuid (str): The uuid of the file
        convert (bool, optional): Convert or not. Defaults to False.
        translate (bool, optional): Translate or not. Defaults to False.

    Raises:
        RuntimeError: Pages limit exceeded
        RuntimeError: Unknown status
        Exception: Get status error

    Returns:
        Tuple[int, str, list]: The progress, status and texts
    """
    if apikey.startswith("sk-"):
        url = f"{Base_URL}/v1/async/status?uuid={uuid}"
    else:
        url = f"{Base_URL}/platform/async/status?uuid={uuid}"
    if translate:
        url += "&parse_to=2"
    timeout = httpx.Timeout(30)
    async with httpx.AsyncClient(timeout=timeout) as client:
        get_res = await client.get(url, headers={"Authorization": "Bearer " + apikey})
    if get_res.status_code == 200:
        datas = None
        try:
            datas = json.loads(get_res.content.decode("utf-8"))["data"]
        except Exception as e:
            raise Exception(
                f"Get status error with {e}! {get_res.status_code}:{get_res.text}"
            )
        if datas["status"] == "ready":
            return 0, "Waiting for processing", [], []

        elif datas["status"] == "processing":
            return int(datas["progress"]), "Processing file", [], []

        elif datas["status"] == "translate_processing":
            return int(datas["progress"]), "Translating file", [], []

        elif datas["status"] == "success":
            texts, locations = await decode_data(datas, convert)
            return 100, "Success", texts, locations

        elif datas["status"] == "translate_success":
            texts, locations = await decode_translate(datas, convert)
            return 100, "Translate success", texts, locations

        elif datas["status"] == "pages limit exceeded":
            raise RuntimeError("Pages limit exceeded!")

        elif datas["status"] == "failed":
            raise RequestError(f"Failed to deal with file! {get_res.text}")

        else:
            raise RuntimeError(f"Unknown status! {get_res.text}")

    raise Exception(f"Get status error! {get_res.status_code}:{get_res.text}")


async def process_status(original_file: list, output_file: list):
    """Check the status of the files, error or success

    Args:
        original_file (list): The original file list
        output_file (list): The output file list

    Returns:
        _type_: The success file list, error file list and has error flag
    """
    success_file = []
    error_file = []

    for orig, out in zip(original_file, output_file):
        # if the output type is texts or in translate mode, the output is a list
        if isinstance(out, list):
            success_file.append(out)
            error_file.append({"error": "", "path": ""})
        elif isinstance(out, dict):
            success_file.append(out)
            error_file.append({"error": "", "path": ""})
        elif out.startswith("Error"):
            success_file.append("")
            error_file.append({"error": out, "path": orig})
        else:
            success_file.append(out)
            error_file.append({"error": "", "path": ""})
    try:
        has_error_flag = any(file.startswith("Error") for file in output_file)
    except AttributeError:
        has_error_flag = False

    return success_file, error_file, has_error_flag