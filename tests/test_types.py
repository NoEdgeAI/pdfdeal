import pytest

from pdfdeal.Doc2X.Types import FormulaLevel, normalize_formula_level


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
