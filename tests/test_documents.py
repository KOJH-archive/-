from io import BytesIO
from docx import Document
import pytest
from legal_studio.documents import extract_document,DocumentError


def test_text_and_docx_extract():
    doc=extract_document('demo.txt','안녕하세요\n테스트'.encode('utf8'))
    assert '테스트' in doc.text
    word=Document()
    word.add_paragraph('문서 내용 확인')
    b=BytesIO()
    word.save(b)
    assert '문서 내용 확인' in extract_document('demo.docx',b.getvalue()).text


def test_bad_files():
    with pytest.raises(DocumentError):
        extract_document('foo.pdf',b'not a pdf')
    with pytest.raises(DocumentError):
        extract_document('foo.exe',b'hello')
    with pytest.raises(DocumentError):
        extract_document('foo.txt',b'')
