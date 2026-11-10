import httpx
import pytest
from fastapi.testclient import TestClient
from legal_studio.api import app
from legal_studio.sources import LawOpenAPI, SourceError, parse_law_detail, validate_xml
from legal_studio.browser_tasks import make_browser_task


@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'api.db'))
    monkeypatch.setenv('DEMO_MODE','1')
    monkeypatch.delenv('OLLAMA_MODEL',raising=False)
    return TestClient(app)


def test_new_endpoints(client):
    assert client.get('/api/statutes/900001/articles',params={'q':'제 3 조'}).json()['articles'][0]['label']=='제3조'
    result=client.post('/api/precedents/similar',json={'query':'가상 통지','limit':3}).json()
    assert result['results'][0]['method']=='BM25_KO_BIGRAM'
    assert client.post('/api/precedents/900002/analysis',json={}).json()['sections']['판결요지']
    r=client.post('/api/analysis/text',json={'text':'【주 문】\n이 가상 문서는 시험용 판결문이다.'})
    assert r.status_code==200 and r.json()['source_id'].startswith('USER_UPLOAD:')
    assert client.post('/api/research/jobs',json={'question':'가상 통지 기록','enable_llm':True}).status_code==400


def test_invalid_requests(client):
    assert client.post('/api/precedents/similar',json={'query':'가상','limit':10000}).status_code==422
    assert client.post('/api/research/jobs',json={'question':'가상 통지','as_of':'2026-99-99'}).status_code==422
    assert client.get('/api/statutes/search',params={'q':'민법','limit':0}).status_code==422
    assert client.get('/api/research/jobs/missing/sources').status_code==404


def test_quote_endpoint_marks_untrusted_authority(client):
    r=client.post('/api/citations/verify',json={'source_id':'MOLEG:123','text':'사용자가 작성한 가상 원문 문자열이다',
                 'quote':'가상 원문 문자열이다'})
    assert r.json()['authority']=='USER_SUPPLIED_TEXT_ONLY'
    assert r.json()['accepted'][0]['status']=='QUOTE_MATCH_ONLY'


def test_snapshot_and_json_exports(client):
    r=client.post('/api/research/jobs',json={'question':'가상 통지 기록','law_query':'샘플거래법'}).json()
    ident=r['job_id']
    assert len(client.get(f'/api/research/jobs/{ident}/sources').json())==3
    assert client.get(f'/api/research/jobs/{ident}/report.json').json()['job_id']==ident


def test_prec_filters_and_retry(monkeypatch):
    seen=[]
    monkeypatch.setattr('legal_studio.sources.time.sleep',lambda _:None)
    def handler(req):
        seen.append(req)
        return httpx.Response(503) if len(seen)==1 else httpx.Response(200,content=b'<PrecSearch/>')
    api=LawOpenAPI('secret',transport=httpx.MockTransport(handler))
    assert api.search_precedents('통지',page=2,court='대법원',case_number='2026다1',date_range='20200101~20261110',referenced=True)==[]
    p=seen[-1].url.params
    assert p['datSrcNm']=='대법원'
    assert p['search']=='3' and p['page']=='2' and p['curt']=='대법원' and p['nb']=='2026다1'
    assert len(seen)==2
    api.close()


def test_credential_not_reflected_and_redirect_not_followed():
    with pytest.raises(SourceError) as exc:
        validate_xml(b'<error>OC=super-secret</error>')
    assert 'super-secret' not in str(exc.value)
    seen=[]
    def handler(req):
        seen.append(req)
        return httpx.Response(302,headers={'location':'https://other.test/?OC=secret'})
    api=LawOpenAPI('secret',transport=httpx.MockTransport(handler))
    with pytest.raises(SourceError): api.search_statutes('민법')
    assert len(seen)==1
    api.close()


def test_chapter_heading_not_a_statute_article():
    xml='<법령><법령명_한글>가상법</법령명_한글><조문단위><조문번호>1</조문번호><조문여부>전문</조문여부><조문내용>제1장 총칙</조문내용></조문단위></법령>'.encode()
    assert parse_law_detail(xml).articles==[]


@pytest.mark.parametrize('url',['http://www.law.go.kr','https://law.go.kr.evil.test','https://localhost','https://www.law.go.kr/?OC=secret'])
def test_browser_task_restricts_destinations(url):
    with pytest.raises(ValueError): make_browser_task('민법',url)


def test_browser_task_is_explicit_handoff(client):
    r=client.post('/api/browser/tasks',json={'query':'통지'})
    assert r.json()['status']=='AWAITING_LOCAL_EGO'
    assert r.json()['evidence_status']=='WEB_DISCOVERY_NOT_API_VERIFIED'


def test_case_reference_endpoint(client):
    r=client.post('/api/citations/case-reference',json={'case_number':'가상2099예시1'})
    assert r.status_code==200 and r.json()['status']=='METADATA_MATCH_ONLY'


def test_browser_encoded_credential_rejected():
    with pytest.raises(ValueError):
        make_browser_task('민법','https://www.law.go.kr/?%4f%43=secret')
