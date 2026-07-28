---
name: retro-ppt
description: retro/spec.md 회고 스펙을 발표용 단일 파일 HTML 슬라이드 덱으로 변환한다. "PPT로 만들어", "발표자료로", "슬라이드 뽑아줘" 요청 시 사용. 스펙이 없으면 먼저 retro 스킬을 실행한다. 키보드로 넘기고 인쇄(Ctrl+P)로 PDF화한다.
---

# retro-ppt — 회고 스펙 → HTML 발표 덱

## 전제

`retro/spec.md`가 없으면 "먼저 /retro로 회고 스펙을 만들어야 해요"라고 안내하고 중단.

## 절차

1. `retro/spec.md`를 Read → `references/deck-guide.md`의 서사 구조로 슬라이드를 설계한다.
2. `assets/deck-template.html`을 Read → `<!-- SLIDES:START -->` ~ `<!-- SLIDES:END -->` 사이를
   설계한 슬라이드로 교체해 `retro/out/ppt/YYYY-MM-DD-<slug>.html`로 저장한다.
   - 템플릿의 슬라이드 타입 클래스만 사용: slide-title / slide-section / slide-content /
     slide-image / slide-two-col / slide-quote / slide-end
   - 이미지는 일단 로컬 상대 경로로 참조한다: `../../assets/auto/….png`
3. 임베드: `python3 "<skill-dir>/scripts/embed_images.py" "retro/out/ppt/<파일>.html"`
   - stderr 경고 확인: 2MB 초과는 리사이즈 제안, 누락은 플레이스홀더 처리됨을 사용자에게 알린다.
4. 검증: 가능하면 브라우저(chrome-devtools MCP)로 열어 표지·중간·끝 슬라이드와
   키보드 내비를 확인한다. 불가하면 파일을 열어 SLIDES 마커 사이 구조를 육안 점검.
5. 사용자 안내: 파일 경로, 조작법(←/→ 이동, Ctrl+P → PDF 저장), 슬라이드 수.
