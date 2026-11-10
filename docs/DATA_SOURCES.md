# 공식 데이터 및 연결 계약

법제처 API는 사용자별 `OC` 인증값과 사용 승인/접근권한이 필요합니다. 소스코드는 HTTPS DRF endpoint를 사용합니다. 이 배포에서는 실제 인증 호출 없이 모의 XML로 검증했습니다.

| 기능 | Endpoint | 주요 파라미터 |
|---|---|---|
| 법령 목록 | `https://www.law.go.kr/DRF/lawSearch.do` | OC, target=law, type=XML, query, display |
| 법령 본문 | `https://www.law.go.kr/DRF/lawService.do` | OC, target=law, type=XML, MST |
| 판례 목록 | lawSearch.do | target=prec, search=1/2/3, query, page, curt, nb, prncYd |
| 판례 본문 | lawService.do | target=prec, ID |
| 로컬 임베딩 | `OLLAMA_BASE_URL/api/embed` | model, input 배열, truncate=false |
| 로컬 AI 분석 | `OLLAMA_BASE_URL/api/chat` | model, messages, stream=false, format=json |

`search=2`는 본문, `search=3`은 참조판례 검색입니다. 사건번호 대조는 `nb`를 사용하고 반환된 번호를 다시 정확 비교합니다. 데이터의 조회 범위와 공개 여부에 따라 검색되지 않는 판례가 있을 수 있습니다.

공식 문서 확인일: 2026-11-10.

- [법제처 판례 목록 API](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=precListGuide)
- [법제처 판례 본문 API](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=precInfoGuide)
- [법령 본문 API](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsNwInfoGuide)
- [Ollama embed](https://docs.ollama.com/api/embed)
- [ego(lite) 공식 ego-browser 가이드 진입점](https://github.com/citrolabs/ego-lite/blob/main/skills/ego-browser/SKILL.md)

Ollama 임베딩 입력은 후보별 선택 구간 최대 2,400자로 제한합니다. 벡터 개수·차원·유한값을 검사하며 실패하면 키워드 순위와 경고를 반환합니다. 모델 설치나 품질은 자동으로 보장하지 않습니다.

공식 ego-browser 진입점은 설치된 버전의 `ego-browser skill` 명령을 우선 실행하도록 안내합니다. 따라서 고정된 비공개 RPC를 추측하지 않고 탐색 요청을 로컬 에이전트에 전달하는 방식으로 구현했습니다. `korean-law-mcp`, `lawful-mcp`는 이 버전에 연결하지 않았습니다.

사용자가 가져온 판결문·계약서는 `USER_UPLOAD` 출처입니다. 원문과 인용이 일치해도 법제처/법원에서 인증된 원문이라는 의미는 아닙니다. 자료 재배포 권한은 이 소프트웨어가 부여하지 않습니다.
