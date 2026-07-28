# session-retro 플러그인 설계서

- 날짜: 2026-07-28
- 상태: 사용자 승인됨 (구현 전)
- 사전 조사 원문: `docs/research/2026-07-28-prior-art.md`

## 1. 목표

Claude Code로 작업한 세션의 사고 과정(의문 → 고민 → 문제 → 시행착오 → 해결)을, 그 내용을 모르는 사람도 빠르게 이해하고 사고 과정을 공유받을 수 있는 두 가지 산출물로 변환한다.

1. **velog 회고 블로그 글** — 이미지 포함, 초안(임시저장) 자동 업로드까지
2. **발표용 HTML 슬라이드 덱** — 의존성 0의 단일 파일, 브라우저에서 발표, 인쇄로 PDF화

톤 원칙: 체계적으로 사고한 것처럼 구조화하되, 막혔던 지점과 아쉬운 점을 솔직하게 드러내는 인간적인 회고.

## 2. 사전 조사 요약 (2026-07-28)

- 동일한 기능의 기존 스킬 없음. 파편적 선행 사례만 존재: logex(세션→영어 블로그), vibe-coding-tools(세션→한국어→Notion), bjpl/session-slides(턴당 1슬라이드 기계적 재생).
- 세션 원본은 이미 `~/.claude/projects/<munged-cwd>/<session-id>.jsonl`에 전부 기록됨(로컬 확인: 31개 프로젝트 977MB). 단, `cleanupPeriodDays` 기본 30일 후 삭제되고 컨텍스트 압축이 디테일을 파괴함 → 훅의 역할은 "기록"이 아니라 "영속화".
- 모든 훅은 stdin JSON으로 `session_id`, `transcript_path`, `cwd`, `hook_event_name`을 받음.
- velog는 공식 API가 없으나 비공식 GraphQL(쓰기: `https://v3.velog.io/graphql`의 `WritePost` mutation)과 이미지 업로드 REST(`POST https://v3.velog.io/api/files/v3/upload`)가 2026-07 현재 동작 확인됨. 인증은 `access_token`(~1h)/`refresh_token`(~30d) 쿠키.
- HTML→pptx 자동 변환은 전부 이미지 박제 방식 → v1에서 .pptx 제외 근거.

## 3. 확정된 결정

| # | 결정 사항 | 선택 | 근거 |
|---|---|---|---|
| 1 | 이미지 전략 | 하이브리드 | 브라우저 화면은 chrome-devtools MCP 캡처를 `retro/assets/auto/`에 저장하는 관례 + 사용자가 아무 때나 `retro/assets/inbox/`에 드롭 + 스킬이 타임라인·내용 분석으로 배치 제안 후 사용자 승인 + 부족 구간은 mermaid 다이어그램 |
| 2 | PPT 범위 | v1은 단일 파일 HTML 덱만 | 편집 가능 .pptx는 PptxGenJS 별도 경로가 필요해 공수 큼. 실수요 확인 후 v2 |
| 3 | velog 발행 | 초안 자동 업로드까지 | 이미지 CDN 업로드 + `is_temp: true` 업로드 → 미리보기 확인 후 발행 버튼은 사람이. 실패 시 MD 파일 폴백 |
| 4 | 시행착오 기록 | 백업 훅 + 온디맨드 증류 | SessionEnd/PreCompact 훅은 JSONL 복사만(AI 호출 없음, 공짜). 요약·증류는 회고 스킬 호출 시. 세션 중 재호출 = 체크포인트(실시간 중간 정리) |
| 5 | 패키징 | 플러그인 1개 + 스킬 3개 | `retro` / `retro-blog` / `retro-ppt` + 훅 + 공용 스크립트를 한 저장소에. 발행 코드(~60줄)는 직접 소유(외부 1인 유지보수 패키지 의존 회피) |

## 4. 아키텍처

```
세션 진행 중 ─(SessionEnd/PreCompact 훅)→ <프로젝트>/retro/archive/*.jsonl   ← 원본 영속화(복사만)
세션 진행 중 ─(웹 검증 스크린샷 관례)→    <프로젝트>/retro/assets/auto/
사용자      ─(아무 때나 드롭)→           <프로젝트>/retro/assets/inbox/

/retro       : 트랜스크립트 파싱 → 증류 → retro/spec.md 생성·갱신(재호출 = 체크포인트)
/retro-blog  : spec.md → velog MD → 이미지 CDN 업로드 → 초안 업로드 → 미리보기 URL
/retro-ppt   : spec.md → 단일 파일 HTML 덱
```

핵심 원칙: **`retro/spec.md`가 단일 진실 소스(single source of truth).** 블로그와 PPT는 같은 스펙의 다른 렌더링이다. 스펙은 사람이 직접 편집 가능한 마크다운이며, 어느 시점에든 어느 형식으로든 다시 뽑을 수 있다.

## 5. 구조

### 5.1 플러그인 저장소 (이 저장소)

```
velog-ppt-skills/
├── .claude-plugin/
│   └── plugin.json                    # name: session-retro, version 0.1.0
├── skills/
│   ├── retro/
│   │   ├── SKILL.md                   # 증류 원칙·톤 가이드·이미지 큐레이션 절차 포함
│   │   └── scripts/parse_transcript.py
│   ├── retro-blog/
│   │   ├── SKILL.md
│   │   ├── scripts/velog_publish.py
│   │   └── references/velog-style.md  # velog 마크다운 관례, 글 구성 가이드
│   └── retro-ppt/
│       ├── SKILL.md
│       ├── assets/deck-template.html
│       └── references/deck-guide.md   # 슬라이드 구성·서사 가이드
├── hooks/
│   ├── hooks.json                     # SessionEnd + PreCompact → archive_transcript.sh
│   └── archive_transcript.sh
├── install.sh                         # v1 개인 설치: 스킬 심링크 + settings.json 훅 병합
├── tests/                             # pytest + 훅 셸 테스트 + fixture
├── docs/
│   ├── research/2026-07-28-prior-art.md
│   └── superpowers/specs/2026-07-28-session-retro-design.md (이 문서)
└── README.md
```

- 설치(v1): `install.sh`가 ① `skills/*` 3개를 `~/.claude/skills/`에 심링크 ② `~/.claude/settings.json`에 훅 항목을 백업 후 병합(python3, 멱등). 플러그인 마켓플레이스 배포는 v2 — 다만 저장소 구조는 처음부터 플러그인 규격을 준수한다(`${CLAUDE_PLUGIN_ROOT}` 경로 사용).

### 5.2 대상 프로젝트 산출물 (스킬이 생성)

```
<프로젝트>/retro/
├── archive/            # 훅이 백업한 세션 JSONL
├── assets/auto/        # 자동 캡처 스크린샷
├── assets/inbox/       # 사용자 드롭 이미지
├── spec.md             # 회고 스펙 (단일 진실 소스)
└── out/
    ├── blog/YYYY-MM-DD-<slug>.md       (+ .published.md = CDN URL 치환본)
    └── ppt/YYYY-MM-DD-<slug>.html
```

- `retro/` 디렉토리는 retro 계열 스킬 최초 실행 시 생성된다. **훅은 `retro/`가 존재하는 프로젝트에서만 동작(opt-in)** — 모든 프로젝트에 무차별 복사되는 것을 방지.
- 최초 실행 전의 세션도 `~/.claude/projects/`에 30일간 남아 있으므로 `/retro`가 소급 수집 가능.

## 6. 데이터 계약: `retro/spec.md`

```markdown
---
title: ""                  # 회고 제목
period: 2026-07-01 ~ 2026-07-28
sessions:                  # 재료로 쓴 세션 (archive 파일명 또는 세션ID)
  - 2026-07-28-4c6329e3.jsonl
audience: 팀원/멘토/블로그 독자
tags: [Claude Code, 회고]
thumbnail: ""              # 선택
status: draft              # draft | final
updated: 2026-07-28
---

## 한 줄 요약
## 배경 / 목표          # 왜 시작했나, 제약 조건
## 여정                  # 시간순. 핵심 섹션.
### 문제 1: <제목>
- 상황:
- 시도 1: … → 실패 (이유)
- 시도 2: … → 부분 성공
- 해결:
- 배운 것:
- 이미지: ![캡션](assets/auto/….png)   # 확정 배치만 기록. 다이어그램은 mermaid 코드블록 직접 포함
### 결정 포인트: <A vs B>   # 무엇을 두고 고민했고 왜 그쪽을 골랐나
## 결과 / 지표
## 아쉬운 점              # 필수 섹션 — 인간적 부족함의 자리
## 다음 단계
```

**증류 필터(SKILL.md에 명문화):** 여정에 남기는 것 = 반복 실패, 방향 전환, 사용자 개입/결정, 예상과 달랐던 결과. 버리는 것 = 오타 수정, 단순 조회, 한 번에 통과한 루틴 작업.

**톤 가이드(SKILL.md에 명문화):** 구조는 체계적으로(문제→시도→해결), 서술은 솔직하게. "완벽하게 설계했다"가 아니라 "여기서 막혀서 이렇게 돌아갔다"를 남긴다. 아쉬운 점 섹션은 생략 불가.

**체크포인트 병합 규칙:** 기존 spec.md가 있으면 새 재료를 여정에 추가 병합하고 frontmatter의 `updated`·`sessions`를 갱신한다. 사람이 수동 편집한 내용은 보존한다(충돌 시 사용자에게 확인).

## 7. 컴포넌트 상세

### 7.1 백업 훅 — `hooks/archive_transcript.sh`

- 이벤트: `SessionEnd`, `PreCompact` (둘 다 stdin으로 `transcript_path`, `cwd`, `session_id` 수신)
- 동작: `$cwd/retro/` 디렉토리가 존재할 때만 → `transcript_path`를 `retro/archive/<YYYY-MM-DD>-<session_id 앞 8자>.jsonl`로 복사. PreCompact는 `-precompact-<HHMMSS>` 접미사로 별도 보존(압축 직전 스냅샷은 덮어쓰지 않음).
- 같은 세션의 SessionEnd 재발생 시 덮어쓰기(최신본이 상위 집합).
- JSON 파싱은 python3 원라이너(외부 의존 0). **어떤 실패에도 exit 0** — 세션 동작에 절대 영향을 주지 않는다. 오류는 `retro/archive/.hook.log`에만 기록.

### 7.2 `retro` 스킬 (증류 엔진)

- 트리거: `/retro`, "회고 정리해줘", "지금까지 정리" 등.
- 절차:
  1. `retro/` 구조가 없으면 생성(최초 opt-in).
  2. 재료 선택 — ① 현재 세션(뒤에 설명) ② `retro/archive/` ③ `~/.claude/projects/<munged-cwd>/`의 최근 세션. 여러 개 선택 가능. 현재 세션 트랜스크립트 탐색법: cwd를 munge(비영숫자→`-`)한 디렉토리에서 가장 최근 수정된 `.jsonl`.
  3. `scripts/parse_transcript.py`로 JSONL → 타임라인 마크다운 변환 후 Claude가 읽고 spec.md 생성/병합.
  4. 이미지 큐레이션(아래).
- `parse_transcript.py` 계약:
  - 입력: JSONL 경로 1개 이상, `--max-chars`(기본 80,000; 초과 시 시간 구간별 파트 분할), `--include-sidechains`(기본 제외)
  - 출력: 마크다운 — 메시지별 `[HH:MM] 역할: 텍스트(장문은 절단)`, 도구 호출은 `[도구: Bash] <설명>` 한 줄 요약, **도구 에러 결과는 ❌로 하이라이트**(시행착오 신호), thinking 블록 제외, 말미에 통계(소요 시간, 턴 수, 도구 사용 횟수, 세션 제목).
  - 방어적 파싱: 모르는 레코드 타입·깨진 라인은 스킵하고 개수만 보고(스키마가 비공식·유동적이므로).
  - 의존성: python3 표준 라이브러리만.
- 이미지 큐레이션 절차: `assets/auto/`·`assets/inbox/` 파일 목록의 mtime(파일명 타임스탬프 우선)을 세션 타임라인과 대조 → 후보 구간 추정 → Claude가 이미지를 직접 열어 내용 확인 → 여정 각 섹션에 배치 제안 → **사용자 승인 후** spec.md에 기록. 매칭 안 되는 이미지는 "미배치 목록"으로 사용자에게 보고. 스크린샷 없는 핵심 구간은 mermaid 다이어그램 초안 제안.
- 자동 캡처 관례(SKILL.md + README에 명시): `retro/`가 있는 프로젝트에서 chrome-devtools MCP 등으로 검증 스크린샷을 찍을 때 `retro/assets/auto/<ISO타임스탬프>-<설명>.png` 사본을 남긴다. v1에서는 강제(훅) 없이 관례 + 프로젝트 CLAUDE.md 한 줄 추가를 설치 가이드로 안내.

### 7.3 `retro-blog` 스킬

- 절차: spec.md → velog 관례에 맞는 MD 생성(`retro/out/blog/`) → 사용자에게 초안 보여주고 확인 → `velog_publish.py`로 업로드.
- 렌더링 규칙(references/velog-style.md): 제목·태그는 frontmatter에서, 여정은 "문제 → 삽질 → 해결" 서사로 재구성, 코드블록·인용 활용, 이미지는 로컬 상대 경로로 참조(업로드 단계에서 치환), 마크다운 이미지 크기 지정이 안 되므로 필요 시 `<img width>`.
- `velog_publish.py` 계약 (python3 표준 라이브러리만, 수제 multipart):
  - `setup`: 사용자가 velog.io 로그인 → 개발자도구 → 쿠키에서 `access_token`/`refresh_token` 복사·붙여넣기 → `~/.config/velog-retro/tokens.json`(chmod 600) 저장.
  - `publish <md파일> --draft`: ① MD 내 로컬 이미지들을 `POST https://v3.velog.io/api/files/v3/upload`(multipart: `image`=파일, `type`="post", Cookie 인증)로 업로드 → 응답 `path`(velcdn URL)로 치환한 `.published.md` 생성 ② `https://v3.velog.io/graphql`의 `WritePost` mutation을 `is_temp: true, is_markdown: true`로 호출(title/tags는 frontmatter에서) ③ 응답의 post id와 임시저장 확인 URL(`https://velog.io/saves`, 편집: `https://velog.io/write?id=<id>`) 출력.
  - 응답 `Set-Cookie`의 토큰 회전을 저장소에 반영. 토큰을 로그·에러 메시지에 절대 노출하지 않음.
  - 공개 발행(`is_temp: false`)은 v1에서 지원하지 않음 — 발행 버튼은 사람이 누른다.
- 폴백: 스크립트가 0이 아닌 종료 코드를 반환하면(토큰 만료, 4xx, 네트워크, 엔드포인트 변경) 스킬은 "MD 파일이 `retro/out/blog/`에 있으니 velog 에디터에 붙여넣고 이미지를 드래그하세요"로 안내하고 종료. 토큰 만료로 판별되면 `setup` 재실행 안내.

### 7.4 `retro-ppt` 스킬

- 절차: spec.md → 발표 서사 설계(references/deck-guide.md: 표지 → 한 줄 요약 → 배경 → 문제별 "문제/시도/해결" → 배운 점 → 아쉬운 점 → 다음 단계) → `assets/deck-template.html` 스캐폴드에 슬라이드 조립 → `retro/out/ppt/`에 저장 → 브라우저 렌더 확인.
- 덱 템플릿 요구사항:
  - 단일 파일, 외부 요청 0(오프라인 동작), 이미지는 빌드 시 data URI로 임베드
  - 16:9 논리 스테이지(1280×720)를 뷰포트에 맞춰 스케일
  - 내비: ←/→/Space/Home/End + 클릭 존, 슬라이드 카운터, 해시 URL(`#3`)
  - `@media print`: 슬라이드당 1페이지 가로 인쇄 → PDF 내보내기 경로
  - 슬라이드 타입: 표지 / 섹션 구분 / 제목+불릿 / 이미지+캡션 / 2단 비교 / 인용(배운 점) / 마무리
  - 한국어 시스템 폰트 스택(외부 폰트 로드 없음), 다크 톤 기본

## 8. 에러 처리

| 지점 | 정책 |
|---|---|
| 훅 | 어떤 오류도 exit 0. 로그 파일에만 기록. 세션을 절대 방해하지 않음 |
| 파서 | 모르는 레코드·깨진 라인 스킵 + 개수 보고. 거대 파일은 청크 분할 |
| velog API | 초안-먼저 원칙. 모든 실패는 MD 폴백으로 강등(글이 사라지는 경우 없음). 토큰 만료는 setup 재안내 |
| 이미지 임베드 | 과대 이미지(예: >2MB)는 리사이즈 제안 후 임베드. 실패 시 해당 슬라이드에 플레이스홀더 + 경고 |
| spec 병합 | 수동 편집 보존. 병합 모호 시 사용자 확인 |

## 9. 테스트 전략

- `parse_transcript.py`: pytest — 소형 익명화 fixture(정상/깨진 라인/sidechain 포함) + 실제 로컬 세션 파일 스모크 테스트. 검증: sidechain 제외, 에러 하이라이트, 청크 분할, 통계.
- `velog_publish.py`: HTTP를 monkeypatch한 단위 테스트(이미지 치환, mutation 페이로드, 토큰 회전, 실패 종료 코드) + 문서화된 수동 스모크 절차(실계정 임시저장 → 확인 → 삭제).
- 훅: 가짜 stdin JSON을 먹이는 bash 테스트 — retro/ 있음/없음, PreCompact 접미사, 오류 시 exit 0.
- 덱: fixture spec → 생성 → chrome-devtools MCP로 렌더·내비 동작 확인.

## 10. 수용 기준 (도그푸딩)

**이 플러그인으로 "velog-ppt-skills를 만든 과정" 회고를 직접 생산한다.** 즉:
1. 이 프로젝트에서 `/retro` 실행 → 이 세션(들)의 시행착오가 담긴 spec.md가 나온다
2. `/retro-blog` → 이미지 포함 velog 임시저장 초안이 올라가고 미리보기 URL이 출력된다
3. `/retro-ppt` → 브라우저에서 발표 가능한 단일 HTML 덱이 나온다

## 11. v1 범위 제외 (v2 후보)

- 편집 가능 .pptx(PptxGenJS 경로), 이미지 박제 .pptx
- 공개 발행 자동화(is_temp: false)
- Windows 데스크톱 전체 화면 캡처 셸(powershell.exe 연동 snap)
- 플러그인 마켓플레이스/skills.sh 배포, 멀티 프로젝트 통합 회고
- SessionEnd 자동 증류(훅에서 AI 호출)

## 12. 리스크와 완화

| 리스크 | 완화 |
|---|---|
| velog 비공식 API 변경/차단 | 초안-먼저 + MD 폴백이 항상 존재. 엔드포인트·mutation은 상수로 분리해 수정 용이. 저볼륨(본인 글 업로드)만 수행 |
| 트랜스크립트 스키마 변동 | 방어적 파싱 + 스킵 보고. 파서 테스트에 실파일 스모크 포함 |
| 토큰 유출 | 0600 파일, 로그 마스킹, 저장소에 절대 커밋 금지(.gitignore) |
| 이미지 data URI로 덱 비대화 | 리사이즈 제안 + 임베드 한도 경고 |
| 훅이 세션을 느리게 함 | 복사 1회뿐(AI 호출 없음), 실패 무시, opt-in |
