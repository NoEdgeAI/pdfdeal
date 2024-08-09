import re
from typing import Tuple, Callable
import httpx
import os
from ..Doc2X.Exception import nomal_retry
import concurrent.futures


def get_imgcdnlink_list(text: str) -> Tuple[list, list]:
    """
    Extract the image links from the text.
    Return the image links list and the image path list.
    """
    patterns = [
        (r'<img\s+src="([^"]+)"\s+alt="([^"]*)">', lambda m: (m.group(0), m.group(1))),
        (
            r'<img\s+style="[^"]*"\s+src="([^"]+)"\s*/>',
            lambda m: (m.group(0), m.group(1)),
        ),
        (r'<img\s+src="([^"]+)"\s*/>', lambda m: (m.group(0), m.group(1))),
        (r"!\[[^\]]*\]\(([^)]+)\)", lambda m: (m.group(0), m.group(1))),
    ]

    origin_text_list = []
    imgpath_list = []

    for pattern, extract in patterns:
        for match in re.finditer(pattern, text):
            origin_text, src = extract(match)
            origin_text_list.append(origin_text)
            imgpath_list.append(src)

    return origin_text_list, imgpath_list


@nomal_retry()
def download_img_from_url(url: str, savepath: str) -> None:
    """
    Download the image from the url to the savepath, changing the extension based on the content type.
    """
    with httpx.stream("GET", url) as response:
        content_type = response.headers.get("Content-Type")
        if content_type:
            extension = content_type.split("/")[-1]
            savepath = f"{savepath}.{extension}"
        with open(savepath, "wb") as file:
            for chunk in response.iter_bytes():
                file.write(chunk)
        return extension


def md_replace_imgs(
    mdfile: str,
    replace,
    outputpath: str = "",
    relative: bool = False,
    threads: int = 5,
) -> bool:
    """Replace the image links in the markdown file (cdn links -> local file).

    Args:
        mdfile (str): The markdown file path.
        replace: Str or function to replace the image links. For str only "local" accepted. Defaults to "local".        outputpath (str, optional): The output path to save the images, if not set, will create a folder named as same as the markdown file name and add `_img`.
        relative (bool, optional): The output path to save the images with relative path. Defaults to False.
        threads (int, optional): The number of threads to download the images. Defaults to 5.

    Returns:
        bool: If all images are downloaded successfully, return True, else return False.
    """
    if isinstance(replace, str) and replace == "local":
        pass
    elif isinstance(replace, Callable):
        pass
    else:
        raise ValueError("The replace must be 'local' or a function.")

    with open(mdfile, "r", encoding="utf-8") as file:
        content = file.read()

    imglist, imgpath = get_imgcdnlink_list(content)
    if len(imglist) == 0:
        print("No image links found in the markdown file.")
        return True

    if outputpath == "":
        outputpath = os.path.splitext(mdfile)[0] + "_img"
    os.makedirs(outputpath, exist_ok=True)

    def download_image(i, imgurl, outputpath, relative, mdfile):
        if not imgurl.startswith("http"):
            print(f"===\nNot a valid url: {imgurl}, Skip it.")
            return None
        try:
            print(f"===\nDownloading the image: {imgurl}")
            savepath = f"{outputpath}/img{i}"
            extension = download_img_from_url(imgurl, savepath)
            savepath = f"{savepath}.{extension}"
            if relative:
                savepath = os.path.relpath(savepath, os.path.dirname(mdfile))
                return (imglist[i], f"![{imgurl}](<{savepath}>)\n")
            else:
                savepath = os.path.abspath(savepath)
                return (imglist[i], f'<img src="{savepath}" alt="{imgurl}">\n')
        except Exception as e:
            print(f"Error to download the image: {imgurl}, {e}")
            print("Continue to download the next image.")
            return None

    replacements = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [
            executor.submit(
                download_image,
                i,
                imgurl,
                outputpath,
                relative,
                mdfile,
            )
            for i, imgurl in enumerate(imgpath)
        ]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                replacements.append(result)

    for old, new in replacements:
        content = content.replace(old, new)

    with open(mdfile, "w", encoding="utf-8") as file:
        file.write(content)

    if len(replacements) < len(imglist):
        print("Some images download failed.")
        return False

    return True


def mds_replace_imgs(
    path: str,
    replace,
    outputpath: str = "",
    relative: bool = False,
    threads: int = 2,
    down_load_threads: int = 3,
) -> Tuple[list, list, bool]:
    """Replace the image links in the markdown file (cdn links -> local file).

    Args:
        path (str): The markdown file path.
        replace: Str or function to replace the image links. For str only "local" accepted. Defaults to "local".
        outputpath (str, optional): The output path to save the images, if not set, will create a folder named as same as the markdown file name and add `_img`. Only works when `replace` is "local".
        relative (bool, optional): Whether to save the images with relative path. Defaults to False, Only works when `replace` is "local".
        threads (int, optional): The number of threads to download the images. Defaults to 2.
        down_load_threads (int, optional): The number of threads to download the images in one md file. Defaults to 3.

    Returns:
        Tuple[list, list, bool]:
                `list1`: list of successfilly processed md file path, if the file failed, its path will be empty string
                `list2`: list of failed files's error message and its original file path, if some files are successful, its error message will be empty string
                `bool`: If all files are processed successfully, return True, else return False.
    """
    if isinstance(replace, str) and replace == "local":
        pass
    elif isinstance(replace, Callable):
        pass
    else:
        raise ValueError("The replace must be 'local' or a function.")

    from pdfdeal import gen_folder_list

    mdfiles = gen_folder_list(path=path, mode="md", recursive=True)
    if len(mdfiles) == 0:
        print("No markdown file found in the path.")
        return [], [], True

    import concurrent.futures

    def process_mdfile(mdfile, replace, outputpath, relative):
        try:
            md_replace_imgs(
                mdfile=mdfile,
                replace=replace,
                outputpath=outputpath,
                relative=relative,
                threads=down_load_threads,
            )
            return mdfile, None
        except Exception as e:
            return mdfile, e

    success_files = []
    fail_files = []
    Fail_flag = True

    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [
            executor.submit(process_mdfile, mdfile, replace, outputpath, relative)
            for mdfile in mdfiles
        ]
        for future in concurrent.futures.as_completed(futures):
            mdfile, error = future.result()
            if error:
                Fail_flag = False
                fail_files.append({"error": str(error), "path": mdfile})
                print(f"Error to process the markdown file: {mdfile}, {error}")
                print("Continue to process the next markdown file.")
            else:
                success_files.append(mdfile)

    print(
        f"\n[MARKDOWN REPLACE] Successfully processed {len(success_files)}/{len(mdfiles)} markdown files."
    )

    if Fail_flag is False:
        print("Some markdown files process failed.")
        return success_files, fail_files, True

    return success_files, fail_files, False
