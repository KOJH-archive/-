"""Law.go.kr DRF source adapter (official API, authenticated with LAW_OC).

Rules:
- Never fabricate source documents.
- Never embed OC into public-facing source links.
- Search uses lawSearch.do, detail uses lawService.do.
- Fail closed on missing auth, parse errors, or malformed responses.
"""
import html
import re
import time
from html.parser import HTMLParser
import httpx
from defusedxml import ElementTree as SafeET

from .models import StatuteHit, StatuteDetail, Article, PrecedentHit, PrecedentDetail

SEARCH_URL = 'https://www.law.go.kr/DRF/lawSearch.do'
DETAIL_URL = 'https://www.law.go.kr/DRF/lawService.do'


class SourceError(RuntimeError):
    pass


class CredentialsMissing(SourceError):
    pass


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in {'p', 'div', 'br', 'li', 'tr', 'h1', 'h2', 'h3'}:
            self.parts.append('\n')


def normalize_text(value):
    """Strip markup safely; preserve newlines when returned by source."""
    if value is None:
        return ''
    raw = html.unescape(str(value))
    if '<' in raw and '>' in raw:
        parser = _PlainText()
        parser.feed(raw)
        raw = ''.join(parser.parts)
    raw = raw.replace('\r', '\n')
    return re.sub(r'\n{3,}', '\n\n', raw).strip()


def field(el, *names):
    for name in names:
        found = el.find(name)
        if found is None:
            found = el.find('.//' + name)
        if found is not None:
            value = ''.join(found.itertext())
            if value.strip():
                return normalize_text(value)
    return ''


def validate_xml(content: bytes):
    if len(content) > 10_000_000:
        raise SourceError('원문 응답이 허용된 크기를 초과했습니다 (10 MB).')
    try:
        root = SafeET.fromstring(content)
    except Exception as exc:
        raise SourceError(f'공식 API XML을 해석할 수 없습니다: {type(exc).__name__}') from exc
    root_name = root.tag.lower() if isinstance(root.tag, str) else ''
    if 'error' in root_name or 'fail' in root_name:
        raise SourceError('공식 API에서 오류가 반환되었습니다. 인증값·접근 권한을 확인하세요.')
    # In actual responses an error may be a plain XML envelope; stop before treating as 0 hits.
    error_message = field(root, 'error', 'ERROR', 'message', '메시지', 'resultMsg')
    if error_message and ('인증' in error_message or '오류' in error_message or 'error' in error_message.lower()):
        raise SourceError('공식 API 오류: 인증값·접근 권한을 확인하세요.')
    return root


def law_url(mst: str) -> str:
    return f'https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq={mst}' if mst else 'https://www.law.go.kr/'


def precedent_url(ident: str) -> str:
    return f'https://www.law.go.kr/LSW/precInfoP.do?precSeq={ident}' if ident else 'https://www.law.go.kr/'


def parse_law_hits(xml: bytes) -> list[StatuteHit]:
    root = validate_xml(xml)
    if root.tag.lower() != 'lawsearch':
        raise SourceError('법령 목록이 아닌 응답입니다. API 인증 또는 출력 형식을 확인하세요.')
    out = []
    for el in root.findall('.//law'):
        mst = field(el, '법령일련번호')
        if not mst:
            continue
        out.append(StatuteHit(
            source_id=mst, law_id=field(el, '법령ID'), name=field(el, '법령명한글', '법령명'),
            effective_date=field(el, '시행일자'), promulgation_date=field(el, '공포일자'),
            ministry=field(el, '소관부처명'), source_url=law_url(mst)))
    return out


def parse_law_detail(xml: bytes, source_id='') -> StatuteDetail:
    root = validate_xml(xml)
    name = field(root, '법령명_한글', '법령명한글', '법령명')
    mst = source_id or field(root, '법령일련번호')
    units = list(root.iter('조문단위'))
    if not units:
        units = list(root.iter('조문'))
    articles = []
    for node in units:
        num = field(node, '조문번호')
        if field(node, '조문여부') == '전문':
            continue
        if not num or not num.isdigit():
            continue
        branch = field(node, '조문가지번호')
        try:
            label = f'제{int(num)}조' + (f'의{int(branch)}' if branch.isdigit() and int(branch) else '')
        except ValueError:
            continue
        title = field(node, '조문제목')
        body_parts = []
        for child in node.iter():
            if child.tag in {'조문내용', '항내용', '호내용', '목내용'}:
                text = normalize_text(''.join(child.itertext()))
                if text and text not in body_parts:
                    body_parts.append(text)
        if not body_parts:
            continue
        articles.append(Article(
            label=label, title=title, text='\n'.join(body_parts),
            effective_date=field(node, '조문시행일자')))
    # Invalid payload must not be interpreted as a law with zero articles.
    if not name and not articles:
        raise SourceError('법령 본문에서 제목 또는 조문을 확인하지 못했습니다.')
    additions = [normalize_text(''.join(el.itertext())) for el in root.iter('부칙내용')]
    return StatuteDetail(source_id=mst, name=name, articles=articles,
                         effective_date=field(root, '시행일자'), addenda='\n'.join(a for a in additions if a),
                         source_url=law_url(mst))


def parse_prec_hits(xml: bytes) -> list[PrecedentHit]:
    root = validate_xml(xml)
    if root.tag.lower() != 'precsearch':
        raise SourceError('판례 목록이 아닌 응답입니다. API 인증 또는 출력 형식을 확인하세요.')
    out = []
    for el in root.findall('.//prec'):
        ident = field(el, '판례일련번호', '판례정보일련번호')
        if not ident:
            continue
        out.append(PrecedentHit(
            source_id=ident, case_number=field(el, '사건번호'),
            case_name=field(el, '사건명'), court=field(el, '법원명'),
            judgment_date=field(el, '선고일자'), source_url=precedent_url(ident)))
    return out


def parse_prec_detail(xml: bytes, source_id='') -> PrecedentDetail:
    root = validate_xml(xml)
    ident = source_id or field(root, '판례정보일련번호', '판례일련번호')
    case = PrecedentDetail(
        source_id=ident, case_number=field(root, '사건번호'),
        case_name=field(root, '사건명'), court=field(root, '법원명'),
        judgment_date=field(root, '선고일자'), source_url=precedent_url(ident),
        issues=field(root, '판시사항'), summary=field(root, '판결요지'),
        referenced_articles=field(root, '참조조문'), referenced_cases=field(root, '참조판례'),
        full_text=field(root, '판례내용'))
    if not case.case_number and not case.full_text and not case.summary:
        raise SourceError('XML 판례 본문이 제공되지 않았습니다. HTML 전용 자료 또는 제공기관의 미제공 자료일 수 있습니다. 공식 원문 링크를 확인하세요.')
    return case


class LawOpenAPI:
    def __init__(self, oc: str, transport=None, timeout: float = 18):
        self.oc = oc.strip()
        self.client = httpx.Client(timeout=timeout, follow_redirects=False,
                                   transport=transport,
                                   headers={'User-Agent': 'KoreanLegalResearchStudio/0.2 (individual research)'})

    def _get(self, kind: str, target: str, **params) -> bytes:
        if not self.oc:
            raise CredentialsMissing('LAW_OC가 없습니다. 공식 법제처 API 인증값을 .env에 입력하세요.')
        endpoint = SEARCH_URL if kind == 'search' else DETAIL_URL
        args = {'OC': self.oc, 'target': target, 'type': 'XML', **params}
        try:
            for attempt in range(3):
                response = self.client.get(endpoint, params=args)
                if response.status_code not in {429,502,503,504} or attempt == 2:
                    response.raise_for_status()
                    break
                time.sleep(0.25 * (attempt+1))
        except httpx.HTTPError as exc:
            raise SourceError(f'공식 API 요청 실패: {type(exc).__name__}') from exc
        # No URL may be logged: it contains the credential in the query string.
        if not response.content.lstrip().startswith(b'<'):
            raise SourceError('공식 API가 XML이 아닌 응답을 반환했습니다. 인증·IP 등록을 확인하세요.')
        return response.content

    def search_statutes(self, query: str, limit: int = 12) -> list[StatuteHit]:
        # Rank before slicing: display=1 previously returned 난민법 for 민법.
        hits = parse_law_hits(self._get('search', 'law', query=query.strip(), display=100))
        compact = lambda text: ''.join(text.split()).casefold()
        needle = compact(query)
        hits.sort(key=lambda h: (compact(h.name) != needle, not compact(h.name).startswith(needle), compact(h.name)))
        return hits[:max(1, min(limit, 100))]

    def statute_detail(self, source_id: str) -> StatuteDetail:
        if not source_id.isdigit():
            raise SourceError('법령 일련번호 형식이 올바르지 않습니다.')
        return parse_law_detail(self._get('detail', 'law', MST=source_id), source_id)

    def search_precedents(self, query: str, limit: int = 12, search_body: bool = True,
                          page: int = 1, court: str = '', case_number: str = '',
                          date_range: str = '', referenced: bool = False) -> list[PrecedentHit]:
        if date_range and not re.fullmatch(r'\d{8}~\d{8}',date_range):
            raise SourceError('선고일 범위는 YYYYMMDD~YYYYMMDD 형식이어야 합니다.')
        extra = {k:v for k,v in {'curt':court,'nb':case_number,'prncYd':date_range}.items() if v}
        return parse_prec_hits(self._get('search', 'prec', query=query.strip(),
                                        datSrcNm='대법원',
                                        search=3 if referenced else (2 if search_body else 1),
                                        page=max(1,min(page,1000)), **extra,
                                        display=max(1, min(limit, 100))))

    def precedent_detail(self, source_id: str) -> PrecedentDetail:
        if not source_id.isdigit():
            raise SourceError('판례 일련번호 형식이 올바르지 않습니다.')
        return parse_prec_detail(self._get('detail', 'prec', ID=source_id), source_id)

    def close(self):
        self.client.close()
