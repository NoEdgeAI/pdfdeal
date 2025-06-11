import asyncio
import logging
from collections import deque
from typing import Dict, List, Optional, Union
from .Doc2X.ConvertV2 import parse_image_layout
from .Doc2X.Exception import RateLimit, run_async
from .FileTools.file_tools import get_files
import os

logger = logging.getLogger("pdfdeal.doc2x")


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
        self, image_path: str, process_type: str = "layout", zip_path: str = None, output_name: str = None
    ) -> tuple[list, str, bool]:
        """Process an image with layout analysis

        Args:
            image_path (str): Path to the image file
            process_type (str): Type of processing, can be 'layout'
            zip_path (str, optional): Path to save the zip file for layout analysis. Defaults to None.
            output_name (str): output file name. Defaults to None.
        Returns:
            Tuple containing:
                - The processing result (list of pages for layout)
                - The uid of the processed image
                - Boolean indicating if the processing was successful

        Raises:
            ValueError: If process_type is invalid or file type is not supported
            RateLimit: If rate limit is exceeded
        """
        if process_type not in ["layout"]:
            raise ValueError("process_type must be one of: 'layout'")

        try:
            logger.info(f"Starting {process_type} processing for {image_path}")
            if process_type == "layout":
                await self._check_rate_limit()
                pages, uid = await parse_image_layout(self.apikey, image_path, zip_path, output_name)
                logger.info(
                    f"Successfully completed layout analysis for {image_path} with uid {uid}"
                )
                if zip_path:
                    logger.info(f"Layout results saved to zip file at {zip_path}")
                return pages, uid, True
            else:
                logger.error(f"Error process_type: {process_type}")
                raise ValueError(f"Unsupported process_type: '{process_type}'")
        except RateLimit as e:
            logger.error(f"Rate limit exceeded while processing {image_path}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error processing image {image_path}: {str(e)}")
            return [], "", False

    async def process_multiple_images(
        self,
        image_paths: List[str],
        process_type: str = "layout",
        concurrent_limit: int = 5,
        zip_path: str = None,
        output_zip_names: List[str] = None,
    ) -> tuple[List[list], Dict[str, bool]]:
        """Process multiple images concurrently with rate limiting

        Args:
            image_paths (List[str]): List of image file paths
            process_type (str): Type of processing, can be 'layout'
            concurrent_limit (int): Maximum number of concurrent processing tasks
            zip_path (str, optional): Path to save the zip file for layout analysis. Defaults to None.
            output_zip_names (List[str]): List of zip file name
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
                print(index, output_zip_names)
                logger.debug(f"Processing image {index + 1}/{len(image_paths)}: {path}")
                output_name = output_zip_names[index] if output_zip_names else None
                result = await self.process_image(path, process_type, zip_path, output_name)
                return index, path, result

        tasks = [process_with_semaphore(path, i) for i, path in enumerate(image_paths)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results = [[] for _ in range(len(image_paths))]
        success_status = {}

        success_count = 0
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Failed to process a file: {str(result)}")
                continue

            index, path, (result_list, _, success) = result
            processed_results[index] = result_list if success else []
            success_status[path] = success
            if success:
                success_count += 1

        logger.info(
            f"Batch processing completed. Successfully processed {success_count}/{len(image_paths)} images"
        )
        return processed_results, success_status

    async def pic2file_back(
        self,
        pic_file,
        process_type: str = "layout",
        concurrent_limit: Optional[int] = None,
        zip_path: str = None,
        output_zip_names: List[str] = None,
    ) -> tuple[List[Union[list, str]], List[dict], bool]:
        """Process image files with layout analysis

        Args:
            pic_file (str | List[str]): Path to image file(s) or directory
            process_type (str): Type of processing, can be 'layout'
            concurrent_limit (int, optional): Maximum number of concurrent tasks. Defaults to None.
            zip_path (str, optional): Path to save the zip file for layout analysis. Defaults to None.

        Returns:
            Tuple containing:
                - List of results in order (empty string for failed items)
                - List of dictionaries containing error information
                - Boolean indicating if any errors occurred
        """
        if isinstance(pic_file, str):
            if os.path.isdir(pic_file):
                pic_file, output_zip_names = get_files(path=pic_file, mode="img", out="zip")
            else:
                pic_file = [pic_file]

        results, success_status = await self.process_multiple_images(
            image_paths=pic_file,
            process_type=process_type,
            concurrent_limit=concurrent_limit or 5,
            zip_path=zip_path,
            output_zip_names=output_zip_names,
        )

        failed_files = []
        has_error = False

        # Convert results to final format
        final_results = []
        success_count = 0
        for i, path in enumerate(pic_file):
            if not success_status.get(path, False):
                failed_files.append({"error": "Processing failed", "path": path})
                final_results.append("")
                has_error = True
                logger.error(f"Failed to process {path}")
            else:
                failed_files.append({"error": "", "path": ""})
                final_results.append(results[i])
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
        process_type: str = "layout",
        concurrent_limit: Optional[int] = None,
        zip_path: str = None,
    ) -> tuple[List[Union[list, str]], List[dict], bool]:
        """Synchronous wrapper for pic2file_back

        Args:
            pic_file (str | List[str]): Path to image file(s) or directory
            process_type (str): Type of processing, can be 'layout'
            concurrent_limit (int, optional): Maximum number of concurrent tasks. Defaults to None.
            zip_path (str, optional): Path to save the zip file for layout analysis. Defaults to None.

        Returns:
            Same as pic2file_back
        """
        return run_async(
            self.pic2file_back(
                pic_file=pic_file,
                process_type=process_type,
                concurrent_limit=concurrent_limit,
                zip_path=zip_path,
            )
        )
