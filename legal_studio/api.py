"""Local-only FastAPI; validated inputs and per-request connection cleanup."""
import hashlib
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from .config import Settings
from .sources import LawOpenAPI, SourceError
from .demo import FictionalDemoSource
from .db import Store
from .llm import OllamaResearcher
from .model_catalog import installed_models, choose_model
from .models import ResearchRequest, ResearchResult, PrecedentDetail, Claim
from .research import ResearchService
from .retrieval import OllamaEmbedder, counter_queries
from .analysis import analyze_case
from .verifier import verify_claims
from .reporter import report_docx, report_markdown
from .browser_tasks import make_browser_task

app = FastAPI(title='Korean Legal Research Studio',version='0.2.0',
              description='LOCAL-ONLY service; bind to 127.0.0.1. No multiuser authentication.')


def build_service(demo: bool | None = None):
    cfg = Settings.from_env()
    demo = cfg.demo_mode if demo is None else demo
    store = Store(cfg.resolved_db_path())
    provider = FictionalDemoSource() if demo else LawOpenAPI(cfg.law_oc)
    allowed = cfg.ollama_allowed()
    catalog = installed_models(cfg.ollama_base_url) if allowed and not demo else []
    chat = choose_model(catalog, 'completion', cfg.ollama_model)
    embedding = choose_model(catalog, 'embedding', cfg.embedding_model)
    llm = OllamaResearcher(cfg.ollama_base_url,chat) if chat else None
    embedder = OllamaEmbedder(cfg.ollama_base_url,embedding) if embedding else None
    return ResearchService(provider,store,llm,cfg.cache_sources,embedder)


def service_dependency():
    service = build_service()
    try:
        yield service
    finally:
        service.close()


def handle_source_error(exc):
    raise HTTPException(status_code=503,detail=str(exc)) from exc


def require_llm(enabled, service):
    if enabled and not service.llm:
        raise HTTPException(400,'설치된 OLLAMA_MODEL과 허용된 Ollama 주소가 필요합니다.')


@app.get('/api/health')
def health():
    cfg = Settings.from_env()
    return {'status':'ok','version':'0.2.0','law_api_configured':bool(cfg.law_oc),
        'llm_configured':bool(cfg.ollama_model),'ollama_allowed':cfg.ollama_allowed(),
        'embedding_configured':bool(cfg.embedding_model),
        'mode':'fictional_demo' if cfg.demo_mode else 'official'}


@app.get('/api/statutes/search')
def statutes_search(q: str = Query(min_length=1,max_length=150), limit: int = Query(10,ge=1,le=30), service=Depends(service_dependency)):
    try:
        return service.statutes(q,limit)
    except SourceError as exc:
        handle_source_error(exc)


@app.get('/api/statutes/{source_id}/articles')
def articles(source_id: str, q: str = Query('',max_length=150), service=Depends(service_dependency)):
    try:
        detail = service.statute_detail(source_id)
        compact = ''.join(q.split())
        return {'statute':detail.name,'source_url':detail.source_url,'effective_date':detail.effective_date,
                'articles':[a for a in detail.articles if not compact or compact in ''.join((a.label+' '+a.title+' '+a.text).split())],
                'addenda':detail.addenda}
    except (SourceError,KeyError) as exc:
        handle_source_error(exc)


@app.get('/api/statutes/{source_id}')
def statute_detail(source_id: str, service=Depends(service_dependency)):
    try:
        return service.statute_detail(source_id)
    except (SourceError,KeyError) as exc:
        handle_source_error(exc)


@app.get('/api/precedents/search')
def precedents_search(q: str = Query(min_length=1,max_length=150), limit: int = Query(10,ge=1,le=30),
                      page: int = Query(1,ge=1,le=1000), court: str = Query('',max_length=80),
                      case_number: str = Query('',max_length=80),date_range: str = Query('',max_length=17),
                      referenced: bool = False, service=Depends(service_dependency)):
    try:
        if service.demo:
            return service.precedents(q,limit)
        return service.provider.search_precedents(q,limit,page=page,court=court,case_number=case_number,
                                                  date_range=date_range,referenced=referenced)
    except SourceError as exc:
        handle_source_error(exc)


class SimilarRequest(BaseModel):
    query: str = Field(min_length=2,max_length=1000)
    limit: int = Field(5,ge=1,le=12)
    semantic: bool = False
    counterarguments: bool = False


@app.post('/api/precedents/similar')
def similar(request: SimilarRequest, service=Depends(service_dependency)):
    queries = counter_queries(request.query) if request.counterarguments else None
    return service.similar_cases(request.query,request.limit,request.semantic,queries)


class AnalysisRequest(BaseModel):
    question: str = Field('',max_length=3000)
    enable_llm: bool = False


@app.post('/api/precedents/{source_id}/analysis')
def case_analysis(source_id: str, request: AnalysisRequest, service=Depends(service_dependency)):
    require_llm(request.enable_llm,service)
    try:
        return service.analyze_case(source_id,request.question,request.enable_llm)
    except (SourceError,KeyError) as exc:
        handle_source_error(exc)


@app.get('/api/precedents/{source_id}')
def precedents_detail(source_id: str, service=Depends(service_dependency)):
    try:
        return service.precedent_detail(source_id)
    except (SourceError,KeyError) as exc:
        handle_source_error(exc)


class TextAnalysisRequest(AnalysisRequest):
    text: str = Field(min_length=10,max_length=130000)


@app.post('/api/analysis/text')
def text_analysis(request: TextAnalysisRequest, service=Depends(service_dependency)):
    require_llm(request.enable_llm,service)
    case = PrecedentDetail(source_id=hashlib.sha256(request.text.encode()).hexdigest()[:16],
        case_name='사용자 제공 문서',source_type='USER_UPLOAD',full_text=request.text)
    return analyze_case(case,request.question,service.llm if request.enable_llm else None)


class VerifyRequest(BaseModel):
    source_id: str = Field(min_length=1,max_length=200)
    text: str = Field(min_length=1,max_length=130000)
    quote: str = Field(min_length=1,max_length=3000)
    claim: str = Field('',max_length=2000)


@app.post('/api/citations/verify')
def verify(request: VerifyRequest):
    good,bad = verify_claims([Claim(text=request.claim,source_id=request.source_id,quote=request.quote)],
                            {request.source_id:request.text})
    return {'accepted':good,'rejected':bad,'authority':'USER_SUPPLIED_TEXT_ONLY'}


@app.post('/api/research/jobs',response_model=ResearchResult)
def research(request: ResearchRequest, service=Depends(service_dependency)):
    require_llm(request.enable_llm,service)
    return service.run(request)


@app.get('/api/research/jobs')
def jobs(service=Depends(service_dependency)):
    return service.store.recent_jobs()


@app.get('/api/research/jobs/{job_id}')
def job(job_id: str, service=Depends(service_dependency)):
    result = service.store.get_job(job_id)
    if result is None:
        raise HTTPException(404,'작업을 찾지 못했습니다.')
    return result


@app.get('/api/research/jobs/{job_id}/sources')
def snapshots(job_id: str, service=Depends(service_dependency)):
    if not service.store.get_job(job_id):
        raise HTTPException(404,'작업을 찾지 못했습니다.')
    return service.store.snapshots(job_id)


@app.get('/api/research/jobs/{job_id}/report.{format}')
def report(job_id: str,format: str, service=Depends(service_dependency)):
    result = service.store.get_job(job_id)
    if result is None:
        raise HTTPException(404,'작업을 찾지 못했습니다.')
    parsed = ResearchResult.model_validate(result)
    if format == 'md':
        return Response(report_markdown(parsed),media_type='text/markdown; charset=utf-8')
    if format == 'json':
        return Response(parsed.model_dump_json(indent=2),media_type='application/json',
                        headers={'Content-Disposition':f'attachment; filename="legal-research-{job_id}.json"'})
    if format == 'docx':
        return Response(report_docx(parsed),media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        headers={'Content-Disposition':f'attachment; filename="legal-research-{job_id}.docx"'})
    raise HTTPException(400,'지원하지 않는 형식입니다 (md/docx/json).')


class BrowserRequest(BaseModel):
    query: str = Field(min_length=1,max_length=300)
    url: str = Field('',max_length=2000)


@app.post('/api/browser/tasks')
def browser_task(request: BrowserRequest):
    try:
        return make_browser_task(request.query,request.url)
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from exc


class CaseReferenceRequest(BaseModel):
    case_number: str = Field(min_length=3,max_length=100)
    court: str = Field('',max_length=80)
    judgment_date: str = Field('',max_length=10)


@app.post('/api/citations/case-reference')
def case_reference(request: CaseReferenceRequest, service=Depends(service_dependency)):
    from .verifier import verify_case_reference
    try:
        return verify_case_reference(service.provider,request.case_number,request.court,request.judgment_date)
    except SourceError as exc:
        handle_source_error(exc)
