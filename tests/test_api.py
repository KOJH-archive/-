from fastapi.testclient import TestClient
from legal_studio.api import app


def test_health(monkeypatch,tmp_path):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'ui.sqlite'))
    monkeypatch.setenv('DEMO_MODE','1')
    client=TestClient(app)
    response=client.get('/api/health')
    assert response.status_code == 200
    assert response.json()['mode']=='fictional_demo'


def test_research_api_demo(monkeypatch,tmp_path):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'api.sqlite'))
    monkeypatch.setenv('DEMO_MODE','1')
    client=TestClient(app)
    r=client.post('/api/research/jobs',json={'question':'가상 통지 기록 확인','law_query':'샘플거래법','precedent_query':'통지'})
    assert r.status_code==200,r.text
    data=r.json()
    assert data['source_mode']=='fictional_demo'
    job_id=data['job_id']
    assert client.get('/api/research/jobs/'+job_id).status_code==200
    assert client.get('/api/research/jobs/'+job_id+'/report.md').status_code==200
    doc=client.get('/api/research/jobs/'+job_id+'/report.docx')
    assert doc.status_code==200
    assert doc.content[:2]==b'PK'
    assert client.get('/api/research/jobs/nonexistent').status_code==404
