"""Synchronous, bounded, evidence-first legal research workflow.

This is the P0 implementation, not an autonomous background agent.
"""
import re
import uuid
from .models import ResearchRequest, ResearchResult, Claim
from .verifier import verify_claims, canonical
from .sources import SourceError
from .llm import OllamaError, OllamaResearcher

KNOWN_LAWS = ('민법','상법','형법','형사소송법','민사소송법','근로기준법','소득세법',
              '법인세법','자본시장과 금융투자업에 관한 법률','주택임대차보호법','개인정보 보호법')


def infer_law(question):
    for law in sorted(KNOWN_LAWS, key=len, reverse=True):
        if law in question:
            return law
    return ''


def infer_case_query(question):
    # Short query works better with the official full-text API than a long free-form prompt.
    pieces = re.findall(r'[가-힣A-Za-z0-9]+', question)
    stop = {'판례','관련','대법원','검색','요약','정리','법률','분석','자세히','알려줘','해줘','민법','상법','법령','조문','대한','어떤','있는','판결','관한','조항'}
    terms = [p for p in pieces if len(p) >= 2 and p not in stop and not re.match(r'^제\d+조$',p)]
    return ' '.join(terms[:3]) if terms else question[:45]


class ResearchService:
    def __init__(self, provider, store, llm: OllamaResearcher | None = None, cache_sources=True, embedder=None):
        self.provider, self.store, self.llm = provider, store, llm
        self.cache_sources = cache_sources
        self.embedder = embedder

    def close(self):
        if hasattr(self.provider,'close'):
            self.provider.close()

    @property
    def demo(self):
        return bool(getattr(self.provider,'demo',False))

    def statutes(self, query, limit=12):
        hits = self.provider.search_statutes(query, limit=limit)
        self.store.add_log('statute_search',f'{len(hits)} hits; source={"DEMO" if self.demo else "MOLEG"}')
        return hits

    def statute_detail(self, source_id):
        doc = self.provider.statute_detail(source_id)
        if self.cache_sources:
            self.store.put_document('statute',doc.source_id,doc.name,
                                    '\n\n'.join(f'{a.label} {a.title}\n{a.text}' for a in doc.articles) + '\n'+doc.addenda,
                                    doc.source_url,doc.source_type,doc.model_dump())
        return doc

    def precedents(self, query, limit=12, search_body=True):
        hits = self.provider.search_precedents(query, limit=limit,search_body=search_body)
        self.store.add_log('precedent_search',f'{len(hits)} hits; source={"DEMO" if self.demo else "MOLEG"}')
        return hits

    def precedent_detail(self, source_id):
        doc = self.provider.precedent_detail(source_id)
        if self.cache_sources:
            combined = '\n'.join([doc.issues,doc.summary,doc.referenced_articles,doc.full_text])
            self.store.put_document('precedent',doc.source_id,
                                    f'{doc.case_name} {doc.case_number}',combined,
                                    doc.source_url,doc.source_type,doc.model_dump())
        return doc

    def similar_cases(self, query, limit=5, semantic=False, queries=None, on_document=None):
        from .models import SearchResult, RankedCase
        from .retrieval import rank_documents, case_text, tokens
        search_queries = list(dict.fromkeys(queries or [query]))[:4]
        output = SearchResult(query=query, queries=search_queries,
                              source_mode='fictional_demo' if self.demo else 'official')
        hits, origins = {}, {}
        per_query = max(1, min(limit, 12))
        # Interleave query results so the broad base query cannot consume all slots.
        batches = []
        for q in search_queries:
            try:
                batch = self.precedents(q, limit=per_query)
                batches.append(batch)
                for hit in batch:
                    origins.setdefault(hit.source_id, []).append(q)
            except SourceError as exc:
                output.warnings.append(str(exc))
        for i in range(per_query):
            for batch in batches:
                if i < len(batch):
                    hits.setdefault(batch[i].source_id, batch[i])
        documents = []
        for ident in list(hits)[:max(1,min(limit,12))]:
            try:
                case = self.precedent_detail(ident)
                output.downloaded += 1
                if not (case.summary or case.issues or case.full_text):
                    output.warnings.append(f'{ident}: 판결 내용이 없어 순위에서 제외')
                    continue
                documents.append(case)
                if on_document:
                    on_document(case)
            except (SourceError,KeyError) as exc:
                output.warnings.append(str(exc))
        embedder = getattr(self, 'embedder', None) if semantic else None
        if semantic and not embedder:
            output.warnings.append('임베딩 모델 미설정: 키워드 검색 순위만 사용했습니다.')
        texts = [case_text(c) for c in documents]
        scores, method, warnings = rank_documents(query, texts, embedder)
        output.warnings.extend(warnings)
        terms = set(tokens(query))
        for case,score,text in zip(documents,scores,texts):
            output.results.append(RankedCase(case=case,score=round(score,6),method=method,
                matched_terms=sorted(terms & set(tokens(text)))[:15],queries=origins[case.source_id]))
        output.results.sort(key=lambda x:-x.score)
        if not output.results:
            output.warnings.append('검색된 원문이 없습니다. 관련 판례 부존재를 의미하지 않습니다.')
        return output

    def analyze_case(self, source_id, question='', enable_llm=False):
        from .analysis import analyze_case
        return analyze_case(self.precedent_detail(source_id),question,self.llm if enable_llm else None)

    def run(self, req: ResearchRequest, on_progress=None) -> ResearchResult:
        from .models import AgentStep, PrecedentHit
        from .db import iso_now
        from .retrieval import case_text, counter_queries, select_context
        from .analysis import analyze_case
        from .agents import run_agent, compose_memo
        from .verifier import temporal_check
        import hashlib
        import time
        started = time.monotonic()
        result = ResearchResult(job_id=uuid.uuid4().hex, question=req.question, status='PLANNING',
            source_mode='fictional_demo' if self.demo else 'official', request=req.model_dump(mode='json'))
        result.research_context = {'chat_model':getattr(self.llm,'model','') if req.enable_llm else '',
            'embedding_model':getattr(self.embedder,'model','') if req.semantic_search else '',
            'precedent_scope':'가상 자료' if self.demo else '법제처 API 대법원 제공 데이터',
            'human_review':'미검토'}
        corpus, cases = {}, {}
        self.store.save_job(result)

        def checkpoint(stage=None, progress=None):
            if stage is not None:
                result.current_stage = stage
            if progress is not None:
                result.progress = progress
            result.checkpoint_at = iso_now()
            result.elapsed_seconds = round(time.monotonic()-started, 1)
            for source in result.sources:
                key = source['id']
                if key in corpus:
                    source.setdefault('sha256', hashlib.sha256(corpus[key].encode()).hexdigest())
                    source.setdefault('fetched_at', iso_now())
                    source.setdefault('source_type',key.split(':')[0])
            self.store.save_job(result)
            if self.cache_sources:
                for source in result.sources:
                    if source['id'] in corpus:
                        self.store.save_snapshot(result.job_id,source['id'],corpus[source['id']],source)
            if on_progress:
                on_progress(result.model_copy(deep=True))

        def step(role, status, detail='', ids=None):
            now = iso_now()
            result.steps.append(AgentStep(role=role,status=status,detail=detail,
                source_ids=ids or [],finished_at=now))
            self.store.add_log(role, status+': '+detail, result.job_id)
            checkpoint()

        def add_case(case):
            key = f'{case.source_type}:precedent:{case.source_id}'
            if key in corpus:
                return key
            text = case_text(case)
            corpus[key], cases[key] = text, case
            result.case_hits.append(PrecedentHit.model_validate(case.model_dump()))
            result.sources.append({'id':key,'type':'precedent','name':f'{case.court} {case.case_number} {case.case_name}',
                'url':case.source_url,'judgment_date':case.judgment_date,'excerpt':(case.summary or case.issues or case.full_text)[:600]})
            checkpoint()
            return key

        try:
            checkpoint('조사 계획', 5)
            law_query = req.law_query.strip() or infer_law(req.question)
            query = req.precedent_query.strip() or infer_case_query(req.question)
            queries = [query]
            if req.mode == 'deep' and len(query.split())>1:
                queries.append(query.split()[0])
            result.search_queries = queries.copy()
            step('planner','COMPLETED',f'법령: {law_query or "미지정"}; 판례 검색 {len(queries)}개; 본문 최대 {min(req.max_cases,12)}개 + 반론 최대 3개')
            result.status = 'RETRIEVING'
            checkpoint('법령 검색·조문 조회', 10)
            if law_query:
                try:
                    result.law_hits = self.statutes(law_query,limit=10)
                    exact = next((h for h in result.law_hits if h.name == law_query),None)
                    hit = exact or (result.law_hits[0] if result.law_hits else None)
                    if hit:
                        if not exact and not self.demo:
                            result.warnings.append(f'정확히 일치하는 법령명이 없어 {hit.name}을 후보로 사용했습니다.')
                        law = self.statute_detail(hit.source_id)
                        key = f'{law.source_type}:statute:{law.source_id}'
                        # Include addenda and all articles, even late articles in long statutes.
                        text = '\n\n'.join(f'{a.label} ({a.title})\n{a.text}' for a in law.articles)
                        if law.addenda:
                            text += '\n부칙\n'+law.addenda
                        if text.strip():
                            corpus[key] = text
                            result.sources.append({'id':key,'type':'statute','name':law.name,'url':law.source_url,
                                'effective_date':law.effective_date,'article_count':len(law.articles),'excerpt':text[:500]})
                    else:
                        result.warnings.append('해당 법령 검색 결과가 없습니다.')
                    step('statute_researcher','COMPLETED' if any(s['type']=='statute' for s in result.sources) else 'EMPTY',ids=list(corpus))
                except (SourceError,KeyError) as exc:
                    result.warnings.append('법령 조회: '+str(exc))
                    step('statute_researcher','FAILED',str(exc))
            else:
                result.warnings.append('법령명 미지정: 판례 검색만 수행했습니다.')
                step('statute_researcher','SKIPPED','법령명 미지정')

            checkpoint('판례 검색·본문 수집', 25)
            found = self.similar_cases(query,min(req.max_cases,12),req.semantic_search,queries,on_document=add_case)
            result.warnings.extend(found.warnings)
            for ranked in found.results:
                add_case(ranked.case)
            step('case_researcher','COMPLETED' if found.results else 'EMPTY',
                 f'{len(found.results)}개 원문 순위화', list(cases))

            counter_ids = []
            if req.counterarguments and req.mode != 'quick':
                cq = counter_queries(query)
                result.search_queries.extend(cq)
                checkpoint('반론 후보 검색·본문 수집', 45)
                opposite = self.similar_cases(query+' '+req.position, min(req.max_cases,3),req.semantic_search,cq,on_document=add_case)
                result.warnings.extend(opposite.warnings)
                for ranked in opposite.results:
                    key = add_case(ranked.case)
                    counter_ids.append(key)
                    result.counter_candidates.append({'source_id':key,'case_number':ranked.case.case_number,
                        'queries':ranked.queries,'status':'CANDIDATE_NOT_CONFIRMED',
                        'reason':'반론 검색에서 발견. 원문 검토 전에는 반대 판례로 확정하지 않음'})
                step('counter_searcher','COMPLETED' if counter_ids else 'EMPTY',f'후보 {len(counter_ids)}건',counter_ids)
            else:
                step('counter_searcher','SKIPPED','빠른 모드 또는 반론 검색 해제')

            # Immutable source snapshot hashes make later cache updates detectable.
            for s in result.sources:
                s['sha256'] = hashlib.sha256(corpus[s['id']].encode()).hexdigest()
                s['fetched_at'] = iso_now()
                s['source_type'] = s['id'].split(':')[0]
                if self.cache_sources:
                    self.store.save_snapshot(result.job_id,s['id'],corpus[s['id']],s)
            result.status = 'ANALYZING'
            checkpoint('판결문 구조 분석', 60)
            for key,case in cases.items():
                # Structured extraction for all cases, optional LLM analysis via dedicated UI/API.
                result.analyses.append(analyze_case(case,req.question))
            step('case_analyst','COMPLETED' if cases else 'EMPTY',f'{len(cases)}개 판결문 구조 추출',list(cases))

            # Deterministic evidence fallback is visibly distinct from AI interpretation.
            for key,text in select_context(req.question,corpus).items():
                lines = [line.strip() for line in text.splitlines() if len(canonical(line)) >= 15]
                quote = next((line for line in lines if len(line)<=300),lines[0][:300] if lines else '')
                if quote:
                    result.claims.append(Claim(text='확보된 원문 발췌 (AI 법률 판단 아님)',source_id=key,quote=quote))
            llm = self.llm if req.enable_llm else None
            roles = ['legal_analyst']
            if req.mode != 'quick':
                if req.counterarguments:
                    roles.append('opposition_analyst')
                roles.append('reviewer')
            for index, role in enumerate(roles):
                checkpoint({'legal_analyst':'법률 분석','opposition_analyst':'반론 분석','reviewer':'비판 검토'}[role], 65+index*7)
                if not llm:
                    step(role,'SKIPPED','AI 추론 비활성화')
                    continue
                good,bad,warnings = run_agent(role,req.question,corpus,llm,req.position,result.claims if role=='reviewer' else None)
                result.warnings.extend(warnings)
                result.excluded_claims.extend(bad)
                if role == 'opposition_analyst':
                    result.counter_claims.extend(good)
                else:
                    result.claims.extend(good)
                step(role,'COMPLETED' if good else 'PARTIAL',f'문구 일치 {len(good)}건 / 배제 {len(bad)}건',[c.source_id for c in good])
            if req.enable_llm and not llm:
                result.warnings.append('Ollama 모델 미설정: 역할별 AI 분석을 실행하지 못했습니다.')

            result.status = 'VERIFYING'
            checkpoint('인용·날짜 대조', 90)
            result.claims,rejected = verify_claims(result.claims,corpus)
            result.excluded_claims.extend(rejected)
            result.counter_claims,rejected = verify_claims(result.counter_claims,corpus)
            result.excluded_claims.extend(rejected)
            metadata = {s['id']:s for s in result.sources}
            for attr in ('claims','counter_claims'):
                items = [temporal_check(c,metadata.get(c.source_id,{}),req.as_of) for c in getattr(result,attr)]
                future = [c for c in items if c.temporal_status == 'AFTER_AS_OF']
                result.excluded_claims.extend(c.model_copy(update={'reason':'검토 기준일 이후 자료: 적용 근거에서 제외'}) for c in future)
                setattr(result,attr,[c for c in items if c.temporal_status!='AFTER_AS_OF'])
            if req.as_of:
                result.warnings.append('기준일과 원문 날짜만 대조했습니다. 과거 시행법·부칙 적용·선례 변경 여부는 미검증입니다.')
            if result.excluded_claims:
                result.warnings.append(f'인용 미일치 또는 기준일 이후 분석 {len(result.excluded_claims)}건을 배제했습니다.')
            step('citation_verifier','COMPLETED',f'원문 일치 {len(result.claims)+len(result.counter_claims)}건 / 법적 타당성 미보증')
            result.warnings = list(dict.fromkeys(result.warnings))
            if not corpus:
                result.summary = '확인 가능한 원문이 없습니다. 인증값·검색어·공식 API 상태를 확인하세요.'
            elif self.demo:
                result.summary = '가상 시연 자료를 분석했습니다. 실제 대한민국 법령·판례가 아닙니다.'
            else:
                result.summary = f'공식 출처 원문 {len(corpus)}개를 확보했습니다. 적용 판단은 추가 검토가 필요합니다.'
            checkpoint('검토서 작성', 95)
            result.memo = compose_memo(result,req.position)
            step('memo_writer','COMPLETED','문구 대조된 근거와 반론을 검토서 초안으로 구성')
            result.status = 'PARTIAL' if result.warnings or not corpus else 'COMPLETED'
        except Exception as exc:
            result.status = 'FAILED'
            result.warnings.append(f'작업 실패: {type(exc).__name__}')
            self.store.add_log('research_error',type(exc).__name__,result.job_id)
        checkpoint('실패: '+result.current_stage if result.status=='FAILED' else '조사 완료',
                   result.progress if result.status=='FAILED' else 100)
        self.store.add_log('research_finished',result.status,result.job_id)
        return result
