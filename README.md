# session-retro

Claude Code 세션의 시행착오(문제→시도→실패→해결)를 **회고 스펙**으로 증류해
**velog 블로그 초안**과 **단일 파일 HTML 발표 덱**으로 변환하는 스킬 모음.

```
세션 진행 중 ─(SessionEnd/PreCompact 훅)→ retro/archive/*.jsonl   ← 원본 영속화
/retro       : 트랜스크립트 파싱 → 증류 → retro/spec.md (단일 진실 소스)
/retro-blog  : spec → velog MD → 이미지 CDN 업로드 → 임시저장 업로드
/retro-ppt   : spec → 단일 파일 HTML 발표 덱
```

## 설치

```bash
bash install.sh   # 스킬 3개 심링크 + 백업 훅 등록(~/.claude/settings.json, 자동 백업 후 병합)
```

## 사용법

| 명령 | 하는 일 |
|---|---|
| `/retro` | 세션 트랜스크립트 → `retro/spec.md` 증류·갱신 (세션 중간 재호출 = 체크포인트) |
| `/retro-blog` | 스펙 → velog 글 초안 → 이미지 CDN 업로드 → **임시저장** 업로드 |
| `/retro-ppt` | 스펙 → 단일 파일 HTML 발표 덱 (←/→ 이동, Ctrl+P로 PDF) |

처음 한 번 `/retro`를 실행하면 프로젝트에 `retro/` 구조가 생기고,
그때부터 세션 종료·컨텍스트 압축 시 트랜스크립트가 `retro/archive/`에 자동 백업된다.
(훅은 `retro/` 폴더가 있는 프로젝트에서만 동작하는 opt-in 방식이다.)

## 이미지 넣기

- **자동**: 브라우저 검증 스크린샷을 `retro/assets/auto/<타임스탬프>-<설명>.png`로 저장하는 관례
- **수동**: 아무 이미지나 `retro/assets/inbox/`에 던져두면 /retro가 맥락에 맞게 배치를 제안
- 스크린샷이 없는 구간은 mermaid 다이어그램을 제안

## velog 토큰 설정 (최초 1회)

velog.io 로그인 → F12 → Application → Cookies → `access_token`/`refresh_token` 복사 후:

```bash
python3 skills/retro-blog/scripts/velog_publish.py setup
```

`~/.config/velog-retro/tokens.json`(0600)에 저장된다. **비공식 API**를 사용하므로
언제든 깨질 수 있고, 깨져도 MD 파일 폴백으로 항상 글을 건질 수 있다.
업로드는 항상 임시저장(초안)까지만 — 공개 발행은 velog에서 직접 누른다.

## 권장 설정

트랜스크립트 보존 기간 연장(기본 30일): `~/.claude/settings.json`에 `"cleanupPeriodDays": 90`

## 테스트

```bash
python3 -m pytest tests/ -q && bash tests/test_hook.sh && bash tests/test_install.sh
```

## 문서

- 설계: `docs/superpowers/specs/2026-07-28-session-retro-design.md`
- 구현 계획: `docs/superpowers/plans/2026-07-28-session-retro.md`
- 사전 조사(선행 사례·기술 검증): `docs/research/2026-07-28-prior-art.md`

## v2 후보

편집 가능 .pptx(PptxGenJS), 공개 발행 자동화, Windows 화면 캡처 셸, 플러그인 마켓플레이스 배포
