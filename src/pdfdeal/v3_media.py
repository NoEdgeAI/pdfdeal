from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import fitz
except ImportError as exc:  # pragma: no cover - runtime guard
    raise SystemExit(
        "PyMuPDF is required. Install it with `pip install pymupdf`."
    ) from exc

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - runtime guard
    raise SystemExit(
        "Pillow is required. Install it with `pip install pillow`."
    ) from exc


TARGET_KIND_TO_BLOCK_TYPE = {
    "figure": "Figure",
    "table": "Table",
}


class V3ValidationError(ValueError):
    pass


def load_v3_result(json_path: str) -> Dict[str, Any]:
    path = Path(json_path)
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload, dict):
        if isinstance(payload.get("pages"), list):
            return payload
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("result"), dict):
            return data["result"]
        result = payload.get("result")
        if isinstance(result, dict) and isinstance(result.get("pages"), list):
            return result

    raise V3ValidationError(
        "Unsupported v3 JSON structure. Expected either raw `result` with `pages`, "
        "or a wrapped response containing `data.result.pages`."
    )


def _safe_stem(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text.strip())
    return cleaned.strip("._-") or "item"


def _ensure_xyxy(value: Any, label: str) -> Tuple[float, float, float, float]:
    if not isinstance(value, list) or len(value) != 4:
        raise V3ValidationError(f"{label} must be a list of 4 numbers.")
    try:
        x1, y1, x2, y2 = (float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise V3ValidationError(f"{label} must contain only numeric values.") from exc
    if x2 <= x1 or y2 <= y1:
        raise V3ValidationError(f"{label} must satisfy x2>x1 and y2>y1.")
    return x1, y1, x2, y2


def _page_xyxy(page: Dict[str, Any]) -> Tuple[float, float, float, float]:
    for key in ("page_xyxy", "page_bbox", "bbox", "xyxy"):
        if key in page:
            return _ensure_xyxy(page[key], f"page.{key}")

    width = page.get("page_width")
    height = page.get("page_height")
    if not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
        raise V3ValidationError(
            "Each page must provide positive `page_width` and `page_height`, or an "
            "explicit `page_xyxy/page_bbox`."
        )
    if width <= 0 or height <= 0:
        raise V3ValidationError("`page_width` and `page_height` must be positive.")
    return 0.0, 0.0, float(width), float(height)


def _block_xyxy(block: Dict[str, Any]) -> Tuple[float, float, float, float]:
    for key in ("bbox", "xyxy"):
        if key in block:
            return _ensure_xyxy(block[key], f"block.{key}")
    raise V3ValidationError(
        f"Block {block.get('id', '<unknown>')} is missing `bbox`/`xyxy`."
    )


def _validate_ratio(
    pdf_page: "fitz.Page",
    page_xyxy: Tuple[float, float, float, float],
    page_idx: int,
) -> None:
    json_width = page_xyxy[2] - page_xyxy[0]
    json_height = page_xyxy[3] - page_xyxy[1]
    pdf_ratio = pdf_page.rect.width / pdf_page.rect.height
    json_ratio = json_width / json_height
    ratio_delta = abs(pdf_ratio - json_ratio) / json_ratio
    if ratio_delta > 0.02:
        raise V3ValidationError(
            f"Page {page_idx} aspect ratio mismatch: PDF={pdf_ratio:.6f}, "
            f"v3-json={json_ratio:.6f}. This violates the crop mapping rule."
        )


def _validate_block_within_page(
    block_xyxy: Tuple[float, float, float, float],
    page_xyxy: Tuple[float, float, float, float],
    block_id: str,
) -> None:
    bx1, by1, bx2, by2 = block_xyxy
    px1, py1, px2, py2 = page_xyxy
    if bx1 < px1 or by1 < py1 or bx2 > px2 or by2 > py2:
        raise V3ValidationError(
            f"Block {block_id} bbox {list(block_xyxy)} exceeds page bounds "
            f"{list(page_xyxy)}."
        )


def validate_v3_result(
    result: Dict[str, Any],
    pdf_path: str,
    target_block_type: str,
) -> List[Dict[str, Any]]:
    pages = result.get("pages")
    if not isinstance(pages, list) or not pages:
        raise V3ValidationError("`pages` must be a non-empty list.")

    validated_pages: List[Dict[str, Any]] = []
    seen_page_idx = set()

    with fitz.open(pdf_path) as doc:
        for page in pages:
            if not isinstance(page, dict):
                raise V3ValidationError("Each page entry must be an object.")

            page_idx = page.get("page_idx")
            if not isinstance(page_idx, int):
                raise V3ValidationError("Each page must provide integer `page_idx`.")
            if page_idx in seen_page_idx:
                raise V3ValidationError(f"Duplicate page_idx detected: {page_idx}.")
            if page_idx < 0 or page_idx >= doc.page_count:
                raise V3ValidationError(
                    f"page_idx {page_idx} is out of PDF page range 0..{doc.page_count - 1}."
                )
            seen_page_idx.add(page_idx)

            layout = page.get("layout")
            if not isinstance(layout, dict):
                raise V3ValidationError(
                    f"Page {page_idx} is missing object field `layout`."
                )
            blocks = layout.get("blocks")
            if not isinstance(blocks, list):
                raise V3ValidationError(
                    f"Page {page_idx} is missing list field `layout.blocks`."
                )

            page_xyxy = _page_xyxy(page)
            pdf_page = doc.load_page(page_idx)
            _validate_ratio(pdf_page, page_xyxy, page_idx)

            target_blocks = []
            for block in blocks:
                if not isinstance(block, dict):
                    raise V3ValidationError(
                        f"Page {page_idx} contains a non-object block entry."
                    )
                block_type = block.get("type")
                block_id = str(block.get("id", ""))
                if not isinstance(block_type, str) or not block_type:
                    raise V3ValidationError(
                        f"Page {page_idx} has a block without valid `type`."
                    )
                if block_type != target_block_type:
                    continue
                block_xyxy = _block_xyxy(block)
                _validate_block_within_page(
                    block_xyxy, page_xyxy, block_id or "<unknown>"
                )
                target_blocks.append(
                    {
                        "id": block_id or f"{target_block_type.lower()}_{page_idx}",
                        "type": block_type,
                        "xyxy": block_xyxy,
                        "parent_id": str(block.get("parent_id", "")),
                        "src": str(block.get("src", "")),
                        "text": str(block.get("text", "")),
                    }
                )

            if target_blocks:
                validated_pages.append(
                    {
                        "page_idx": page_idx,
                        "page_xyxy": page_xyxy,
                        "page_width": page_xyxy[2] - page_xyxy[0],
                        "page_height": page_xyxy[3] - page_xyxy[1],
                        "target_blocks": target_blocks,
                    }
                )

    return validated_pages


def _page_image_to_pil(page_pixmap: "fitz.Pixmap") -> Image.Image:
    mode = "RGB"
    if page_pixmap.alpha:
        mode = "RGBA"
    return Image.frombytes(
        mode, [page_pixmap.width, page_pixmap.height], page_pixmap.samples
    )


def _crop_box_in_pixels(
    block_xyxy: Tuple[float, float, float, float],
    page_xyxy: Tuple[float, float, float, float],
    image_width: int,
    image_height: int,
) -> Tuple[int, int, int, int]:
    px1, py1, px2, py2 = page_xyxy
    bx1, by1, bx2, by2 = block_xyxy
    page_width = px2 - px1
    page_height = py2 - py1
    x1 = int(round((bx1 - px1) / page_width * image_width))
    y1 = int(round((by1 - py1) / page_height * image_height))
    x2 = int(round((bx2 - px1) / page_width * image_width))
    y2 = int(round((by2 - py1) / page_height * image_height))
    x1 = max(0, min(x1, image_width - 1))
    y1 = max(0, min(y1, image_height - 1))
    x2 = max(x1 + 1, min(x2, image_width))
    y2 = max(y1 + 1, min(y2, image_height))
    return x1, y1, x2, y2


def extract_target_images(
    pdf_path: str,
    v3_json_path: str,
    dpi: int,
    output_dir: str,
    target_kind: str,
) -> Dict[str, Any]:
    if target_kind not in TARGET_KIND_TO_BLOCK_TYPE:
        raise ValueError(
            f"Unsupported target_kind={target_kind!r}. "
            f"Choose one of {sorted(TARGET_KIND_TO_BLOCK_TYPE)}."
        )
    if dpi <= 0:
        raise ValueError("dpi must be a positive integer.")

    target_block_type = TARGET_KIND_TO_BLOCK_TYPE[target_kind]
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    page_images_dir = output_path / "_pages"
    page_images_dir.mkdir(parents=True, exist_ok=True)

    result = load_v3_result(v3_json_path)
    validated_pages = validate_v3_result(result, pdf_path, target_block_type)

    manifest: List[Dict[str, Any]] = []
    page_render_count = 0

    with fitz.open(pdf_path) as doc:
        matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        for page_info in validated_pages:
            page_idx = page_info["page_idx"]
            page = doc.load_page(page_idx)
            page_pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            page_image = _page_image_to_pil(page_pixmap)
            page_image_path = page_images_dir / f"page_{page_idx + 1:04d}.png"
            page_image.save(page_image_path)
            page_render_count += 1

            for block_idx, block in enumerate(page_info["target_blocks"], start=1):
                crop_box = _crop_box_in_pixels(
                    block_xyxy=block["xyxy"],
                    page_xyxy=page_info["page_xyxy"],
                    image_width=page_image.width,
                    image_height=page_image.height,
                )
                crop_image = page_image.crop(crop_box)
                crop_name = (
                    f"page_{page_idx + 1:04d}_{target_kind}_{block_idx:03d}_"
                    f"{_safe_stem(block['id'])}.png"
                )
                crop_path = output_path / crop_name
                crop_image.save(crop_path)
                manifest.append(
                    {
                        "page_idx": page_idx,
                        "page_image_path": str(page_image_path),
                        "target_kind": target_kind,
                        "block_id": block["id"],
                        "block_type": block["type"],
                        "block_xyxy": list(block["xyxy"]),
                        "page_xyxy": list(page_info["page_xyxy"]),
                        "crop_box_pixels": list(crop_box),
                        "crop_path": str(crop_path),
                    }
                )

    manifest_path = output_path / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "pdf_path": str(Path(pdf_path)),
                "v3_json_path": str(Path(v3_json_path)),
                "dpi": dpi,
                "target_kind": target_kind,
                "target_block_type": target_block_type,
                "page_count_with_targets": page_render_count,
                "crop_count": len(manifest),
                "items": manifest,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    return {
        "output_dir": str(output_path),
        "page_images_dir": str(page_images_dir),
        "manifest_path": str(manifest_path),
        "page_count_with_targets": page_render_count,
        "crop_count": len(manifest),
        "items": manifest,
    }


def extract_v3_figure_images(
    pdf_path: str,
    v3_json_path: str,
    dpi: int,
    output_dir: str,
) -> Dict[str, Any]:
    return extract_target_images(
        pdf_path=pdf_path,
        v3_json_path=v3_json_path,
        dpi=dpi,
        output_dir=output_dir,
        target_kind="figure",
    )


def extract_v3_table_images(
    pdf_path: str,
    v3_json_path: str,
    dpi: int,
    output_dir: str,
) -> Dict[str, Any]:
    return extract_target_images(
        pdf_path=pdf_path,
        v3_json_path=v3_json_path,
        dpi=dpi,
        output_dir=output_dir,
        target_kind="table",
    )


def build_parser(target_kind: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            f"Extract {target_kind} crops from a PDF using Doc2X v3 JSON. "
            "The script first validates that the v3 JSON matches the crop rules, "
            "renders only pages containing target blocks, saves full-page PNGs "
            "under `_pages/`, and writes cropped images plus `manifest.json`."
        )
    )
    parser.add_argument("--pdf", required=True, help="Path to the source PDF.")
    parser.add_argument(
        "--v3-json",
        required=True,
        help="Path to the raw v3 JSON (`result`) or wrapped response JSON.",
    )
    parser.add_argument(
        "--dpi",
        required=True,
        type=int,
        help="Render DPI used for the page PNGs and final crops.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where crops, page PNGs, and manifest.json are written.",
    )
    return parser


def run_cli(target_kind: str) -> int:
    parser = build_parser(target_kind)
    args = parser.parse_args()
    try:
        summary = extract_target_images(
            pdf_path=args.pdf,
            v3_json_path=args.v3_json,
            dpi=args.dpi,
            output_dir=args.output_dir,
            target_kind=target_kind,
        )
    except (ValueError, V3ValidationError) as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"Extracted {summary['crop_count']} {target_kind} crops from "
        f"{summary['page_count_with_targets']} page(s)."
    )
    print(f"Page PNGs: {summary['page_images_dir']}")
    print(f"Manifest: {summary['manifest_path']}")
    return 0


__all__ = [
    "V3ValidationError",
    "load_v3_result",
    "validate_v3_result",
    "extract_target_images",
    "extract_v3_figure_images",
    "extract_v3_table_images",
    "build_parser",
    "run_cli",
]
