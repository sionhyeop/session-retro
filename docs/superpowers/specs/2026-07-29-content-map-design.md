# session-retro v1.3 설계 — 콘텐츠 맵 + 설정 파일

- 날짜: 2026-07-29 / 상태: 사용자 승인됨 (선택: ①맵 + ②설정. 말투 학습·시리즈 연동은 다음 후보)
- 원칙 교정: 로컬 정적 HTML은 입력을 돌려받을 수 없으므로 **맵 = 보기 전용**, 설정은 대화 + config.md.

## 1. 콘텐츠 맵 — `retro/map.html`

`skills/retro/scripts/build_map.py`가 **실데이터만으로** 생성하는 단일 파일 HTML(외부 요청 0, 다크/라이트 자동).

데이터 소스와 상태 해석:
- `retro/specs/YYYY-MM-DD-<slug>.md` → frontmatter(title/status/period/updated/tags) + 본문 여정의 `### 문제*` 섹션별 이미지(`![`) 유무
- `retro/out/blog/YYYY-MM-DD-<slug>.md` 존재 → 초안 단계. **slug(날짜 뒤 부분)로 스펙과 매칭**
- `<블로그>.velog.json` 사이드카 → visibility: draft(임시저장)/private/public
- `retro/out/ppt/*-<slug>.html` 존재 → 덱 배지
- `retro/overview.md`의 "## 에피소드 목차" 불릿 중 스펙 없는 항목 → 계획 단계(방어적 파싱)
- `retro/assets/inbox|auto` 파일 수 → 미배치 이미지 카운트

단계(색): ⚪ 계획 → 🔵 스펙 → 🟡 초안(임시저장 포함) → 🟣 비공개 발행 → 🟢 공개 발행.
노드 카드: 제목·기간·상태·이미지 배지("N장" 또는 "⚠️ 부족: 문제 2, 3")·산출물 배지(📝/🎞️)·발행 URL.
상단: 범례 + **다음 작성 추천**(가장 덜 진행된 에피소드) + 미배치 이미지 수.

CLI: `build_map.py [--retro-dir retro] [--out retro/map.html]`. 표준 라이브러리만, AI 호출 없음.
갱신 시점: retro·retro-blog·retro-ppt 절차 마지막에 재생성(SKILL.md에 명시).

## 2. 설정 파일 — `retro/config.md`

retro 스킬이 초기화 때 생성하는, Claude가 읽는 마크다운(스크립트 파싱 없음):

```markdown
---
default_visibility: private   # private | public | draft — public이면 발행 전 한 번 더 확인
default_tags: [Claude Code, 회고]
series: ""                    # velog 시리즈명 (API 연동은 추후 — 지금은 메모)
audience: 팀원/멘토/블로그 독자
---

## 말투 메모
(말투 학습 기능 전까지, 원하는 문체 특징을 적어두면 retro-blog가 반영)
```

- retro-blog: 글 쓰기 전에 config를 읽어 기본값 적용. `default_visibility: public`이어도 발행 직전 한 번 더 확인(공개 명시 원칙 유지).
- 값이 비어 있고 처음 발행하는 경우 선택지로 묻고 config에 저장.

## 3. 작업 목록

1. `build_map.py` + `tests/test_map.py` (TDD)
2. SKILL.md 3개에 맵 재생성 단계 + retro에 config 생성, retro-blog에 config 적용·이미지 0장 경고
3. README·랜딩 한 줄 반영, 도그푸딩(이 프로젝트 맵 생성)
