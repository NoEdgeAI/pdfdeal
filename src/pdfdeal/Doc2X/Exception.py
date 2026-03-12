import asyncio
from functools import wraps
import time
import sys
from concurrent.futures import ThreadPoolExecutor
import logging
from httpx import RemoteProtocolError, ConnectError, ConnectTimeout


async def code_check(code: str, uid: str = None, trace_id: str = None):
    if code in ["parse_page_limit_exceeded", "parse_concurrency_limit"]:
        raise RateLimit(trace_id=trace_id)
    if code in RequestError.ERROR_CODES:
        raise RequestError(code, uid=uid, trace_id=trace_id)
    if code == "unauthorized":
        raise ValueError("API key is unauthorized. (认证失败，请检测API key是否正确)")
    if code not in ["ok", "success"]:
        raise Exception(f"Unknown error code: {code}, UID: {uid}, Trace ID: {trace_id}")


class RateLimit(Exception):
    """
    Error when rate limit is reached.
    """

    def __init__(self, trace_id: str = None):
        self.trace_id = trace_id
        super().__init__()

    def __str__(self):
        trace_msg = f" (Trace ID: {self.trace_id})" if self.trace_id else ""
        return f"Rate limit reached. Please wait a moment and try again. (速率限制，请稍后重试){trace_msg}"


class RequestError(Exception):
    """
    Error when request is not successful, with known status code.
    """

    ERROR_CODES = {
        "parse_quota_limit": "可用的解析页数额度不足 (Insufficient parsing quota)",
        "parse_create_task_error": "创建任务失败 (Failed to create task)",
        "parse_file_too_large": "单个文件大小超过限制 (File size exceeds limit)",
        "parse_file_page_limit": "单个文件页数超过限制 (File page count exceeds limit)",
        "parse_file_lock": "文件解析失败 (File parsing failed)",
        "parse_pdf_invalid": "传入的文件不是有效的PDF文件 (File is not a valid PDF)",
        "parse_file_not_pdf": "传入的文件不是PDF文件 (File is not a PDF)",
        "parse_file_not_image": "传入的文件不在支持的图片文件范围内 (File is not a supported image type)",
        "internal_error": "内部错误 (Internal error)",
        "parse_concurrency_limit": "同时解析的PDF页数超出上限 (Concurrent PDF page parsing limit exceeded)",
        "parse_error": "解析失败 (Parsing failed)",
    }

    SOLUTIONS = {
        "parse_quota_limit": "当前可用的页数不足，请检查余额或联系负责人 (Insufficient parsing quota, check balance or contact support)",
        "parse_create_task_error": "短暂等待后重试, 如果还出现报错则请联系负责人 (Retry after a short wait, contact support if error persists)",
        "parse_file_too_large": "当前允许单个文件大小 <= 1GB(通过 preupload 上传), 请拆分 pdf (File size must be <= 1GB via preupload upload, please split the PDF)",
        "parse_file_page_limit": "当前允许单个文件页数 <= 1000页, 请拆分 pdf (File page count must be <= 1000 pages, please split the PDF)",
        "parse_file_lock": "为了防止反复解析, 暂时锁定一天,考虑PDF可能有兼容性问题, 重新打印后再尝试。仍然失败请反馈request_id给负责人 (Locked for a day to prevent repeated parsing. Consider reprinting the PDF if compatibility issues persist. Report request_id if it still fails)",
        "parse_pdf_invalid": "不是有效的PDF文件,考虑PDF可能有兼容性问题, 重新打印后再尝试。仍然失败请反馈request_id给负责人 (File is not a valid PDF. Consider reprinting the PDF if compatibility issues persist. Report request_id if it still fails)",
        "parse_file_not_pdf": "请解析后缀为.pdf的文件 (Please parse files with .pdf extension)",
        "parse_file_not_image": "目前只支持 jpg/png 图片文件的解析 (Currently only jpg/png image files are supported)",
        "internal_error": "请联系技术支持 (Please contact technical support)",
        "parse_concurrency_limit": "短暂等待后重试, 当前解析的PDF页数超出上限 (Retry after a short wait, concurrent PDF page parsing limit exceeded)",
        "parse_error": "短暂等待后重试, 如果还出现报错则请联系负责人 (Retry after a short wait, contact support if error persists)",
    }

    def __init__(self, error_code, uid: str = None, trace_id: str = None, message=None):
        self.error_code = error_code
        self.uid = uid
        self.trace_id = trace_id
        self.reason = self.ERROR_CODES.get(error_code, "未知错误 (Unknown error)")
        self.solution = self.SOLUTIONS.get(
            error_code, "请联系技术支持 (Please contact technical support)"
        )
        super().__init__(message or f"{self.error_code}: {self.reason}")

    def __str__(self):
        self.uid = (
            self.uid
            or "Failed to get uid! Please set DEBUG mode to check the failed file path."
        )
        return f"{self.error_code}: {self.reason}\nUID: {self.uid}\nTrace ID: {self.trace_id}\nYou can try to do:\n{self.solution}"


class FileError(Exception):
    """
    Error when file is not found or cannot be opened or othes.
    """

    pass


def async_retry(max_retries=2, backoff_factor=2, timeout=60):
    """
    Decorator to retry an async function when an exception is raised.
    `max_retries`: Maximum number of retries.
    `backoff_factor`: Factor to increase the wait time between retries.
    `timeout`: Timeout in seconds for each function call.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for retries in range(max_retries + 1):
                try:
                    return await asyncio.wait_for(
                        func(*args, **kwargs), timeout=timeout
                    )
                except asyncio.TimeoutError:
                    if retries == max_retries:
                        logging.exception(
                            f"Function '{func.__name__}' timed out after {timeout} seconds"
                        )
                        raise
                    logging.warning(
                        f"Function '{func.__name__}' timed out, retrying..."
                    )
                except (
                    RateLimit,
                    FileError,
                    RequestError,
                    FileNotFoundError,
                    ValueError,
                ) as e:
                    logging.error(
                        f"Error in '{func.__name__}': {type(e).__name__} - {e}"
                    )
                    raise
                except (RemoteProtocolError, ConnectError, ConnectTimeout) as e:
                    if retries == max_retries:
                        logging.error(
                            f"Error in '{func.__name__}': {type(e).__name__} - {e}"
                        )
                        raise
                    wait_time = backoff_factor**retries
                    logging.warning(
                        f"{type(e).__name__}, this is most likely a network link issue, if this problem occurs frequently check your network environment (e.g. turn off your VPN, check your DNS seeting), will retry in {wait_time} seconds..."
                    )
                    await asyncio.sleep(wait_time)
                except Exception as e:
                    if isinstance(e, RequestError):
                        logging.error(str(e))
                        raise
                    elif isinstance(e, RateLimit):
                        raise
                    elif retries == max_retries:
                        logging.exception(
                            f"Error in '{func.__name__}': {type(e).__name__} - {e}"
                        )
                        raise
                    wait_time = backoff_factor**retries
                    logging.exception(
                        f"Exception in '{func.__name__}': {type(e).__name__} - {e}"
                    )
                    logging.warning(
                        f"Errors detected that may be resolved by retrying, will retrying in {wait_time} seconds..."
                    )
                    await asyncio.sleep(wait_time)

        return wrapper

    return decorator


def nomal_retry(max_retries=3, backoff_factor=2):
    """
    Decorator to retry an async function when an exception is raised.
    `max_retries`: Maximum number of retries.
    `backoff_factor`: Factor to increase the wait time between retries.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for retries in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except RateLimit:
                    raise
                except FileError as e:
                    logging.exception(f"FileError in '{func.__name__}': {e}")
                    raise
                except Exception as e:
                    if retries == max_retries:
                        logging.exception(
                            f"Max retries reached in '{func.__name__}': {e}"
                        )
                        raise
                    wait_time = backoff_factor**retries
                    logging.warning(
                        f"Retrying '{func.__name__}' in {wait_time} seconds. Error: {e}"
                    )
                    time.sleep(wait_time)

        return wrapper

    return decorator


def run_async(coro):
    """This function is used to run async function in sync way. As `asyncio.run` not work in jupyter notebook.

    Args:
        coro (_type_): The function to run.

    Returns:
        _type_: The result of the function.
    """
    if "IPython" in sys.modules:
        # Jupyter Notebook
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
    # Python
    return asyncio.run(coro)
