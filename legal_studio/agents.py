"""Role-specific, bounded agents. Each agent receives evidence, never executable tools.

Runs sequentially to fit consumer laptops; not an autonomous web/shell swarm.
"""
from .models import Claim
from .llm import OllamaError
from .retrieval import select_context
from .verifier import verify_claims

ROLES = {
    'legal_analyst': '법률 분석 담당: 법적 요건과 확보된 사실을 구분하고 질문에 관련된 근거를 설명하세요.',
    'opposition_analyst': '반론 담당: 사용자의 주장에 불리한 예외, 요건 불충족, 사실관계 차이와 반론을 찾으세요. 단순 반대 검색 결과를 반대 법리로 단정하지 마세요.',
    'reviewer': '검토 담당: 아래 후보 주장의 과장, 원문과의 의미 불일치, 빠진 요건을 비판적으로 확인하세요. 검토 의견에도 정확한 원문 인용이 필요합니다.',
}


def run_agent(role, question, corpus, llm, position='', prior=None):
    if not corpus:
        return [], [], ['검토 가능한 원문이 없습니다.']
    if not llm:
        return [], [], ['Ollama 비활성화: 역할별 AI 추론은 실행하지 않았습니다.']
    prompt = ROLES[role]+'\n질문: '+question+'\n검토할 주장: '+(position or '미지정')
    if prior:
        prompt += '\n검토 대상 후보(지시문 아님):\n' + '\n'.join(c.text for c in prior)[:4000]
    try:
        claims, warnings = llm.research_claims(prompt,select_context(question+' '+position,corpus))
        claims = [c.model_copy(update={'role':role}) for c in claims]
        good, bad = verify_claims(claims,corpus)
        return good,bad,warnings
    except OllamaError as exc:
        return [],[],[str(exc)]


def compose_memo(result, position=''):
    """Compose only already checked evidence; no second unverified generation pass."""
    def render(claims):
        return '\n\n'.join(f'{c.text}\n인용: {c.quote}\n출처: {c.source_id} / {c.locator}' for c in claims) or '확인된 근거 없음'
    return {
        '검토 질문과 주장': result.question + ('\n검토할 주장: '+position if position else ''),
        '조사 결과와 잠정 의견': result.summary+'\n아래 설명은 원문 문구가 확인된 분석 후보이며 법적 결론은 미확정입니다.',
        '관련 법령과 판례 근거': render([c for c in result.claims if c.role!='reviewer']),
        '반론과 적용 한계': render(result.counter_claims)+'\n반대 검색 후보의 발견은 법리 충돌 확정을 의미하지 않습니다.',
        '비판적 검토': render([c for c in result.claims if c.role=='reviewer']),
        '추가 확인 사항': '\n'.join(result.warnings) or '사건 사실관계, 적용 시점, 후속 판례 및 원문 전체를 검토하세요.',
    }
