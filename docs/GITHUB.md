# GitHub 등록 준비

대상은 `KOJH-archive/korean-legal-research-studio`입니다. 2026-11-10 연결된 GitHub API 조회는 404, 저장소 검색은 0건입니다. 저장소 미존재와 권한 부족을 이 결과만으로 구분할 수 없어 생성·push는 수행하지 않았습니다.

## 먼저 확인

Git for Windows와 GitHub CLI가 설치된 PC에서:

```powershell
gh auth login
gh repo view KOJH-archive/korean-legal-research-studio
```

또는 프로젝트에서:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/prepare_github.ps1
```

이 기본 실행은 조회만 합니다. 실제로 새 저장소가 필요하고 본인 소유 계정으로 인증됐다면 다음 명시적 옵션으로 비공개 저장소를 만들 수 있습니다:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/prepare_github.ps1 -CreatePrivate
```

이 스크립트는 인증 계정과 저장소 목록을 확인하며 파일은 push하지 않습니다. 오류를 인증 문제로 확인해야 하는 경우 새 저장소를 만들거나 덮어쓰지 않습니다.

## 새 빈 저장소일 때만 최초 등록

ZIP에는 작업 환경의 `.git`·데이터·인증값이 없습니다. 압축 해제 폴더에서:

```powershell
git init -b main
git add .
git status --short
# .env, data, 개인 문서가 포함되지 않았는지 확인
git commit -m "Implement evidence-based legal research v0.2"
git remote add origin https://github.com/KOJH-archive/korean-legal-research-studio.git
git push -u origin main
```

Git 사용자 이름/이메일 미설정이면 본인 값을 먼저 설정하세요. `--force`는 사용하지 마세요.

기존 저장소에 파일이 있다면 먼저 clone하고 새 브랜치를 만든 뒤 변경 내용을 비교하여 반영합니다. `.github/workflows/tests.yml`은 Windows/Linux, Python 3.11/3.13/3.14 테스트를 설정해 두었으며 실제 GitHub 실행 결과는 아직 없습니다.
