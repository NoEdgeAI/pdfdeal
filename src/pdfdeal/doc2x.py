import asyncio
import csv
import os
from datetime import datetime
from typing import Dict, Tuple, List, Union, Optional, Any, Coroutine
import logging

import aiofiles
import aiofiles.os

from .Doc2X.ConvertV2 import (
    upload_pdf,
    uid_status,
    convert_parse,
    get_convert_result,
    download_file,
)
from .Doc2X.Types import OutputFormat
from .Doc2X.Pages import get_pdf_page_count
from .Doc2X.Exception import RequestError, RateLimit, run_async
from .FileTools.file_tools import get_files, save_json
import time
from .doc2x_img import ImageProcessor

logger = logging.getLogger(name="pdfdeal.doc2x")


async def record_export_history(
        csv_path: str,
        uid: str,
        file_name: str = None,
        upload_time: float = None,
        status: str = None,
        is_export: bool = False,
        lock: asyncio.Lock = None,
):
    """Record history using csv"""
    csv_header = ["uid", "file_name", "upload_time_str", "status", "is_export"]
    async with lock:
        update_data = {}
        if file_name is not None:
            update_data["file_name"] = file_name
        if upload_time is not None:
            update_data["upload_time_str"] = datetime.fromtimestamp(upload_time).strftime("%Y-%m-%d %H:%M:%S")
        if status is not None:
            update_data["status"] = status
        if is_export is not None:
            update_data["is_export"] = str(is_export)
        output_dir = os.path.dirname(csv_path)
        if output_dir:
            await aiofiles.os.makedirs(output_dir, exist_ok=True)
        try:
            async with aiofiles.open(csv_path, mode="r+", encoding="utf-8", newline="") as f:
                lines = await f.readlines()
                output_lines = []
                uid_found = False
                if not lines:
                    output_lines.append(",".join(csv_header) + "\n")
                else:
                    output_lines.append(lines[0])
                    for line in lines[1:]:
                        if line.strip():
                            row_list = line.strip().split(',')
                            row_uid = row_list[0] if row_list else ""
                            if row_uid == uid:
                                uid_found = True
                                row_dict = dict(zip(csv_header, row_list))
                                row_dict.update(update_data)
                                updated_row_list = [row_dict.get(h, "") for h in csv_header]
                                output_lines.append(",".join(map(str, updated_row_list)) + "\n")
                            else:
                                output_lines.append(line)
                if not uid_found:
                    new_row_dict = {
                        "uid": uid,
                        "file_name": file_name,
                        "upload_time_str": update_data.get("upload_time_str", ""),
                        "status": status,
                        "is_export": str(is_export) if is_export is not None else ""
                    }
                    new_row_list = [new_row_dict.get(h, "") for h in csv_header]
                    output_lines.append(",".join(map(str, new_row_list)) + "\n")
                await f.seek(0)
                await f.truncate()
                await f.writelines(output_lines)

        except FileNotFoundError:
            async with aiofiles.open(csv_path, mode="w", encoding="utf-8", newline="") as f:
                await f.write(",".join(csv_header) + "\n")
                new_row_dict = {
                    "uid": uid,
                    "file_name": file_name,
                    "upload_time_str": update_data.get("upload_time_str", ""),
                    "status": status,
                    "is_export": str(is_export) if is_export is not None else ""
                }
                new_row_list = [new_row_dict.get(h, "") for h in csv_header]
                await f.write(",".join(map(str, new_row_list)) + "\n")


async def read_export_history(csv_path: str) -> Dict[str, bool]:
    """Read export history from csv_path"""
    file_to_export_status_map: Dict[str, bool] = {}
    if not await aiofiles.os.path.exists(csv_path):
        return file_to_export_status_map
    try:
        async with aiofiles.open(csv_path, mode="r", encoding="utf-8", newline="") as f:
            header_read = False
            file_name_index = -1
            is_export_index = -1
            async for line in f:
                if not line.strip():
                    continue
                row = next(csv.reader([line]))
                if not header_read:
                    try:
                        file_name_index = row.index("file_name")
                        is_export_index = row.index("is_export")
                        header_read = True
                    except ValueError as e:
                        print(f"错误: CSV文件中缺少必要的列: {e}")
                        return {}  # 表头不正确，返回空字典
                    continue  # 跳过表头行，继续下一次循环
                if len(row) > max(file_name_index, is_export_index):
                    file_name = row[file_name_index]
                    is_export_str = row[is_export_index]
                    is_export_bool = is_export_str.strip().lower() == 'true'
                    file_to_export_status_map[file_name] = is_export_bool
    except Exception as e:
        print(f"读取或解析CSV文件时发生错误: {e}")
    return file_to_export_status_map


async def parse_pdf(
        apikey: str,
        pdf_path: str,
        maxretry: int,
        wait_time: int,
        max_time: int,
        convert: bool,
        oss_choose: str = "auto",
        export_history: str = "",
) -> Tuple[str, List[str], List[dict]]:
    """Parse PDF file and return uid and extracted text"""

    async def task_limit_lock():
        global full_speed
        if full_speed:
            global limit_lock, get_max_limit, max_threads, thread_min
            nonlocal thread_lock
            if not get_max_limit and not thread_lock:
                get_max_limit = True
                thread_lock = True
                async with limit_lock:
                    max_threads = max(thread_min, max_threads - 1)
            else:
                if not thread_lock:
                    async with limit_lock:
                        max_threads = max(thread_min, max_threads - 1)
                    thread_lock = True

    thread_lock = False
    for attempt in range(maxretry):
        try:
            logger.info(f"Uploading {pdf_path}...")
            uid = await upload_pdf(apikey, pdf_path, oss_choose)
            if export_history is not "":
                await record_export_history(
                    csv_path=export_history,
                    uid=uid,
                    file_name=pdf_path,
                    upload_time=time.time(),
                    status="Processing",
                    is_export=False,
                    lock=asyncio.Lock())

            logger.info(f"Uploading successful for {pdf_path} with uid {uid}")

            for _ in range(max_time // 3):
                try:
                    progress, status, texts, locations = await uid_status(
                        apikey, uid, convert
                    )
                    if status == "Success":
                        logger.info(f"Parsing successful for {pdf_path} with uid {uid}")
                        if export_history is not "":
                            await record_export_history(
                                csv_path=export_history,
                                uid=uid,
                                status="Success",
                                lock=asyncio.Lock())
                        return uid, texts, locations
                    elif status == "Processing file":
                        logger.info(f"Processing {uid} : {progress}%")
                        await asyncio.sleep(3)
                    else:
                        if export_history is not "":
                            await record_export_history(
                                csv_path=export_history,
                                uid=uid,
                                status="Failed",
                                lock=asyncio.Lock())
                        raise RequestError(
                            f"Unexpected status: {status} with uid: {uid}"
                        )
                except RateLimit:
                    logger.warning(
                        "Rate limit reached during status check, retrying from upload..."
                    )
                    await task_limit_lock()
                    await asyncio.sleep(wait_time)
                    break
            else:
                raise RequestError(f"Max time reached for uid_status with uid: {uid}")
        except RateLimit:
            if attempt < maxretry - 1:
                await task_limit_lock()
                logger.warning("Rate limit reached during upload, retrying...")
                await asyncio.sleep(wait_time)
            else:
                raise RequestError(
                    "Max retry reached for parse_pdf, this may be a rate limit issue, try to reduce the number of threads."
                )
    raise RequestError("Failed to parse PDF after maximum retries")


async def convert_to_format(
        apikey: str,
        uid: str,
        output_format: str,
        output_path: str,
        output_name: str,
        max_time: int,
        merge_cross_page_forms: bool = False,
        save_subdir: bool = False,
) -> str:
    """Convert parsed PDF to specified format"""
    logger.info(f"Converting {uid} to {output_format}...")
    status, url = await convert_parse(
        apikey, uid, output_format, merge_cross_page_forms=merge_cross_page_forms
    )
    for _ in range(max_time // 3):
        if status == "Success":
            logger.info(f"Downloading {uid} {output_format} file to {output_path}...")
            return await download_file(
                url=url,
                file_type=output_format,
                target_folder=output_path,
                target_filename=output_name or uid,
                save_subdir=save_subdir,
            )
        elif status == "Processing":
            logger.info(f"Converting {uid} {output_format} file...")
            await asyncio.sleep(3)
            status, url = await get_convert_result(apikey, uid)
        else:
            raise RequestError(f"Unexpected status: {status} with uid: {uid}")
    raise RequestError(f"Max time reached for get_convert_result with uid: {uid}")


async def save_json_format(
        output_path: str,
        output_name: str,
        json_content: list[dict] = None,
):
    """Save the JSON file
    Args:
    output_path (str): The path to save the JSON file
    output_name(str): JSON file name
    json_content (list[dict]): The JSON content to save
    """
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        save_json,
        output_path,
        output_name,
        json_content
    )


class Doc2X:
    def __init__(
            self,
            apikey: str = None,
            thread: int = 5,
            max_pages: int = 1000,
            retry_time: int = 5,
            max_time: int = 300,
            debug: bool = False,
            full_speed: bool = False,
    ) -> None:
        """
        Initialize a Doc2X client.

        Args:
            apikey (str, optional): The API key for Doc2X. If not provided, it will try to get from environment variable 'DOC2X_APIKEY'.
            thread (int, optional): The maximum number of concurrent threads at same time. Defaults to 5.
            max_pages (int, optional): The maximum number of pages to process at same time. Defaults to 1000.
            retry_time (int, optional): The number of retry attempts. Defaults to 5.
            max_time (int, optional): The maximum time (in seconds) to wait for a response. Defaults to 300.
            debug (bool, optional): Whether to enable debug logging. Defaults to False.
            full_speed (bool, optional): **Experimental function**. Whether to enable automatic sniffing of the concurrency limit. Defaults to False.

        Raises:
            ValueError: If no API key is found.

        Note:
            If debug is set to True, it will set the logging level of 'pdfdeal' logger to DEBUG.
        """
        self.apikey = apikey or os.environ.get("DOC2X_APIKEY", "")
        if not self.apikey:
            raise ValueError("No apikey found")
        self.retry_time = retry_time
        self.max_time = max_time
        self.thread = thread
        self.max_pages = max_pages
        self.request_interval = 0.1
        self.full_speed = full_speed
        self._image_processor = None

        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.propagate = False
        if debug:
            logging.getLogger("pdfdeal").setLevel(logging.DEBUG)
        self.debug = debug

    @property
    def image_processor(self) -> ImageProcessor:
        """Lazy initialization of ImageProcessor"""
        if self._image_processor is None:
            self._image_processor = ImageProcessor(self.apikey)
        return self._image_processor

    def piclayout(
            self,
            pic_file,
            zip_path: Optional[str] = None,
            concurrent_limit: Optional[int] = 5,
    ) -> tuple[List[Union[list, str]], List[dict], bool]:
        """Process image files with layout analysis

        Args:
            pic_file (str | List[str]): Path to image files (jpg/png)
            zip_path (str, optional): Path to save the zip file containing images. Defaults to None.
            concurrent_limit (int, optional): Maximum number of concurrent tasks. Defaults to 5.

        Returns:
            Tuple containing:
                - List of layout analysis results (list or str)
                - List of dictionaries containing error information
                - Boolean indicating if any errors occurred
        """
        return self.image_processor.pic2file(
            pic_file=pic_file,
            process_type="layout",
            concurrent_limit=concurrent_limit,
            zip_path=zip_path,
        )

    async def pdf2file_back(
            self,
            pdf_file,
            output_names: List[str] = None,
            output_path: str = "./Output",
            output_format: str = "md_dollar",
            convert: bool = False,
            oss_choose: str = "auto",
            merge_cross_page_forms: bool = False,
            save_subdir: bool = False,
            export_history: str = "",
    ) -> Tuple[List[str], List[dict], bool]:
        if isinstance(pdf_file, str):
            if os.path.isdir(pdf_file):
                pdf_file, output_names = get_files(
                    # 实际上由于文件后缀名是在下载阶段才确定的，所以这里的后缀名是无效的，只是为了向上兼容
                    path=pdf_file,
                    mode="pdf",
                    out="md_dollar",
                )
            else:
                pdf_file = [pdf_file]
                if output_names is None:
                    output_names = [os.path.basename(pdf_file[0])]

        output_names = output_names or [None] * len(pdf_file)
        if len(pdf_file) != len(output_names):
            raise ValueError("The length of files and output_names should be the same.")

        output_formats = []
        if isinstance(output_format, str):
            if "," in output_format:
                output_formats = [fmt.strip() for fmt in output_format.split(",")]
                logger.warning(
                    "You are using multiple output formats, this will increase many time, please be patient.(您正在使用多个输出格式，这将增加很多时间，请耐心等待。)"
                )
            else:
                output_formats = [output_format]
        else:
            raise ValueError("Invalid output format, should be a string.")

        for fmt in output_formats:
            fmt = OutputFormat(fmt)
            if isinstance(fmt, OutputFormat):
                fmt = fmt.value

        # Track total pages and last request time
        total_pages = 0
        last_request_time = 0
        page_lock = asyncio.Lock()
        parse_tasks = set()
        convert_tasks = set()
        results = [None] * len(pdf_file)
        parse_results = [None] * len(pdf_file)
        global limit_lock, get_max_limit, max_threads, full_speed, thread_min, file_export_map
        thread_min = self.thread
        full_speed = self.full_speed
        limit_lock = asyncio.Lock()
        get_max_limit = False
        max_threads = self.thread

        if full_speed:
            self.max_time = 600
            self.retry_time = 10
            self.request_interval = 0.01

        async def process_file(index, pdf, name):
            try:
                page_count = get_pdf_page_count(pdf)
            except RequestError as e:
                results[index] = ("", str(e), True)
                logger.warning(f"Skiping {pdf}: {str(e)}")
                return
            except Exception as e:
                logger.warning(f"Failed to get page count for {pdf}: {str(e)}")
                page_count = self.max_pages - 1  #! Assume the worst case
            if page_count > self.max_pages:
                logger.warning(f"File {pdf} has too many pages, skipping.")
                results[index] = ("", "File has too many pages", True)
                return

            nonlocal total_pages, last_request_time

            try:
                # Check if we can start new task
                while True:
                    async with page_lock:
                        if total_pages + page_count <= self.max_pages:
                            current_time = time.time()
                            if current_time - last_request_time < self.request_interval:
                                await asyncio.sleep(
                                    self.request_interval
                                    - (current_time - last_request_time)
                                )

                            total_pages += page_count
                            last_request_time = time.time()
                            break
                    await asyncio.sleep(0.1)

                # Process the file
                try:
                    uid, texts, locations = await parse_pdf(
                        apikey=self.apikey,
                        pdf_path=pdf,
                        maxretry=self.retry_time,
                        wait_time=5,
                        max_time=self.max_time,
                        convert=convert,
                        oss_choose=oss_choose,
                        export_history=export_history,
                    )
                    parse_results[index] = (uid, texts, locations)
                    # Create convert task as soon as parse is complete
                    task = asyncio.create_task(convert_file(index, name))
                    convert_tasks.add(task)

                except asyncio.TimeoutError:
                    results[index] = (
                        "",
                        "Operation timed out, this may be a rate limit issue or network issue, try to reduce the number of threads.",
                        True,
                    )
                except Exception as e:
                    results[index] = ("", str(e), True)
            finally:
                async with page_lock:
                    total_pages -= page_count

        async def convert_file(index, name):
            if parse_results[index] is None:
                return
            uid, texts, locations = parse_results[index]
            all_results = []
            all_errors = []

            for name_index, fmt in enumerate(output_formats):
                if isinstance(name, list):
                    try:
                        name_fmt = name[name_index]
                    except IndexError:
                        name_fmt = name[-1]
                else:
                    name_fmt = name
                try:
                    if fmt in ["md", "md_dollar", "tex", "docx"]:
                        nonlocal last_request_time
                        # Wait for request interval
                        current_time = time.time()
                        if current_time - last_request_time < self.request_interval:
                            await asyncio.sleep(
                                self.request_interval
                                - (current_time - last_request_time)
                            )

                        async with page_lock:
                            last_request_time = time.time()

                        result = await convert_to_format(
                            apikey=self.apikey,
                            uid=uid,
                            output_format=fmt,
                            output_path=output_path,
                            output_name=name_fmt,
                            max_time=self.max_time,
                            merge_cross_page_forms=merge_cross_page_forms,
                            save_subdir=save_subdir
                        )
                        if export_history is not "":
                            await record_export_history(
                                csv_path=export_history,
                                uid=uid,
                                is_export=True,
                                lock=asyncio.Lock())
                        all_results.append(result)
                        all_errors.append("")
                        # Wait 5 seconds between formats
                        if fmt != output_formats[-1]:
                            logger.info(
                                f"Due to the rate limit, waiting 5 seconds before converting {pdf_file[index]} to the{fmt} format."
                            )
                            await asyncio.sleep(5)
                    else:
                        if fmt == "texts":
                            result = texts
                        elif fmt == "text":
                            result = "\n".join(texts)
                        elif fmt == "detailed" or fmt == "json":
                            result = [
                                {"text": text, "location": loc}
                                for text, loc in zip(texts, locations)
                            ]
                            if fmt == "json":
                                await save_json_format(output_path=os.path.join(output_path, os.path.dirname(name_fmt)),
                                                       output_name=os.path.basename(name_fmt),
                                                       json_content=result)
                        if export_history is not "":
                            await record_export_history(
                                csv_path=export_history,
                                uid=uid,
                                is_export=True,
                                lock=asyncio.Lock())
                        all_results.append(result)
                        all_errors.append("")

                except asyncio.TimeoutError:
                    all_results.append("")
                    all_errors.append(
                        f"Operation timed out while converting to {fmt}, this may be a rate limit issue or network issue, try to reduce the number of threads."
                    )
                except Exception as e:
                    all_results.append("")
                    error_message = str(e) if str(e) else type(e).__name__
                    all_errors.append(
                        f"Error while converting to {fmt}: {error_message}"
                    )

            results[index] = (
                (all_results[0], all_errors[0], not all_results[0])
                if len(all_results) == 1 and len(all_errors) == 1
                else (
                    all_results,
                    all_errors,
                    any(not result for result in all_results),
                )
            )

        # Create and run parse tasks with controlled concurrency

        if export_history is not "":
            file_export_map = await read_export_history(export_history)
            print(f"export_history{file_export_map}")

        for i, (pdf, name) in enumerate(zip(pdf_file, output_names)):
            if export_history is not "":
                if file_export_map.get(pdf, False) is True:
                    results[i] = ('', '', '')
                    continue
            while len(parse_tasks) >= max_threads:
                done, parse_tasks = await asyncio.wait(
                    parse_tasks, return_when=asyncio.FIRST_COMPLETED
                )
                if full_speed:
                    async with limit_lock:
                        if not get_max_limit:
                            max_threads = max_threads + 1
            task = asyncio.create_task(process_file(i, pdf, name))
            parse_tasks.add(task)

        # Wait for remaining parse tasks
        if parse_tasks:
            await asyncio.wait(parse_tasks)

        # Wait for remaining convert tasks
        if convert_tasks:
            await asyncio.wait(convert_tasks)
        else:
            logger.warning("No successful parse tasks, skipping conversion.")
        print(results)
        if full_speed:
            logger.info(f"Convert tasks done with {max_threads} threads.")
        success_files = []
        for r in results:
            success_files.append(r[0])

        failed_files = []
        for r, pdf in zip(results, pdf_file):
            if r and r[2]:
                failed_files.append({"error": r[1], "path": pdf})
            else:
                failed_files.append({"error": r[1], "path": ""})
        has_error = any(r[2] for r in results if r)
        if has_error:
            logger.error(
                f"Failed to convert {sum(1 for r in results if r and r[2])} file(s), please enable DEBUG mode to check or read the output variable."
            )
            if self.debug:
                if has_error:
                    print("=====================")
                    for fail in failed_files:
                        if isinstance(fail["error"], list):
                            for e in fail["error"]:
                                if e != "":
                                    print(
                                        f"Failed to convert {fail['path']}: {e}\n====================="
                                    )
                        else:
                            if fail["error"] != "":
                                print(
                                    f"Failed to convert {fail['path']}: {fail['error']}\n====================="
                                )

        logger.info(
            f"Successfully converted {sum(1 for r in results if r and not r[2])} file(s) and failed to convert {sum(1 for r in results if r and r[2])} file(s)."
        )
        return success_files, failed_files, has_error

    def pdf2file(
            self,
            pdf_file,
            output_names: List[str] = None,
            output_path: str = "./Output",
            output_format: str = "md_dollar",
            convert: bool = False,
            oss_choose: str = "always",
            merge_cross_page_forms: bool = False,
            ocr: bool = False,
            save_subdir: bool = False,
            export_history: str = "",
    ) -> Tuple[List[str], List[dict], bool]:
        """Convert PDF file to specified format
        Args:
            pdf_file (str or list): The path of the PDF file or a list of PDF file paths
            output_names (List[str], optional): The output file names. Defaults to None.
            output_path (str, optional): The output path. Defaults to "./Output".
            output_format (str, optional): The output format. Defaults to "md_dollar".
            convert (bool, optional): Convert "[" and "[[" to "$" and "$$". Defaults to False.
            oss_choose (str, optional): OSS upload preference. "always" for always using OSS, "auto" for using OSS only when the file size exceeds 100MB, "never" for never using OSS. Defaults to "always".
            merge_cross_page_forms (bool, optional): Whether to merge cross-page forms. Defaults to False.
            ocr (bool, optional): This option is deprecated and will not be used.
            save_subdir(bool, optional): Save the output to a subfolder under output_path. Defaults to False.
            export_history(str, optional): Export history file. Defaults to None.
        Returns:
            Tuple[List[str], List[dict], bool]: A tuple containing:
                - List[str]: List of output file paths
                - List[dict]: List of error messages
                - bool: Whether there was an error
        """
        if ocr:
            import warnings

            warnings.warn(
                "The 'ocr' option is deprecated and will not be used.",
                DeprecationWarning,
                stacklevel=2,
            )
        return run_async(
            self.pdf2file_back(
                pdf_file=pdf_file,
                output_names=output_names,
                output_path=output_path,
                output_format=output_format,
                convert=convert,
                oss_choose=oss_choose,
                merge_cross_page_forms=merge_cross_page_forms,
                save_subdir=save_subdir,
                export_history=export_history,
            )
        )
