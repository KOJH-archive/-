"""Reproducible fictional report; never downloads live legal documents."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tempfile
from legal_studio.demo import FictionalDemoSource
from legal_studio.db import Store
from legal_studio.research import ResearchService
from legal_studio.models import ResearchRequest
from legal_studio.reporter import report_docx,report_markdown

with tempfile.TemporaryDirectory() as temp:
    svc=ResearchService(FictionalDemoSource(),Store(Path(temp)/'demo.db'))
    result=svc.run(ResearchRequest(question='가상 통지 기록 유무에 따른 확인 절차를 검토',
        law_query='샘플거래법',precedent_query='가상 통지',position='가상 기록이 누락되어도 확인 표시가 가능하다는 주장'))
    dest=Path(__file__).resolve().parents[1]/'examples'
    dest.mkdir(exist_ok=True)
    (dest/'demo-report.docx').write_bytes(report_docx(result))
    (dest/'demo-report.md').write_text(report_markdown(result),encoding='utf-8')
    (dest/'demo-result.json').write_text(result.model_dump_json(indent=2),encoding='utf-8')
    print(result.status, len(result.sources), 'sources; example reports generated')
