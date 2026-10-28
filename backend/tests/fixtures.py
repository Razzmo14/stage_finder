"""Test fixtures: minimal valid PDF built by hand (no extra dependency)."""

import io


def make_pdf(text: str) -> bytes:
    """Build a one-page PDF containing a single text line."""

    def escape(value: str) -> str:
        return value.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    stream = f"BT /F1 12 Tf 72 720 Td ({escape(text)}) Tj ET"
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        4: f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        5: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    buffer = io.BytesIO()
    buffer.write(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = buffer.tell()
        buffer.write(f"{number} 0 obj\n{objects[number]}\nendobj\n".encode())
    xref_pos = buffer.tell()
    buffer.write(b"xref\n0 6\n0000000000 65535 f \n")
    for number in sorted(objects):
        buffer.write(f"{offsets[number]:010d} 00000 n \n".encode())
    buffer.write(f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode())
    return buffer.getvalue()


def make_docx(paragraphs: list[str]) -> bytes:
    """Build a DOCX in memory using python-docx."""
    from docx import Document

    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
