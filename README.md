# session-retro

**Claude Code 세션이 곧 회고가 됩니다.** 세션 속 시행착오(문제→시도→실패→해결)를 증류해
**velog 블로그 초안**과 **단일 파일 HTML 발표 덱**으로 내보내는 스킬 모음.

> 📖 **처음이라면 도식 가이드부터**: [`docs/index.html`](docs/index.html)을 브라우저에서 여세요
> (Windows 탐색기에서 더블클릭 — 외부 의존성 없는 단일 파일입니다).

## ⚡ 3분 시작

```bash
bash install.sh   # ① 스킬 3개 연결 + 백업 훅 등록 (기존 설정은 백업 후 병합, 멱등)
```

② 회고를 남기고 싶은 프로젝트의 Claude Code에서:

```
지금까지 한 거 회고로 정리해줘        ← /retro : retro/spec.md 생성
이거 velog에 올려줘                  ← /retro-blog : 초안 작성 → 비공개 발행 업로드
발표자료로도 만들어줘                ← /retro-ppt : HTML 덱 생성
```

③ 결과물 위치: `retro/out/blog/*.md` (velog에 **비공개로 발행**됨 — "공개로 바꿔줘" 하면 공개 전환), `retro/out/ppt/*.html` (더블클릭 → 발표, Ctrl+P → PDF), `retro/map.html` (**콘텐츠 맵** — 에피소드별 진행 상태 색칠, 이미지 부족 경고, 다음 작성 추천. 스킬 실행 때마다 자동 갱신)

`/retro`를 한 번 실행해 `retro/` 폴더가 생긴 프로젝트는, 이후 세션 종료·컨텍스트 압축 시
트랜스크립트가 `retro/archive/`에 **자동 백업**됩니다 (opt-in 방식 — 다른 프로젝트는 건드리지 않음).

## 이렇게 말하면 됩니다

슬래시 명령을 외울 필요 없습니다 — 자연어로 트리거됩니다.

| 하고 싶은 것 | Claude에게 이렇게 | 일어나는 일 |
|---|---|---|
| 세션 정리 | "회고 정리해줘" / `/retro` | `retro/spec.md` 생성·갱신 + 이미지 배치 제안 |
| 중간 저장 | "체크포인트 찍어줘" | spec에 이후 진행분 병합 (실시간 중간 정리) |
| 블로그 | "velog에 올려줘" / `/retro-blog` | 초안 작성 → 승인 → 이미지 CDN 업로드 → **비공개 발행** |
| 공개 전환 | "공개로 바꿔줘" | 비공개로 발행된 글을 공개로 전환 ("비공개로 돌려줘"도 가능) |
| 말투 학습 | "말투 학습해줘" | 내 velog 공개 글에서 문체 프로필 증류 → 이후 모든 글에 자동 적용 |
| 말투 바꾸기 | "이번 글은 삽질러 말투로" | 프리셋 4종(담백 `plain`·친근 `friendly`·유쾌 `meme`·강사 `tutor`) 또는 내 말투 선택 |
| 발표 자료 | "발표자료 만들어줘" / `/retro-ppt` | 에피소드 발표 또는 overview 기반 프로젝트 전체 발표 |
| **중간 도입** | "이 프로젝트 지금까지 정리해줘" | **소급 모드**: 세션×git 인벤토리 → 에피소드(주제 단위) 분할 제안 → 블로그 여러 편 + 개요 |

## 전체 그림

```
세션 진행 중 ─(SessionEnd/PreCompact 훅)→ retro/archive/*.jsonl        ← 원본 영속화
세션 시작 시 ─(SessionStart 넛지 훅)→ 재료가 쌓이면 Claude가 먼저 회고 제안
/retro       : 파싱·증류 → retro/specs/<에피소드>.md (블로그 1편 = 스펙 1개)
                          + retro/overview.md (온보딩용 개요: 결정·지뢰밭·목차)
/retro-blog  : 스펙 선택 → velog MD → 이미지 CDN 업로드 → 비공개 발행 (공개는 명시 요청 시)
/retro-ppt   : 에피소드 발표 or overview 기반 전체 발표 → 단일 파일 HTML 덱
```

에피소드 스펙이 단일 진실 소스입니다. 블로그와 덱은 같은 스펙의 다른 렌더링이라
언제든, 몇 번이든 다시 뽑을 수 있고 사람이 직접 편집해도 됩니다.

**이미 한참 진행된 프로젝트에 중간 도입해도 됩니다** — 첫 `/retro`가 소급 모드를 제안합니다:
세션 기록(30일 보관)과 git 커밋을 교차한 인벤토리로 기능/문제 단위 에피소드를 나눠 제안하고,
승인한 것부터 스펙과 개요를 만듭니다. 한 에피소드가 너무 길면 1부/2부 분할을 제안합니다.
세션이 이미 지워진 구간은 git 뼈대 + 짧은 인터뷰로 보완합니다.

## 이미지 넣기

- **자동**: 브라우저 검증 스크린샷을 `retro/assets/auto/<타임스탬프>-<설명>.png`로 저장하는 관례
- **수동**: 아무 이미지나 `retro/assets/inbox/`에 던져두면 `/retro`가 타임라인·내용을 대조해 배치를 제안
- 승인한 것만 spec에 기록되고, 스크린샷 없는 구간은 mermaid 다이어그램을 제안

## velog 토큰 설정 (블로그 쓸 때 최초 1회)

velog.io 로그인 → F12 → Application → Cookies → `access_token`/`refresh_token` 복사 후:

```bash
python3 skills/retro-blog/scripts/velog_publish.py setup
```

`~/.config/velog-retro/tokens.json`(0600)에 저장됩니다. **비공식 API**라 언제든 깨질 수 있지만,
깨져도 MD 파일 폴백으로 항상 글을 건질 수 있습니다. 업로드 기본값은 **비공개 발행**(본인만 보임) —
공개는 "공개로 바꿔줘"라고 명시적으로 요청할 때만 전환됩니다.

## 권장 설정

트랜스크립트 보존 기간 연장(기본 30일): `~/.claude/settings.json`에 `"cleanupPeriodDays": 90`

## 테스트

```bash
python3 -m pytest tests/ -q && bash tests/test_hook.sh && bash tests/test_install.sh
```

## 문서

- **도식 가이드(온보딩)**: `docs/index.html`
- 설계: `docs/superpowers/specs/2026-07-28-session-retro-design.md`
- 구현 계획: `docs/superpowers/plans/2026-07-28-session-retro.md`
- 사전 조사(선행 사례·기술 검증): `docs/research/2026-07-28-prior-art.md`

## v2 후보

편집 가능 .pptx(PptxGenJS), 공개 발행 자동화, Windows 화면 캡처 셸, 플러그인 마켓플레이스 배포
