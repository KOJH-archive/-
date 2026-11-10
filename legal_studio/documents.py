"""Read-only, local, bounded document extraction; no OCR and no persistence.

Uploaded documents are user evidence, NOT authoritative legal sources.
"""
from io import BytesIO
from zipfile import ZipFile, BadZipFile
from pathlib import PurePath
from dataclasses import dataclass

MAX_BYTES = 12 * 1024 * 1024
MAX_TEXT = 130_000

class DocumentError(RuntimeError):
    pass

@dataclass
class ExtractedDocument:
    filename: str
    format: str
    pages_or_sections: int
    text: str
    truncated: bool = False


def extract_document(filename: str, content: bytes) -> ExtractedDocument:
    if not content or len(content) > MAX_BYTES:
        raise DocumentError('비어 있거나 12MB를 초과한 파일은 처리하지 않습니다.')
    suffix = PurePath(filename).suffix.lower()
    if suffix == '.pdf':
        if not content.startswith(b'%PDF-'):
            raise DocumentError('PDF 파일 헤더가 올바르지 않습니다.')
        try:
            import fitz
            with fitz.open(stream=content, filetype='pdf') as pdf:
                if pdf.is_encrypted:
                    raise DocumentError('암호화된 PDF는 지원하지 않습니다.')
                pieces = []
                for i in range(min(pdf.page_count,80)):
                    pieces.append(pdf.load_page(i).get_text('text'))
                text = '\n\n'.join(pieces)
                sections = min(pdf.page_count,80)
                truncated = pdf.page_count > 80
        except DocumentError:
            raise
        except Exception as exc:
            raise DocumentError('PDF 텍스트 추출에 실패했습니다.') from exc
    elif suffix == '.docx':
        if not content.startswith(b'PK'):
            raise DocumentError('DOCX 파일 형식이 올바르지 않습니다.')
        try:
            with ZipFile(BytesIO(content)) as zf:
                infos=zf.infolist()
                if len(infos)>500 or sum(i.file_size for i in infos)>40*1024*1024:
                    raise DocumentError('압축 해제 시 크기가 너무 큰 DOCX는 허용하지 않습니다.')
            from docx import Document
            doc = Document(BytesIO(content))
            pieces = [p.text for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    pieces.append(' | '.join(c.text for c in row.cells))
            text = '\n'.join(pieces)
            sections = len(pieces)
            truncated = False
        except DocumentError:
            raise
        except Exception as exc:
            raise DocumentError('DOCX 텍스트 추출에 실패했습니다.') from exc
    elif suffix in {'.txt','.md'}:
        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                text = content.decode('cp949')
            except UnicodeDecodeError as exc:
                raise DocumentError('UTF-8 또는 CP949로 해석할 수 없는 텍스트입니다.') from exc
        sections = len(text.splitlines())
        truncated = False
    else:
        raise DocumentError('PDF, DOCX, TXT, MD 파일만 지원합니다.')
    if not text.strip():
        raise DocumentError('추출된 텍스트가 없습니다. 이미지 스캔 PDF는 별도 OCR이 필요합니다.')
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT]
        truncated = True
    return ExtractedDocument(filename=filename,format=suffix, pages_or_sections=sections,
                             text=text,truncated=truncated)
