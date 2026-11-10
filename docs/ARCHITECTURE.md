> 갱신 안내 (2026-11-11): 아래 문서는 이전 개발 기록을 포함합니다. 현재 구현·검증·제약은 [최신 개발명세서](DEVELOPMENT_SPEC.md)와 [README](../README.md)를 우선 확인하세요.

# Architecture v0.2

## Runtime

Streamlit UI and optional FastAPI share `ResearchService`. The source adapter is either `LawOpenAPI` or `FictionalDemoSource`; there is no silent fallback from official data to fictional data.

| Module | Responsibility |
|---|---|
| sources.py | Authenticated DRF XML, safe parsing, bounded 429/502/503/504 retries, pagination/filter parameters |
| retrieval.py | Korean bigram BM25, query-aware text windows, optional Ollama embeddings and reciprocal rank fusion |
| analysis.py | Explicit judgment headings, structured source fields, optional source-bound LLM analysis |
| agents.py | Separate analyst/opposition/reviewer prompts, verifier-gated claims, deterministic memo composition |
| research.py | Bounded sequential orchestration, progress records, source collection and temporal exclusion |
| verifier.py | Normalized quote matching, locator, hash, case metadata and date checks |
| db.py | Additive SQLite tables, FTS5 cache, jobs/events, immutable per-job source snapshots |
| browser_tasks.py | Official-site handoff task and fixed local CLI guide probe; no browser protocol emulation |
| reporter.py | Common evidence sections for MD and DOCX, report provenance |
| doctor.py | Explicit opt-in live connectivity checks without credential logging |

## Agent execution

Planner and source agents are deterministic retrieval components. With AI enabled, `legal_analyst`, `opposition_analyst`, and `reviewer` use three separate Ollama calls in research/deep modes; quick mode makes at most one call. They run sequentially, not simultaneously. Each has a different task and the reviewer receives prior candidates. They do not have shell, browser, or network tool permissions; application code controls all retrieval.

All generated claims are checked against retrieved full text. The memo writer uses the already checked results and makes no unverified final LLM generation call. Document analysis receives selected text windows with a 16,000-character total budget. This is not a guarantee of full-document semantic review.

## Persistence

The preexisting schema is retained. `source_snapshots(job_id,source_id,content,metadata_json)` is additive with a cascading FK to jobs. A snapshot is immutable within a job; later cache refreshes cannot rewrite the investigation evidence. Hashes refer to the normalized corpus supplied for analysis, not raw downloaded XML bytes. Dates and content provenance are persisted with the source. Cache-disabled mode still saves result excerpts and user questions.

Steps are saved at completion boundaries. These are audit checkpoints, not a durable queue. Interruption can leave a nonterminal job visible; resuming/cancelling jobs is not implemented.

## Boundaries

- No credentials in public source URLs or reflected API error bodies. Redirects are rejected rather than forwarding a credential to an unverified destination.
- Remote Ollama is opt-in; host parsing checks the actual hostname rather than a string prefix.
- FTS parameters are escaped and SQL values bound. Demo and official document cache identities are separate.
- A browser task is discovery assistance only. A discovered ID must be fetched through the official API to become API evidence; uploaded text remains USER_UPLOAD.
- Quote matching proves text presence only. Metadata matching proves matching fields in returned API results only. Date flags do not establish historical applicability or precedential treatment.
- UI and API are local-only, unauthenticated personal tools. No internet deployment is included.

## Budgets and limitations

Up to four query variants per similarity call, at most 12 fetched base cases and 3 counter candidates. LLM request timeout 115 seconds; embedding timeout 90 seconds. Retry backoff is bounded, not an adaptive distributed rate limiter. Live access quota varies by the issued API access and must be checked locally. No persistent vector index, cross-encoder, legal citator, model-driven replanning, automatic browser operation, or cancellation worker exists yet.
