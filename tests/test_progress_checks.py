import httpx
from legal_studio.sources import LawOpenAPI
from legal_studio.research import ResearchService
from legal_studio.demo import FictionalDemoSource
from legal_studio.db import Store
from legal_studio.models import ResearchRequest
from legal_studio.config import Settings
from legal_studio.connection_checks import connection_checks


def test_exact_law_ranked_before_result_limit():
    xml='<LawSearch><law><법령일련번호>1</법령일련번호><법령명한글>난민법</법령명한글></law><law><법령일련번호>2</법령일련번호><법령명한글>민법</법령명한글></law></LawSearch>'
    api=LawOpenAPI('test',transport=httpx.MockTransport(lambda r:httpx.Response(200,content=xml.encode())))
    try:
        assert api.search_statutes('민법',1)[0].name=='민법'
    finally:
        api.close()


def test_checkpoints_persist_sources_before_completion(tmp_path):
    store=Store(tmp_path/'progress.db')
    svc=ResearchService(FictionalDemoSource(),store)
    seen=[]
    def progress(result):
        saved=store.get_job(result.job_id)
        assert saved['progress']==result.progress
        assert saved['checkpoint_at']
        if result.sources:
            assert store.snapshots(result.job_id)
        seen.append((result.progress,len(result.sources)))
    result=svc.run(ResearchRequest(question='가상 통지의 기록을 검토',law_query='샘플거래법',precedent_query='통지'),on_progress=progress)
    assert result.status=='COMPLETED'
    assert seen[-1][0]==100
    assert any(percent<60 and count>0 for percent,count in seen)
    assert result.research_context['human_review']=='미검토'


def test_missing_connections_report_independently_without_calls():
    rows=list(connection_checks(Settings()))
    assert len(rows)==4
    assert all(row['상태']=='미설정' for row in rows)
