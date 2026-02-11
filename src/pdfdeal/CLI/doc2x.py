import argparse
import os
from pdfdeal import Doc2X
from pdfdeal.Doc2X.Types import FormulaLevel, V2ParseModel


def main():
    parser = argparse.ArgumentParser(
        description="Using doc2x to deal with pictures or pdfs"
    )
    parser.add_argument("filename", help="PDF file/folder", nargs="?")
    parser.add_argument(
        "-y",
        help="Will skip any scenarios that require a second input from the user.",
        required=False,
        action="store_true",
    )
    parser.add_argument(
        "-k",
        "--api_key",
        help="The API key of Doc2X, if not set, will use the global setting",
        required=False,
    )
    parser.add_argument(
        "--thread",
        help="The thread limit of request, DO NOT set if you don't know",
        required=False,
    )
    parser.add_argument(
        "--max_pages",
        help="The maximum number of pages to process at same time, default is 1000, DO NOT set if you don't know",
        required=False,
    )
    parser.add_argument(
        "--model",
        help='Upload model for v2 preupload API, e.g. "v3-2026". Leave empty to use server default v2.',
        required=False,
        choices=[model.value for model in V2ParseModel],
    )
    parser.add_argument(
        "--formula_level",
        help=(
            'Formula degradation level for v2 export body. '
            '0=keep formulas, 1=inline formulas to text, 2=all formulas to text. '
            'Only effective when --model is "v3-2026".'
        ),
        required=False,
        type=int,
        choices=[level.value for level in FormulaLevel],
        default=FormulaLevel.KEEP_MARKDOWN.value,
    )
    parser.add_argument(
        "-o",
        "--output",
        help="The output folder of the result, if not set, will set to './Output'",
        required=False,
    )
    parser.add_argument(
        "-f",
        "--format",
        help="The output format of the result, accept md、md_dollar、tex、docx, default is md_dollar",
        required=False,
        choices=["md", "md_dollar", "tex", "docx"],
    )
    parser.add_argument(
        "--graphrag",
        help="Change md document to txt form, used for output is converted to the txt form accepted by graphRAG. The output format needs to be md or md_dollar at this time",
        required=False,
        action="store_true",
    )
    parser.add_argument(
        "--unzip",
        help="Unzip the output file, only works for the output is zip file",
        required=False,
        action="store_true",
    )
    # Only if need user input, will ask language
    args = parser.parse_args()

    if args.api_key is None:
        api_key = os.getenv("DOC2X_APIKEY")
        if api_key is None and not args.y:
            api_key = input("Please input the API key of Doc2X: ")
    else:
        api_key = str(args.api_key)

    if args.thread is not None:
        thread = int(args.thread)
    else:
        thread = 5

    if args.max_pages is not None:
        max_pages = int(args.max_pages)
    else:
        max_pages = 1000

    if args.filename is None:
        if args.y:
            filename = "./"
        else:
            filename = input("Please input the file/folder path: ")
    else:
        filename = args.filename

    output = args.output if args.output else "./Output"

    format = args.format if args.format else "md_dollar"

    Client = Doc2X(apikey=api_key, thread=thread, max_pages=max_pages, debug=True)

    if args.graphrag:
        assert format in [
            "md",
            "md_dollar",
        ], "The output format needs to be md or md_dollar at this time"

    success, fail, flag = Client.pdf2file(
        pdf_file=filename,
        output_path=output,
        output_format=format,
        model=args.model,
        formula_level=args.formula_level,
    )

    for file in success:
        if file != "":
            file = os.path.abspath(file)
            print(f"Save to: {file}")
    if flag:
        print("Some files failed to process, please check the error message.")
        print("Try to save the failed file path and reasons to fail.txt")
        try:
            with open("fail.txt", "w") as f:
                for file in fail:
                    if file["path"] != "":
                        f.write(str(file))
        except Exception as e:
            print(f"Failed to save the failed files to fail.txt: {e}")
            print("The failed files are:")
            for file in fail:
                print(file)

    if args.graphrag or args.unzip:
        from pdfdeal.FileTools.file_tools import unzip

        for file in success:
            if file != "" and file.endswith(".zip"):
                file = os.path.abspath(file)
                try:
                    unzip(zip_path=file, rename=True)
                except Exception as e:
                    print(f"Failed to unzip the file: {file}, error: {e}")
        output_folder = os.path.abspath(output)
        if args.graphrag:
            for root, dirs, files in os.walk(output_folder):
                for file in files:
                    if file.endswith(".md"):
                        file_path = os.path.join(root, file)
                        new_file_path = file_path[:-3] + ".txt"
                        os.rename(file_path, new_file_path)
        print(f"Unzip and rename the files in {output_folder} successfully.")

    print("==Have a nice day!===")


if __name__ == "__main__":
    main()
