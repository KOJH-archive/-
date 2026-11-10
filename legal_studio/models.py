"""Normalized data contracts, kept separate from source-specific XML."""
from pydantic import BaseModel, Field
from typing import Literal
from datetime import date


class StatuteHit(BaseModel):
    source_id: str
    law_id: str = ''
    name: str
    effective_date: str = ''
    promulgation_date: str = ''
    ministry: str = ''
    source_url: str = ''
    source_type: str = 'MOLEG'


class Article(BaseModel):
    label: str
    title: str = ''
    text: str
    effective_date: str = ''


class StatuteDetail(BaseModel):
    source_id: str
    name: str
    articles: list[Article] = Field(default_factory=list)
    effective_date: str = ''
    addenda: str = ''
    source_url: str = ''
    source_type: str = 'MOLEG'


class PrecedentHit(BaseModel):
    source_id: str
    case_number: str = ''
    case_name: str = ''
    court: str = ''
    judgment_date: str = ''
    source_url: str = ''
    source_type: str = 'MOLEG'


class PrecedentDetail(PrecedentHit):
    issues: str = ''
    summary: str = ''
    referenced_articles: str = ''
    referenced_cases: str = ''
    full_text: str = ''


class ResearchRequest(BaseModel):
    question: str = Field(min_length=3, max_length=3000)
    law_query: str = Field(default='', max_length=150)
    precedent_query: str = Field(default='', max_length=150)
    max_cases: int = Field(default=5, ge=1, le=20)
    enable_llm: bool = False
    mode: Literal['quick', 'research', 'deep'] = 'research'
    position: str = Field(default='', max_length=2000)
    counterarguments: bool = True
    semantic_search: bool = False
    as_of: date | None = None


class Claim(BaseModel):
    text: str
    source_id: str
    quote: str
    status: str = 'NOT_CHECKED'
    reason: str = ''
    role: str = 'evidence'
    locator: str = ''
    source_hash: str = ''
    temporal_status: str = 'NOT_CHECKED'


class AgentStep(BaseModel):
    role: str
    status: str = 'COMPLETED'
    detail: str = ''
    source_ids: list[str] = Field(default_factory=list)
    started_at: str = ''
    finished_at: str = ''


class CaseAnalysis(BaseModel):
    source_id: str
    case_number: str = ''
    sections: dict[str, str] = Field(default_factory=dict)
    claims: list[Claim] = Field(default_factory=list)
    excluded_claims: list[Claim] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    coverage: str = 'EXTRACTIVE'


class RankedCase(BaseModel):
    case: PrecedentDetail
    score: float
    method: str
    matched_terms: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    query: str
    results: list[RankedCase] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    source_mode: str = 'official'
    downloaded: int = 0


class ResearchResult(BaseModel):
    job_id: str
    question: str
    status: str
    law_hits: list[StatuteHit] = Field(default_factory=list)
    case_hits: list[PrecedentHit] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    excluded_claims: list[Claim] = Field(default_factory=list)
    summary: str = ''
    warnings: list[str] = Field(default_factory=list)
    source_mode: Literal['official', 'fictional_demo'] = 'official'
    steps: list[AgentStep] = Field(default_factory=list)
    analyses: list[CaseAnalysis] = Field(default_factory=list)
    counter_claims: list[Claim] = Field(default_factory=list)
    counter_candidates: list[dict] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    memo: dict[str, str] = Field(default_factory=dict)
    request: dict = Field(default_factory=dict)
    current_stage: str = ''
    progress: int = 0
    checkpoint_at: str = ''
    elapsed_seconds: float = 0
    research_context: dict = Field(default_factory=dict)
