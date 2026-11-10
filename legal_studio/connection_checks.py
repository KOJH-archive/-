"""Independent live checks; one failure must not hide other service results."""
import time
from .sources import LawOpenAPI
from .llm import OllamaResearcher
from .retrieval import OllamaEmbedder
from .verifier import verify_claims


def connection_checks(cfg, chat_model='', embedding_model=''):
    api = LawOpenAPI(cfg.law_oc)

    def statute():
        hits = api.search_statutes('민법', 1)
        if not hits or hits[0].name != '민법':
            raise ValueError('exact statute not found')
        detail = api.statute_detail(hits[0].source_id)
        if not detail.articles:
            raise ValueError('empty statute')
        return f'{detail.name}: 조문 {len(detail.articles)}개 수신'

    def precedent():
        hits = api.search_precedents('채권양도', 1)
        if not hits:
            raise ValueError('empty search')
        detail = api.precedent_detail(hits[0].source_id)
        if not detail.full_text:
            raise ValueError('empty precedent')
        return f'{detail.case_number}: 본문 {len(detail.full_text):,}자 수신'

    def chat():
        corpus = {'check':'이것은 연결 점검용 가상 자료이다. 가상 계약의 통지 기한은 7일이다.'}
        claims, _ = OllamaResearcher(cfg.ollama_base_url,chat_model).research_claims('가상 계약의 통지 기한을 인용하라',corpus)
        good, bad = verify_claims(claims,corpus)
        if not good or bad:
            raise ValueError('unverified claims')
        return f'{chat_model}: JSON 응답·원문 인용 대조 성공 (법률 정확도 평가는 별도)'

    def embedding():
        vector = OllamaEmbedder(cfg.ollama_base_url,embedding_model).embed(['연결 점검용 가상 문서'])[0]
        return f'{embedding_model}: {len(vector)}차원 벡터 수신'

    checks = [('법령 검색·조문', bool(cfg.law_oc), statute),
              ('판례 검색·본문', bool(cfg.law_oc), precedent),
              ('채팅 모델', bool(chat_model) and cfg.ollama_allowed(), chat),
              ('임베딩 모델', bool(embedding_model) and cfg.ollama_allowed(), embedding)]
    try:
        for name, enabled, check in checks:
            start = time.monotonic()
            row = {'항목':name, '상태':'미설정', '설명':'인증값 또는 사용 가능한 모델을 선택하세요.', '소요초':0.0}
            if enabled:
                try:
                    row.update(상태='성공', 설명=check())
                except Exception as exc:
                    row.update(상태='실패', 설명=f'{type(exc).__name__}: 서비스 응답 또는 모델 출력을 확인하세요.')
            row['소요초'] = round(time.monotonic()-start,1)
            yield row
    finally:
        api.close()
