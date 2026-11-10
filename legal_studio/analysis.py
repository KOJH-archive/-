"""Evidence-preserving judgment analysis. Missing headings are never inferred facts."""
import re
from .models import CaseAnalysis, Claim
from .retrieval import case_text, select_context
from .verifier import verify_claims
from .llm import OllamaError

HEADINGS = re.compile(r'(?:^|\n)\s*(?:【|\[)?(주\s*문|이\s*유|기초\s*사실|인정\s*사실|당사자의\s*주장|판단|결론)(?:】|\])?\s*(?:\n|:|：)', re.MULTILINE)


def analyze_case(case, question='', llm=None):
    key = f'{case.source_type}:precedent:{case.source_id}'
    sections = {name:value for name,value in [('판시사항',case.issues),('판결요지',case.summary),
                ('참조조문',case.referenced_articles),('참조판례',case.referenced_cases)] if value}
    matches = list(HEADINGS.finditer(case.full_text))
    for i, match in enumerate(matches):
        end = matches[i+1].start() if i+1<len(matches) else len(case.full_text)
        name = re.sub(r'\s+', '', match.group(1))
        value = case.full_text[match.end():end].strip()
        if value:
            sections[name] = sections.get(name,'') + ('\n' if name in sections else '') + value
    warnings = []
    if not matches:
        warnings.append('주문·이유 등 제목을 식별하지 못했습니다. 사실관계·판단을 추정하지 않았습니다.')
    if not case.full_text:
        warnings.append('판결 전문이 제공되지 않아 요지 범위에서만 분석했습니다.')
    claims = [Claim(text=f'{name} 원문 발췌',source_id=key,quote=text[:600],role='case_analyst')
              for name,text in sections.items() if name not in {'참조조문','참조판례'}]
    corpus = {key:case_text(case)}
    rejected = []
    coverage = 'EXTRACTIVE'
    if llm:
        prompt = ('판결문 심층 분석. 사실관계, 당사자 주장, 쟁점, 법원의 판단과 이유, 주문, 적용 한계별로 '
                  '구분해 원문으로 뒷받침되는 설명만 작성. 누락 정보는 limitations에 기록. 질문: '+question)
        try:
            generated, limits = llm.research_claims(prompt, select_context(question+' 판단 이유 사실관계 주문',corpus))
            if generated:
                claims = [c.model_copy(update={'role':'case_analyst'}) for c in generated]
            warnings.extend(limits)
            coverage = 'LLM_SELECTED_WINDOWS'
            warnings.append('AI는 길이 제한 내 선택된 원문 구간을 분석했습니다. 전문 전체 검토가 아닙니다.')
        except OllamaError as exc:
            warnings.append(str(exc))
    accepted, rejected = verify_claims(claims,corpus)
    return CaseAnalysis(source_id=key,case_number=case.case_number,sections=sections,
                        claims=accepted,excluded_claims=rejected,warnings=warnings,coverage=coverage)
