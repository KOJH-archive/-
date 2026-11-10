from datetime import date
import io
from docx import Document
from legal_studio.models import ResearchRequest, Claim, PrecedentDetail, PrecedentHit
from legal_studio.research import ResearchService
from legal_studio.demo import FictionalDemoSource
from legal_studio.db import Store
from legal_studio.verifier import temporal_check,verify_claim
from legal_studio.reporter import report_markdown,report_docx
from legal_studio.sources import SourceError


class RoleLLM:
    def __init__(self): self.calls=[]
    def research_claims(self,question,corpus):
        self.calls.append(question)
        key=next(k for k in corpus if ':precedent:' in k)
        return [Claim(text='가상 요지에 근거한 후보',source_id=key,quote='가상 기록이 존재하면 예시 절차에서 확인 표시를 할 수 있다.'),
                Claim(text='허위 출처 후보',source_id='missing',quote='존재하지 않는 출처에 있는 주장이다.')],[]


def test_agents_counter_verifier_report_and_snapshots(tmp_path):
    store=Store(tmp_path/'a.db'); llm=RoleLLM()
    svc=ResearchService(FictionalDemoSource(),store,llm)
    result=svc.run(ResearchRequest(question='가상 기록의 통지 확인',law_query='샘플거래법',enable_llm=True))
    assert len(llm.calls)==3
    assert result.counter_claims and len(result.excluded_claims)==3
    assert {s.role for s in result.steps}>={'planner','legal_analyst','opposition_analyst','reviewer','citation_verifier','memo_writer'}
    assert all(c.locator and c.source_hash for c in result.claims)
    snapshots=store.snapshots(result.job_id)
    assert len(snapshots)==3
    original=snapshots[0]['content']
    store.put_document('statute','900001','changed','changed',source_type='FICTIONAL_DEMO')
    assert store.snapshots(result.job_id)[0]['content']==original
    markdown=report_markdown(result)
    assert '반론과 적용 한계' in markdown and 'SOURCE_MISSING' in markdown and 'SHA-256' in markdown
    doc=Document(io.BytesIO(report_docx(result)))
    assert any(p.text=='역할별 수행 기록' for p in doc.paragraphs)
    store.clear_all()
    assert not store.snapshots(result.job_id)


def test_no_ai_means_skipped_not_invented_output(tmp_path):
    result=ResearchService(FictionalDemoSource(),Store(tmp_path/'a.db')).run(ResearchRequest(question='가상 통지 기록',law_query='샘플거래법'))
    assert not result.counter_claims
    assert next(x for x in result.steps if x.role=='legal_analyst').status=='SKIPPED'
    assert result.counter_candidates[0]['status']=='CANDIDATE_NOT_CONFIRMED'


def test_cache_opt_out_no_snapshots_or_documents(tmp_path):
    store=Store(tmp_path/'a.db')
    result=ResearchService(FictionalDemoSource(),store,cache_sources=False).run(ResearchRequest(question='가상 기록 통지',law_query='샘플거래법'))
    assert not store.snapshots(result.job_id)
    assert not store.local_search('가상',source_type='FICTIONAL_DEMO')
    assert store.get_job(result.job_id) # excerpts in jobs documented separately


def test_future_sources_excluded_from_memo_evidence(tmp_path):
    result=ResearchService(FictionalDemoSource(),Store(tmp_path/'a.db')).run(ResearchRequest(question='가상 통지 기록',law_query='샘플거래법',as_of=date(2026,11,10)))
    assert not result.claims
    assert all(c.temporal_status=='AFTER_AS_OF' for c in result.excluded_claims)
    assert result.status=='PARTIAL'


def test_date_flag_never_asserts_legal_validity():
    c=Claim(text='설명',source_id='x',quote='충분히 긴 원문 문자열이다')
    assert temporal_check(c,{'effective_date':'2020.01.01'},date(2026,1,1)).temporal_status=='DATE_PRECEDES_AS_OF_ONLY'
    assert temporal_check(c,{'judgment_date':'20259999'},date(2026,1,1)).temporal_status=='DATE_UNKNOWN'


def test_quotes_normalized_with_locator():
    c=verify_claim(Claim(text='설명',source_id='x',quote='가상   기록은\n존재한다고 쓰여 있다'),{'x':'가상 기록은 존재한다고 쓰여 있다.'})
    assert c.status=='QUOTE_MATCH_ONLY' and '정규화' in c.locator


class BrokenProvider:
    def search_statutes(self,*a,**kw): raise SourceError('API 접근 실패')
    def search_precedents(self,*a,**kw): raise SourceError('API 접근 실패')


def test_all_sources_fail_no_fake_success(tmp_path):
    result=ResearchService(BrokenProvider(),Store(tmp_path/'a.db')).run(ResearchRequest(question='민법 관련 통지'))
    assert result.status=='PARTIAL' and not result.sources and not result.claims
    assert '원문이 없습니다' in result.summary


class BoundedProvider(FictionalDemoSource):
    def __init__(self): self.downloads=[]
    def search_precedents(self,query,limit=12,search_body=True):
        base=100 if '예외' in query else 200 if '부정' in query else 300
        return [PrecedentHit(source_id=str(base+i),case_name='가상') for i in range(limit)]
    def precedent_detail(self,source_id):
        self.downloads.append(source_id)
        return PrecedentDetail(source_id=source_id,summary='가상 통지 기록이 있다',source_type='FICTIONAL_DEMO')


def test_interleaving_dedup_and_download_budget(tmp_path):
    provider=BoundedProvider()
    found=ResearchService(provider,Store(tmp_path/'a.db')).similar_cases('통지',3,queries=['통지 예외','통지 부정','통지 제한'])
    assert provider.downloads==['100','200','300']
    assert len(found.results)==3


def test_case_reference_metadata_not_legal_support():
    from legal_studio.verifier import verify_case_reference
    provider=FictionalDemoSource()
    assert verify_case_reference(provider,'가상2099예시1')['status']=='METADATA_MATCH_ONLY'
    assert verify_case_reference(provider,'가상2099예시1','다른 법원')['status']=='METADATA_MISMATCH'
    assert verify_case_reference(provider,'없는 사건')['status']=='NOT_FOUND_IN_RESULTS'
