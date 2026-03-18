import asyncio
import logging
from collections import deque
from typing import Dict, List, Optional, Union
from .Doc2X.ConvertV2 import parse_image_layout
from .Doc2X.Exception import RateLimit, run_async
from .Doc2X.Types import OutputFormat
from .FileTools.file_tools import get_files, save_md
import os
import copy

logger = logging.getLogger("pdfdeal.doc2x")

async def save_md_format(
        output_path: str,
        output_name: str,
        content: str = '',
        save_subdir: bool = False,
    ):
    """Save the text to md file 
    Args:
    output_path (str): The path to save the MD file
    output_name(str): MD file name
    content (list[dict]): The MD content to save
    """
    loop = asyncio.get_running_loop()
    saved_path, fail_reason = await loop.run_in_executor(
        None,
        save_md,
        output_path,
        output_name,
        content,
        save_subdir,
    )

    return saved_path, fail_reason

class ImageProcessor:
    """Image processor with rate limiting support"""

    def __init__(self, apikey: str):
        """Initialize the image processor
        Args:
            apikey (str): API key for authentication
        """
        self.apikey = apikey
        self._request_times = deque()
        self._lock = None
        self._loop = None
        self._rate = 30
        self._period = 30

    async def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            # Get the loop from the current async context
            self._loop = asyncio.get_running_loop()
            self._lock = asyncio.Lock() # Pass the loop explicitly
        return self._lock

    async def _check_rate_limit(self):
        """Check and enforce rate limit (30 requests per 30 seconds)"""
        lock = await self._get_lock()

        while True:
            async with lock:
                current_time = asyncio.get_event_loop().time()
                # Remove requests older than 30 seconds
                while self._request_times and (current_time - self._request_times[0] > self._period):
                    self._request_times.popleft()
                if len(self._request_times) < self._rate:
                    # Append new timestamp to sliding window
                    self._request_times.append(current_time)
                    return
                # Wait time until oldest timestamp pop out
                wait_time = self._period - (current_time - self._request_times[0])
            # Sleep outside the critical section to avoid holding the lock during sleep
            if wait_time > 0:
                logger.warning(
                    f"Rate limit reached, waiting for {wait_time:.2f} seconds. "
                    f"Current count: {len(self._request_times)}"
                )
                await asyncio.sleep(wait_time)


    async def process_image(
            self, 
            image_path: str, 
            process_type: str = "layout", 
            output_path: str = 'Output',
            save_subdir: bool = False,
        ) -> tuple[list, str, bool]:
        """Process an image with layout analysis

        Args:
            image_path (str): Path to the image file
            process_type (str): Type of processing, can be 'layout'
            output_path (str, optional): Path to save the result json and decoded base64 image zip. Defaults to Output.

        Returns:
            Tuple containing:
                - The processing result (list of pages for layout)
                - The uid of the processed image
                - Boolean indicating if the processing was successful
                - The failure information

        Raises:
            ValueError: If process_type is invalid or file type is not supported
            RateLimit: If rate limit is exceeded
        """


        if process_type not in ["layout"]:
            raise ValueError("process_type must be one of: 'layout'")

        if save_subdir:
            subdir_name = os.path.basename(image_path).split('.')[0]
            output_path = os.path.join(output_path, subdir_name)

        try:
            logger.info(f"Starting {process_type} processing for {image_path}")
            if process_type == "layout":
                await self._check_rate_limit()
                pages, uid, output_zip_path = await parse_image_layout(self.apikey, image_path, output_path)
                logger.info(
                    f"Successfully completed layout analysis for {image_path} with uid {uid}"
                )
                if output_zip_path != '':
                    logger.info(f"Layout results saved to zip file at {output_zip_path}")

                pages[0]['zip_path'] = output_zip_path
                pages[0]['path'] = image_path

                return pages, uid, True, ""
            else:
                logger.error(f"Error process_type: {process_type}")
                raise ValueError(f"Unsupported process_type: '{process_type}'")
        except RateLimit as e:
            logger.error(f"Rate limit exceeded while processing {image_path}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error processing image {image_path}: {str(e)}")
            return [], "", False, str(e)

    async def process_multiple_images(
        self,
        image_paths: List[str],
        output_format: str = 'text',
        process_type: str = "layout",
        output_path: str = 'Output/',
        save_subdir: bool = False,
        concurrent_limit: int = 5,
    ) -> tuple[List[list], Dict[str, bool]]:
        """Process multiple images concurrently with rate limiting

        Args:
            image_paths (List[str]): List of image file paths
            process_type (str): Type of processing, can be 'layout'
            output_format (str): The output format. Defaults to "text". Available values are 'text', 'md', ''md_dollar
            output_path (str): Path to save the result json and decoded base64 image zip. Defaults to Output.
            save_subdir (bool): Save the output to a subfolder under output_path. Defaults to False.
            concurrent_limit (int): Maximum number of concurrent processing tasks

        Returns:
            Tuple containing:
                - List of processing results in order (empty list for failed items)
                - Dict mapping image paths to their success status
        """
        semaphore = asyncio.Semaphore(concurrent_limit)

        async def process_with_semaphore(
                path: str,
                index: int,
            ) -> tuple[int, str, tuple[list, str, bool]]:
            async with semaphore:
                logger.debug(f"Processing image {index + 1}/{len(image_paths)}: {path}")
                output_result, uid, is_success, fail_reasons = await self.process_image(path, process_type, output_path, save_subdir)
                async def save_result_as_md(
                        image_path: str,
                        result
                    ):

                        all_results = []
                        all_errors = []

                        basename, ext = os.path.basename(image_path).split('.')

                        output_formats = []

                        if isinstance(output_format, str):
                            if "," in output_format:
                                output_formats = [fmt.strip() for fmt in output_format.split(",")]
                            else:
                                output_formats = [output_format]
                        else:
                            raise ValueError("Invalid output format, should be a string.")
                        for fmt in output_formats:
                            fmt = OutputFormat(fmt)
                            if isinstance(fmt, OutputFormat):
                                fmt = fmt.value


                            if fmt in ["md", "md_dollar"]:
                                if fmt == 'md_dollar':
                                    new_result = copy.deepcopy(result)
                                    new_result[0]['md'] = \
                                        new_result[0]['md'].replace('\\[', '$$').replace('\\]', '$$').replace('\\(', '$').replace('\\)', '$')
                                    
                                    output_result, fail_reason = await save_md_format(
                                        output_path=output_path,
                                        output_name=f'{basename}_dollar.md',
                                        content=new_result[0]['md'],
                                        save_subdir=save_subdir,
                                    )
                                elif fmt == 'md':
                                    new_result = copy.deepcopy(result)
                                    output_result, fail_reason = await save_md_format(
                                        output_path=output_path,
                                        output_name=f'{basename}.md',
                                        content=new_result[0]['md'],
                                        save_subdir=save_subdir,
                                    )
                            elif fmt in ['text']:
                                output_result = result
                                # 此处只会出现 在保存中 出现的错误，text不保存，不会出现错误
                                fail_reason = ''
                            
                            all_results.append(output_result)
                            all_errors.append(fail_reason)
                        
                        return all_results, all_errors
                        
                # 处理阶段失败的图片
                if not is_success:
                    results = []
                    fail_reasons = fail_reasons
                else: 
                    results, save_fail_reasons = await save_result_as_md(image_path=path, result=output_result)
                    if all(x != '' for x in save_fail_reasons):
                        fail_reasons = save_fail_reasons
                        is_success = False
                    else:
                        is_success = True
                        fail_reasons = save_fail_reasons


                return index, path, (results, fail_reasons, uid, is_success)

        tasks = [process_with_semaphore(path, i) for i, path in enumerate(image_paths)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results = [[] for _ in range(len(image_paths))]
        fail_reasons = ['' for _ in range(len(image_paths))]
        success_status = {}

        success_count = 0
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Failed to process a file: {str(result)}")
                continue

            index, path, (result_list, fail_reason, _, success) = result

            processed_results[index] = result_list if success else []
            fail_reasons[index] = fail_reason if not success else ''
            success_status[path] = success
            if success:
                success_count += 1

        logger.info(
            f"Batch processing completed. Successfully processed {success_count}/{len(image_paths)} images"
        )
        return processed_results, fail_reasons, success_status

    async def pic2file_back(
        self,
        pic_file,
        process_type: str = "layout",
        output_format: str = 'text',
        output_path: str = "./Output",
        save_subdir: bool = False,
        concurrent_limit: Optional[int] = None,
        ) -> tuple[List[Union[list, str]], List[dict], bool]:
        """Process image files with layout analysis

        Args:
            pic_file (str | List[str]): Path to image file(s) or directory
            process_type (str): Type of processing, can be 'layout'
            output_format (str): The output format. Defaults to "text". Available values are 'text', 'md', ''md_dollar
            output_path (str): Path to save the result json and decoded base64 image zip .Defaults to Output.
            save_subdir (bool): Save the output to a subfolder under output_path. Defaults to False.
            concurrent_limit (int, optional): Maximum number of concurrent tasks. Defaults to None.


        Returns:
            Tuple containing:
                - List of results in order (empty string for failed items)
                - List of dictionaries containing error information
                - Boolean indicating if any errors occurred
        """
        if isinstance(pic_file, str):
            if os.path.isdir(pic_file):
                pic_file, _ = get_files(path=pic_file, mode="img", out="zip")
            else:
                pic_file = [pic_file]


        
        success_results, failed_results, success_status = await self.process_multiple_images(
            image_paths=pic_file,
            process_type=process_type,
            concurrent_limit=concurrent_limit or 5,
            output_path=output_path,
            output_format=output_format,
            save_subdir=save_subdir,
        )


        failed_files = []
        has_error = False

        # Convert results to final format
        final_results = []
        success_count = 0
        for i, path in enumerate(pic_file):
            if not success_status.get(path, False):
                failed_files.append({"error": failed_results[i], "path": path}) 
                final_results.append([])
                has_error = True
                logger.error(f"Failed to process {path}, error: {failed_results[i]}")
            else:
                failed_files.append({"error": "", "path": ""})
                final_results.append(success_results[i])
                success_count += 1
                logger.debug(f"Successfully processed {path}")

        if has_error:
            logger.error(
                f"Processing completed with errors: {len([f for f in failed_files if f['error']])} file(s) failed"
            )
        else:
            logger.info(
                f"Processing completed successfully: {success_count} file(s) processed"
            )
        return final_results, failed_files, has_error

    def pic2file(
            self,
            pic_file,
            process_type: str = 'layout',
            output_format: str = 'text',
            output_path: str = 'Output',
            save_subdir: bool = False,
            concurrent_limit: Optional[int] = None,
        ) -> tuple[List[Union[list, str]], List[dict], bool]:
        """Synchronous wrapper for pic2file_back

        Args:
            pic_file (str | List[str]): Path to image file(s) or directory
            process_type (str): Type of processing, can be 'layout'
            output_format (str): The output format. Defaults to "text". Available values are 'text', 'md', ''md_dollar
            output_path (str): Path to save the result json and decoded base64 image zip .Defaults to Output.
            save_subdir (bool): Save the output to a subfolder under output_path. Defaults to False.
            concurrent_limit (int, optional): Maximum number of concurrent tasks. Defaults to None.


        Returns:
            Same as pic2file_back
        """
        return run_async(
            self.pic2file_back(
                pic_file=pic_file,
                process_type=process_type,
                output_format=output_format,
                output_path=output_path,
                save_subdir=save_subdir,
                concurrent_limit=concurrent_limit,
            )
        )
