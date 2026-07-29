---
name: retro
description: Claude Code 세션의 시행착오를 에피소드(주제 단위) 회고 스펙으로 증류·갱신한다. "회고 정리", "지금까지 정리해줘", "체크포인트", "이 프로젝트 정리해줘", "retro" 요청 시 사용. 이미 진행된 프로젝트는 소급 모드(세션×git 인벤토리로 에피소드 분할)를 지원하며, retro-blog(velog 글)·retro-ppt(발표 덱)의 선행 단계다.
---

# retro — 세션 → 에피소드 회고 스펙 증류

세션 트랜스크립트(JSONL)에서 시행착오(문제→시도→실패→해결)를 추출해
**에피소드별 스펙**(`retro/specs/YYYY-MM-DD-<slug>.md`, 블로그 1편 = 스펙 1개)과
**온보딩용 개요**(`retro/overview.md`)를 만들거나 갱신한다.
블로그와 발표 덱은 이 스펙들을 렌더링할 뿐이다. 스크립트 경로는 이 스킬의 base directory 기준.

## 0. 초기화와 모드 판정

1. 구조가 없으면 생성:
   `mkdir -p retro/archive retro/assets/auto retro/assets/inbox retro/specs retro/out/blog retro/out/ppt retro/.timeline`
   (retro/가 생기면 이후 세션부터 백업 훅이 이 프로젝트에서 활성화된다.)
   `retro/config.md`가 없으면 아래 템플릿으로 생성한다:

   ```markdown
   ---
   default_visibility: private   # private | public | draft — public이어도 발행 전 한 번 더 확인
   default_tags: [Claude Code, 회고]
   series: ""                    # velog 시리즈명 (API 연동 전까지 메모)
   velog_username: ""            # 말투 학습·발행 URL에 사용
   audience: 팀원/멘토/블로그 독자
   ---

   ## 말투 메모
   (원하는 문체 특징을 적어두면 retro-blog가 글 쓸 때 반영)
   ```
2. **마이그레이션**: 구버전 단일 `retro/spec.md`가 있으면 frontmatter의 updated·title로
   `retro/specs/<updated날짜>-<slug>.md`로 이동을 제안한다.
3. **모드 판정**: `retro/specs/`가 비어 있는데 프로젝트에 세션 기록(현재 보관분 + archive)이
   3개 이상이면 → **소급 모드**를 제안. 그 외 → **증분 모드**.

## 1. 소급 모드 (이미 진행된 프로젝트에 중간 도입)

1. **인벤토리** (AI 호출 없음):
   `python3 "<skill-dir>/scripts/inventory.py" --out retro/.timeline/inventory.md`
   → 세션(제목·기간·턴·도구실패) × git 커밋 교차표 + "세션 기록이 없는 커밋"
   (30일 경과로 소실됐거나 Claude 밖 작업) 목록. Read로 읽는다.
2. **에피소드 제안**: 표를 근거로 **순수 기능/문제 단위**로 클러스터를 제안한다 —
   "에피소드 1: <주제> (세션 2개, 커밋 `abc` `def`) → 블로그 1편감" 형식으로,
   각 에피소드의 근거(세션·커밋)를 함께 보여주고 사용자가 병합/분리/제외/우선순위를 정한다.
3. **스펙 생성**: 승인된 에피소드부터 **한 번에 1~2개씩만** 생성한다(컨텍스트 관리).
   에피소드에 속한 세션들을 `parse_transcript.py`로 파싱해 증류 규칙대로 스펙을 쓴다.
   세션이 소실된 구간은 git 커밋으로 뼈대를 서술하되, **사용자 인터뷰로 디테일을 보완한다**
   ("이 구간에서 뭐가 제일 힘들었어요?", "왜 이 방식으로 바꿨어요?").
4. **overview.md 생성/갱신** (아래 형식).

## 2. 증분 모드 (평소)

1. 재료 선택(기본: 현재 세션):
   `ls -t ~/.claude/projects/$(python3 -c 'import re,os;print(re.sub(r"[^A-Za-z0-9]","-",os.getcwd()))')/*.jsonl | head -3`
   또는 `ls -t retro/archive/*.jsonl`.
2. 파싱: `python3 "<skill-dir>/scripts/parse_transcript.py" <파일...> --out retro/.timeline/timeline.md`
   → Read (PART 마커가 있으면 순서대로).
3. **에피소드 귀속**: 내용을 보고 "기존 에피소드 <X>에 병합할까요, 새 에피소드로 시작할까요?"를
   제안하고 확인받는다. 승인 후 해당 스펙을 갱신/생성하고 overview 목차를 갱신한다.
4. 재호출 = 체크포인트: 같은 에피소드 스펙에 이후 진행분을 병합한다.

## 3. 분량 가드레일 (부작 분할)

한 에피소드 스펙의 여정 문제가 **4개를 초과**하거나 예상 글 분량이 블로그 1편 적정선을
명백히 넘으면, `<slug>-part1` / `<slug>-part2`로 분할을 제안한다(승인제).
부작이 되면 velog 시리즈명도 함께 제안한다(시리즈 API 연동은 v2 — 이름 제안까지만).

## 4. 증류 규칙

- **남긴다**: 반복 실패, 방향 전환(pivot), 사용자 개입·결정, 예상과 다른 결과, 배운 것.
- **버린다**: 오타 수정, 단순 조회, 한 번에 통과한 루틴 작업.
- 타임라인의 ❌(도구 실패) 표시와 그 직후의 대응이 시행착오의 1차 신호다.
- **톤**: 구조는 체계적으로(문제→시도→해결), 서술은 솔직하게. "완벽하게 설계했다"가 아니라
  "여기서 막혀서 이렇게 돌아갔다"를 남긴다. `## 아쉬운 점` 섹션은 생략 불가.
- 사람이 수동 편집한 문구는 보존한다. 병합이 모호하면 사용자에게 확인.

## 5. 에피소드 스펙 형식 (`retro/specs/YYYY-MM-DD-<slug>.md`, 날짜 = 에피소드 시작일)

```markdown
---
title: ""
period: YYYY-MM-DD ~ YYYY-MM-DD
sessions:
  - <재료로 쓴 파일명 또는 세션ID>
audience: 팀원/멘토/블로그 독자
tags: [Claude Code, 회고]
thumbnail: ""
status: draft
updated: YYYY-MM-DD
---

## 한 줄 요약
## 배경 / 목표
## 여정
### 문제 1: <제목>
- 상황:
- 시도 1: … → 실패 (이유)
- 시도 2: … → 해결
- 배운 것:
- 이미지: ![캡션](assets/auto/….png)
### 결정 포인트: <A vs B>
## 결과 / 지표
## 아쉬운 점
## 다음 단계
```

다이어그램은 mermaid 코드블록으로 본문에 직접. 이미지 경로는 retro/ 기준(assets/… 형태).

## 6. overview.md 형식 (온보딩 문서형 — 새 합류자·미래의 내가 30분 안에 따라잡는 문서)

```markdown
---
title: <프로젝트명> 개요
updated: YYYY-MM-DD
---

## 한 줄 소개
## 왜 만들었나            # 배경·목표·제약
## 아키텍처 큰 그림        # 텍스트 다이어그램/mermaid 허용
## 중대한 결정들           # 표: 결정 | 선택 | 이유("왜 A 대신 B")
## 지뢰밭 지도             # 우리가 밟은 삽질 → 다음 사람은 밟지 않도록: 증상 | 원인 | 회피법
## 에피소드 목차           # 각 에피소드: 제목 · 기간 · 한 줄 요약 · 상태(스펙만/블로그 발행/덱 있음)
```

에피소드를 만들거나 갱신할 때마다 목차와 관련 섹션(결정·지뢰밭)을 함께 갱신한다.

## 7. 이미지 큐레이션

1. `ls -l --time-style=+%Y-%m-%dT%H:%M retro/assets/auto/ retro/assets/inbox/ 2>/dev/null`
2. 파일명 타임스탬프(우선) 또는 수정 시각을 세션 타임라인과 대조해 후보 구간을 추정한다.
3. 각 이미지를 Read로 직접 열어 내용을 확인하고, 어느 에피소드의 어느 섹션에 어울리는지 제안한다.
4. **사용자 승인 후** 스펙에 `![캡션](assets/…)`로 기록한다. 캡션 초안도 함께 제안.
5. 매칭되지 않는 이미지는 "미배치 목록"으로 보고하고, 스크린샷 없는 핵심 구간은
   mermaid 다이어그램 초안을 제안한다.

## 8. 자동 캡처 관례

retro/가 있는 프로젝트에서 브라우저 검증 스크린샷을 찍을 때는
`retro/assets/auto/<YYYY-MM-DDTHH-MM-SS>-<설명>.png` 사본을 남긴다.
(프로젝트 CLAUDE.md에 이 관례를 한 줄 적어두면 다른 세션에서도 유지된다.)

## 9. 콘텐츠 맵 갱신 + 완료 보고

1. `python3 "<skill-dir>/scripts/build_map.py"` 실행 → `retro/map.html` 재생성
   (에피소드 상태 색칠 + 이미지 부족 배지 + 다음 작성 추천).
2. 생성/갱신된 스펙과 overview를 요약하고, 맵 경로와 함께 "이제 /retro-blog(velog 글)
   또는 /retro-ppt(발표 덱)로 내보낼 수 있어요"를 안내한다.
