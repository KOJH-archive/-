> 갱신 안내 (2026-11-11): 아래 문서는 이전 개발 기록을 포함합니다. 현재 구현·검증·제약은 [최신 개발명세서](DEVELOPMENT_SPEC.md)와 [README](../README.md)를 우선 확인하세요.

# 검증 결과 v0.2.0

검증일: 2026-11-10. 환경: Linux, Python 3.12.14, SQLite 3.53.1. 정확한 직접 의존성 버전은 `requirements-tested.txt`에 기록했습니다.

## 결과

| 검증 | 결과 |
|---|---|
| pytest 전체 | **59 passed**, 2 dependency deprecation warnings |
| 기존 v0.1 테스트 | 회귀 통과. 데모 판례가 2건이 되어 예상 원문 건수만 조정 |
| Python compileall | 통과 |
| Streamlit AppTest | 시작·통합 리서치·유사 판례·모드 전환 통과 |
| Streamlit 서버 | localhost:8514 기동 로그 확인 |
| FastAPI TestClient | 기존 및 신규 API, 입력 제한, 보고서·원문 스냅샷 통과 |
| DOCX | 예시 생성, Word 구조 읽기, 2페이지 렌더링과 전체 페이지 육안 확인 |
| SQLite | 저장·FTS5·모드 분리·스냅샷 불변·원문 저장 해제·삭제 연쇄 통과 |
| 실제 LAW_OC 호출 | 미실행 — 인증값 없음 |
| 실제 Ollama 추론/임베딩 | 미실행 — 연결된 설치 모델 없음 |
| 실제 ego(lite) | 미실행 — CLI_NOT_FOUND |
| Windows 및 GitHub CI | 미실행 — 설정/스크립트만 준비 |

## 추가 테스트 핵심

- 한국어 조사/어미를 포함한 키워드 관련도와 긴 원문 후반의 조문 검색.
- Ollama embed 요청 계약, 벡터 개수·차원·자료형 오류 시 키워드 순위 대체.
- 판결문 제목 추출 및 전문/구조 미제공 시 사실관계 생성 방지.
- 역할별 독립 LLM 호출과 존재하지 않는 출처 인용 배제.
- 인용 위치·원문 해시·공백 정규화, 기준일 이후 자료 제외.
- 사건번호 정확 일치, 법원/선고일 불일치, 미검색을 부존재로 단정하지 않음.
- 공식 API 503 재시도, 사건번호/날짜/법원/참조판례 파라미터.
- XML 외부 엔티티 차단, 오류 메시지의 인증값 반사 차단, 리다이렉트 미추적.
- 원격 Ollama 호스트 위장 차단, 브라우저 탐색 URL/인증값 제한.
- 원문 캐시 갱신이 조사 당시 스냅샷을 변경하지 않음.

## 브라우저 테스트 제한

Playwright 기본 Chromium 바이너리가 없어 시스템 Chromium으로 시도했습니다. 시스템 Chromium은 환경의 `socket() failed: Operation not permitted`로 시작하지 못했습니다. 공유 브라우저에서도 해당 실행 환경의 localhost 접근이 `ERR_CONNECTION_REFUSED`로 실패했습니다. 따라서 전체 브라우저 기반 E2E/시각 QA는 통과로 표기하지 않습니다. UI 동작은 Streamlit 공식 AppTest로 검증했습니다.

## 재현

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q legal_studio ui.py
.\.venv\Scripts\python.exe -m legal_studio.doctor
# 인증값·로컬 서버 준비 후에만
.\.venv\Scripts\python.exe -m legal_studio.doctor --live
```

원시 결과: `pytest-output.txt`, `test-results.xml`, `diagnostics.json`.
오프라인 테스트 통과는 실제 법률 정확도·공식 API 권한·사용자 PC 성능을 보증하지 않습니다.
