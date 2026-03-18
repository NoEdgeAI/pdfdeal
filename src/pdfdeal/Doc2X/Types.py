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
    V2 = "v2"
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


class FormulaLevel(int, Enum):
    """Formula degradation levels for v2 export body.

    0 (default, recommended): Keep original formulas (no degradation).
    1: Degrade inline formulas to plain text (\\(...\\), $...$).
    2: Degrade all formulas to plain text, including inline and block formulas
       (\\(...\\), $...$, \\[...\\], $$...$$).
    """

    KEEP_MARKDOWN = 0
    INLINE_TO_TEXT = 1
    ALL_TO_TEXT = 2

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            try:
                value = int(value)
            except ValueError:
                pass
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(
            f"{value} is not a valid {cls.__name__}, must be one of {', '.join([str(m.value) for m in cls])}"
        )


FormulaLevelType = Optional[Union[int, str, FormulaLevel]]


def normalize_v2_parse_model(model: V2ParseModelType) -> str:
    if model is None:
        return ""
    if isinstance(model, V2ParseModel):
        return "" if model == V2ParseModel.V2 else model.value

    model = model.strip()
    if not model:
        return ""

    model_enum = V2ParseModel(model)
    return "" if model_enum == V2ParseModel.V2 else model_enum.value


def normalize_formula_level(formula_level: FormulaLevelType) -> int:
    if formula_level is None:
        return FormulaLevel.KEEP_MARKDOWN.value
    if isinstance(formula_level, FormulaLevel):
        return formula_level.value
    if isinstance(formula_level, bool):
        raise ValueError(
            "formula_level must be one of 0, 1, 2 "
            "(0=keep original formulas [default/recommended], "
            "1=degrade inline formulas, 2=degrade all formulas)"
        )

    try:
        level = FormulaLevel(formula_level)
    except (TypeError, ValueError):
        raise ValueError(
            "formula_level must be one of 0, 1, 2 "
            "(0=keep original formulas [default/recommended], "
            "1=degrade inline formulas, 2=degrade all formulas)"
        )

    return level.value
