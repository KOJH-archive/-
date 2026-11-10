# Local REST API v0.2

Start `Legal-Research-Studio.bat api`, then open http://127.0.0.1:8800/docs.
Set `DEMO_MODE=1` in `.env` for API demo. UI mode changes do not change an independently running API server.

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/health` | Configured flags, not a live access guarantee |
| GET | `/api/statutes/search?q=민법` | Statute list |
| GET | `/api/statutes/{id}` | Full statute, articles and addenda |
| GET | `/api/statutes/{id}/articles?q=제450조` | Filtered articles |
| GET | `/api/precedents/search?q=채권양도` | Cases, optional page/court/case_number/date_range/referenced |
| POST | `/api/precedents/similar` | Bounded candidate collection + ranking |
| GET | `/api/precedents/{id}` | Case detail |
| POST | `/api/precedents/{id}/analysis` | Structured/optional AI analysis |
| POST | `/api/analysis/text` | User-provided text analysis, never official authority |
| POST | `/api/citations/verify` | Quote vs user-provided text |
| POST | `/api/citations/case-reference` | Case number/court/date vs API metadata |
| POST | `/api/research/jobs` | Synchronous research execution |
| GET | `/api/research/jobs` | Saved jobs |
| GET | `/api/research/jobs/{id}` | Full saved result |
| GET | `/api/research/jobs/{id}/sources` | Immutable source snapshots, if caching enabled |
| GET | `/api/research/jobs/{id}/report.md` | Markdown report; `.docx` and `.json` also supported |
| POST | `/api/browser/tasks` | Human-assisted ego handoff task |

## PowerShell research example

```powershell
$body = @{
  question = '민법상 채권양도 통지와 대항요건을 검토'
  law_query = '민법'
  precedent_query = '채권양도 통지'
  position = '통지 기록만으로 대항할 수 있다는 주장'
  max_cases = 5
  mode = 'research'
  enable_llm = $false
  semantic_search = $false
  counterarguments = $true
  as_of = '2026-11-10'
} | ConvertTo-Json
Invoke-RestMethod 'http://127.0.0.1:8800/api/research/jobs' -Method Post `
  -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

## JSON request examples

Similarity:
```json
{"query":"채권양도 통지 기록이 없는 경우", "limit":5, "semantic":false, "counterarguments":true}
```

Case reference (use a real case number obtained from the source; this example is fictional and demo-only):
```json
{"case_number":"가상2099예시1", "court":"가상 법원", "judgment_date":"20991231"}
```

Analysis:
```json
{"question":"주문과 판단 이유, 적용상 한계를 설명", "enable_llm":false}
```

Date filter `date_range` is `YYYYMMDD~YYYYMMDD`. `referenced=true` sets the official `search=3` referenced-case search. JSON endpoints validate lengths and bounds; invalid requests return 422. Unavailable required LLM configuration returns 400; source errors on direct operations return 503. Composite research preserves partial results and warnings.

## Current implementation notes (2026-11-11)

Precedent search uses `datSrcNm=대법원`; HTML-only National Tax Service sources are outside automated search. Statute exact-name ranking is applied before the result limit, within the first 100 API candidates. Research results include `current_stage`, `progress`, `checkpoint_at`, `elapsed_seconds`, and `research_context`. These are persisted checkpoints, not a resume/cancel API. Health flags describe explicit environment settings; empty model preference fields can still resolve to installed models during service construction. UI and API model selections are independent. See [development specification](DEVELOPMENT_SPEC.md).
