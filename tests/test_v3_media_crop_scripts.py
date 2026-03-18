import json
from pathlib import Path

import fitz
from pdfdeal.v3_media import extract_v3_figure_images, extract_v3_table_images


def _build_test_pdf(pdf_path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.draw_rect(fitz.Rect(20, 20, 120, 100), color=(1, 0, 0), fill=(1, 0.8, 0.8))
    page.draw_rect(
        fitz.Rect(40, 120, 180, 180), color=(0, 0, 1), fill=(0.8, 0.8, 1)
    )
    doc.save(pdf_path)
    doc.close()


def _build_test_v3_json(json_path: Path) -> None:
    payload = {
        "pages": [
            {
                "page_idx": 0,
                "page_width": 1000,
                "page_height": 1000,
                "layout": {
                    "blocks": [
                        {
                            "id": "figure_0",
                            "type": "Figure",
                            "bbox": [100, 100, 600, 500],
                        },
                        {
                            "id": "table_0",
                            "type": "Table",
                            "bbox": [200, 600, 900, 900],
                        },
                    ]
                },
            }
        ]
    }
    json_path.write_text(json.dumps(payload), encoding="utf-8")


def test_extract_v3_figure_crops(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    json_path = tmp_path / "sample.json"
    output_dir = tmp_path / "figures"

    _build_test_pdf(pdf_path)
    _build_test_v3_json(json_path)

    summary = extract_v3_figure_images(
        pdf_path=str(pdf_path),
        v3_json_path=str(json_path),
        dpi=144,
        output_dir=str(output_dir),
    )

    assert summary["crop_count"] == 1
    assert summary["page_count_with_targets"] == 1
    assert (output_dir / "_pages" / "page_0001.png").is_file()
    assert (output_dir / "manifest.json").is_file()
    crop_path = Path(summary["items"][0]["crop_path"])
    assert crop_path.is_file()


def test_extract_v3_table_crops(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    json_path = tmp_path / "sample.json"
    output_dir = tmp_path / "tables"

    _build_test_pdf(pdf_path)
    _build_test_v3_json(json_path)

    summary = extract_v3_table_images(
        pdf_path=str(pdf_path),
        v3_json_path=str(json_path),
        dpi=144,
        output_dir=str(output_dir),
    )

    assert summary["crop_count"] == 1
    assert summary["page_count_with_targets"] == 1
    assert (output_dir / "_pages" / "page_0001.png").is_file()
    assert (output_dir / "manifest.json").is_file()
    crop_path = Path(summary["items"][0]["crop_path"])
    assert crop_path.is_file()
