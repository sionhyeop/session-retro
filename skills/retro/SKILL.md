---
name: retro
description: Claude Code 세션의 시행착오를 회고 스펙(retro/spec.md)으로 증류·갱신한다. "회고 정리", "지금까지 정리해줘", "체크포인트", "retro" 요청 시 사용. retro-blog(velog 글)·retro-ppt(발표 덱)의 선행 단계이며, 세션 중간 재호출로 실시간 중간 정리를 지원한다.
---

# retro — 세션 → 회고 스펙 증류

세션 트랜스크립트(JSONL)에서 시행착오(문제→시도→실패→해결)를 추출해 `retro/spec.md`
(단일 진실 소스)를 만들거나 갱신한다. 블로그와 발표 덱은 이 스펙을 렌더링할 뿐이다.
스크립트 경로는 이 스킬의 base directory 기준이다.

## 절차

1. **초기화**: `retro/` 구조가 없으면 생성한다.
   `mkdir -p retro/archive retro/assets/auto retro/assets/inbox retro/out/blog retro/out/ppt retro/.timeline`
   (retro/가 생기면 이후 세션부터 백업 훅이 이 프로젝트에서 활성화된다.)
2. **재료 선택** — 어떤 세션을 회고할지 사용자에게 확인한다(기본: 현재 세션).
   - 현재 세션(가장 최근 수정된 트랜스크립트):
     `ls -t ~/.claude/projects/$(python3 -c 'import re,os;print(re.sub(r"[^A-Za-z0-9]","-",os.getcwd()))')/*.jsonl | head -3`
   - 백업본: `ls -t retro/archive/*.jsonl`
   - 여러 파일을 함께 넘겨도 된다.
3. **파싱**: `python3 "<skill-dir>/scripts/parse_transcript.py" <파일...> --out retro/.timeline/timeline.md`
   실행 후 결과 파일을 Read로 읽는다. `<!-- ── PART n/m ── -->` 마커가 있으면 순서대로 나눠 읽는다.
4. **증류**: 아래 규칙으로 spec.md를 작성/병합한다.
5. **이미지 큐레이션**: 아래 절차대로 제안하고 사용자 승인 후 반영한다.
6. 완료 보고: spec.md 요약 + "이제 /retro-blog(velog 글) 또는 /retro-ppt(발표 덱)로 내보낼 수 있어요" 안내.

## 증류 규칙

- **남긴다**: 반복 실패, 방향 전환(pivot), 사용자 개입·결정, 예상과 다른 결과, 배운 것.
- **버린다**: 오타 수정, 단순 조회, 한 번에 통과한 루틴 작업.
- 타임라인의 ❌(도구 실패) 표시와 그 직후의 대응이 시행착오의 1차 신호다.
- **톤**: 구조는 체계적으로(문제→시도→해결), 서술은 솔직하게. "완벽하게 설계했다"가 아니라
  "여기서 막혀서 이렇게 돌아갔다"를 남긴다. `## 아쉬운 점` 섹션은 생략 불가.

## spec.md 형식

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

다이어그램이 필요하면 mermaid 코드블록을 본문에 직접 넣는다.
이미지 경로는 retro/ 기준 상대 경로(assets/… 형태)로 적는다.

## 체크포인트 병합 (spec.md가 이미 있을 때)

- frontmatter의 `sessions`·`updated`를 갱신하고, 새 재료는 여정에 추가 병합한다.
- 같은 문제의 후속 진행이면 해당 문제 섹션에 이어 쓴다.
- **사람이 수동 편집한 문구는 보존한다.** 병합이 모호하면 사용자에게 확인.

## 이미지 큐레이션

1. `ls -l --time-style=+%Y-%m-%dT%H:%M retro/assets/auto/ retro/assets/inbox/ 2>/dev/null`
2. 파일명의 타임스탬프(우선) 또는 수정 시각을 세션 타임라인과 대조해 후보 구간을 추정한다.
3. 각 이미지를 Read로 직접 열어 내용을 확인하고, 여정의 어느 섹션에 어울리는지 제안한다.
4. **사용자 승인 후** spec.md에 `![캡션](assets/…)`로 기록한다. 캡션 초안도 함께 제안.
5. 매칭되지 않는 이미지는 "미배치 목록"으로 보고하고, 스크린샷 없는 핵심 구간은
   mermaid 다이어그램 초안을 제안한다.

## 자동 캡처 관례

retro/가 있는 프로젝트에서 브라우저 검증 스크린샷을 찍을 때는
`retro/assets/auto/<YYYY-MM-DDTHH-MM-SS>-<설명>.png` 사본을 남긴다.
(프로젝트 CLAUDE.md에 이 관례를 한 줄 적어두면 다른 세션에서도 유지된다.)
