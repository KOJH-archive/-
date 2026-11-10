import httpx
import pytest
from legal_studio.retrieval import lexical_scores, select_context, rank_documents, OllamaEmbedder, cosine
from legal_studio.llm import OllamaError, OllamaResearcher
from legal_studio.models import PrecedentDetail
from legal_studio.analysis import analyze_case
from legal_studio.config import Settings


def test_korean_suffix_and_relevance():
    scores=lexical_scores('채권양도 통지', ['채권양도의 통지가 문제된다.','임대차 보증금 반환'])
    assert scores[0]>scores[1]


def test_long_source_retrieves_late_article():
    text=('제1조 일반적 목적이다.\n'*1000)+'제450조 채권양도 통지 대항요건의 특별한 요건\n'
    selected=select_context('제450조 채권양도 통지 대항요건',{'law':text},budget=3000)
    assert '제450조' in selected['law']
    assert len(selected['law'])<=3000


def test_embed_protocol_and_fusion():
    def handler(req):
        import json
        body=json.loads(req.content)
        assert req.url.path=='/api/embed'
        assert body['truncate'] is False
        return httpx.Response(200,json={'embeddings':[[1,0],[1,0],[0,1]]})
    embedder=OllamaEmbedder('http://localhost:11434','test',httpx.MockTransport(handler))
    scores,method,warnings=rank_documents('채권양도',['채권양도 통지','임대차'],embedder)
    assert scores[0]>scores[1] and method=='RRF_BM25_OLLAMA' and not warnings


@pytest.mark.parametrize('payload',[{'embeddings':[]},{'embeddings':[[1],[1,2]]},{'embeddings':[['x'],[1]]}])
def test_bad_embeddings_fallback(payload):
    embedder=OllamaEmbedder('http://localhost','test',httpx.MockTransport(lambda r:httpx.Response(200,json=payload)))
    scores,method,warnings=rank_documents('통지',['가상 통지'],embedder)
    assert method=='BM25_KO_BIGRAM' and warnings


def test_embedding_dimension_rejected():
    with pytest.raises(OllamaError):
        cosine([1,2],[1])


def test_case_headings_and_verbatim_evidence():
    text='【주 문】\n가상 청구를 기각한다.\n【이 유】\n가상 통지 기록이 없어 인정하지 않는다.\n'
    case=PrecedentDetail(source_id='x',source_type='FICTIONAL_DEMO',full_text=text)
    result=analyze_case(case)
    assert result.sections['주문']=='가상 청구를 기각한다.'
    assert result.sections['이유']=='가상 통지 기록이 없어 인정하지 않는다.'
    assert all(c.status=='QUOTE_MATCH_ONLY' and c.source_hash for c in result.claims)


def test_missing_headings_never_invents_facts():
    result=analyze_case(PrecedentDetail(source_id='x',summary='공식 요지 문자열만 있음'))
    assert '인정사실' not in result.sections and len(result.warnings)==2


@pytest.mark.parametrize('content',['[]','{"claims":"bad"}','{"claims":null}','not json'])
def test_llm_invalid_json_shapes(content):
    llm=OllamaResearcher('http://localhost','test',httpx.MockTransport(lambda r:httpx.Response(200,json={'message':{'content':content}})))
    with pytest.raises(OllamaError):
        llm.research_claims('질문',{'x':'원문 내용'})


@pytest.mark.parametrize('url,allowed',[
    ('http://127.0.0.1:11434',True),('http://localhost:11434',True),('http://[::1]:11434',True),
    ('http://localhost.evil.test',False),('http://127.0.0.1@evil.test',False),
    ('file:///etc/passwd',False),('http://localhost?token=secret',False)])
def test_remote_ollama_boundary(url,allowed):
    assert Settings(ollama_base_url=url).ollama_allowed()==allowed
