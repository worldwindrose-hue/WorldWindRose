"""
ROSA OS — PDF Handler.

Extracts text from PDF files using pdfplumber.
Falls back to pytesseract OCR if no text is found.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from core.ingest.handlers.base import BaseHandler, IngestResult

logger = logging.getLogger("rosa.ingest.pdf")


class PDFHandler(BaseHandler):
    """Ingest PDF documents into the knowledge graph."""

    async def process(self, job) -> IngestResult:
        source = job.source
        self.update_progress(job, 5, "Открываю PDF...")
        try:
            path = Path(source)
            text = self._extract_text(path)

            if not text.strip():
                self.update_progress(job, 40, "Текст не найден, запускаю OCR...")
                text = self._ocr_extract(path)

            if not text.strip():
                raise ValueError("PDF не содержит извлекаемого текста")

            self.update_progress(job, 60, "Разбиваю на чанки...")
            chunks = self.chunk(text)

            self.update_progress(job, 80, "Сохраняю в граф знаний...")
            nodes = await self.save_to_graph(chunks, source=source, tags=["pdf"])

            self.update_progress(job, 100)
            return IngestResult(
                type="pdf",
                source=source,
                nodes_created=nodes,
                chunks=len(chunks),
                summary=f"✅ PDF: {len(chunks)} чанков → {nodes} узлов",
                metadata={"pages": self._page_count(path)},
            )
        except Exception as exc:
            logger.error("PDF ingest failed: %s", exc)
            raise

    def _extract_text(self, path: Path) -> str:
        try:
            import pdfplumber
            pages = []
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        pages.append(t)
            return "\n\n".join(pages)
        except ImportError:
            logger.warning("pdfplumber not installed; trying PyPDF2")
            return self._extract_pypdf2(path)

    def _extract_pypdf2(self, path: Path) -> str:
        try:
            import PyPDF2
            text_parts = []
            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    t = page.extract_text()
                    if t:
                        text_parts.append(t)
            return "\n\n".join(text_parts)
        except Exception as exc:
            logger.warning("PyPDF2 failed: %s", exc)
            return ""

    def _ocr_extract(self, path: Path) -> str:
        try:
            import pytesseract
            from pdf2image import convert_from_path
            images = convert_from_path(str(path), dpi=200)
            pages = []
            for img in images:
                pages.append(pytesseract.image_to_string(img, lang="rus+eng"))
            return "\n\n".join(pages)
        except Exception as exc:
            logger.warning("OCR extraction failed: %s", exc)
            return ""

    def _page_count(self, path: Path) -> int:
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                return len(pdf.pages)
        except Exception:
            return 0
