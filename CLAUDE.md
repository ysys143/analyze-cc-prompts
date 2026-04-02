# Claude Code 프롬프트 분석 프로젝트

## 프로젝트 성격

Claude Code CLI의 내부 구조를 소스코드 수준에서 역공학하는 연구 프로젝트다.
minified 번들, 유출 TypeScript 소스, 실제 API 캡처를 교차 분석해 프롬프트 구조, 내부 아키텍처, 기능 구현 방식을 추출하고 문서화한다.

분석 대상:
1. npm 패키지 `@anthropic-ai/claude-code`의 `cli.js` (minified JavaScript) — `sources/npm/`
2. 유출 TypeScript 소스 (`ysys143/forked-claude-code`) — `sources/leaked/` (submodule)
3. Native 바이너리 (`~/.local/share/claude/versions/`) 에서 추출한 JavaScript — `sources/native/` (gitignored)
4. 공식 플러그인 저장소 (`anthropics/claude-plugins-official`) — `sources/plugins/`
5. proxy를 통해 캡처한 실제 API 요청/응답 — `tools/proxy/`

분석 방법:
1. Python 스크립트로 minified 파일에서 키워드 위치 추출 후 슬라이싱
2. 난독화 변수명 추적 (함수 호출 관계, 패턴 매칭)
3. 유출 소스와 minified 코드 교차 검증 (cross-ref)
4. 공식 문서, GitHub, 실제 동작과 교차 검증

---

## 파일 네이밍 규칙

리포트 파일은 순번 접두사를 붙인다:

```
NN-topic-name.md
```

1. NN은 두 자리 숫자 (01, 02, ..., 28, 29, ...)
2. topic-name은 소문자 하이픈 구분
3. 현재 마지막 번호를 확인하고 다음 번호 사용
4. 리포트가 아닌 파일 (README, CLAUDE.md 등)은 번호 없음

현재 최신 번호: 30 (`reports/cross-ref/30-source-verification.md`)

---

## 리포트 작성 규칙

### 구조

1. 제목: `# [주제] 기술 분석 리포트` 또는 `# [주제] 분석`
2. 상단 메타: 분석 대상 버전, 분석 일자, 내부 코드명 (있는 경우)
3. 섹션은 `## N. 제목` 형식으로 번호 부여
4. 서브섹션은 `### N.M 제목` 형식
5. 마지막에 분석 소스 명시

### 목록 형식

목록은 반드시 번호를 붙인다. 불릿(-) 사용 금지.

```
[O] 올바른 방식:
1. 첫 번째 항목
2. 두 번째 항목
3. 세 번째 항목

[X] 잘못된 방식:
- 첫 번째 항목
- 두 번째 항목
```

중첩 목록도 동일:
```
1. 상위 항목
   1. 하위 항목
   2. 하위 항목
2. 상위 항목
```

### 다이어그램

ASCII 다이어그램을 사용한다. 유니코드 박스 문자(┌┐└┘├┤┬┴┼│─) 대신 ASCII 문자 사용:

```
[O] ASCII:          [X] 유니코드:
+------+            ┌──────┐
|      |            │      │
+------+            └──────┘

[O] 화살표:         [X] 화살표:
->  <-  -->         -> <- (동일하므로 OK)
|                   |
v                   v
```

코드 블록 내 다이어그램은 백틱 세 개로 감싼다.

### 코드 인용

1. 실제 코드는 언어 지정 코드 블록 사용 (`javascript`, `typescript`, `python`, `bash` 등)
2. 난독화 변수명은 원본 그대로 표기하고 주석으로 의미 설명
3. 재구성한 코드는 주석으로 "재구성" 또는 원본 함수명 표기

### 언어

1. 본문: 한국어
2. 코드, 변수명, 함수명: 원본 유지 (영어)
3. 기술 용어: 영어 원문 병기 권장 (예: "피처 플래그(feature flag)")
4. 이모지 사용 금지 (프로젝트 훅이 차단함)

### 내용 원칙

1. 추측과 확인된 사실을 구분한다. 확인되지 않은 내용은 명시
2. 난독화 변수명을 추적할 때는 근거 코드를 함께 제시
3. 버전 정보를 항상 명시한다 (버전마다 구현이 다를 수 있음)
4. 보안 관련 발견은 방어 관점에서 서술한다

---

## cli.js 분석 방법

minified 파일은 grep 결과가 라인 전체를 반환해 출력이 수 MB에 달한다.
반드시 Python 스크립트로 위치만 추출하고 슬라이싱한다:

```python
# [O] 올바른 방식: 위치 추출 후 슬라이싱
import re
with open('cli.js') as f:
    content = f.read()
for m in re.finditer(r'키워드', content):
    print(f"pos={m.start()}")
    print(content[m.start()-100:m.start()+400])

# [X] 잘못된 방식: grep 직접 사용 (라인 전체 출력으로 수 MB 발생)
# grep -n "키워드" cli.js
```

---

## 디렉토리 구조

```
analyze-cc-prompts/
1. sources/             -- 원본 소스 아카이브
   1. npm/              -- minified 번들 버전별 스냅샷
      1. v2.1.29/
      2. v2.1.38/
      3. v2.1.70/
      4. v2.1.80/
   2. leaked/           -- 유출 TypeScript 소스 (submodule: ysys143/forked-claude-code)
   3. native/           -- Native 바이너리 추출본 (gitignored)
   4. plugins/          -- 공식 플러그인 (claude-plugins-official)
2. reports/             -- 분석 리포트
   1. reverse/          -- cli.js 리버스 엔지니어링 (버전별)
      1. v2.1.29/       -- 01-11번 리포트
      2. v2.1.38/       -- 12-16번 리포트
      3. v2.1.42/       -- 28번 리포트 (Firecracker/Web)
      4. v2.1.70/       -- 17-19, 24-25번 리포트
      5. v2.1.80/       -- 27, 29번 리포트
   2. api/              -- API 트래픽/인증/빌링 분석 (20-23, 26번)
   3. source/           -- 유출 TypeScript 소스 직접 분석 (신규)
   4. cross-ref/        -- minified <-> 소스 대조 분석 (신규)
3. tools/               -- 분석 도구
   1. proxy/            -- API 캡처 프록시 (mitmproxy 기반)
4. README.md            -- 프로젝트 소개 (한국어)
5. README_EN.md         -- 프로젝트 소개 (영어)
6. CLAUDE.md            -- 이 파일
```
