# 이미지 만들기 가이드 — "내 데이터로 만드는" 블로그 이미지

## 대원칙 2가지

1. **정리된 HTML이 없으면 만들어서 찍는다.** 프로젝트의 기능·데이터·결과물 중 보여줄 것이
   있는데 시각 자료가 없다면, 그것을 보여주는 HTML 페이지를 즉석에서 만들어 렌더링한다.
   카메라·AI·차트 같은 기능도 대부분 HTML 안에서 데모 형태로 재현할 수 있다 — "찍을 게 없다"는
   결론을 내리기 전에 항상 "HTML로 만들 수 있지 않나?"를 먼저 자문한다.
   CSV·JSON·로그 같은 데이터도 표·타일·막대 HTML로 렌더링하면 인사이트 이미지가 된다(E 참조).
2. **항상 가로형(너비 > 높이)으로 찍는다.** 블로그 본문에 딱 맞게 들어가는 규격:
   - 기본·썸네일 겸용: **1200×630** / 로그·코드 카드: 1200×480 / 표·데이터 카드: 최대 1200×700
   - 내용이 세로로 길면 한 장에 욱여넣지 말고 **여러 장으로 분할**한다.
   - 세로로 긴 페이지(랜딩 등)는 전체 캡처 금지 — 대표 영역만 가로 크롭.

AI 생성 일러스트 대신 **실제 세션·실제 데이터·실제 화면**에서 이미지를 만든다.
그게 오리지널리티다. 생성은 전부
`python3 "$HOME/.claude/skills/retro/scripts/html_shot.py" <html> <out.png> --width W --height H`
로 하고, 결과는 `retro/assets/auto/<YYYY-MM-DDTHH-MM-SS>-<설명>.png`에 저장한다.

## A. 코드/로그 카드 — 시행착오의 증거

세션에서 실제로 나온 코드·로그·에러를 터미널 프레임에 담는다. 아래 템플릿을 임시 HTML로
쓰고(`retro/.timeline/card.html`), 내용을 채워 1200×(줄수×36+150) 크기로 찍는다.

```html
<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;background:#0d1117;display:flex;align-items:center;justify-content:center;
  min-height:100vh;font-family:'Cascadia Code',Consolas,monospace}
.frame{background:#161b22;border:1px solid #30363d;border-radius:14px;width:1100px;
  box-shadow:0 18px 50px rgba(0,0,0,.5)}
.bar{display:flex;gap:8px;padding:14px 18px;border-bottom:1px solid #30363d}
.bar i{width:13px;height:13px;border-radius:50%}
.bar i:nth-child(1){background:#ff5f56}.bar i:nth-child(2){background:#ffbd2e}.bar i:nth-child(3){background:#27c93f}
.bar span{color:#8b949e;font-size:14px;margin-left:8px}
pre{margin:0;padding:22px 26px;color:#c9d1d9;font-size:19px;line-height:1.7;overflow:hidden}
.err{color:#f85149}.ok{color:#3fb950}.dim{color:#8b949e}.hl{background:#3d2c00}
</style></head><body>
<div class="frame">
  <div class="bar"><i></i><i></i><i></i><span>제목 — 예: git commit 실패 로그</span></div>
  <pre><span class="dim">$ git commit -m "..."</span>
<span class="err">fatal: Unable to create '.git/index.lock': File exists.</span>
<span class="hl">→ statusline이 프롬프트마다 git을 실행해 생기는 경합이었다</span></pre>
</div>
</body></html>
```

- 실제 세션에서 나온 텍스트를 그대로 쓴다(각색 금지 — 토큰 등 민감 문자열만 마스킹).
- 핵심 줄에 `.err`(실패)/`.ok`(해결)/`.hl`(깨달음) 클래스로 색을 준다.

## B. 스탯 카드 — 숫자로 보는 여정

세션 통계(시간·턴·도구 호출·실패 수), 테스트 수, 커밋 수를 큰 숫자 타일로.

```html
<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;background:linear-gradient(135deg,#111418,#1b2340);min-height:100vh;
  display:flex;align-items:center;justify-content:center;
  font-family:-apple-system,"Segoe UI","Pretendard","Malgun Gothic",sans-serif}
.wrap{width:1100px;padding:40px}
h1{color:#e8eaed;font-size:34px;margin:0 0 28px}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:18px}
.tile{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);
  border-radius:16px;padding:26px 22px;text-align:center}
.tile b{display:block;color:#7aa2f7;font-size:52px;line-height:1.1}
.tile span{color:#9aa0a6;font-size:17px}
</style></head><body><div class="wrap">
<h1>session-retro를 만든 이틀</h1>
<div class="grid">
  <div class="tile"><b>1,311</b><span>세션 분</span></div>
  <div class="tile"><b>228</b><span>도구 호출</span></div>
  <div class="tile"><b>8</b><span>실패(=회고 재료)</span></div>
  <div class="tile"><b>68</b><span>테스트 그린</span></div>
</div></div></body></html>
```

- 크기: 1200×630 (블로그·SNS 썸네일 규격) — `--width 1200 --height 630`.
- 숫자는 파서/인벤토리 실측값만 사용(지어내지 않는다).

## C. 다이어그램 — 구조·흐름 설명

mermaid 코드블록을 본문에 넣으면 발행 시 자동으로 이미지(kroki)로 변환된다.
덱·미리보기용으로 미리 뽑고 싶으면 mermaid를 담은 HTML 없이도
`velog_publish.py`의 변환을 그대로 쓰면 된다(발행 시점 처리 권장).

## D. 산출물 스크린샷 — 실제 화면

- 콘텐츠 맵/랜딩/덱 슬라이드: `html_shot.py retro/map.html out.png` (덱은 해시로 특정 슬라이드:
  파일을 복사해 `#5`를 기본 표시하도록 열 수 없으므로, 덱 전체 대신 원하는 슬라이드 섹션만
  추린 임시 HTML을 만들어 찍는 편이 깔끔하다)
- 개발 중인 웹앱: 로컬 서버가 떠 있으면 그 URL 대신 정적 파일로 저장해 찍거나,
  사용자에게 실물 스크린샷을 요청한다(브라우저 상호작용이 필요한 화면은 실물이 낫다).

## E. 데이터 인사이트 카드 — CSV/JSON을 이미지로

측정치·집계·비교 데이터는 표 + CSS 막대로 렌더링한다. 값은 반드시 실데이터에서 가져온다.

```html
<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;background:linear-gradient(135deg,#111418,#1b2340);min-height:100vh;
  display:flex;align-items:center;justify-content:center;
  font-family:-apple-system,"Segoe UI","Pretendard","Malgun Gothic",sans-serif;color:#e8eaed}
.wrap{width:1100px;padding:36px}
h1{font-size:30px;margin:0 0 22px}
.row{display:grid;grid-template-columns:220px 1fr 90px;gap:14px;align-items:center;
  padding:10px 0;border-bottom:1px solid rgba(255,255,255,.08);font-size:19px}
.bar{height:22px;border-radius:6px;background:linear-gradient(90deg,#7aa2f7,#3d59a1)}
.val{text-align:right;color:#7aa2f7;font-weight:700}
.dim{color:#9aa0a6;font-size:15px;margin-top:14px}
</style></head><body><div class="wrap">
<h1>제목 — 예: 세션별 도구 호출 수</h1>
<div class="row"><span>항목 A</span><div class="bar" style="width:90%"></div><b class="val">228</b></div>
<div class="row"><span>항목 B</span><div class="bar" style="width:35%"></div><b class="val">89</b></div>
<p class="dim">출처: retro/.timeline/inventory.md (실측)</p>
</div></body></html>
```

- 막대 width%는 최대값 대비 비율로 계산한다. 행이 7개를 넘으면 상위 N개 + "기타"로 줄이거나 분할.

## F. 기능 데모 페이지 — 앱·기능을 HTML로 재현해 찍기

글이 다루는 기능(웹 UI, 카메라 프리뷰 레이아웃, AI 응답 화면, 채팅 흐름 등)의 **대표 장면**을
보여주는 데모 HTML을 만들어 찍는다. 실제 앱을 띄우기 어려울 때 특히 유용하다.

- 실동작이 아니라 "장면 재현"임을 캡션에 밝힌다(정직성): *실제 UI를 재현한 데모 화면입니다*
- 앱의 실제 CSS/컴포넌트가 저장소에 있으면 그대로 가져다 쓴다 — 재현도가 오리지널리티다.
- 상호작용 결과(예: AI 응답)는 세션에 남은 실제 출력물을 붙여넣는다.

## G. 타이틀 카드 — 썸네일 자동 생성 (API·비용 0)

발행 전에 **제목·태그·시리즈로 타이틀 카드를 만들어 썸네일로 지정**한다. AI 이미지 생성 API가
필요 없다 — 아래 템플릿에 값을 채워 `html_shot`으로 1200×630에 찍으면 끝. 스타일은
`retro/config.md`의 `thumbnail_style`로 고정해 **블로그 목록의 디자인 일관성**을 지킨다.
저장: `retro/assets/auto/<ts>-title-card.png` → frontmatter `thumbnail:`에 상대 경로로 지정
(발행 스크립트가 업로드해 CDN URL로 바꿔준다). 본문에는 넣지 않는다(커버 전용).

### 스타일 1: `gradient` (기본) — 다크 그래디언트 + 큰 타이포

```html
<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;background:linear-gradient(135deg,#111418 30%,#1b2340 70%,#2a3555);
  min-height:100vh;display:flex;align-items:center;
  font-family:-apple-system,"Segoe UI","Pretendard","Malgun Gothic",sans-serif}
.wrap{padding:70px 80px;width:100%}
.series{display:inline-block;color:#7aa2f7;border:1px solid #3d59a1;border-radius:999px;
  padding:6px 18px;font-size:19px;margin-bottom:26px}
h1{color:#e8eaed;font-size:58px;line-height:1.3;margin:0 0 30px;word-break:keep-all;max-width:1000px}
.tags{color:#9aa0a6;font-size:21px}
.tags b{color:#7aa2f7;margin-right:14px}
</style></head><body><div class="wrap">
<span class="series">개발 회고</span>
<h1>제목이 들어갈 자리 — 두 줄까지 자연스럽게</h1>
<p class="tags"><b>#ClaudeCode</b><b>#회고</b><b>#자동화</b></p>
</div></body></html>
```

### 스타일 2: `terminal` — 터미널 프레임 감성

코드 카드(A) 프레임을 재사용하되, pre 안에 `$ <제목 키워드>` + 커서(▌)와 태그 주석만 담는다.
제목이 명령어처럼 보이는 개발 블로그 특화 스타일.

### 스타일 3: `pattern` — 밝은 배경 + 그리드 패턴

`background:#f7f8fa; background-image:radial-gradient(#c9d3e6 1.5px, transparent 1.5px);
background-size:26px 26px;` 위에 어두운 타이포(#1b2027)와 컬러 포인트 한 가지. 라이트한 인상.

### 공통 규칙

- 크기 항상 **1200×630**. 제목이 28자를 넘으면 폰트를 48px로 줄이고, 40자 초과 시 핵심 구절만 발췌.
- 시리즈 칩·태그는 config 값에서 자동으로. 날짜는 넣지 않는다(목록에 이미 표시됨).
- 진짜 일러스트 배경을 원하면(선택): 외부 이미지 생성 API 키를 setup 방식으로 받아 배경만 생성하고
  타이포는 위 템플릿으로 얹는 하이브리드가 가능하다 — 단, 스타일 일관성이 깨지기 쉬워 기본은 비추천.

## 슬롯을 채울 수 없을 때

브라우저 밖 실물(IDE 화면, 실기기, 오프라인 현장)은 자동 생성 대상이 아니다 —
사용자에게 "이 슬롯은 직접 찍어서 `retro/assets/inbox/`에 넣어주세요" 목록으로 요청한다.
