import asyncio
import os
from .Doc2X.Exception import RateLimit, run_async
from .Doc2X.Types import RAG_OutputType
from .Doc2X.Types import OutputFormat_Legacy as OutputFormat
from .FileTools.dealpdfs import strore_pdf
from typing import Tuple
from .FileTools.file_tools import list_rename
import uuid
import logging

from .Doc2X.ConvertV1 import (
    refresh_key,
    get_limit,
    uuid2file,
    upload_pdf,
    upload_img,
    uuid_status,
    check_folder,
    process_status,
)


async def get_key(apikey: str) -> str:
    """Get apikey from environment variable or input

    Args:
        apikey (str): The apikey, or get from environment variable `DOC2X_APIKEY`

    Raises:
        ValueError: If no apikey found

    Returns:
        str: Your real apikey
    """
    if apikey is None:
        apikey = os.environ.get("DOC2X_APIKEY", "")
    if apikey == "":
        raise ValueError("No apikey found")
    if not apikey.startswith("sk-"):
        apikey = await refresh_key(apikey)
    return apikey


async def pdf2file_v1(
        apikey: str,
        pdf_path: str,
        output_path: str,
        output_format: str,
        ocr: bool,
        maxretry: int,
        rpm: int,
        convert: bool,
        translate: bool = False,
        language: str = "zh",
        model: str = "deepseek",
):
    """
    Convert pdf file to specified file,
    """
    # Upload the file and get uuid
    try:
        uuid = await upload_pdf(
            apikey=apikey,
            pdffile=pdf_path,
            ocr=ocr,
            translate=translate,
            language=language,
            model=model,
        )
    except RateLimit:
        while True:
            logging.warning("Reach the rate limit, wait for 25 seconds")
            await asyncio.sleep(25)
            try:
                uuid = await upload_pdf(
                    apikey=apikey,
                    pdffile=pdf_path,
                    ocr=ocr,
                    translate=translate,
                    language=language,
                    model=model,
                )
                break
            except RateLimit:
                continue
    # Wait for the process to finish
    while True:
        status_process, status_str, texts, other = await uuid_status(
            apikey=apikey, uuid=uuid, convert=convert, translate=translate
        )
        if status_process == 100 and status_str == "Success" and not translate:
            # If output_format is texts, return texts directly
            if output_format == "texts":
                return texts
            logging.info(
                f"{status_str} - Exporting document: {status_process}%    -- uuid: {uuid}"
            )
            break
        # If translate is True, return texts and other(texts location inside)
        elif status_process == 100 and status_str == "Translate success":
            final = {"texts": texts, "location": other}
            return final
        logging.info(f"{status_str}: {status_process}%    -- uuid: {uuid}")
        await asyncio.sleep(1)
    # Convert uuid to file
    return await uuid2file(
        apikey=apikey, uuid=uuid, output_path=output_path, output_format=output_format
    )


async def img2file_v1(
        apikey: str,
        img_path: str,
        output_path: str,
        output_format: str,
        formula: bool,
        img_correction: bool,
        maxretry: int,
        rpm: int,
        convert: bool,
) -> str:
    """
    Convert image file to specified file
    """
    try:
        uuid = await upload_img(
            apikey=apikey,
            imgfile=img_path,
            formula=formula,
            img_correction=img_correction,
        )
    except RateLimit:
        # Retry according to maxretry and current rpm
        while True:
            logging.warning("Reach the rate limit, wait for 25 seconds")
            await asyncio.sleep(25)
            try:
                uuid = await upload_img(
                    apikey=apikey,
                    imgfile=img_path,
                    formula=formula,
                    img_correction=img_correction,
                )
                break
            except RateLimit:
                continue
    # Wait for the process to finish
    while True:
        status_process, status_str, texts, other = await uuid_status(
            apikey=apikey, uuid=uuid, convert=convert
        )
        if status_process == 100 and status_str == "Success":
            # If output_format is texts, return texts directly
            if output_format == "texts":
                return texts
            logging.info(f"{status_str}: {status_process}%    -- uuid: {uuid}")
            break
        logging.info(f"{status_str}: {status_process}%    -- uuid: {uuid}")
        await asyncio.sleep(1)
    return await uuid2file(
        apikey=apikey, uuid=uuid, output_path=output_path, output_format=output_format
    )


class Doc2X:
    """Init the Doc2X class(V1)"""

    def __init__(
            self,
            apikey: str = None,
            rpm: int = None,
            thread: int = None,
    ) -> None:
        """Init the Doc2X class

        Args:
            apikey (str, optional): Your doc2x apikey. Defaults to read from environment variable `DOC2X_APIKEY`.
            rpm (int, optional): The rate of concurrent processing. Defaults will be auto set according to the apikey. Please use `thread` instead of `rpm`.
            thread (int, optional): The rate of concurrent processing. Defaults will be auto set according to the apikey.
        """
        self.apikey = run_async(get_key(apikey))
        if rpm is not None and thread is not None:
            raise ValueError(
                "Please use `rpm` or `thread`, not both. Suggest to use `thread`."
            )
        elif thread is not None:
            self.rpm = thread
        elif rpm is not None:
            import warnings

            warnings.warn(
                "The `rpm` parameter is deprecated and will be removed in the future. Please use the `thread` parameter instead.",
            )
            self.rpm = rpm
        else:
            if self.apikey.startswith("sk-"):
                self.rpm = 10
            else:
                self.rpm = 1
        self.maxretry = None

    async def pic2file_back(
            self,
            image_file: list,
            output_path: str = "./Output",
            output_format: str = "md_dollar",
            img_correction: bool = True,
            equation=False,
            convert: bool = False,
    ) -> str:
        """
        Convert image file to specified file, with rate/thread limit
        input refers to `pic2file` function
        """
        limit = asyncio.Semaphore(self.rpm)

        async def limited_img2file_v1(img):
            try:
                await limit.acquire()
                return await img2file_v1(
                    apikey=self.apikey,
                    img_path=img,
                    output_path=output_path,
                    output_format=output_format,
                    formula=equation,
                    img_correction=img_correction,
                    maxretry=self.maxretry,
                    rpm=self.rpm,
                    convert=convert,
                )
            except Exception as e:
                return f"Error {e}"
            finally:
                limit.release()

        task = [limited_img2file_v1(img) for img in image_file]
        completed_tasks = await asyncio.gather(*task)
        return await process_status(image_file, completed_tasks)

    def pic2file(
            self,
            image_file,
            output_path: str = "./Output",
            output_names: list = None,
            output_format: str = "md_dollar",
            img_correction: bool = True,
            equation: bool = False,
            convert: bool = False,
    ) -> Tuple[list, list, bool]:
        """Convert image file to specified file

        Args:
            image_file (str or list): Image file path, or a list of image file path
            output_path (str, optional): Output folder path. Defaults to "./Output".
            output_names (list, optional): Custom Output File Names, must be the same length as `image_file`. Defaults to None.
            output_format (str, optional): Output format, accept `texts`, `md`, `md_dollar`, `latex`, `docx`. Defaults to `md_dollar`.
            img_correction (bool, optional): The image correction. Defaults to True.
            equation (bool, optional): Whether the image is an equation. Defaults to False.
            convert (bool, optional): Whether to convert `[` to `$` and `[[` to `$$`. Defaults to False.

        Raises:
            ValueError: The length of files and output_names should be the same.

        Returns:
            tuple[list,list,str]:
            will return `list1`,`list2`,`bool`
                `list1`: list of successful files path, if some files are failed, its path will be empty string
                `list2`: list of failed files's error message and its original file path, id some files are successful, its error message will be empty string
                `bool`: True means that at least one file process failed
        """
        output_format = OutputFormat(output_format)
        if isinstance(output_format, OutputFormat):
            output_format = output_format.value

        if isinstance(image_file, str):
            image_file = [image_file]

        if output_names is not None:
            if len(image_file) != len(output_names):
                raise ValueError(
                    "The length of files and output_names should be the same."
                )

        success, failed, flag = run_async(
            self.pic2file_back(
                image_file,
                output_path,
                output_format,
                img_correction,
                equation,
                convert,
            )
        )

        logging.info(
            f"IMG Progress: {sum(1 for s in success if s != '')}/{len(image_file)} files successfully processed."
        )
        if flag:
            for failed_file in failed:
                if failed_file["error"] != "":
                    logging.error(
                        f"-----\nFailed deal with {failed_file['path']} with error:\n{failed_file['error']}\n-----"
                    )

        if output_names is not None:
            success = list_rename(success, output_names)

        return success, failed, flag

    async def pdf2file_back(
            self,
            pdf_file: list,
            output_path: str = "./Output",
            output_format: str = "md_dollar",
            ocr: bool = True,
            convert: bool = False,
            translate: bool = False,
            language: str = "zh",
            model: str = "deepseek",
    ) -> str:
        """
        Convert pdf file to specified file, with rate/thread limit, async version
        input refers to `pdf2file` function
        """
        limit = asyncio.Semaphore(self.rpm)

        async def limited_pdf2file_v1(pdf):
            try:
                await limit.acquire()
                return await pdf2file_v1(
                    apikey=self.apikey,
                    pdf_path=pdf,
                    output_path=output_path,
                    output_format=output_format,
                    ocr=ocr,
                    maxretry=self.maxretry,
                    rpm=self.rpm,
                    convert=convert,
                    translate=translate,
                    language=language,
                    model=model,
                )
            except Exception as e:
                return f"Error {e}"
            finally:
                limit.release()

        tasks = [limited_pdf2file_v1(pdf) for pdf in pdf_file]
        completed_tasks = await asyncio.gather(*tasks)
        return await process_status(pdf_file, completed_tasks)

    def pdf2file(
            self,
            pdf_file,
            output_path: str = "./Output",
            output_names: list = None,
            output_format: str = "md_dollar",
            ocr: bool = True,
            convert: bool = False,
    ) -> Tuple[list, list, bool]:
        """Convert pdf file to specified file

        Args:
            pdf_file (str or list): pdf file path, or a list of pdf file path
            output_path (str, optional): output folder path. Defaults to "./Output".
            output_names (list, optional): Custom Output File Names, must be the same length as `pdf_file`. Defaults to None.
            output_format (str, optional): output format, accept `texts`, `md`, `md_dollar`, `latex`, `docx`. Defaults to `md_dollar`.
            ocr (bool, optional): whether to use OCR. Defaults to True.
            convert (bool, optional): whether to convert `[` to `$` and `[[` to `$$`. Defaults to False.

        Raises:
            ValueError: The length of files and output_names should be the same.

        Returns:
            tuple[list,list,str]:
            will return `list1`,`list2`,`bool`
                `list1`: list of successful files path, if some files are failed, its path will be empty string
                `list2`: list of failed files's error message and its original file path, id some files are successful, its error message will be empty string
                `bool`: True means that at least one file process failed
        """
        output_format = OutputFormat(output_format)
        if isinstance(output_format, OutputFormat):
            output_format = output_format.value

        if isinstance(pdf_file, str):
            pdf_file = [pdf_file]

        if output_names is not None:
            if len(pdf_file) != len(output_names):
                raise ValueError(
                    "The length of files and output_names should be the same."
                )

        success, failed, flag = run_async(
            self.pdf2file_back(
                pdf_file, output_path, output_format, ocr, convert, False
            )
        )
        logging.info(
            f"PDF Progress: {sum(1 for s in success if s != '')}/{len(pdf_file)} files successfully processed."
        )
        if flag:
            for failed_file in failed:
                if failed_file["error"] != "":
                    logging.error(
                        f"-----\nFailed deal with {failed_file['path']} with error:\n{failed_file['error']}\n-----"
                    )

        if output_names is not None:
            success = list_rename(success, output_names)

        return success, failed, flag

    def get_limit(self) -> int:
        """Get the rate limit of the apikey

        Returns:
            int: The rate limit of the apikey
        """
        return run_async(get_limit(self.apikey))

    async def pdfdeal_back(
            self,
            input: str,
            output: str,
            path: str,
            convert: bool,
            limit: asyncio.Semaphore,
    ):
        """
        Convert pdf files into recognisable pdfs, significantly improving their effectiveness in RAG systems
        async version function
        """
        try:
            await limit.acquire()
            texts = await pdf2file_v1(
                apikey=self.apikey,
                pdf_path=input,
                output_path=output,
                output_format="texts",
                ocr=True,
                maxretry=self.maxretry,
                rpm=self.rpm,
                convert=convert,
                translate=False,
            )
            await check_folder(path)
            file_name = os.path.basename(input).replace(
                ".pdf", f"_{uuid.uuid4()}.{output}"
            )
            output_path = os.path.join(path, file_name)
            if output == "pdf":
                strore_pdf(output_path, texts)
            elif output == "texts":
                return texts, "", True
            else:
                md_text = "\n".join(texts) + "\n"
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(md_text)
            return output_path, "", True
        except Exception as e:
            return input, e, False
        finally:
            limit.release()

    async def pdfdeals(
            self,
            pdf_files: list,
            output_path: str = "./Output",
            output_format: str = "pdf",
            convert: bool = True,
    ) -> list:
        """
        Convert pdf files into recognisable pdfs, significantly improving their effectiveness in RAG systems
        async version function, input refers to `pdfdeal` function
        """
        limit = asyncio.Semaphore(self.rpm)
        tasks = [
            self.pdfdeal_back(pdf_file, output_format, output_path, convert, limit)
            for pdf_file in pdf_files
        ]
        completed_tasks = await asyncio.gather(*tasks)
        success_file = []
        error_file = []
        error_flag = False
        for temp in completed_tasks:
            path = temp[0]
            error = temp[1]
            flag = temp[2]
            if flag:
                success_file.append(path)
                error_file.append({"error": "", "path": ""})
            else:
                success_file.append("")
                error_file.append({"error": error, "path": path})
                error_flag = True
        return success_file, error_file, error_flag

    def pdfdeal(
            self,
            pdf_file,
            output_format: str = "pdf",
            output_names: list = None,
            output_path: str = "./Output",
            convert: bool = True,
    ) -> Tuple[list, list, bool]:
        """Deal with pdf file, convert it to specified format for RAG system

        Args:
            pdf_file (str or list): input file path, or a list of input file path
            output_format (str, optional): output format, accept 'pdf', 'md' or 'texts'. Defaults to "pdf".
            output_names (list, optional): Custom Output File Names, must be the same length as `image_file`. Defaults to None.
            output_path (str, optional): output path. Defaults to "./Output".
            convert (bool, optional): Whether to convert "[" to "$" and "[[" to "$$". Defaults to True.

        Returns:
            tuple[list,list,str]:
            will return `list1`,`list2`,`bool`
                `list1`: list of successful files path, if some files are failed, its path will be empty string
                `list2`: list of failed file's error message and its original file path, id some files are successful, its error message will be empty string
                `bool`: True means that at least one file process failed
        """
        output_format = RAG_OutputType(output_format)
        if isinstance(output_format, RAG_OutputType):
            output_format = output_format.value

        if isinstance(pdf_file, str):
            pdf_file = [pdf_file]

        success, failed, flag = run_async(
            self.pdfdeals(pdf_file, output_path, output_format, convert)
        )
        logging.info(
            f"PDFDEAL Progress: {sum(1 for s in success if s != '')}/{len(pdf_file)} files successfully processed."
        )
        if flag:
            for failed_file in failed:
                if failed_file["error"] != "":
                    logging.error(
                        f"-----\nFailed deal with {failed_file['path']} with error:\n{failed_file['error']}\n-----"
                    )

        if output_names is not None:
            success = list_rename(success, output_names)

        return success, failed, flag