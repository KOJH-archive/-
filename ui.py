"""Streamlit desktop UI. Start with: streamlit run ui.py --server.address 127.0.0.1"""
import streamlit as st
import json
import hashlib
from legal_studio.model_catalog import installed_models, choose_model
from legal_studio.retrieval import OllamaEmbedder
from legal_studio.analysis import analyze_case
from legal_studio.models import PrecedentDetail
from legal_studio.browser_tasks import make_browser_task, task_prompt, ego_status
from legal_studio.config import Settings
from legal_studio.db import Store
from legal_studio.sources import LawOpenAPI, SourceError
from legal_studio.demo import FictionalDemoSource
from legal_studio.llm import OllamaResearcher, OllamaError
from legal_studio.models import ResearchRequest, ResearchResult, Claim
from legal_studio.research import ResearchService
from legal_studio.reporter import report_markdown, report_docx
from legal_studio.verifier import verify_claims
from legal_studio.documents import extract_document, DocumentError

st.set_page_config(page_title='Korean Legal Research Studio',page_icon='⚖️',layout='wide',initial_sidebar_state='expanded')

st.markdown('''<style>
[data-testid="stMetricValue"] {font-size:1.25rem;}
h1,h2,h3 {letter-spacing:-0.02em;}
.smallcaps {letter-spacing:.12em; text-transform:uppercase; font-size:.7rem; color:#9cb4c3;}
</style>''',unsafe_allow_html=True)

cfg=Settings.from_env()

@st.cache_resource
def store_for(path):
    return Store(path)

store=store_for(str(cfg.resolved_db_path()))

@st.cache_data(ttl=30)
def model_catalog(url):
    return installed_models(url)

with st.sidebar:
    st.markdown('## ⚖️ Legal Research Studio')
    st.caption('한국 법률·판례 리서치 | v0.2.0 · 로컬 리서치')
    demo=st.toggle('가상 샘플 모드',value=cfg.demo_mode,
                   help='공식 법령·판례가 아닌 소프트웨어 동작 확인용 가상 자료를 사용합니다.')
    if demo:
        st.warning('가상 데이터입니다. 실제 법률 검토에 사용할 수 없습니다.')
    elif not cfg.law_oc:
        st.warning('LAW_OC가 없습니다. .env에 API 인증값을 설정하거나 가상 샘플 모드를 켜세요.')
    else:
        st.success('법제처 API 인증값 설정됨 (실제 연결 성공은 검색으로 확인)')
    if st.button('설치된 모델 새로고침'):
        model_catalog.clear()
    catalog=model_catalog(cfg.ollama_base_url) if cfg.ollama_allowed() else []
    if not cfg.ollama_allowed():
        st.error('허용되지 않은 Ollama 주소입니다.')
    chat_names=[m['name'] for m in catalog if 'completion' in m['capabilities']]
    embedding_names=[m['name'] for m in catalog if 'embedding' in m['capabilities']]
    default_chat=choose_model(catalog,'completion',cfg.ollama_model)
    model_choices=['(사용 안 함)']+chat_names
    selected_model=st.selectbox('Ollama 모델',model_choices,
        index=model_choices.index(default_chat) if default_chat else 0,
        help='설치된 채팅 모델만 표시합니다. 기본값은 설치 용량이 가장 작은 모델입니다.')
    default_embed=choose_model(catalog,'embedding',cfg.embedding_model)
    embed_choices=['(사용 안 함)']+embedding_names
    selected_embed=st.selectbox('임베딩 모델',embed_choices,
        index=embed_choices.index(default_embed) if default_embed else 0)
    if not embedding_names:
        st.caption('설치된 임베딩 모델이 없어 키워드 검색을 사용합니다.')
    if not chat_names:
        st.warning('설치된 채팅 모델을 찾지 못했습니다. Ollama 실행 상태를 확인하세요.')
    use_llm=st.checkbox('AI 분석 활성화',value=cfg.enable_llm and selected_model!='(사용 안 함)',
                        disabled=(selected_model=='(사용 안 함)'))
    st.caption('출처 확인과 검색은 LLM 없이도 동작합니다.')
    st.divider()
    st.caption('이 앱은 법률 자문을 대체하지 않습니다. 인용 검증은 원문 문구 일치이며 법적 타당성을 보증하지 않습니다.')

# A mode switch must never leave fictional results visible in official mode (or vice versa).
if st.session_state.get('_active_demo_mode') != demo:
    for key in ('law_hits','law_detail','case_hits','case_detail','case_comparison','last_result','similar_result','case_analysis'):
        st.session_state.pop(key,None)
    st.session_state['_active_demo_mode'] = demo

provider=FictionalDemoSource() if demo else LawOpenAPI(cfg.law_oc)
llm=OllamaResearcher(cfg.ollama_base_url,selected_model) if selected_model!='(사용 안 함)' else None
embedder=OllamaEmbedder(cfg.ollama_base_url,selected_embed) if selected_embed!='(사용 안 함)' and cfg.ollama_allowed() else None
service=ResearchService(provider,store,llm,cfg.cache_sources,embedder)

st.title('한국 법률 리서치 워크스페이스')
st.caption('공식 원문 중심 검색 · 판례 요약 · 인용 원문 대조 · 로컬 기록')
if demo:
    st.error('DEMO / 가상 자료만 사용 중입니다. 실제 법령·판례 결과가 아닙니다.',icon='🧪')

law_tab, case_tab, research_tab, document_tab, archive_tab, browser_tab, system_tab=st.tabs(['📚 법령·조문','⚖️ 판례 리서치','🧠 심층 리서치','📄 문서 분석','🗂️ 기록·보고서','🌐 웹 탐색 보조','⚙️ 설정·로그'])

with law_tab:
    st.subheader('법령 검색 및 조문 분석')
    with st.form('law_search_form'):
        q=st.text_input('법률명',value='샘플거래법' if demo else '민법',help='가능하면 공식 법령명을 입력하세요.')
        search=st.form_submit_button('법령 검색',type='primary')
    if search:
        try:
            st.session_state['law_hits']=service.statutes(q)
            st.session_state.pop('law_detail',None)
        except SourceError as exc:
            st.error(str(exc))
            st.session_state['law_hits']=[]
    hits=st.session_state.get('law_hits',[])
    if hits:
        pick=st.selectbox('검색된 법령',range(len(hits)),
                          format_func=lambda i:f'{hits[i].name}  |  시행 {hits[i].effective_date or "미확인"}',key='law_choice')
        if st.button('전체 조문 열기',key='open_statute'):
            try:
                st.session_state['law_detail']=service.statute_detail(hits[pick].source_id)
            except (SourceError,KeyError) as exc:
                st.error(str(exc))
        detail=st.session_state.get('law_detail')
        if detail:
            st.markdown(f'### {detail.name}')
            st.caption(f'시행일 {detail.effective_date or "미확인"} · 조문 {len(detail.articles)}개')
            if detail.source_url:
                st.link_button('공식 법령 원문',detail.source_url)
            if detail.articles:
                keyword=st.text_input('조문 안에서 검색',placeholder='예: 통지, 채권')
                filtered=[a for a in detail.articles if not keyword or keyword in a.text or keyword in a.title or keyword in a.label]
                st.caption(f'{len(filtered)}개 조문 표시')
                options=list(range(len(filtered)))
                if options:
                    i=st.selectbox('조항 선택',options,format_func=lambda j:f'{filtered[j].label} {filtered[j].title}')
                    article=filtered[i]
                    st.markdown(f'#### {article.label} {article.title}')
                    st.code(article.text,language=None,wrap_lines=True)
                    if article.effective_date:
                        st.caption('조항 시행일: '+article.effective_date)
                    if st.button('선택 조항 원문 기반 AI 해설',disabled=not use_llm or not llm):
                        corpus={f'{detail.source_type}:statute:{detail.source_id}:{article.label}':article.text}
                        try:
                            raw,limits=llm.research_claims(f'{detail.name} {article.label}의 법률적 요건을 원문 범위 내에서 설명',corpus)
                            good,bad=verify_claims(raw,corpus)
                            if good:
                                for c in good:
                                    st.write(c.text)
                                    st.caption('원문 일치: '+c.quote)
                            else:
                                st.warning('검증을 통과한 인용이 없습니다. 원문만 참고하세요.')
                            for msg in limits:
                                st.info(msg)
                            if bad:
                                st.caption(f'원문 미일치 AI 주장 {len(bad)}건 제외')
                        except OllamaError as exc:
                            st.error(str(exc))
                    st.caption('AI 해설을 제공하더라도 법률적 타당성을 보증하지 않습니다.')
            if detail.addenda:
                with st.expander('부칙 (원문 추출)'):
                    st.text(detail.addenda[:30000])
    elif search:
        st.info('검색 결과가 없습니다. 인증 및 검색어를 확인하세요.')

with case_tab:
    st.subheader('관련 판례 검색·원문 분석')
    st.caption('자동 분석 검색 범위: 법제처 API의 대법원 제공 데이터. 국세청 HTML 전용 자료는 포함하지 않습니다.')
    with st.form('case_search_form'):
        q=st.text_input('판례명·법률 쟁점·사건번호',value='샘플 통지' if demo else '채권양도 대항요건')
        search_body=st.checkbox('본문 검색',value=True)
        limit=st.slider('목록 최대 건수',min_value=3,max_value=30,value=10)
        searched=st.form_submit_button('판례 검색',type='primary')
    if searched:
        try:
            st.session_state['case_hits']=service.precedents(q,limit,search_body)
            st.session_state.pop('case_detail',None)
        except SourceError as exc:
            st.error(str(exc))
            st.session_state['case_hits']=[]
    case_hits=st.session_state.get('case_hits',[])
    if case_hits:
        selected=st.selectbox('판례 목록',list(range(len(case_hits))),
                              format_func=lambda i:f'{case_hits[i].court} {case_hits[i].case_number} | {case_hits[i].case_name}')
        if st.button('판결문 내용 불러오기'):
            try:
                st.session_state['case_detail']=service.precedent_detail(case_hits[selected].source_id)
            except (SourceError,KeyError) as exc:
                st.error(str(exc))
        detail=st.session_state.get('case_detail')
        if detail:
            st.markdown(f'### {detail.case_name}')
            st.caption(f'{detail.court} · {detail.case_number} · {detail.judgment_date}')
            if detail.source_url:
                st.link_button('공식 판례 원문 확인',detail.source_url)
            for title,content in [('판시사항',detail.issues),('판결요지 (공식 자료)',detail.summary),
                                  ('참조조문',detail.referenced_articles),('참조판례',detail.referenced_cases)]:
                st.markdown(f'**{title}**')
                st.write(content or '원문 제공 정보 없음')
            with st.expander('판결문 전체 (제공 범위)',expanded=False):
                st.text(detail.full_text or '전체 원문 미제공')
    elif searched:
        st.info('조회된 판례가 없습니다. 검색 범위와 API 상태를 확인하세요. 판례 부존재를 의미하지 않습니다.')


    if len(case_hits) >= 2:
        st.divider()
        st.markdown('#### 판례 2건 원문 비교')
        pair=st.multiselect('비교할 판례 2건 선택',options=list(range(len(case_hits))),max_selections=2,
                            format_func=lambda i:f'{case_hits[i].court} {case_hits[i].case_number}',key='compare_case_pair')
        if len(pair)==2 and st.button('판례 비교표 생성'):
            try:
                docs=[service.precedent_detail(case_hits[i].source_id) for i in pair]
                st.session_state['case_comparison']=docs
            except (SourceError,KeyError) as exc:
                st.error(str(exc))
        if st.session_state.get('case_comparison'):
            docs=st.session_state['case_comparison']
            ca,cb=st.columns(2)
            for col,doc in zip((ca,cb),docs):
                with col:
                    st.markdown(f'**{doc.court} {doc.case_number}**')
                    st.caption(doc.case_name+' / '+doc.judgment_date)
                    st.markdown('**판시사항**')
                    st.write(doc.issues or '미제공')
                    st.markdown('**판결요지**')
                    st.write(doc.summary or '미제공')
                    st.markdown('**참조조문**')
                    st.write(doc.referenced_articles or '미제공')
            st.info('나란히 조회한 공식 원문 필드 비교입니다. 법리 충돌·선례 변경을 자동 판단하지 않습니다.')

    st.divider()
    st.markdown('#### 유사 판례와 반대 판례 후보')
    with st.form('similar_form'):
        sim_query=st.text_area('사실관계·쟁점',value='가상 통지 기록의 확인' if demo else '채권양도 통지 없이 대항요건을 주장하는 경우')
        sim_limit=st.slider('확보할 판례 최대 수',1,12,5)
        sim_semantic=st.checkbox('임베딩 결합',value=False)
        sim_counter=st.checkbox('예외·부정·제한 후보 탐색',value=False)
        sim_run=st.form_submit_button('유사 판례 찾기')
    if sim_run:
        from legal_studio.retrieval import counter_queries
        with st.spinner('후보 원문을 수집하고 순위를 계산합니다…'):
            st.session_state['similar_result']=service.similar_cases(sim_query,sim_limit,sim_semantic,counter_queries(sim_query) if sim_counter else None)
    sim_result=st.session_state.get('similar_result')
    if sim_result:
        st.caption('순위 점수는 검색된 후보 내 관련도이며 승소 확률이나 법리 일치 확률이 아닙니다.')
        for warning in sim_result.warnings:
            st.warning(warning)
        for ranked in sim_result.results:
            with st.expander(ranked.case.case_number+' | '+ranked.case.case_name):
                st.caption(f'{ranked.method} / 점수 {ranked.score} / 일치어: '+', '.join(ranked.matched_terms))
                st.write(ranked.case.summary or ranked.case.issues)
                st.caption('검색어: '+', '.join(ranked.queries))
                if st.button('심층 분석',key='analyze_'+ranked.case.source_id):
                    with st.spinner('판결문을 분석합니다…'):
                        st.session_state['case_analysis']=analyze_case(ranked.case,sim_result.query,llm if use_llm else None)
        analysis=st.session_state.get('case_analysis')
        if analysis:
            st.markdown('#### 심층 분석 결과 · '+analysis.case_number)
            st.caption(analysis.coverage)
            for claim in analysis.claims:
                st.write(claim.text)
                st.code(claim.quote,language=None,wrap_lines=True)
                st.caption(claim.locator)
            for warning in analysis.warnings:
                st.warning(warning)
            st.download_button('판결문 분석 JSON',analysis.model_dump_json(indent=2),file_name='case-analysis.json',mime='application/json')

    st.divider()
    st.markdown('#### 사건번호 인용 확인')
    with st.form('case_citation_form'):
        cite_number=st.text_input('확인할 사건번호',value='가상2099예시1' if demo else '')
        cite_court=st.text_input('법원명 (선택)',value='')
        cite_date=st.text_input('선고일 (선택, YYYYMMDD)',value='')
        cite_run=st.form_submit_button('공식 목록과 사건번호 대조')
    if cite_run:
        from legal_studio.verifier import verify_case_reference
        try:
            check=verify_case_reference(provider,cite_number,cite_court,cite_date)
            st.write(check)
        except SourceError as exc:
            st.error(str(exc))

with research_tab:
    st.subheader('법령 + 판례 통합 리서치')
    with st.form('research_form'):
        question=st.text_area('법률 검토 질문',value=('샘플 거래의 통지와 확인 기록' if demo else '민법상 채권양도의 대항요건과 관련 판례를 분석해 줘'),height=110)
        col1,col2=st.columns(2)
        with col1:
            law_query=st.text_input('법률명 (선택)',value='샘플거래법' if demo else '민법')
            mode=st.selectbox('조사 깊이',['quick','research','deep'],index=1,
                              format_func=lambda x:{'quick':'Quick','research':'Research','deep':'Deep (추가 검색)'}[x])
        with col2:
            prec_query=st.text_input('판례 검색어 (선택)',value='샘플 통지' if demo else '채권양도')
            max_cases=st.slider('판례 본문 조회 최대 수',1,8,4)
        position=st.text_area('검토할 주장 또는 상대방 주장 (선택)',placeholder='예: 통지 기록만으로 상대방에게 대항할 수 있다는 주장')
        counter=st.checkbox('반대 판례 후보 검색 및 반론 검토',value=True)
        semantic=st.checkbox('Ollama 임베딩 순위 결합',value=False,help='사이드바에서 임베딩 모델을 선택하세요. 실패하면 키워드 순위로 대체합니다.')
        as_of=st.date_input('검토 기준일 (선택)',value=None,help='날짜 대조만 수행합니다. 해당 날짜 시행 법령을 자동 확보하는 기능은 아닙니다.')
        run=st.form_submit_button('리서치 실행',type='primary')
    if run:
        try:
            req=ResearchRequest(question=question,law_query=law_query,precedent_query=prec_query,
                                max_cases=max_cases,mode=mode,enable_llm=use_llm,position=position,
                                counterarguments=counter,semantic_search=semantic,as_of=as_of)
            progress_bar=st.progress(0,text='조사 준비 중')
            stage_detail=st.empty()
            def show_progress(partial):
                progress_bar.progress(partial.progress,text=partial.current_stage)
                stage_detail.caption(f'경과 {partial.elapsed_seconds:.1f}초 · 확보 원문 {len(partial.sources)}개 · 중간 저장 {partial.checkpoint_at} · 작업 {partial.job_id}')
            with st.spinner('현재 단계를 수행 중입니다. 단계 완료 시 경과 시간과 저장 상태가 갱신됩니다.'):
                st.session_state['last_result']=service.run(req,on_progress=show_progress)
        except Exception as exc:
            st.error('요청 오류: '+str(exc))
    result=st.session_state.get('last_result')
    if result:
        st.markdown('### 결과')
        c1,c2,c3=st.columns(3)
        c1.metric('작업 상태',result.status)
        c2.metric('확보된 원문',len(result.sources))
        c3.metric('인용 원문 일치',len(result.claims))
        st.info(result.summary)
        with st.expander('역할별 수행 내역',expanded=True):
            st.dataframe([{'역할':x.role,'상태':x.status,'결과':x.detail} for x in result.steps],hide_index=True,width='stretch')
            st.caption('Ollama를 켜면 법률 분석·반론·비판 검토가 각각 독립 호출됩니다. 순차 실행하며, AI가 꺼진 역할은 SKIPPED로 표시합니다.')
        with st.expander('반대 판례 검색 후보'):
            st.dataframe(result.counter_candidates,hide_index=True,width='stretch')
            st.caption('검색 후보는 반대 법리가 확정된 판례가 아닙니다.')
            for claim in result.counter_claims:
                st.write(claim.text)
                st.code(claim.quote,language=None,wrap_lines=True)
                st.caption(claim.source_id+' / '+claim.locator)
        with st.expander('판결문 구조 분석'):
            for analysis in result.analyses:
                st.markdown('**'+analysis.case_number+'**')
                for name,text in analysis.sections.items():
                    st.text(name+': '+text[:2000])
                for warning in analysis.warnings:
                    st.caption(warning)
        with st.expander('법률 검토서 초안',expanded=False):
            for heading,body in result.memo.items():
                st.markdown('#### '+heading)
                st.text(body)
        st.download_button('전체 결과 JSON',result.model_dump_json(indent=2),file_name=f'legal-research-{result.job_id}.json',mime='application/json')
        for warning in result.warnings:
            st.warning(warning)
        st.markdown('#### 확인된 인용 (텍스트 일치만 검증)')
        if not result.claims:
            st.info('검증된 인용이 없습니다.')
        for i,claim in enumerate(result.claims,1):
            with st.expander(f'{i}. {claim.source_id}',expanded=i<=2):
                st.write(claim.text)
                st.code(claim.quote,language=None,wrap_lines=True)
                st.caption(claim.reason+' / '+claim.locator+' / 시점: '+claim.temporal_status)
        if result.excluded_claims:
            with st.expander(f'검증 실패 / 제외 {len(result.excluded_claims)}건'):
                for c in result.excluded_claims:
                    st.write(f'{c.source_id}: {c.status} / {c.reason}')
        st.markdown('#### 자료 목록')
        for s in result.sources:
            st.markdown(f'**{s["name"]}**')
            st.caption(s.get('excerpt','')[:300])
            if s.get('url'):
                st.link_button('공식 원문 열기',s['url'])
        st.markdown('#### 보고서 내보내기')
        b1,b2=st.columns(2)
        b1.download_button('Markdown 보고서',report_markdown(result),file_name=f'legal-research-{result.job_id}.md',mime='text/markdown')
        b2.download_button('Word 검토서 (DOCX)',report_docx(result),file_name=f'legal-research-{result.job_id}.docx',
                           mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document')


with document_tab:
    st.subheader('파일 기반 원문 분석 (로컬 처리)')
    st.caption('PDF · DOCX · TXT · MD / 12MB 이하 / PDF 최대 80쪽. 업로드 파일은 기본적으로 SQLite에 저장하지 않습니다.')
    uploaded=st.file_uploader('문서 선택',type=['pdf','docx','txt','md'])
    if uploaded is not None:
        try:
            document=extract_document(uploaded.name,uploaded.getvalue())
            if document.truncated:
                st.warning('문서 길이 제한으로 일부만 추출했습니다.')
            st.success(f'{document.format.upper()} · 텍스트 {len(document.text):,}자 · 범위 {document.pages_or_sections}')
            with st.expander('추출된 텍스트 미리보기'):
                st.text(document.text[:10000])
            st.warning('업로드 문서는 법적 권위 있는 원문이 아닙니다. 계약 내용·사실관계의 자료로만 취급하세요.')
            if st.button('판결문 구조 추출 (AI 없이)'):
                uploaded_case=PrecedentDetail(source_id=hashlib.sha256(document.text.encode()).hexdigest()[:16],source_type='USER_UPLOAD',full_text=document.text)
                parsed=analyze_case(uploaded_case)
                for name,text in parsed.sections.items():
                    st.markdown('**'+name+'**')
                    st.text(text[:5000])
                for warning in parsed.warnings:
                    st.info(warning)
            quote_to_check=st.text_area('원문에서 확인할 인용문 (선택)',key='manual_quote')
            if st.button('인용문 직접 대조',disabled=not quote_to_check):
                from legal_studio.verifier import verify_claim
                checked=verify_claim(Claim(text='사용자 입력 인용',source_id='USER_UPLOAD:current',quote=quote_to_check),{'USER_UPLOAD:current':document.text})
                st.write(checked.model_dump())
                st.caption('사용자 제공 문서 안의 문자열 대조이며 공식 출처 확인은 아닙니다.')
            doc_question=st.text_area('문서에서 확인할 내용',value='이 문서의 핵심 의무와 기한을 원문 인용과 함께 정리해줘')
            from urllib.parse import urlsplit
            is_remote=urlsplit(cfg.ollama_base_url).hostname not in {'localhost','127.0.0.1','::1'}
            consent=st.checkbox('외부 서버로 문서 내용 전송에 동의합니다',value=False,disabled=not is_remote) if is_remote else True
            if is_remote:
                st.error('Ollama 주소가 로컬이 아닙니다. 문서 원문이 네트워크로 전송될 수 있습니다.')
            if st.button('AI 원문 문구 분석',disabled=not use_llm or not llm or not consent):
                corpus={'USER_UPLOAD:document:'+uploaded.name:document.text}
                try:
                    raw,limits=llm.research_claims(doc_question,corpus)
                    good,bad=verify_claims(raw,corpus)
                    for claim in good:
                        st.markdown('**'+claim.text+'**')
                        st.code(claim.quote,language=None)
                    if not good:
                        st.warning('원문 문구 대조를 통과한 결과가 없습니다.')
                    if bad:
                        st.caption(f'원문 미일치 주장이 {len(bad)}건 제외되었습니다.')
                    for limit in limits:
                        st.info(limit)
                except OllamaError as exc:
                    st.error(str(exc))
        except DocumentError as exc:
            st.error(str(exc))

with archive_tab:
    st.subheader('로컬 리서치 기록')
    jobs=store.recent_jobs()
    if not jobs:
        st.info('아직 저장된 연구가 없습니다.')
    else:
        chosen=st.selectbox('저장된 작업',list(range(len(jobs))),
                            format_func=lambda i:jobs[i]['created_at'][:19]+' | '+jobs[i]['question'][:65])
        selected=ResearchResult.model_validate(store.get_job(jobs[chosen]['job_id']))
        st.write(selected.summary)
        st.caption(f'마지막 저장 단계: {selected.current_stage or "이전 기록"} · 진행 {selected.progress}% · 경과 {selected.elapsed_seconds}초 · 저장 시각 {selected.checkpoint_at}')
        st.caption(f'작업번호 {selected.job_id} · 상태 {selected.status} · 원문 {len(selected.sources)}개')
        if selected.status not in {'COMPLETED','PARTIAL','FAILED'}:
            st.warning('진행 중이거나 중단된 작업의 마지막 저장본입니다. 완료 결과가 아니며 자동 재개는 지원하지 않습니다.')
        with st.expander('저장된 원문 목록·단계 기록'):
            st.dataframe(selected.sources,hide_index=True,width='stretch')
            st.dataframe([s.model_dump() for s in selected.steps],hide_index=True,width='stretch')
        if selected.source_mode == 'fictional_demo':
            st.warning('이 저장 결과는 가상 자료입니다.')
        for claim in selected.claims:
            st.markdown(f'- {claim.quote[:250]} ({claim.status})')
        st.download_button('저장된 DOCX 보고서',report_docx(selected),
                           file_name=f'{selected.job_id}.docx',mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        st.download_button('저장된 Markdown 보고서',report_markdown(selected),
                           file_name=f'{selected.job_id}.md',mime='text/markdown')
    st.divider()
    st.markdown('#### 로컬 문서 인덱스 검색')
    cacheq=st.text_input('캐시에 저장된 원문만 검색',placeholder='예: 채권양도')
    if cacheq:
        docs=store.local_search(cacheq,limit=15,source_type='FICTIONAL_DEMO' if demo else 'MOLEG')
        for doc in docs:
            with st.expander(doc['title']):
                st.caption(doc['source_type']+' · SHA-256 '+doc['hash_sha256'][:16])
                st.text(doc['content'][:3000])
        if not docs:
            st.caption('현재 로컬 캐시에서 검색된 자료가 없습니다.')

with browser_tab:
    st.subheader('ego(lite)로 공식 웹 원문 탐색')
    st.caption('API 검색을 보완할 때 사용합니다. 현재 앱은 탐색 요청을 만들며, 실제 브라우저 조작은 PC의 ego-browser 연결 에이전트에서 수행합니다.')
    bquery=st.text_input('추가 조사할 쟁점',value='채권양도 대항요건',key='browser_query')
    burl=st.text_input('공식 원문 URL (선택)',key='browser_url')
    if st.button('웹 탐색 요청 만들기'):
        try:
            task=make_browser_task(bquery,burl)
            st.code(task_prompt(task),language=None,wrap_lines=True)
            st.download_button('탐색 요청 JSON',json.dumps(task,ensure_ascii=False,indent=2),file_name='ego-legal-task.json',mime='application/json')
            st.info('발견한 자료는 공식 API에서 다시 조회하거나 문서 분석에 넣어 확인하세요. 웹 발췌를 자동으로 공식 검증 자료로 승격하지 않습니다.')
        except ValueError as exc:
            st.error(str(exc))
    if st.button('로컬 ego-browser 설치 확인'):
        status=ego_status()
        st.write({k:v for k,v in status.items() if k!='guide'})
        if status.get('guide'):
            with st.expander('설치된 버전의 사용 가이드'):
                st.code(status['guide'],language=None)

with system_tab:
    st.subheader('환경 상태 및 실행 로그')
    st.write({'법제처 API 인증값 설정 여부':bool(cfg.law_oc),
              'Ollama 모델':selected_model,
              '실제 원문 캐시':cfg.cache_sources,
              '데이터베이스 위치':str(cfg.resolved_db_path()),
              '현재 소스':'FICTIONAL DEMO' if demo else 'MOLEG'})
    st.caption('키 값은 화면과 로그에 노출하지 않습니다.')
    st.markdown('#### 실제 연결 점검')
    st.caption('실제 법령·판례 요청과 선택한 모델의 추론을 실행합니다. 모델 점검은 CPU에서 수 분 걸릴 수 있습니다.')
    if st.button('전체 연결 점검',disabled=demo):
        from legal_studio.connection_checks import connection_checks
        rows=[]
        check_table=st.empty()
        with st.spinner('법제처 및 선택한 모델을 실제 호출하고 있습니다…'):
            for row in connection_checks(cfg,selected_model if llm else '', selected_embed if embedder else ''):
                rows.append(row)
                check_table.dataframe(rows,hide_index=True,width='stretch')
        st.session_state['connection_check_result']=rows
    elif st.session_state.get('connection_check_result'):
        st.caption('마지막 점검 결과입니다. 설정을 바꿨다면 다시 점검하세요.')
        st.dataframe(st.session_state['connection_check_result'],hide_index=True,width='stretch')
    st.markdown('#### 최근 실행 로그')
    st.dataframe(store.logs(50),width="stretch",hide_index=True)
    st.divider()
    with st.expander('로컬 데이터 완전 삭제'):
        st.warning('모든 저장된 원문, 연구 결과, 로그가 삭제됩니다. 복구할 수 없습니다.')
        confirm=st.checkbox('삭제 결과를 이해했고 삭제에 동의합니다')
        if st.button('전체 로컬 데이터 삭제',disabled=not confirm):
            store.clear_all()
            for k in ('law_hits','law_detail','case_hits','case_detail','case_comparison','last_result','similar_result','case_analysis'):
                st.session_state.pop(k,None)
            st.success('로컬 DB 내 해당 데이터가 삭제되었습니다. 외부 원본·백업은 삭제되지 않습니다.')

# HTTP pools must not accumulate across Streamlit reruns.
service.close()
