import asyncio
import random
import string

import httpx
import json
import os
import re
from typing import Tuple
from .Exception import RateLimit, FileError, RequestError, async_retry, code_check
import logging
from .Types import OutputFormat
import base64

Base_URL = "https://v2.doc2x.noedgeai.com/api"

logger = logging.getLogger("pdfdeal.convertV2")

# Add new error codes for image processing
IMAGE_ERROR_CODES = {
    "parse_quota_limit": "可用的解析额度不足 (Insufficient parsing quota)",
    "parse_error": "解析错误 (Parsing error)",
    "parse_file_invalid": "解析文件错误或者不合法 (Invalid or illegal image file)",
    "request_limit_exceeded": "请求频率超过限制 (Request frequency limit exceeded)",
    "parse_file_too_large": "单个图片大小超过限制 (Image size exceeds limit)",
}

IMAGE_ERROR_SOLUTIONS = {
    "parse_quota_limit": "当前可用的额度不够 (Current available quota is insufficient)",
    "parse_error": "图片内容无法解析，请反馈给我们 (Image content cannot be parsed, please provide feedback)",
    "parse_file_invalid": "无法解析这个图片，一般是图片不合法 (Cannot parse this image, usually due to invalid format)",
    "request_limit_exceeded": "请等待一段时间后再请求 (Please wait for a while before making another request)",
    "parse_file_too_large": "当前允许单个图片大小 <= 7M，尝试对图片进行压缩 (Current single image size limit is <= 7M, try compressing the image)",
}


@async_retry(timeout=200)
async def upload_pdf(apikey: str, pdffile: str, oss_choose: str = "always") -> str:
    """Upload pdf file to server and return the uid of the file

    Args:
        apikey (str): The key
        pdffile (str): The pdf file path
        oss_choose (str, optional): OSS upload preference. "always" for always using OSS, "auto" for using OSS only when the file size exceeds 100MB, "never" for never using OSS. Defaults to "always".

    Raises:
        FileError: Input file size is too large
        FileError: Open file error
        RateLimit: Rate limit exceeded
        Exception: Upload file error

    Returns:
        str: The uid of the file
    """
    url = f"{Base_URL}/v2/parse/pdf"
    if oss_choose == "always" or (
            oss_choose == "auto" and os.path.getsize(pdffile) >= 100 * 1024 * 1024
    ):
        return await upload_pdf_big(apikey, pdffile)
    elif oss_choose == "none" and os.path.getsize(pdffile) >= 100 * 1024 * 1024:
        logger.warning("Now not support PDF file > 300MB!")
        raise RequestError("parse_file_too_large")
    try:
        with open(pdffile, "rb") as f:
            file = f.read()
    except Exception as e:
        raise FileError(f"Open file error! {e}")

    async with httpx.AsyncClient(timeout=httpx.Timeout(120), http2=True) as client:
        post_res = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {apikey}",
                "Content-Type": "application/pdf",
            },
            content=file,
        )
    trace_id = post_res.headers.get("trace-id", "Failed to get trace-id ")
    if post_res.status_code == 200:
        response_data = json.loads(post_res.content.decode("utf-8"))
        uid = response_data.get("data", {}).get("uid")

        await code_check(
            code=response_data.get("code", response_data), uid=uid, trace_id=trace_id
        )
        return uid

    if post_res.status_code == 429:
        raise RateLimit(trace_id=trace_id)
    if post_res.status_code == 400:
        raise RequestError(error_code=post_res.text, trace_id=trace_id)
    elif post_res.status_code == 401:
        raise ValueError("API key is unauthorized. (认证失败，请检测API key是否正确)")
    raise Exception(
        f"Upload file error,trace_id{trace_id}:{post_res.status_code}:{post_res.text}"
    )


async def upload_pdf_big(apikey: str, pdffile: str) -> str:
    """Upload big pdf file to server and return the uid of the file

    Args:
        apikey (str): The key
        pdffile (str): The pdf file path

    Raises:
        FileError: Input file size is too large
        FileError: Open file error
        RateLimit: Rate limit exceeded
        Exception: Upload file error

    Returns:
        str: The uid of the file
    """
    if os.path.getsize(pdffile) >= 1024 * 1024 * 1024:
        logger.warning("Not support PDF file > 1GB!")
        raise RequestError("parse_file_too_large")
    try:
        file = {"file": open(pdffile, "rb")}
    except Exception as e:
        raise FileError(f"Open file error! {e}")

    url = f"{Base_URL}/v2/parse/preupload"
    filename = os.path.basename(pdffile)

    async with httpx.AsyncClient(timeout=httpx.Timeout(15), http2=True) as client:
        post_res = await client.post(
            url,
            headers={"Authorization": f"Bearer {apikey}"},
            json={"file_name": filename},
        )
    trace_id = post_res.headers.get("trace-id")
    if post_res.status_code == 200:
        response_data = json.loads(post_res.content.decode("utf-8"))
        uid = response_data.get("data", {}).get("uid")
        await code_check(
            code=response_data.get("code", response_data),
            uid=uid,
            trace_id=trace_id,
        )
        upload_data = response_data["data"]
        upload_url = upload_data["url"]

        async with httpx.AsyncClient(timeout=httpx.Timeout(180), http2=True) as client:
            s3_res = await client.put(
                url=upload_url,
                files=file,
            )
        if s3_res.status_code == 200:
            return uid
        else:
            raise Exception(f"Upload file to OSS error! {s3_res.text}")
    if post_res.status_code == 400:
        raise RequestError(error_code=post_res.text, trace_id=trace_id)
    elif post_res.status_code == 401:
        raise ValueError("API key is unauthorized. (认证失败，请检测API key是否正确)")
    raise Exception(
        f"Upload file error! trace_ID:{trace_id}:{post_res.status_code}:{post_res.text}"
    )


async def decode_data(data: dict, convert: bool) -> Tuple[list, list]:
    """Decode the data

    Args:
        data (dict): The response data
        convert (bool): Convert "[" and "[[" to "$" and "$$"

    Returns:
        Tuple[list, list]: The texts and locations
    """
    texts = []
    locations = []
    if "result" not in data or "pages" not in data["result"]:
        logger.warning("Although parsed successfully, the content is empty!")
        return [], []
    texts, locations = [], []
    for page in data["result"]["pages"]:
        text = page.get("md", "")
        if convert:
            text = re.sub(r"\\[()]", "$", text)
            text = re.sub(r"\\[\[\]]", "$$", text)
        texts.append(text)
        locations.append(
            {
                "url": page.get("url", ""),
                "page_idx": page.get("page_idx", 0),
                "page_width": page.get("page_width", 0),
                "page_height": page.get("page_height", 0),
            }
        )
    return texts, locations


@async_retry()
async def uid_status(
        apikey: str,
        uid: str,
        convert: bool = False,
) -> Tuple[int, str, list, list]:
    """Get the status of the file

    Args:
        apikey (str): The key
        uid (str): The uid of the file
        convert (bool, optional): Convert "[" and "[[" to "$" and "$$" or not. Defaults to False.

    Raises:
        RequestError: Failed to deal with file
        Exception: Get status error

    Returns:
        Tuple[int, str, list, list]: The progress, status, texts and locations
    """
    url = f"{Base_URL}/v2/parse/status?uid={uid}"
    async with httpx.AsyncClient(timeout=httpx.Timeout(30), http2=True) as client:
        response_data = await client.get(
            url, headers={"Authorization": f"Bearer {apikey}"}
        )
    trace_id = response_data.headers.get("trace-id", "Failed to get trace-id ")
    if response_data.status_code != 200:
        raise Exception(
            f"Get status error! Trace-id:{trace_id}:{response_data.status_code}:{response_data.text}"
        )

    try:
        data = json.loads(response_data.content.decode("utf-8"))
    except Exception as e:
        raise Exception(
            f"Get status error with {e}! Trace-id:{trace_id}:{response_data.status_code}:{response_data.text}"
        )

    await code_check(data.get("code", response_data), uid, trace_id=trace_id)

    progress, status = data["data"].get("progress", 0), data["data"].get("status", "")
    if status == "processing":
        return progress, "Processing file", [], []
    elif status == "success":
        texts, locations = await decode_data(data["data"], convert)
        return 100, "Success", texts, locations
    elif status == "failed":
        raise RequestError(
            f"Failed to deal with file uid {uid}! Trace-id:{trace_id}:{response_data.text}"
        )
    else:
        logger.warning(
            f"Unknown status: {status} in uid {uid} file! Trace-id:{trace_id}:{response_data.text}"
        )
        return progress, status, [], []


@async_retry()
async def convert_parse(
        apikey: str,
        uid: str,
        to: str,
        filename: str = None,
        merge_cross_page_forms: bool = False,
) -> Tuple[str, str]:
    """Convert parsed file to specified format

    Args:
        apikey (str): The API key
        uid (str): The uid of the parsed file
        to (str): Export format, supports: md|tex|docx|md_dollar
        filename (str, optional): Output filename for md/tex (without extension). Defaults to None.
        merge_cross_page_forms (bool, optional): Whether to merge cross-page forms. Defaults to False.

    Raises:
        ValueError: If 'to' is not a valid format
        RequestError: If the conversion fails
        Exception: For any other errors during the process

    Returns:
        Tuple[str, str]: A tuple containing the status and URL of the converted file
    """
    url = f"{Base_URL}/v2/convert/parse"

    to = OutputFormat(to)
    if isinstance(to, OutputFormat):
        to = to.value

    payload = {
        "uid": uid,
        "to": to,
        "formula_mode": "normal",
        "merge_cross_page_forms": merge_cross_page_forms,
    }
    if filename and to in ["md", "md_dollar", "tex"]:
        payload["filename"] = filename
    if to == "md_dollar":
        payload["formula_mode"] = "dollar"
        payload["to"] = "md"
    async with httpx.AsyncClient(timeout=httpx.Timeout(30), http2=True) as client:
        response_data = await client.post(
            url, json=payload, headers={"Authorization": f"Bearer {apikey}"}
        )
    trace_id = response_data.headers.get("trace-id", "Failed to get trace-id ")
    if response_data.status_code != 200:
        raise Exception(
            f"Conversion request failed: Trace-id:{trace_id}:{response_data.status_code}:{response_data.text}"
        )

    data = response_data.json()

    await code_check(data.get("code", response_data), uid, trace_id=trace_id)
    status = data["data"]["status"]
    url = data["data"].get("url", "")

    if status == "processing":
        return "Processing", ""
    elif status == "success":
        return "Success", url
    else:
        raise RequestError(
            f"Conversion uid {uid} file failed in Trace-id:{trace_id}:{data}"
        )


@async_retry()
async def get_convert_result(apikey: str, uid: str) -> Tuple[str, str]:
    """Get the result of a conversion task

    Args:
        apikey (str): The API key
        uid (str): The uid of the conversion task

    Raises:
        RequestError: If the request fails
        Exception: For any other errors during the process

    Returns:
        Tuple[str, str]: A tuple containing the status and URL of the converted file
    """
    url = f"{Base_URL}/v2/convert/parse/result"

    params = {"uid": uid}

    async with httpx.AsyncClient(timeout=httpx.Timeout(30), http2=True) as client:
        response = await client.get(
            url, params=params, headers={"Authorization": f"Bearer {apikey}"}
        )
    trace_id = response.headers.get("trace-id", "Failed to get trace-id ")
    if response.status_code != 200:
        raise Exception(
            f"Get conversion result failed: Trace-id:{trace_id}:{response.status_code}:{response.text}"
        )

    data = response.json()
    await code_check(data.get("code", response), uid, trace_id=trace_id)
    status = data["data"]["status"]
    url = data["data"].get("url", "")

    if status == "processing":
        return "Processing", ""
    elif status == "success":
        return "Success", url
    else:
        raise RequestError(
            f"Get conversion result for uid {uid} failed:Trace-id:{trace_id}:{data}"
        )


@async_retry()
async def download_file(
        url: str, file_type: str, target_folder: str, target_filename: str
) -> str:
    """
    Download a file from the given URL to the specified target folder with the given filename.

    Args:
        url (str): The URL to download the file from.
        file_type (str): The type of file being downloaded (e.g., 'zip', 'docx').
        target_folder (str): The folder where the file should be saved.
        target_filename (str): The desired filename for the downloaded file, can include subdirectories.

    Raises:
        Exception: If there's an error creating the target folder or downloading the file.

    Returns:
        str: The full path of the downloaded file.
    """
    target_path = os.path.join(target_folder, target_filename)
    target_dir = os.path.dirname(target_path)
    filename = os.path.basename(target_path)
    os.makedirs(target_dir, exist_ok=True)

    filename = os.path.splitext(filename)[0]
    if file_type != "docx":
        file_type = "zip"
    file_path = os.path.join(target_dir, f"{filename}.{file_type}")
    counter = 1
    while os.path.exists(file_path):
        file_path = os.path.join(target_dir, f"{filename}_{counter}.{file_type}")
        counter += 1

    async with httpx.AsyncClient(timeout=httpx.Timeout(60), http2=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        with open(file_path, "wb") as f:
            f.write(response.content)

    return file_path


async def image_code_check(code: str, trace_id: str = None):
    """Check image processing error codes and raise appropriate exceptions

    Args:
        code (str): The error code to check
        trace_id (str, optional): The trace ID for debugging. Defaults to None.

    Raises:
        RateLimit: When rate limit is reached
        RequestError: When a known error occurs
        ValueError: When API key is unauthorized
        Exception: When an unknown error occurs
    """
    if code == "request_limit_exceeded":
        raise RateLimit(trace_id=trace_id)
    if code in IMAGE_ERROR_CODES:
        raise RequestError(code, trace_id=trace_id)
    if code == "unauthorized":
        raise ValueError("API key is unauthorized. (认证失败，请检测API key是否正确)")
    if code not in ["ok", "success"]:
        raise Exception(f"Unknown error code: {code}, Trace ID: {trace_id}")

@async_retry()
async def parse_image_layout(
        apikey: str, image_path: str, zip_path: str = None
) -> tuple[list, str]:
    """Parse image layout

    Args:
        apikey (str): The API key
        image_path (str): Path to the image file
        zip_path (str, optional): Path to save the zip file containing images. Defaults to image_name + 'picture.zip'.

    Raises:
        FileError: If file size exceeds limit or file cannot be opened
        RateLimit: If rate limit is reached
        RequestError: If parsing fails
        Exception: For any other errors

    Returns:
        tuple: A tuple containing:
            - list: List of page dictionaries with page dimensions and md content
            - str: The unique identifier (uid) of the request
    """
    # Use the image name as the prefix for the zip file name
    default_zip_filename = os.path.splitext(os.path.basename(image_path))[0]
    new_zip_filename = f"{default_zip_filename}picture.zip"
    
    # Use zip_path + image name + picture.zip to name zip files
    if zip_path is None:
        parent_directory = os.path.dirname(image_path)
        if not parent_directory:
            parent_directory = "."
        zip_path = os.path.join(parent_directory, new_zip_filename)
    else:
        zip_path = os.path.join(zip_path, new_zip_filename)

    if not os.path.exists(zip_path):
        os.makedirs(os.path.dirname(zip_path), exist_ok=True)

    # Check zip_path is a file path and not exists
    base_name, extension = os.path.splitext(zip_path)
    random_digits = ''.join(random.choices(string.digits, k=10))
    zip_path = f"{base_name}-{random_digits}{extension}"
        # raise FileError("zip_path already exists! Please check the path")
    if not zip_path.endswith(".zip"):
        raise FileError("zip_path must end with .zip")
    # Check file size
    if os.path.getsize(image_path) > 7 * 1024 * 1024:  # 7MB
        raise FileError("Image file size exceeds 7MB limit")

    url = f"{Base_URL}/v2/parse/img/layout"

    try:
        with open(image_path, "rb") as f:
            file = f.read()
    except Exception as e:
        raise FileError(f"Open file error! {e}")

    async with httpx.AsyncClient(timeout=httpx.Timeout(30), http2=True) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {apikey}"},
            content=file,
        )

    trace_id = response.headers.get("trace-id", "Failed to get trace-id")

    if response.status_code == 429:
        raise RateLimit(trace_id=trace_id)

    if response.status_code != 200:
        raise Exception(
            f"Image layout parsing failed: {response.status_code}:{response.text}"
        )

    data = response.json()
    await image_code_check(data.get("code", ""), trace_id=trace_id)

    # Save zip file if path provided and zip content exists
    if zip_path and data.get("data", {}).get("convert_zip"):
        zip_content = base64.b64decode(data["data"]["convert_zip"])
        with open(zip_path, "wb") as f:
            f.write(zip_content)

    return (
        data.get("data", {}).get("result", {}).get("pages", []),
        data.get("data", {}).get("uid", "Failed to get uid"),
    )
