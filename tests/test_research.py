import io
from pathlib import Path
from docx import Document
from legal_studio.db import Store
from legal_studio.demo import FictionalDemoSource
from legal_studio.models import ResearchRequest, Claim
from legal_studio.research import ResearchService
from legal_studio.reporter import report_docx, report_markdown
from legal_studio.verifier import verify_claim, verify_claims


def test_fictional_demo_flow_and_persistence(tmp_path):
    db=Store(tmp_path/'demo.sqlite')
    svc=ResearchService(FictionalDemoSource(),db)
    req=ResearchRequest(question='가상 통지의 기록을 분석',law_query='샘플거래법',precedent_query='통지',max_cases=2)
    result=svc.run(req)
    assert result.status == 'COMPLETED',result.warnings
    assert result.source_mode == 'fictional_demo'
    assert len(result.sources) == 3
    assert len(result.claims) >= 1
    assert all(x.status == 'QUOTE_MATCH_ONLY' for x in result.claims)
    saved=db.get_job(result.job_id)
    assert saved['question'] == req.question
    assert len(db.recent_jobs()) == 1
    assert db.local_search('샘플',source_type='FICTIONAL_DEMO')
    doc=Document(io.BytesIO(report_docx(result)))
    assert '법률 리서치 보고서' in doc.paragraphs[0].text
    assert '가상' in report_markdown(result)
    db.clear_all()
    assert db.recent_jobs() == []


def test_quote_check_is_not_legal_entailment():
    source={'MOLEG:precedent:123':'원문에는 A 사실과 B 사실이 기록되어 있다.'}
    good=Claim(text='법률적 결론',source_id='MOLEG:precedent:123',quote='A 사실과 B 사실이 기록되어 있다')
    verified=verify_claim(good,source)
    assert verified.status == 'QUOTE_MATCH_ONLY'
    bad=Claim(text='오류',source_id='MOLEG:precedent:123',quote='없는 판결문 문구를 만들어냈다')
    assert verify_claim(bad,source).status == 'CITATION_MISMATCH'
    missing=Claim(text='오류',source_id='missing',quote='이것은 충분히 긴 문자열')
    accepted,rejected=verify_claims([good,bad,missing],source)
    assert len(accepted)==1 and len(rejected)==2


def test_cache_separates_demo_and_official(tmp_path):
    db=Store(tmp_path/'test.db')
    db.put_document('precedent','42','가상','본문 일부 기록이다',source_type='FICTIONAL_DEMO')
    db.put_document('precedent','42','공식','다른 기록이다',source_type='MOLEG')
    assert db.get_document('FICTIONAL_DEMO:precedent:42')['title']=='가상'
    assert db.get_document('MOLEG:precedent:42')['title']=='공식'
