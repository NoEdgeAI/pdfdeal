import io
import re
import unicodedata
import os
import zipfile
import shutil
from typing import Tuple
from ..Doc2X.Types import Support_File_Type, OutputFormat
from .dealmd import split_of_md
import logging


def clean_text(text):
    """
    Clean the text
    """
    import emoji

    # remove extra whitespaces
    text = re.sub(r"\n\s*\n", "\n\n", text)

    # remove special characters
    text = re.sub(r"-\d+-", "", text)

    def is_valid_unicode(char):
        # Check if a character is a valid unicode character
        try:
            unicodedata.name(char)
            return True
        except ValueError:
            return False

    cleaned_text = []
    for char in text:
        if (
            char.isalnum()
            or char.isspace()
            or emoji.is_emoji(char)
            or is_valid_unicode(char)
        ):
            cleaned_text.append(char)
    text = "".join(cleaned_text)

    return text


def clear_cache():
    """
    Clear the cache folder
    """
    temp_image_folder = os.path.join(
        os.path.expanduser("~"), ".cache", "pdfdeal", "pictures"
    )
    for file in os.listdir(temp_image_folder):
        file_path = os.path.join(temp_image_folder, file)
        if os.path.isfile(file_path):
            os.remove(file_path)

def gen_folder_list(path: str, mode: str, recursive: bool = False) -> list:
    """Generate a list of all files in the folder

    Args:
        path (str): The path of the folder to be processed
        mode (str): The type of file to find, 'pdf', 'img' or 'md'
        recursive (bool): Whether to search subdirectories recursively

    Raises:
        ValueError: If the mode is not 'pdf', 'img' or 'md'

    Returns:
        list: The list of full paths of the files
    """
    if os.path.isfile(path):
        raise ValueError("The input should be a folder.")

    def _find_files(path, mode):
        if mode == "pdf":
            return [
                os.path.join(path, f) for f in os.listdir(path) if f.endswith(".pdf")
            ]
        elif mode == "img":
            return [
                os.path.join(path, f)
                for f in os.listdir(path)
                if f.endswith(".png") or f.endswith(".jpg") or f.endswith(".jpeg")
            ]
        elif mode == "md":
            return [
                os.path.join(path, f) for f in os.listdir(path) if f.endswith(".md")
            ]
        else:
            raise ValueError("Mode should be 'pdf','img' or 'md'")

    if not recursive:
        return _find_files(path, mode)
    else:
        all_files = []
        for root, _, files in os.walk(path):
            all_files.extend(_find_files(root, mode))
        return all_files


def get_files(path: str, mode: str, out: str) -> Tuple[list, list]:
    """Generate a list of files in the folder, keeps the structure of the file the same before and after processing

    Args:
        path (str): The path of the folder to be processed
        mode (str): Which type of file to process, 'pdf' or 'img'
        out (str): Which type of file want to output, `md`, `md_dollar`, `latex` or `docx`, or `pdf` if you are using for RAG

    Returns:
        Tuple[list, list]: The list of full paths and relative paths, use in (like)`input` and `output_format`
    """
    # check if input is a file or a folder
    if os.path.isfile(path):
        raise ValueError("The input should be a folder.")
    mode = Support_File_Type(mode)
    if isinstance(mode, Support_File_Type):
        mode = mode.value
    if not out:
        out = "md_dollar"
    if out != "pdf":
        out = OutputFormat(out)
        if isinstance(out, OutputFormat):
            out = out.value
        out = out if out == "docx" else "zip"
    full_paths = []
    relative_paths = []

    if mode == "pdf":
        extensions = [".pdf"]
    elif mode == "img":
        extensions = [".jpg", ".jpeg", ".png"]

    if os.path.isfile(path):
        if any(path.lower().endswith(ext) for ext in extensions):
            full_paths.append(path)
            rel_path = os.path.relpath(path, os.path.dirname(path))
            rel_path_out = os.path.splitext(rel_path)[0] + "." + out
            relative_paths.append(rel_path_out)
            return full_paths, relative_paths

    for root, dirs, files in os.walk(path):
        for file in files:
            if any(file.lower().endswith(ext) for ext in extensions):
                full_path = os.path.join(root, file)
                full_paths.append(full_path)

                rel_path = os.path.relpath(full_path, path)
                rel_path_out = os.path.splitext(rel_path)[0] + "." + out
                relative_paths.append(rel_path_out)

    return full_paths, relative_paths


def unzip(zip_path: str, rename: bool = True) -> str:
    """Unzip the zip file and return the path of the extracted folder

    Args:
        zip_path (str): The path to the zip file
        rename (bool, optional): If rename the .md or .tex file with the unziped folder name. Defaults to True.

    Raises:
        Exception: If the zip file is not valid

    Returns:
        str: The path of the extracted folder
    """
    folder_name = os.path.splitext(os.path.basename(zip_path))[0]
    extract_path = os.path.join(os.path.dirname(zip_path), folder_name)
    os.makedirs(extract_path, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_path)
        os.remove(zip_path)
        if rename:
            # Only find the first .md or .tex file and rename it
            for root, _, files in os.walk(extract_path):
                for file in files:
                    if file.endswith(".md") or file.endswith(".tex"):
                        old_file_path = os.path.join(root, file)
                        new_file_path = os.path.join(
                            root, folder_name + os.path.splitext(file)[1]
                        )
                        os.rename(old_file_path, new_file_path)
                        return extract_path
        return extract_path
    except Exception as e:
        raise Exception(f"Unzip file error! {e}")


def unzips(zip_paths: list, rename: bool = True) -> Tuple[list, list, bool]:
    """Unzip the zip files and return the paths of the extracted folders

    Args:
        zip_paths (list): The list of paths to the zip files
        rename (bool, optional):  If rename the .md or .tex file with the unziped folder name. Defaults to True.

    Returns:
        Tuple[list,list,str]:
        will return `list1`,`list2`,`bool`
        `list1`: is the list of the output files, if some files are not unziped, the element will be `""`
        `list2`: is the list of the error message and its original file path, if some files are successfully unziped, the element will be `""`
        `bool`: True means that at least one file process failed
    """
    extract_paths = []
    failed_paths = []
    flag = False
    for zip_path in zip_paths:
        try:
            extract_paths.append(unzip(zip_path, rename))
            failed_paths.append("")
        except Exception as e:
            extract_paths.append("")
            failed_paths.append(f"Error deal with {zip_path} : {e}")
            flag = True
    return extract_paths, failed_paths, flag


def texts_to_file(texts, filepath, output_format="txt"):
    """
    Write texts to a file.
    `texts`: a list of strings, each string is a paragraph.
    `filepath`: the folder path of the file to write.
    `output_format`: the format of the output file, default is "txt",acceptable values are "txt", "md".

    Return the path of the output file.
    """
    import time

    if output_format not in ["txt", "md"]:
        raise ValueError("The output format is not supported.")
    if not os.path.exists(filepath):
        os.makedirs(filepath)
    try:
        temp_file = os.path.join(filepath, f"{time.time()}.{output_format}")
    except Exception as e:
        raise RuntimeError(f"Error: {e}")
    with open(temp_file, "w") as file:
        for text in texts:
            file.write(text)
            file.write("\n")
    return temp_file


def list_rename(files: list, new_name: list) -> list:
    """
    Rename files according to the new name list

    Args:
        `files`: list of files
        `new_name`: list of new names

    Return:
        `list`: list of new files
    """
    if len(files) != len(new_name):
        raise ValueError("The length of files and new_name should be the same.")
    new_files = []
    for file, name in zip(files, new_name):
        if file == "":
            new_files.append("")
            continue
        new_file = os.path.join(os.path.dirname(file), name)
        new_file_folder = os.path.dirname(new_file)
        os.makedirs(new_file_folder, exist_ok=True)
        if os.path.dirname(file) != new_file_folder:
            shutil.move(file, new_file_folder)
        os.rename(os.path.join(new_file_folder, os.path.basename(file)), new_file)
        new_files.append(new_file)
    return new_files


def auto_split_md(
    mdfile: str,
    mode: str = "auto",
    out_type: str = "single",
    split_str: str = "=+=+=+=+=+=+=+=+=",
    output_path: str = "./Output",
) -> Tuple[str, bool]:
    """Split the md file

    Args:
        mdfile (str): The path to md file
        mode (str, optional): The way to split. Support `auto`, `H1`, `H2`, `H3`. Defaults to "auto".
        out_type (str, optional): The way to output the splited file. Support `single`(one file) ,`replace`(replace the original file) and `multi`(multiple files) now. Defaults to "single".
        split_str (str, optional): The string to split the md file. Defaults to `=+=+=+=+=+=+=+=+=`.
        output_path (str, optional): The path to output the splited file. Defaults to "./Output". Not work when `out_type` is `replace`.

    Returns:
        Tuple[str,bool] : The path to the output file and whether the file is splited. If `out_type` is `multi", will return the path to the folder containing the splited files.
    """
    if not os.path.exists(mdfile):
        raise FileNotFoundError(f"The file {mdfile} does not exist.")
    elif os.path.isdir(mdfile):
        raise IsADirectoryError(f"The path {mdfile} is a directory.")

    try:
        new_content = split_of_md(mdfile=mdfile, mode=mode)
    except Exception as e:
        logging.exception(f"Error deal with {mdfile} :")
        return f"Error deal with {mdfile} : {e}", False

    if out_type == "multi":
        new_file_folder = os.path.join(output_path, os.path.basename(mdfile))
        os.makedirs(new_file_folder, exist_ok=True)
        for content in new_content:
            file_name = os.path.basename(mdfile) + content.split("\n")[0] + ".md"
            with open(
                os.path.join(new_file_folder, file_name), "w", encoding="utf-8"
            ) as file:
                file.writelines(content)
        return new_file_folder, True

    write_contene = ""
    for content in new_content:
        write_contene += split_str + "\n" + content + "\n"

    if out_type == "replace":
        with open(mdfile, "w", encoding="utf-8") as file:
            file.writelines(write_contene)
        return mdfile, True

    elif out_type == "single":
        if not os.path.exists(output_path):
            os.makedirs(output_path)
        new_file = os.path.join(output_path, os.path.basename(mdfile))
        with open(new_file, "w", encoding="utf-8") as file:
            file.writelines(write_contene)
        return new_file, True

    else:
        raise ValueError(f"The out_type {out_type} is not supported.")


def auto_split_mds(
    mdpath: str,
    mode: str = "auto",
    out_type: str = "single",
    split_str: str = "=+=+=+=+=+=+=+=+=",
    output_path: str = "./Output",
    recursive: bool = True,
) -> Tuple[list, list, bool]:
    """Split the md files in the folder

    Args:
        mdpath (str): The path to the folder containing md files
        mode (str, optional): The way to split. Support `auto`, `H1`, `H2`, `H3`. Defaults to "auto".
        out_type (str, optional): The way to output the splited file. Support `single`(one file) ,`replace`(replace the original file) and `multi`(multiple files) now. Defaults to "single".
        split_str (str, optional): The string to split the md file. Defaults to `=+=+=+=+=+=+=+=+=`.
        output_path (str, optional): The path to output the splited file. Defaults to "./Output". Not work when `out_type` is `replace`.
        recursive (bool, optional): Whether to search subdirectories recursively. Defaults to True.

    Returns:
        Tuple[list,list,str]:
        will return `list1`,`list2`,`bool`
        `list1`: is the list of the output files, if some files are not splited, the element will be `""`
        `list2`: is the list of the error message and its original file path, if some files are successfully splited, the element will be `""`
        `bool`: True means that at least one file process failed
    """
    if not os.path.exists(mdpath):
        raise FileNotFoundError(f"The path {mdpath} does not exist.")
    elif os.path.isfile(mdpath):
        raise IsADirectoryError(f"The path {mdpath} is a file.")

    md_files = gen_folder_list(mdpath, mode="md", recursive=recursive)
    if len(md_files) == 0:
        return [], "No md files found in the folder.", False
    success = []
    failed = []
    flag = False
    for mdfile in md_files:
        try:
            temp, is_splited = auto_split_md(
                mdfile=mdfile,
                mode=mode,
                out_type=out_type,
                split_str=split_str,
                output_path=output_path,
            )
            if is_splited:
                success.append(temp)
                failed.append({"error": "", "file": ""})
            else:
                success.append("")
                failed.append({"error": temp, "file": mdfile})
                flag = True
        except Exception as e:
            success.append("")
            failed.append({"error": e, "file": mdfile})
            flag = True
    logging.info(
        f"MD SPLIT: {sum([1 for i in success if i != ''])}/{len(success)} files are successfully splited."
    )
    logging.warning(f"Note the split string is :\n{split_str}")
    if flag:
        for failed_file in failed:
            if failed_file["error"] != "":
                logging.warning(
                    f"=====\nError deal with {failed_file['file']} : {failed_file['error']}"
                )
    return success, failed, flag
