---
name: retro-blog
description: 회고 스펙(retro/specs/)을 velog 블로그 글로 변환해 퇴고 게이트를 거쳐 비공개 발행까지 수행한다(공개는 명시 요청 시만). 이미지·mermaid 다이어그램 CDN 업로드, 썸네일·시리즈 자동 처리. "velog에 올려줘", "회고 글 써줘", "글 업데이트해줘"(발행 후 수정), "공개로/비공개로 바꿔줘", "말투 학습해줘" 요청 시 사용. 스펙이 없으면 먼저 retro 스킬을 실행한다.
---

# retro-blog — 회고 스펙 → velog 초안

## 전제

- 회고 스펙(`retro/specs/*.md`, 구버전은 `retro/spec.md`)이 하나도 없으면:
  "먼저 /retro로 회고 스펙을 만들어야 해요"라고 안내하고 중단.
- 업로드 기본값은 **비공개 발행**(본인만 보임). **공개는 사용자가 명시적으로 요청할 때만**
  (`--public` 또는 발행 후 전환). 임시저장을 원하면 `--draft`.

## 절차

0. **설정 확인**: `retro/config.md`가 있으면 Read — `default_tags`·`audience`·"말투 메모"를
   글에 반영하고, `default_visibility`를 업로드 모드 기본값으로 쓴다(public이면 발행 직전
   한 번 더 확인 — 공개 명시 원칙 유지). 없으면 retro 스킬 초기화를 먼저 안내.
   **말투 결정** — `references/style-presets.md`의 우선순위를 따른다:
   ① 사용자가 이번 글에 직접 지정한 말투 → ② config의 `style_preset`(plain/friendly/meme/tutor)
   → ③ 학습 프로필 `~/.config/velog-retro/style.md`("내 말투") → ④ config의 말투 메모
   → ⑤ 아무것도 없으면 friendly에 준해 쓰되, 첫 발행 때 프리셋 4종+내 말투 선택지를
   제시하고(각 프리셋의 비교 샘플 활용) 선택을 config에 저장한다.
0-1. **스펙 선택**: `ls -t retro/specs/*.md` — 여러 개면 제목·갱신일 목록을 보여주고 고르게 한다
   (기본: 최근 갱신). 1개뿐이거나 사용자가 이미 지정했으면 바로 진행.
   부작 스펙(`-part1`, `-part2`)은 부별로 각각 글을 만들고 velog 시리즈명을 제안한다
   (시리즈 등록 자체는 velog에서 직접 — API 연동은 v2).
1. 선택한 스펙을 Read → `references/velog-style.md` 가이드에 따라 글을 작성해
   `retro/out/blog/YYYY-MM-DD-<slug>.md`로 저장한다.
   - frontmatter: `title`(필수), `tags`(3~5개 리스트), `thumbnail`(선택)
   - 이미지는 **MD 파일 기준 상대 경로**로 적는다: `../../assets/auto/….png`
   - **이미지 슬롯 규칙 — 주요 섹션(##/###)마다 이미지 1장이 목표.** 확보된 이미지가 없는
     자리마다 주석을 촘촘히 심는다(velog에선 안 보이고 수정란에서만 보임):
     `<!-- 🖼️ 이미지 슬롯: <무엇을 보여줄지> | 후보: 코드카드/스탯카드/다이어그램/실물스샷 -->`
1-1. **슬롯 채우기** (`references/image-cards.md` 절차): 슬롯을 순회하며
   - **"찍을 게 없다"고 판단하기 전에 항상 "HTML로 만들 수 있지 않나?"를 먼저 자문한다** —
     기능(웹 UI·카메라·AI 응답 화면 등)은 데모 HTML로 재현하고, CSV·JSON·로그 데이터는
     표·막대 HTML로 렌더링해서 찍으면 대부분의 슬롯이 채워진다.
   - 자동 생성(코드/로그 카드, 스탯 카드, 데이터 인사이트 카드, 기능 데모 페이지,
     mermaid 다이어그램, HTML 산출물 스샷) → 카드 HTML을 만들어 `html_shot.py`로 PNG를 뽑아
     `retro/assets/auto/`에 저장하고 슬롯 주석을 실제 이미지 참조로 교체한다.
   - **규격: 항상 가로형(너비 > 높이).** 기본 1200×630, 로그 카드 1200×480, 표 카드 최대
     1200×700. 내용이 길면 여러 장으로 분할하고, 세로로 긴 페이지는 대표 영역만 크롭.
   - 실물 스크린샷이 필요한 슬롯(브라우저 밖 실기기·IDE 화면 등)만 사용자에게
     "직접 찍어서 `retro/assets/inbox/`에 넣어주세요" 목록으로 요청하고, 못 채운 주석은 남긴다.
2. 초안 전문을 사용자에게 보여주고 승인받는다. 수정 요청은 반영 후 재확인.
2-1. **퇴고 게이트**: `references/quality-gate.md` 체크리스트로 점검·수정하고 통과 요약을 보고한다.
2-2. **시리즈**: config의 `series`가 있으면
   `python3 "<skill-dir>/scripts/velog_publish.py" series <username>` 으로 목록을 조회해
   이름이 일치하는 시리즈의 id를 `--series-id`로 전달한다. 일치하는 게 없으면 목록을 보여주고
   선택받거나, 새 시리즈는 velog에서 만들도록 안내(생성 API 미지원). 첫 발행인데 config가
   비어 있으면 시리즈에 넣을지 한 번 묻고 선택을 config에 저장.
2-3. **썸네일**: `retro/assets/inbox/`에 `cover.*` 파일이 있으면 frontmatter `thumbnail`로
   지정한다(발행 시 CDN 업로드됨). 없으면 스크립트가 본문 첫 이미지를 자동 지정한다.
3. 업로드 실행 (기본 = 비공개 발행):
   `python3 "<skill-dir>/scripts/velog_publish.py" publish "retro/out/blog/<파일>.md" [--series-id <id>]`
   - 사용자가 처음부터 공개를 요청한 경우에만 `--public`, 임시저장을 원하면 `--draft`.
   - 본문의 mermaid 코드블록은 자동으로 이미지(kroki→CDN)로 변환된다. 변환 실패 경고가
     나오면 사용자에게 전달(코드블록은 그대로 유지되므로 글이 깨지진 않음).
4. 성공(종료 코드 0): 출력된 글 주소를 전달하고, 비공개 상태이며 "공개로 바꿔줘"라고 하면
   전환해줄 수 있음을 안내한다. 발행 기록은 `<파일>.velog.json` 사이드카에 저장된다.
   마지막으로 콘텐츠 맵을 재생성한다:
   `python3 "$HOME/.claude/skills/retro/scripts/build_map.py"`
   - 글에 이미지가 0장이면 업로드 전에 경고한다: "이미지가 없습니다 — retro/assets/inbox/에
     넣어주시면 배치할게요. 그대로 올릴까요?"

## 말투 학습 (사용자가 "말투 학습해줘" 요청 시)

1. username 확보: `retro/config.md`의 `velog_username` → 없으면 발행 사이드카(`*.velog.json`)의
   username → 그것도 없으면 사용자에게 묻고 config에 저장.
2. 수집(공개 글만, 인증 불필요): `python3 "<skill-dir>/scripts/style_learn.py" <username> --max 10`
   → `~/.config/velog-retro/style-corpus.md` 생성. 공개 글이 없으면(exit 1) 그대로 안내하고 종료.
3. 코퍼스를 Read하고 **따라 할 수 있는 규칙 형태**로 문체 프로필을 증류한다:
   어미 분포(습니다/어요/다체 비율), 문단 길이·리듬, 이모지·기호 습관, 자주 쓰는 연결어·표현,
   제목 스타일, 코드블록·인용 사용 패턴. 각 항목에 실제 예시 문장 1개씩 인용.
4. `~/.config/velog-retro/style.md`로 저장(계정 단위 — 모든 프로젝트에 적용됨) 후
   프로필 요약을 사용자에게 보여주고 어색한 규칙은 수정받는다.
5. 이후 글 작성 시 절차 0에서 자동 반영된다. 갱신하고 싶으면 다시 "말투 학습해줘".

## 발행 후 수정 (사용자가 "글 고쳐줘/업데이트해줘" 요청 시)

1. 스펙 또는 초안 MD를 수정하고 사용자 확인을 받는다 (퇴고 게이트 재적용).
2. `python3 "<skill-dir>/scripts/velog_publish.py" update "retro/out/blog/<파일>.md"`
   — 발행 기록(사이드카)의 글을 새 내용으로 갱신한다. 공개 상태·시리즈는 그대로 유지된다.
3. 주의: **사용자가 velog 웹에서 글을 직접 수정한 뒤라면** 로컬 내용으로 덮어써도 되는지
   먼저 확인한다.

## 공개/비공개 전환

사용자가 "공개로 바꿔줘"(또는 "다시 비공개로") 요청하면:
`python3 "<skill-dir>/scripts/velog_publish.py" visibility "retro/out/blog/<파일>.md" --public` (또는 `--private`)
- 주의: 전환은 로컬 치환본(`*.published.md`) 내용으로 글을 다시 쓴다. **사용자가 velog 웹에서
  글을 직접 수정한 뒤라면** 덮어쓰지 말고 velog 화면의 공개 설정을 쓰도록 안내한다.
5. 실패 폴백(종료 코드별):
   - **2 (토큰 없음/만료)**: 아래 "최초 설정"을 안내하고, 완료되면 3번부터 재시도.
   - **3/4/5 (업로드·API·형식 실패)**: "MD 파일이 `retro/out/blog/`에 있으니 velog 에디터에
     통째로 붙여넣고 이미지를 드래그하면 됩니다"라고 안내한다. 이미지 URL 치환본
     (`*.published.md`)이 생성돼 있으면 그 파일을 붙여넣으라고 안내한다(이미지 재업로드 불필요).

## 최초 설정 (velog 토큰)

1. 브라우저에서 velog.io 로그인 → 개발자도구(F12) → Application → Cookies → https://velog.io
2. `access_token`, `refresh_token` 값을 복사
3. 터미널에서 실행: `python3 "<skill-dir>/scripts/velog_publish.py" setup`
   (`~/.config/velog-retro/tokens.json`에 0600 권한으로 저장된다. 토큰은 절대 채팅에 붙여넣지
   않게 하고, 위 명령을 사용자가 직접 실행하도록 안내한다 — `! ` 접두사로 실행 가능.)

## 주의

- velog 비공식 API 사용 — 언제든 변경될 수 있다. 실패해도 MD 폴백이 항상 존재한다.
- **공개 발행은 사용자의 명시적 요청 없이는 절대 하지 않는다** (기본은 비공개).
- 토큰을 로그·대화·커밋에 절대 노출하지 않는다.
