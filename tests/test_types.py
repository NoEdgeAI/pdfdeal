import asyncio
import importlib

import pytest

from pdfdeal.Doc2X.Types import (
    FormulaLevel,
    V2ParseModel,
    normalize_formula_level,
    normalize_v2_parse_model,
)

convert_v2 = importlib.import_module("pdfdeal.Doc2X.ConvertV2")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 0),
        (FormulaLevel.KEEP_MARKDOWN, 0),
        (FormulaLevel.INLINE_TO_TEXT, 1),
        (FormulaLevel.ALL_TO_TEXT, 2),
        (0, 0),
        (1, 1),
        (2, 2),
        ("0", 0),
        ("1", 1),
        ("2", 2),
    ],
)
def test_normalize_formula_level_valid(value, expected):
    assert normalize_formula_level(value) == expected


@pytest.mark.parametrize("value", [-1, 3, "bad", True, False])
def test_normalize_formula_level_invalid(value):
    with pytest.raises(ValueError, match="formula_level must be one of 0, 1, 2"):
        normalize_formula_level(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        ("", ""),
        ("  ", ""),
        ("v2", ""),
        ("V2", ""),
        (V2ParseModel.V2, ""),
        ("v3-2026", "v3-2026"),
        ("V3-2026", "v3-2026"),
        (V2ParseModel.V3_2026, "v3-2026"),
    ],
)
def test_normalize_v2_parse_model_valid(value, expected):
    assert normalize_v2_parse_model(value) == expected


def test_normalize_v2_parse_model_invalid():
    with pytest.raises(ValueError, match="is not a valid V2ParseModel"):
        normalize_v2_parse_model("v3")


def test_upload_pdf_rejects_deprecated_direct_upload_mode():
    with pytest.raises(ValueError, match="direct upload endpoint has been deprecated"):
        asyncio.run(
            convert_v2.upload_pdf(
                "test_apikey", "tests/pdf/sample.pdf", oss_choose="never"
            )
        )


def test_upload_pdf_auto_still_uses_preupload(monkeypatch):
    calls = []

    async def fake_upload_pdf_big(apikey, pdffile, model=None):
        calls.append((apikey, pdffile, model))
        return "uid_123"

    monkeypatch.setattr(convert_v2, "upload_pdf_big", fake_upload_pdf_big)

    uid = asyncio.run(
        convert_v2.upload_pdf(
            "test_apikey",
            "tests/pdf/sample.pdf",
            oss_choose="auto",
            model=V2ParseModel.V3_2026,
        )
    )

    assert uid == "uid_123"
    assert calls == [("test_apikey", "tests/pdf/sample.pdf", V2ParseModel.V3_2026)]
