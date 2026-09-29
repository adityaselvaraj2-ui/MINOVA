from __future__ import annotations

import logging
import uuid as uuid_mod
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Document

logger = logging.getLogger("minetrace.ingestion")

ALLOWED_TYPES = {
    ".pdf": "PDF",
    ".png": "IMAGE",
    ".jpg": "IMAGE",
    ".jpeg": "IMAGE",
    ".tif": "IMAGE",
    ".tiff": "IMAGE",
}


def save_upload(
    db: Session, filename: str, content: bytes, user_id: int,
) -> Document:
    suffix = Path(filename).suffix.lower()
    file_type = ALLOWED_TYPES.get(suffix)
    if not file_type:
        msg = f"Unsupported file type: {suffix}"
        raise ValueError(msg)

    dest_name = f"{uuid_mod.uuid4().hex}{suffix}"
    dest_path = settings.uploads_path / dest_name
    dest_path.write_bytes(content)

    doc = Document(
        filename=filename,
        file_path=str(dest_path),
        file_type=file_type,
        file_size=len(content),
        uploaded_by=user_id,
        status="UPLOADED",
    )
    db.add(doc)
    db.flush()
    return doc


def extract_text(doc: Document) -> list[dict]:
    path = Path(doc.file_path)
    if doc.file_type == "PDF":
        return _extract_pdf(path)
    return _extract_image(path)


def _extract_pdf(path: Path) -> list[dict]:
    pages = []
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if not text.strip():
                    text = _ocr_page_image(path, i)
                pages.append({"page": i + 1, "text": text})
    except ImportError:
        logger.warning("pdfplumber not installed, using OCR only")
        pages = [{"page": 1, "text": _ocr_file(path)}]
    return pages


def _extract_image(path: Path) -> list[dict]:
    text = _ocr_file(path)
    return [{"page": 1, "text": text}]


def _ocr_file(path: Path) -> str:
    try:
        from paddleocr import PaddleOCR

        ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        result = ocr.ocr(str(path), cls=True)
        lines = []
        if result and result[0]:
            for line in result[0]:
                if line and len(line) >= 2:
                    lines.append(line[1][0])
        return "\n".join(lines)
    except ImportError:
        logger.warning("PaddleOCR not installed")
        return ""
    except Exception:
        logger.exception("OCR failed for %s", path)
        return ""


def _ocr_page_image(pdf_path: Path, page_idx: int) -> str:
    try:
        import pdfplumber

        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[page_idx]
            img = page.to_image(resolution=300)
            tmp = settings.page_cache_path / f"ocr_{page_idx}.png"
            img.save(tmp)
            text = _ocr_file(tmp)
            tmp.unlink(missing_ok=True)
            return text
    except Exception:
        logger.exception("Page OCR failed")
        return ""


def delete_document(db: Session, doc: Document) -> None:
    path = Path(doc.file_path)
    if path.exists():
        path.unlink()
    db.delete(doc)
