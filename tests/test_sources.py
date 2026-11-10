import httpx
import pytest
from legal_studio.sources import (LawOpenAPI, SourceError, CredentialsMissing,
                                  parse_law_hits,parse_law_detail,parse_prec_hits,parse_prec_detail)

LAW_SEARCH = '''<LawSearch><totalCnt>1</totalCnt><law id="1"><법령일련번호>123456</법령일련번호><법령ID>000123</법령ID><법령명한글>예시법</법령명한글><시행일자>20261101</시행일자></law></LawSearch>'''.encode()
LAW_DETAIL = '''<법령><기본정보><법령명_한글>예시법</법령명_한글><시행일자>20261101</시행일자></기본정보><조문><조문단위><조문번호>1</조문번호><조문가지번호>0</조문가지번호><조문제목>목적</조문제목><조문내용>이것은 테스트 본문이다.</조문내용><항내용>① 추가 항이다.</항내용></조문단위><조문단위><조문번호>2</조문번호><조문가지번호>1</조문가지번호><조문제목>시험</조문제목><조문내용>제2조의1 테스트.</조문내용></조문단위></조문></법령>'''.encode()
PREC_SEARCH = '''<PrecSearch><prec id="1"><판례일련번호>456789</판례일련번호><사건번호>2026가상101</사건번호><사건명>테스트 사건</사건명><법원명>테스트 법원</법원명></prec></PrecSearch>'''.encode()
PREC_DETAIL = '''<판례><판례정보일련번호>456789</판례정보일련번호><사건번호>2026가상101</사건번호><사건명>테스트 사건</사건명><법원명>테스트 법원</법원명><판시사항>실제 시험용 문구</판시사항><판결요지>관련 요지 설명</판결요지><판례내용>이것은 시험용 판결문이다.</판례내용></판례>'''.encode()


def test_law_search_parser():
    result = parse_law_hits(LAW_SEARCH)
    assert len(result) == 1
    assert result[0].source_id == '123456'
    assert result[0].name == '예시법'
    assert 'OC=' not in result[0].source_url


def test_detail_parser_articles():
    doc = parse_law_detail(LAW_DETAIL,'123456')
    assert doc.name == '예시법'
    assert len(doc.articles) == 2
    assert doc.articles[0].label == '제1조'
    assert '추가 항' in doc.articles[0].text
    assert doc.articles[1].label == '제2조의1'


def test_precedents_parser():
    cases = parse_prec_hits(PREC_SEARCH)
    assert cases[0].source_id == '456789'
    detail = parse_prec_detail(PREC_DETAIL,'456789')
    assert detail.summary == '관련 요지 설명'
    assert detail.case_number == '2026가상101'


def test_no_credentials_and_http_errors():
    api = LawOpenAPI('')
    with pytest.raises(CredentialsMissing):
        api.search_statutes('민법')
    api.close()


def test_mocked_http_api_request_parameters():
    seen = []
    def handler(req: httpx.Request):
        seen.append(req.url)
        assert req.url.params.get('OC') == 'unit-test-value'
        if req.url.path.endswith('lawSearch.do'):
            if req.url.params['target'] == 'law':
                return httpx.Response(200,content=LAW_SEARCH)
            return httpx.Response(200,content=PREC_SEARCH)
        if req.url.params['target'] == 'law':
            return httpx.Response(200,content=LAW_DETAIL)
        return httpx.Response(200,content=PREC_DETAIL)
    api = LawOpenAPI('unit-test-value',transport=httpx.MockTransport(handler))
    assert api.search_statutes('예시법')[0].source_id == '123456'
    assert api.statute_detail('123456').articles[0].text
    assert api.search_precedents('테스트',3)[0].source_id == '456789'
    assert api.precedent_detail('456789').issues
    assert seen[0].params['target'] == 'law'
    assert seen[1].params['MST'] == '123456'
    assert seen[2].params['search'] == '2'
    assert seen[3].params['ID'] == '456789'
    api.close()


def test_malformed_xml_rejected():
    with pytest.raises(SourceError):
        parse_law_hits(b'<not-xml')


def test_no_xxe():
    xml=b'<!DOCTYPE r [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><LawSearch>&xxe;</LawSearch>'
    with pytest.raises(SourceError):
        parse_law_hits(xml)


def test_auth_error_html_not_silent_zero_hits():
    with pytest.raises(SourceError):
        parse_law_hits(b'<html><body>login required</body></html>')
    with pytest.raises(SourceError):
        parse_prec_hits(b'<html><body>login required</body></html>')
