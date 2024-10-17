import httpx
import json
import os
import re
from typing import Tuple
from .Exception import RateLimit, FileError, RequestError, async_retry, code_check
import logging

Base_URL = "https://v2.doc2x.noedgeai.com/api"


@async_retry()
async def upload_pdf(apikey: str, pdffile: str, ocr: bool = True) -> str:
    """Upload pdf file to server and return the uid of the file

    Args:
        apikey (str): The key
        pdffile (str): The pdf file path
        ocr (bool, optional): Do OCR or not. Defaults to True.

    Raises:
        FileError: Input file size is too large
        FileError: Open file error
        RateLimit: Rate limit exceeded
        Exception: Upload file error

    Returns:
        str: The uid of the file
    """
    url = f"{Base_URL}/v2/parse/pdf"
    if os.path.getsize(pdffile) >= 300 * 1024 * 1024:
        logging.warning("Now not support PDF file > 300MB!")
        raise RequestError("parse_file_too_large")
        logging.warning(
            "File size is too large, will auto switch to S3 file upload way, this may take a while"
        )
        return await upload_pdf_big(apikey, pdffile, ocr)

    try:
        with open(pdffile, "rb") as f:
            file = f.read()
    except Exception as e:
        raise FileError(f"Open file error! {e}")

    async with httpx.AsyncClient(timeout=httpx.Timeout(120)) as client:
        post_res = await client.post(
            url,
            params={"ocr": str(ocr).lower()},
            headers={
                "Authorization": f"Bearer {apikey}",
                "Content-Type": "application/pdf",
            },
            content=file,
        )

    if post_res.status_code == 200:
        response_data = json.loads(post_res.content.decode("utf-8"))
        await code_check(response_data.get("code", response_data))
        return response_data["data"]["uid"]

    if post_res.status_code == 429:
        raise RateLimit()
    if post_res.status_code == 400:
        raise RequestError(post_res.text)

    raise Exception(f"Upload file error! {post_res.status_code}:{post_res.text}")


@async_retry()
async def upload_pdf_big(apikey: str, pdffile: str, ocr: bool = True) -> str:
    """Upload big pdf file(>100m) to server and return the uid of the file

    Args:
        apikey (str): The key
        pdffile (str): The pdf file path
        ocr (bool, optional): Do OCR or not. Defaults to True.

    Raises:
        FileError: Input file size is too large
        FileError: Open file error
        RateLimit: Rate limit exceeded
        Exception: Upload file error

    Returns:
        str: The uid of the file
    """
    if os.path.getsize(pdffile) < 100 * 1024 * 1024:
        raise FileError("PDF file size should be bigger than 100MB!")

    try:
        file = {"file": open(pdffile, "rb")}
    except Exception as e:
        raise FileError(f"Open file error! {e}")

    url = f"{Base_URL}/v2/parse/preupload"
    filename = os.path.basename(pdffile)[:20]
    timeout = httpx.Timeout(120)

    async with httpx.AsyncClient(timeout=timeout) as client:
        post_res = await client.post(
            url,
            headers={"Authorization": f"Bearer {apikey}"},
            json={"file_name": filename, "ocr": ocr},
        )

    if post_res.status_code == 200:
        response_data = json.loads(post_res.content.decode("utf-8"))
        await code_check(response_data.get("code", response_data))

        upload_data = response_data["data"]
        upload_url = upload_data["url"]
        uid = upload_data["form"]["x-amz-meta-uid"]

        async with httpx.AsyncClient(timeout=timeout) as client:
            s3_res = await client.post(
                url=upload_url,
                data=upload_data["form"],
                files=file,
            )
        if s3_res.status_code == 204:
            return uid
        else:
            raise RequestError(s3_res.text)
    if post_res.status_code == 400:
        raise RequestError(post_res.text)
    raise Exception(f"Upload file error! {post_res.status_code}:{post_res.text}")


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
        logging.warning("Although parsed successfully, the content is empty!")
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
    async with httpx.AsyncClient(timeout=httpx.Timeout(30)) as client:
        response_data = await client.get(
            url, headers={"Authorization": f"Bearer {apikey}"}
        )
    if response_data.status_code != 200:
        raise Exception(
            f"Get status error! {response_data.status_code}:{response_data.text}"
        )

    try:
        data = json.loads(response_data.content.decode("utf-8"))
    except Exception as e:
        raise Exception(
            f"Get status error with {e}! {response_data.status_code}:{response_data.text}"
        )

    await code_check(data.get("code", response_data))

    progress, status = data["data"].get("progress", 0), data["data"].get("status", "")
    if status == "processing":
        return progress, "Processing file", [], []
    elif status == "success":
        texts, locations = await decode_data(data["data"], convert)
        return 100, "Success", texts, locations
    elif status == "failed":
        raise RequestError(f"Failed to deal with file! {response_data.text}")
    else:
        logging.warning(f"Unknown status: {status}")
        return progress, status, [], []


@async_retry()
async def convert_parse(
    apikey: str, uid: str, to: str, filename: str = None
) -> Tuple[str, str]:
    """Convert parsed file to specified format

    Args:
        apikey (str): The API key
        uid (str): The uid of the parsed file
        to (str): Export format, supports: md|tex|docx
        filename (str, optional): Output filename for md/tex (without extension). Defaults to None.

    Raises:
        ValueError: If 'to' is not a valid format
        RequestError: If the conversion fails
        Exception: For any other errors during the process

    Returns:
        Tuple[str, str]: A tuple containing the status and URL of the converted file
    """
    url = f"{Base_URL}/api/v2/convert/parse"

    if to not in ["md", "tex", "docx"]:
        raise ValueError("Invalid export format. Supported formats are: md, tex, docx")

    payload = {"uid": uid, "to": to}
    if filename and to in ["md", "tex"]:
        payload["filename"] = filename

    async with httpx.AsyncClient(timeout=httpx.Timeout(30)) as client:
        response_data = await client.post(
            url, json=payload, headers={"Authorization": f"Bearer {apikey}"}
        )

    if response_data.status_code != 200:
        raise Exception(
            f"Conversion request failed: {response_data.status_code}:{response_data.text}"
        )

    data = response_data.json()
    status = data["data"]["status"]
    url = data["data"].get("url", "")

    if status == "processing":
        return "Processing", ""
    elif status == "success":
        return "Success", url
    else:
        raise RequestError(f"Conversion uid {uid} file failed: {data}")


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
    url = f"{Base_URL}/api/v2/convert/parse/result"

    params = {"uid": uid}

    async with httpx.AsyncClient(timeout=httpx.Timeout(30)) as client:
        response = await client.get(
            url, params=params, headers={"Authorization": f"Bearer {apikey}"}
        )

    if response.status_code != 200:
        raise Exception(
            f"Get conversion result failed: {response.status_code}:{response.text}"
        )

    data = response.json()
    status = data["data"]["status"]
    url = data["data"].get("url", "")

    if status == "processing":
        return "Processing", ""
    elif status == "success":
        return "Success", url
    else:
        raise RequestError(f"Get conversion result for uid {uid} failed: {data}")
