"""Editable evidence-linked legal memorandum, with explicit verification boundaries."""
from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.oxml.ns import qn
from .models import ResearchResult


def report_sections(result):
    overview = [result.summary]
    if result.request.get('position'):
        overview.append('검토할 주장: '+result.request['position'])
    if result.request.get('as_of'):
        overview.append('검토 기준일: '+result.request['as_of']+' (날짜 대조만 수행)')
    overview.append('조사 조건: '+str(result.research_context))
    overview.append('검색어: '+', '.join(result.search_queries))
    overview.append(f'마지막 저장 단계: {result.current_stage} / 진행 {result.progress}% / 경과 {result.elapsed_seconds}초')
    evidence = []
    for i,c in enumerate(result.claims,1):
        evidence += [f'근거 {i} / {c.role}\n{c.text}', '원문 발췌: '+c.quote,
            f'출처: {c.source_id}\n위치: {c.locator or "기존 기록에 없음"}\n상태: {c.status} / 시점: {c.temporal_status}']
    counter = []
    for c in result.counter_claims:
        counter += [c.text, '원문 발췌: '+c.quote, f'출처: {c.source_id}\n위치: {c.locator}']
    for candidate in result.counter_candidates:
        counter.append(f'검색 후보: {candidate.get("case_number", "")} / {candidate["source_id"]}\n'
                       +candidate.get('reason','')+'\n검색어: '+', '.join(candidate.get('queries',[])))
    if not result.counter_claims:
        counter.insert(0,'원문이 대조된 AI 반론은 없습니다. 검색 후보는 반대 법리를 확정한 판례가 아닙니다.')
    sources = []
    for source in result.sources:
        sources.append(source['name']+'\n'+(source.get('url') or '가상 자료 또는 링크 없음')+
            '\nID: '+source['id']+'\n조회시각: '+source.get('fetched_at','기존 기록에 없음')+
            '\nSHA-256: '+source.get('sha256','기존 기록에 없음'))
    excluded = [f'{c.text} / {c.status} / {c.temporal_status}: {c.reason}' for c in result.excluded_claims]
    excluded.extend(result.warnings)
    excluded.append('인용 검증은 원문 문구 일치만 확인합니다. 법적 타당성, 사건 적용, 후속 판례 및 과거 시행법은 별도 검토가 필요합니다.')
    trace = [f'{s.role} / {s.status}: {s.detail}' for s in result.steps]
    return [('조사 개요와 잠정 의견',overview),('관련 법령과 판례 근거',evidence or ['검증된 인용 없음']),
            ('반론과 적용 한계',counter),('조회 원문 목록',sources or ['확보한 원문 없음']),
            ('미확인 사항과 배제된 분석',excluded),('역할별 수행 기록',trace or ['이전 버전 기록'])]


def report_markdown(result: ResearchResult) -> str:
    lines = ['# 법률 리서치 보고서 초안']
    if result.source_mode == 'fictional_demo':
        lines.append('**가상 자료 시연 — 실제 법령·판례가 아닙니다.**')
    lines += [f'질문: {result.question}',f'작업번호: {result.job_id} / 상태: {result.status}',
              '자동 작성된 조사 초안입니다. 원문 전체와 법적 적용을 별도로 확인하세요.']
    for heading,paragraphs in report_sections(result):
        lines.append('## '+heading)
        lines.extend(paragraphs)
    return '\n\n'.join(lines)+'\n'


def report_docx(result: ResearchResult) -> bytes:
    doc = Document()
    # Default Word templates can inherit a colored border under Title.
    for border in list(doc.styles.element.xpath('.//w:pBdr')):
        border.getparent().remove(border)
    section = doc.sections[0]
    section.top_margin = section.bottom_margin = Inches(0.65)
    section.left_margin = section.right_margin = Inches(0.8)
    for name in ('Normal','Title','Heading 1','Heading 2'):
        style = doc.styles[name]
        style.font.name = 'Malgun Gothic'
        style.element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'Malgun Gothic')
        style.font.color.rgb = RGBColor.from_string('172D3E') if name.startswith('Heading') else RGBColor(0,0,0)
    normal = doc.styles['Normal']
    normal.font.size = Pt(9)
    normal.paragraph_format.space_after = Pt(5)
    normal.paragraph_format.line_spacing = 1.1
    doc.styles['Title'].font.size = Pt(22)
    doc.styles['Heading 1'].font.size = Pt(14)
    doc.add_paragraph('법률 리서치 보고서 초안',style='Title')
    if result.source_mode == 'fictional_demo':
        p=doc.add_paragraph('가상 자료 시연입니다. 실제 대한민국 법령이나 판례가 아닙니다.')
        p.runs[0].bold = True
    doc.add_paragraph('질문: '+result.question)
    doc.add_paragraph('작업번호: '+result.job_id+' / 상태: '+result.status)
    doc.add_paragraph('확보한 원문과 인용 대조 결과를 정리한 검토 초안입니다. 실제 사건에 적용하기 전에 사실관계와 원문 전체를 확인해야 합니다.')
    for heading,paragraphs in report_sections(result):
        doc.add_heading(heading,level=1)
        for text in paragraphs:
            doc.add_paragraph(text)
    output = BytesIO()
    doc.save(output)
    return output.getvalue()
