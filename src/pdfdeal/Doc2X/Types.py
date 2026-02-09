from enum import Enum
from typing import Optional, Union


class OutputFormat(str, Enum):
    DOCX = "docx"
    TXTS = "texts"
    TXT = "text"
    DETAILED = "detailed"
    LATEX = "tex"
    MD = "md"
    MD_DOLLAR = "md_dollar"
    ZIP = "zip"
    JSON = "json"

    @classmethod
    def _missing_(cls, value):
        for member in cls:
            if member.value.lower() == value.lower():
                return member
        raise ValueError(
            f"{value} is not a valid {cls.__name__}, must be one of {', '.join([m.value for m in cls])}"
        )


class OutputFormat_Legacy(str, Enum):
    DOCX = "docx"
    TXTS = "texts"
    LATEX = "latex"
    MD = "md"
    MD_DOLLAR = "md_dollar"

    @classmethod
    def _missing_(cls, value):
        for member in cls:
            if member.value.lower() == value.lower():
                return member
        raise ValueError(
            f"{value} is not a valid {cls.__name__}, must be one of {', '.join([m.value for m in cls])}"
        )


class RAG_OutputType(str, Enum):
    PDF = "pdf"
    MD = "md"
    TEXTS = "texts"

    @classmethod
    def _missing_(cls, value):
        for member in cls:
            if member.value.lower() == value.lower():
                return member
        raise ValueError(
            f"{value} is not a valid {cls.__name__}, must be one of {', '.join([m.value for m in cls])}"
        )


class Support_File_Type(str, Enum):
    PDF = "pdf"
    IMG = "img"

    @classmethod
    def _missing_(cls, value):
        for member in cls:
            if member.value.lower() == value.lower():
                return member
        raise ValueError(
            f"{value} is not a valid {cls.__name__}, must be one of {', '.join([m.value for m in cls])}"
        )


class V2ParseModel(str, Enum):
    V3_2026 = "v3-2026"

    @classmethod
    def _missing_(cls, value):
        for member in cls:
            if member.value.lower() == value.lower():
                return member
        raise ValueError(
            f"{value} is not a valid {cls.__name__}, must be one of {', '.join([m.value for m in cls])}"
        )


V2ParseModelType = Optional[Union[str, V2ParseModel]]


def normalize_v2_parse_model(model: V2ParseModelType) -> str:
    if model is None:
        return ""
    if isinstance(model, V2ParseModel):
        return model.value

    model = model.strip()
    if not model:
        return ""

    return V2ParseModel(model).value
