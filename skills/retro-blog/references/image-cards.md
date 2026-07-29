# 이미지 만들기 가이드 — "내 데이터로 만드는" 블로그 이미지

원칙: AI 생성 일러스트 대신 **실제 세션·실제 데이터·실제 화면**에서 이미지를 만든다.
그게 오리지널리티다. 자동 생성 가능한 이미지는 4종이고, 전부
`python3 "$HOME/.claude/skills/retro/scripts/html_shot.py" <html> <out.png> --width W --height H`
로 만든다. 결과는 `retro/assets/auto/<YYYY-MM-DDTHH-MM-SS>-<설명>.png`에 저장.

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

## 슬롯을 채울 수 없을 때

브라우저 밖 실물(IDE 화면, 실기기, 오프라인 현장)은 자동 생성 대상이 아니다 —
사용자에게 "이 슬롯은 직접 찍어서 `retro/assets/inbox/`에 넣어주세요" 목록으로 요청한다.
