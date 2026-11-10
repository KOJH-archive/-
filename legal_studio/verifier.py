"""Deterministic checks of source quotation. This is NOT full legal entailment verification."""
import re
import unicodedata
import hashlib
from .models import Claim


def canonical(text):
    text = unicodedata.normalize('NFKC', text)
    return re.sub(r'\s+', '', text).casefold()


def verify_claim(claim: Claim, corpus: dict[str, str]) -> Claim:
    source_text = corpus.get(claim.source_id, '')
    if not source_text:
        return claim.model_copy(update={'status': 'SOURCE_MISSING', 'reason': '연결된 원문을 확보하지 못함'})
    quote = canonical(claim.quote)
    if len(quote) < 8:
        return claim.model_copy(update={'status': 'CITATION_MISMATCH', 'reason': '너무 짧은 인용문'})
    if quote not in canonical(source_text):
        return claim.model_copy(update={'status': 'CITATION_MISMATCH', 'reason': '원문에서 인용 문자열을 찾지 못함'})
    return claim.model_copy(update={'status': 'QUOTE_MATCH_ONLY',
                                    'reason': '원문 문구 일치 확인. 주장의 법적 타당성은 별도 검토 필요',
                                    'source_hash': hashlib.sha256(source_text.encode()).hexdigest(),
                                    'locator': locate_quote(claim.quote, source_text)})


def locate_quote(quote, text):
    offset = text.find(quote)
    if offset >= 0:
        return f'원문 문자 {offset + 1}–{offset + len(quote)} / 줄 {text[:offset].count(chr(10))+1}'
    return f'정규화 문자열 위치 {canonical(text).find(canonical(quote))+1} (공백·유니코드 정규화)'


def temporal_check(claim, metadata, as_of):
    """Date consistency flags, explicitly NOT historical applicability or citator."""
    if not as_of:
        return claim
    value = metadata.get('judgment_date') or metadata.get('effective_date') or ''
    digits = re.sub(r'[^0-9]', '', value)
    status = 'DATE_UNKNOWN'
    if len(digits) == 8:
        from datetime import date
        try:
            source_date = date(int(digits[:4]),int(digits[4:6]),int(digits[6:8]))
            status = 'AFTER_AS_OF' if source_date > as_of else 'DATE_PRECEDES_AS_OF_ONLY'
        except ValueError:
            pass
    return claim.model_copy(update={'temporal_status':status})


def verify_claims(claims: list[Claim], corpus: dict[str,str]):
    accepted, rejected = [], []
    for claim in claims:
        checked = verify_claim(claim, corpus)
        if checked.status == 'QUOTE_MATCH_ONLY':
            accepted.append(checked)
        else:
            rejected.append(checked)
    return accepted, rejected


def verify_case_reference(provider, case_number, court='', judgment_date=''):
    """Verify metadata against API candidates; never equate a match to legal support."""
    if getattr(provider,'demo',False):
        hits = provider.search_precedents(case_number,limit=30)
    else:
        hits = provider.search_precedents('',limit=30,case_number=case_number)
    normalize_number = lambda value: re.sub(r'\s+', '',value)
    exact = [h for h in hits if normalize_number(h.case_number)==normalize_number(case_number)]
    if not exact:
        return {'status':'NOT_FOUND_IN_RESULTS','matches':[],
                'reason':'조회 결과에서 사건번호 정확 일치 없음. 가짜 판례 또는 판례 부존재를 확정하지 않습니다.'}
    matching = [h for h in exact if (not court or h.court==court) and
                (not judgment_date or re.sub(r'\D','',h.judgment_date)==re.sub(r'\D','',judgment_date))]
    return {'status':'METADATA_MATCH_ONLY' if matching else 'METADATA_MISMATCH',
            'matches':[h.model_dump() for h in exact],
            'reason':'사건번호·입력된 법원·날짜 대조. 인용 법리 및 후속 판례 변경은 미검증.',
            'source_mode':'fictional_demo' if getattr(provider,'demo',False) else 'official'}
