# 20. Reverse Proxy를 통한 Claude Code 실시간 API 캡처 분석

## 개요

이전 `test_local_cc` 실험에서는 `ANTHROPIC_BASE_URL`을 로컬 llama.cpp 서버로 리다이렉트하여 API 요청을 캡처했다. 이번에는 같은 기법을 활용하되, 실제 Anthropic API로 투명하게 포워딩하는 **리버스 프록시**를 만들어 라이브 세션의 요청/응답을 모두 캡처했다. 기존 분석(01~19)이 소스 코드 역공학이나 로컬 llama.cpp 서버 기반이었다면, 이번에는 **실제 프로덕션 API 통신**을 그대로 가로채어 분석한 최초의 사례이다.

---

## 실험 세팅

### 프록시 구조

```
Claude Code  ──→  localhost:8082 (proxy.py)  ──→  api.anthropic.com
                       │
                   dumps/ 에 req/res JSON 저장
```

- **proxy.py**: aiohttp 기반 비동기 리버스 프록시
  - `POST /v1/messages` 요청을 가로채어 요청 본문을 `dumps/YYYY-MM-DDTHHMMSS.sss-req.json`으로 저장
  - 원본 헤더(x-api-key, anthropic-version 등)를 그대로 포워딩
  - SSE 스트리밍 청크를 실시간 패스스루 (버퍼링 지연 없음)
  - 응답 이벤트를 축적하여 `-res.json`으로 저장
  - 기타 엔드포인트는 투명 패스스루

- **test.sh**: 격리된 `HOME` 환경에서 Claude Code 실행
  - `HOME=proxy/.claude-home/` 으로 오버라이드 → 실제 사용자 설정에 영향 없음
  - `.env`에서 `ANTHROPIC_API_KEY` 자동 로드
  - `ANTHROPIC_BASE_URL=http://localhost:8082` 설정

### 테스트 환경

| 항목 | 값 |
|------|-----|
| 모델 | claude-sonnet-4-6 |
| 클라이언트 | Claude Code (headless, `-p` 모드) |
| 프록시 | aiohttp 리버스 프록시 (localhost:8082) |
| API | 실제 Anthropic API (api.anthropic.com) |
| 설정 | 순정 (격리된 HOME, 플러그인/설정 없음) |

### 캡처 데이터

두 차례의 캡처 세션 결과를 종합한다.

| 항목 | 세션 1 | 세션 2 |
|------|--------|--------|
| 총 요청 수 | 19 | 13 (main 10 + haiku 2 + web_search 1) |
| 총 데이터량 | ~2.0 MB (요청만) | ~1.5 MB (요청만) |
| 모델 | claude-sonnet-4-6 | claude-sonnet-4-6, claude-haiku-4-5-20251001 |
| 대화 턴 수 | msgs 1→35 | msgs 1→45 |
| 내부 haiku 호출 | 0 | 2 |

---

## 1. 요청 구조 (Top-level Keys)

### 1.1 Main 요청 (claude-sonnet-4-6)

```json
{
  "model": "claude-sonnet-4-6",
  "stream": true,
  "max_tokens": 32000,
  "system": [...],
  "messages": [...],
  "tools": [...],
  "thinking": {"type": "adaptive"},
  "output_config": {"effort": "medium"},
  "context_management": {"edits": "clear_thinking_20251015", "keep": "all"},
  "metadata": {"user_id": "user_<hash>_account__session_<uuid>"}
}
```

**주요 필드:**

| 필드 | 값 | 의미 |
|------|-----|------|
| `thinking.type` | `"adaptive"` | Extended thinking 사용하되, 모델이 필요 여부를 자체 판단 |
| `output_config.effort` | `"medium"` | 응답 생성 노력 수준 (API 파라미터) |
| `context_management.edits` | `clear_thinking_20251015` | 사고 컨텍스트 관리 정책 |
| `metadata.user_id` | `user_<hash>_account__session_<uuid>` | 사용자 해시 + 세션 UUID 조합 |
| `max_tokens` | `32000` | 소스 분석에서 확인한 16384가 아닌 32000 사용 |

### 1.2 Haiku 내부 요청 (claude-haiku-4-5-20251001)

```json
{
  "model": "claude-haiku-4-5-20251001",
  "stream": true,
  "max_tokens": 32000,
  "system": [{"type": "text", "text": "You are Claude Code..."}],
  "messages": [...],
  "tools": [],
  "temperature": <value>,
  "metadata": {"user_id": "..."}
}
```

Haiku 요청의 특징:
- **`thinking` 필드 없음** -- extended thinking 미사용
- **`output_config` 필드 없음**
- **`temperature` 필드 있음** -- main 요청에는 없는 필드
- **`tools` 빈 배열** -- 도구를 전혀 보내지 않음
- **`cache_control` 없음** -- 시스템 프롬프트와 메시지 모두 캐시 마커 없음
- **시스템 프롬프트 1개** (57자, "You are Claude Code..." 한 줄)
- 용도: WebFetch 결과 요약 (83~104 KB의 웹 페이지 콘텐츠를 메시지로 전달)

### 1.3 Web Search 전용 요청

세션 2에서 **첫 번째 요청**이 web_search 전용 호출이었다:

```json
{
  "model": "claude-sonnet-4-6",
  "tools": [{"name": "web_search", ...}],
  "system": [
    {"text": "You are Claude Code...", "cache_control": {"type": "ephemeral"}},
    {"text": "You are an assistant for performing a web search...", "cache_control": {"type": "ephemeral"}}
  ],
  "messages": [{"role": "user", "content": [{"type": "text", "text": "Perform a web search for..."}]}]
}
```

이것은 Claude Code가 **도구별로 분리된 전용 호출**을 만든다는 것을 보여준다:
- 시스템 프롬프트가 완전히 다름 (web search 전용 지시)
- 도구가 `web_search` 하나만 포함
- 전체 요청 크기 1.1 KB (main 요청 123 KB 대비 1/100)

---

## 2. 캐싱 전략 (실제 관찰)

### 2.1 시스템 프롬프트 캐싱

Main 요청의 시스템 프롬프트 2개 블록 모두 `cache_control: {"type": "ephemeral"}` 적용:
- `sys[0]`: "You are Claude Code..." (57자) -- 짧은 식별 문구
- `sys[1]`: 전체 시스템 지시 (15,956~15,978자) -- 도구 사용 정책, 코딩 지침, 환경 정보 포함

### 2.2 메시지 캐싱 패턴

마지막 메시지의 마지막 content block에 `cache_control: {"type": "ephemeral"}`을 삽입하는 패턴을 확인했다. 그러나 **모든 요청에 적용되지는 않았다**:

| 요청 | msgs | cache_control | retry? |
|------|------|---------------|--------|
| T1 (첫 요청) | 1 | [O] | - |
| T16 | 31 | [O] | - |
| T17 | 33 | [O] | - |
| T18 (1차) | 35 | [X] | N |
| T18 (2차) | 35 | [O] | Y (재시도) |
| T19 | 37 | [O] | - |
| T20 | 39 | [O] | - |
| T21 (1차) | 41 | [X] | N |
| T21 (2차) | 41 | [O] | Y (재시도) |
| T22 | 43 | [O] | - |
| T23 | 45 | [X] | - |

**발견: 재시도 메커니즘과 캐싱의 관계**

같은 메시지 수로 재전송되는 요청이 3건 관찰되었다 (msgs=35, msgs=41). 패턴:
1. **첫 시도**: `cache_control` 없이 전송 -> 실패/타임아웃
2. **재시도**: `cache_control` 추가하여 재전송 -> 성공

이는 Claude Code가 **첫 시도에서는 캐시 없이** 보내고, 실패 시 **캐시를 활성화하여 재시도**하는 전략일 수 있다. 또는 반대로, 정상 흐름에서는 캐시를 사용하고 특정 조건(응답 불만족 등)에서 캐시 없이 재요청하는 것일 수 있다.

> **참고**: 마지막 요청 (T23, msgs=45)도 `cache_control` 없는데, 이는 세션이 종료되어 재시도가 발생하지 않은 것으로 추정.

---

## 3. 크기 분석

### 3.1 구성 요소별 크기 (Main 요청)

**세션 1 (첫 번째 요청 기준):**

| 구성 요소 | 크기 | 비율 |
|-----------|------|------|
| System Prompt | 16.2 KB | 16.6% |
| Tools (도구 정의) | 59.6 KB | 60.9% |
| Messages | 19.8 KB | 20.2% |
| 기타 (metadata 등) | ~2.3 KB | 2.3% |
| **합계** | **~97.9 KB** | **100%** |

**세션 1 (마지막 요청 기준):**

| 구성 요소 | 크기 | 비율 |
|-----------|------|------|
| System Prompt | 16.2 KB | 13.7% |
| Tools | 59.6 KB | 50.4% |
| Messages | 39.5 KB | 33.4% |
| 기타 | ~2.9 KB | 2.5% |
| **합계** | **~118.1 KB** | **100%** |

**세션 2 (범위):**

| 구성 요소 | 첫 전체턴 | 마지막 턴 |
|-----------|-----------|-----------|
| System | 16.6 KB | 16.6 KB |
| Tools | 61.0 KB | 61.0 KB |
| Messages | 35.0 KB | 50.6 KB |
| **총** | **123.2 KB** | **137.9 KB** |

### 3.2 턴별 크기 성장

**세션 1:**
```
최소 요청:   1,246 bytes (첫 번째, msgs=1)
최대 요청: 127,978 bytes (마지막, msgs=35)
평균 요청: 109,072 bytes (106.5 KB)
```

**세션 2:**
```
T1:   1.1 KB  (web_search 전용, 도구 1개)
T16: 123.2 KB (본격적 대화 시작, 도구 21개)
T17: 124.1 KB (+0.9 KB)
T18: 126.6 KB (+2.5 KB)
T19: 129.8 KB (+4.2 KB)
T20: 133.9 KB (+4.2 KB)
T21: 135.7 KB (+1.8 KB)
T22: 136.5 KB (+1.2 KB)
T23: 137.9 KB (+1.4 KB)
```

- **고정 오버헤드**: System(~16 KB) + Tools(~60 KB) = **~76 KB** (매 턴 반복)
- **메시지 성장**: 턴당 평균 ~2.3 KB 증가
- 고정 오버헤드가 차지하는 비율: 56~63%

### 3.3 Haiku 내부 요청 크기

| 항목 | 요청 1 | 요청 2 |
|------|--------|--------|
| 크기 | 83.5 KB | 104.2 KB |
| 시스템 | 87 B | 87 B |
| 도구 | 2 B (`[]`) | 2 B (`[]`) |
| 메시지 | 83.6 KB | 104.6 KB |

Haiku 요청은 **웹 페이지 콘텐츠 전체**를 메시지로 전달하기 때문에 크기가 크다. 그러나 도구와 시스템 프롬프트는 거의 없어 순수 컨텐츠 비용만 발생한다.

### 3.4 멀티턴 오버헤드

매 턴마다 **System + Tools (~76 KB)**가 반복 전송된다. 세션 1에서 19회 요청에 걸쳐 이 고정 오버헤드만 **1,440 KB (1.4 MB)**가 전송되었다.

```
고정 오버헤드 (sys+tools): ~76 KB × 19회 = ~1,440 KB
실제 새 콘텐츠 (messages 증분): ~584 KB
오버헤드 비율: 71.2%
```

---

## 4. 도구 (Tools) 분석

### 4.1 도구 목록 (21개)

순정 환경(플러그인 없음, MCP 서버 없음)의 기본 도구 세트:

```
Agent, TaskOutput, Bash, Glob, Grep, ExitPlanMode, Read, Edit, Write,
NotebookEdit, WebFetch, WebSearch, TaskStop, AskUserQuestion, Skill,
EnterPlanMode, TaskCreate, TaskGet, TaskUpdate, TaskList, EnterWorktree
```

### 4.2 도구 스키마 크기

전체 도구 스키마: **~60 KB** (전체 요청의 44~61%)

이전 로컬 llama.cpp 분석에서 관찰한 것과 일치하는 패턴:
- 도구 스키마가 요청의 최대 구성 요소
- 매 턴마다 전체 스키마 재전송
- 순정 환경에서도 ~60 KB (플러그인/MCP 추가 시 85+ KB)

---

## 5. 메시지 구조 패턴

### 5.1 대화 흐름

```
[0]  user: [text, text, text]     <- 초기 컨텍스트 (CLAUDE.md 등 system-reminder 포함)
[1]  assistant: [thinking, tool_use]
[2]  user: [tool_result]
[3]  assistant: [tool_use]
[4]  user: [tool_result]
[5]  assistant: [text]            <- 사용자에게 응답
[6]  user: text                   <- 다음 사용자 입력
[7]  assistant: [thinking, tool_use]
...
```

패턴:
- **사용자 입력**: `role: "user"`, content type `text`
- **도구 실행 결과**: `role: "user"`, content type `tool_result`
- **어시스턴트 응답**: `role: "assistant"`, content types `thinking` + `tool_use` 또는 `text`
- 첫 메시지에 `text` 블록 3개 -- 사용자 입력 외에 system-reminder 등이 포함

### 5.2 메시지 내 system-reminder 주입

사용자 메시지 (`role: "user"`)의 `content` 배열에 여러 `text` 블록이 존재한다. 실제 사용자 프롬프트 외에 **`<system-reminder>` 태그로 감싼 추가 컨텍스트**가 주입된다:

- 사용 가능한 스킬 목록
- `claudeMd` (CLAUDE.md 내용)
- 현재 날짜 등

이는 시스템 프롬프트가 아닌 **사용자 메시지 안에** 삽입되는 방식이다.

### 5.3 Thinking 블록

`thinking.type: "adaptive"`로 설정되어 있어 모델이 필요할 때만 thinking 블록을 생성한다. 관찰된 패턴:
- 새로운 사용자 입력 직후 -> `[thinking, tool_use]` (thinking 포함)
- 도구 결과 수신 후 -> `[tool_use]` 또는 `[text]` (thinking 생략하는 경우 많음)
- `[text, tool_use]` 조합도 관찰 -- 텍스트 응답과 도구 호출을 동시에

---

## 6. 재시도 (Retry) 메커니즘

### 6.1 관찰된 재시도

| 원본 요청 | 재시도 요청 | msgs | 크기 변화 |
|-----------|-----------|------|-----------|
| T145008 (cache=[X]) | T145050 (cache=[O]) | 35 | 126.6->125.5 KB (-1.0 KB) |
| T145134 (cache=[X]) | T145230 (cache=[O]) | 41 | 135.7->135.2 KB (-0.5 KB) |

재시도 시 크기가 약간 줄어드는 것이 관찰됨. 이는:
- 재시도 시 thinking 블록이 제거/축소되었을 가능성
- 또는 assistant prefill의 차이

### 6.2 재시도 간격

- T145008 -> T145050: **42초** 간격
- T145134 -> T145230: **56초** 간격

상당한 대기 시간이 있으며, 이는 API 응답 타임아웃 또는 불만족스러운 응답 후 자동 재시도로 추정된다.

### 6.3 ClientConnectionResetError

```
aiohttp.client_exceptions.ClientConnectionResetError: Cannot write to closing transport
```

Claude Code가 응답을 기다리다 연결을 끊으면 프록시에서 에러 발생. 이는 재시도 메커니즘과 연관:
1. Claude Code가 요청을 보냄
2. 응답이 만족스럽지 않거나 타임아웃
3. 연결을 끊고 (-> proxy 에러)
4. 새 연결로 재시도

---

## 7. System Prompt 버전 변화

### 이전 버전(test_local_cc v2.1.62)과의 비교

| | test_local_cc (v2.1.62) | proxy (최신) |
|---|---|---|
| **Block 0** | `x-anthropic-billing-header: cc_version=2.1.62.3d5; cc_entrypoint=sdk-cli; cch=00000;` (cache=**false**) | `"You are Claude Code, Anthropic's official CLI for Claude."` (cache=true) |
| **Block 1** | `"You are a Claude agent, built on Anthropic's Claude Agent SDK."` (cache=true) | 전체 행동 지침 (cache=true) |
| **Block 2** | 전체 행동 지침 (cache=true) | 없음 |
| **블록 수** | 3 | 2 |

주요 변화:
- **빌링 헤더 블록 삭제**: `x-anthropic-billing-header`가 시스템 프롬프트에서 제거됨. 빌링 정보를 시스템 프롬프트가 아닌 HTTP 헤더 등 다른 경로로 전달하는 방식으로 변경된 것으로 추정.
- **브랜딩 변경**: `"Claude Agent SDK"` → `"Claude Code, Anthropic's official CLI"`. SDK 기반 에이전트에서 자체 제품 브랜딩으로 전환.
- **블록 수 축소**: 3→2. 빌링 블록 제거와 함께 첫 블록이 브랜딩 역할을 겸하게 됨.

---

## 8. 순정 vs 플러그인 환경 비교

이전 `test_local_cc` 실험 (Normal 설정)과 비교:

| 항목 | 순정 (이번) | Normal (이전) |
|------|------------|--------------|
| 도구 수 | 21 | ~40+ |
| 도구 크기 | ~60 KB | 85.9 KB |
| 시스템 프롬프트 | ~16 KB | ~50+ KB |
| 평균 요청 크기 | 106.5 KB | 138 KB |
| 내부 haiku 호출 | 0~2 | 있음 |

플러그인/설정이 추가되면 시스템 프롬프트가 3배 이상, 도구가 1.4배 이상 커진다.

---

## 9. 이전 분석과의 종합 비교

| 항목 | 소스 분석 (01-19) | 라이브 캡처 (이번) |
|------|-------------------|-------------------|
| 모델 | claude-opus-4-5-20251101 | claude-sonnet-4-6 |
| max_tokens | 16384 | 32000 |
| thinking | `{type: "enabled", budget_tokens: N}` | `{type: "adaptive"}` |
| output_config | 미확인 | `{effort: "medium"}` |
| context_management | 미확인 | `{edits: "clear_thinking_20251015", keep: "all"}` |
| 도구 수 (순정) | ~20개 (추정) | 21개 (확인) |
| 도구 크기 | ~61 KB (추정) | ~60 KB (확인) |
| 시스템 프롬프트 | ~30 KB (추정, 플러그인 포함) | 16.2~16.6 KB (순정) |
| 캐싱 | sys ephemeral + last msg ephemeral | 동일 패턴 확인 + 재시도 시 캐시 변동 발견 |
| metadata | user_id 해시 (추정) | `user_<hash>_account__session_<uuid>` 형식 확인 |
| web_search | 별도 호출 추정 | 별도 전용 요청으로 확인 (도구 1개, 시스템 프롬프트 별도) |
| haiku 내부 호출 | 도구 없음 추정 | 확인 (tools=[], thinking 없음, temperature 있음, cache 없음) |

---

## 10. 내부 호출 로직 심층 분석 (cli.js 역공학)

캡처된 Haiku 요청과 WebSearch 전용 요청이 **어떤 코드 경로에서 발생하는지** cli.js (v2.1.70) 소스를 역공학하여 분석했다.

### 10.1 Haiku 호출의 발생 경로: WebFetch 도구

Haiku 내부 요청은 **WebFetch 도구의 콘텐츠 처리 파이프라인**에서 자동 발생한다.

```
사용자 요청 → Main 모델이 WebFetch tool_use 생성
           → WebFetch.call() 실행
           → _U8(): URL fetch + HTML→Markdown 변환
           → $U8(): applyPromptToMarkdown (Haiku 호출 발생)
           → 결과를 tool_result로 Main 모델에 반환
```

**핵심 함수 `$U8` (applyPromptToMarkdown):**

```javascript
async function $U8(prompt, content, signal, isNonInteractive, isPreapproved) {
  // 콘텐츠가 MAX_MARKDOWN_LENGTH(100KB) 초과 시 잘라냄
  let truncated = content.length > Br6
    ? content.slice(0, Br6) + "\n[Content truncated...]"
    : content;

  // arA(): 프롬프트 템플릿 생성
  let userPrompt = arA(truncated, prompt, isPreapproved);

  // tZ(): 내부 API 호출 (Haiku 모델 사용)
  let result = await tZ({
    systemPrompt: jK([]),      // 빈 시스템 프롬프트 → "You are Claude Code..." 한 줄만
    userPrompt: userPrompt,
    signal: signal,
    options: {
      querySource: "web_fetch_apply",
      agents: [],
      isNonInteractiveSession: isNonInteractive,
      hasAppendSystemPrompt: false,
      mcpTools: []
    }
  });
  return result;
}
```

**`arA` 프롬프트 템플릿:**

```javascript
function arA(content, url, isPreapproved) {
  return `
Web page content:
---
${content}
---

${url}

${isPreapproved
  ? "Provide a concise response based on the content above. Include relevant details, code examples, and documentation excerpts as needed."
  : "Provide a concise response based only on the content above. In your response:\n - Enforce a strict 125-character maximum for quotes from any source document..."}
`;
}
```

**Haiku가 선택되는 이유:**
- `tZ()`는 내부적으로 "small, fast model"을 사용하는 경량 API 호출 함수
- `querySource: "web_fetch_apply"`로 태깅되어 비용 추적에서 구분됨
- 도구 스키마는 전달하지 않음 (`tools: []`) — 순수 텍스트 처리만 수행
- `thinking` 설정도 전달하지 않아 extended thinking 비활성화
- `temperature` 값을 설정하여 일관된 요약 결과를 유도
- `cache_control` 미적용 — 일회성 요약이므로 캐싱 불필요

**Haiku 호출의 조건:**
- WebFetch가 preapproved URL의 markdown 콘텐츠를 가져왔고, 크기가 `MAX_MARKDOWN_LENGTH` (100KB) 미만이면 Haiku를 **건너뛰고** 원본 markdown을 그대로 반환
- 그 외 모든 경우 (일반 URL이거나 HTML 변환 결과) Haiku를 통해 요약/처리

```javascript
// WebFetch.call() 내부
if (isPreapproved && contentType.includes("text/markdown") && content.length < Br6)
  result = content;          // Haiku 호출 없이 원본 반환
else
  result = await $U8(...);   // Haiku 호출하여 처리
```

### 10.2 WebSearch 전용 호출의 발생 경로

WebSearch 도구는 Main 대화와 **완전히 분리된 API 호출**을 만든다. 이는 Anthropic의 server-side tool인 `web_search`를 사용하기 위한 것이다.

캡처에서 관찰된 WebSearch 전용 요청의 특징:

| 항목 | Main 요청과의 차이 |
|------|-------------------|
| 시스템 프롬프트 | 별도 전용 ("You are an assistant for performing a web search...") |
| 도구 | `web_search` 1개만 (server-side tool) |
| 메시지 | "Perform a web search for..." 형태의 단일 메시지 |
| 요청 크기 | 1.1 KB (Main의 1/100) |
| 모델 | Main과 동일 (claude-sonnet-4-6) |

WebSearch의 프롬프트에는 연도 강제 지시가 포함된다:

```
IMPORTANT - Use the correct year in search queries:
  - The current month is ${currentMonth}. You MUST use this year when searching...
  - Example: If the user asks for "latest React docs", search for "React documentation"
    with the current year, NOT last year
```

### 10.3 내부 호출 모델 선택 체계

cli.js에서 확인된 내부 API 호출(`querySource`)별 모델 선택:

| querySource | 모델 | 용도 | 도구 | thinking |
|-------------|------|------|------|----------|
| (main) | sonnet/opus | 사용자 대화 | 21개 전체 | adaptive |
| `web_fetch_apply` | haiku | WebFetch 콘텐츠 처리 | 없음 | 없음 |
| `web_search_query` | sonnet | WebSearch 전용 | web_search 1개 | - |
| `insights` | haiku | 세션 분석/통계 | 없음 | 없음 |
| `memory` | haiku | 메모리 파일 선택 | 없음 | 없음 |
| `compact` | sonnet | 대화 압축 (compaction) | 없음 | - |
| `agent_creation` | sonnet | 에이전트 생성 | 없음 | disabled |

**패턴 요약:**
- **Haiku**: 비용 최적화가 중요한 반복적/일상적 처리 (요약, 메모리 선택, 통계)
- **Sonnet**: 품질이 중요한 처리 (검색, 압축, 에이전트 생성)
- **Main 모델**: 사용자가 선택한 모델 (sonnet/opus)은 메인 대화 루프에서만 사용

### 10.4 내부 호출의 API 요청 구성 차이

```
Main 요청:
  system: [cache_control] + [cache_control]     ← 2블록, 캐시 활성화
  tools:  21개 전체 스키마 (60 KB)
  thinking: {type: "adaptive"}
  output_config: {effort: "medium"}
  messages: 전체 대화 히스토리

Haiku 내부 요청 (web_fetch_apply):
  system: ["You are Claude Code..."]             ← 1블록, 57자, 캐시 없음
  tools:  []                                     ← 빈 배열
  thinking: (없음)
  output_config: (없음)
  temperature: <value>                           ← Main에는 없는 필드
  messages: [웹 콘텐츠 전체 + 프롬프트]          ← 단일 턴

WebSearch 전용 요청:
  system: [cache_control] + [cache_control]      ← 2블록, 검색 전용 지시
  tools:  [web_search]                           ← server-side tool 1개
  messages: ["Perform a web search for..."]      ← 단일 메시지
```

이 구조는 Claude Code가 **단일 모놀리식 API 호출이 아니라, 용도별로 최적화된 다중 API 호출 파이프라인**으로 작동한다는 것을 보여준다.

### 10.5 빌링 헤더 (`x-anthropic-billing-header`)의 부재

프록시 캡처의 시스템 프롬프트에서 `x-anthropic-billing-header`가 관찰되지 않았다. 그러나 이전 로컬 모델 실험(v2.1.62)에서는 system 블록 #0으로 존재했다:

```
[0] text='x-anthropic-billing-header: cc_version=2.1.62.3d5; cc_entrypoint=sdk-cli; cch=00000;'
    cache_control=None
```

**원인 분석 (cli.js v2.1.70):**

빌링 헤더는 `Y91` 함수가 클라이언트에서 직접 생성한다:

```javascript
function Y91(fingerprint) {
  if (!Tj3()) return "";  // feature flag 체크 — false면 빈 문자열
  let version = `${VERSION}.${fingerprint}`;
  let entrypoint = process.env.CLAUDE_CODE_ENTRYPOINT ?? "unknown";
  return `x-anthropic-billing-header: cc_version=${version}; cc_entrypoint=${entrypoint}; cch=00000;`;
}

function Tj3() {
  if (process.env.CLAUDE_CODE_ATTRIBUTION_HEADER === "false") return false;
  return e8("tengu_attribution_header", true);  // GrowthBook feature flag, 기본값 true
}
```

프록시 캡처에서 빠진 이유는 **`tengu_attribution_header` feature flag가 `false`**였기 때문이다:

| 환경 | .claude.json 위치 | `tengu_attribution_header` | 빌링 헤더 |
|------|-------------------|---------------------------|-----------|
| 실제 홈 (~/.claude.json) | 사용자 홈 | `true` | 있음 |
| 프록시 실험 (proxy/.claude-home/) | 격리된 HOME | `false` | 없음 |
| 로컬 모델 실험 (v2.1.62) | 사용자 홈 | `true` (기본값) | 있음 |

프록시 실험 시 `HOME`을 별도 디렉터리로 격리했기 때문에, Claude Code가 새로운 OAuth 로그인을 수행하여 **다른 계정/조직**(`accountUuid: 8490898f`, `orgUuid: 0ea4de60`)으로 인증되었다. GrowthBook은 계정/조직 단위로 feature flag를 분배하며, 이 계정에 대해 서버가 `false`를 내려준 것이다. 인증 방식(API Key vs OAuth)과는 무관하다.

**빌링 헤더 필드:**

| 필드 | 예시 값 | 생성 방식 |
|------|---------|----------|
| `cc_version` | `2.1.62.3d5` | `{패키지 버전}.{메시지 핑거프린트}` |
| `cc_entrypoint` | `sdk-cli` | `CLAUDE_CODE_ENTRYPOINT` 환경변수 |
| `cch` | `00000` | 고정값 (예약 필드) |

핑거프린트는 첫 user 메시지의 특정 위치 문자 + 버전을 SHA256 해시한 3자리이다. 빌링 헤더 블록은 `cacheScope: null`로 설정되어 **캐시에서 의도적으로 제외**된다.

> 상세 분석은 [21-billing-and-auth-management.md](21-billing-and-auth-management.md) 참조.

---

## 11. 주요 발견 요약

1. **다중 모델 파이프라인** -- Claude Code는 단일 모델 호출이 아니라, 메인 대화(sonnet/opus) + WebFetch 요약(haiku) + WebSearch(sonnet, 전용) + 메모리/통계(haiku) 등 용도별로 최적화된 다중 API 호출 파이프라인으로 동작한다.

2. **`output_config.effort: "medium"`** -- 기존 소스 분석에서 미확인된 새로운 파라미터. 모델의 응답 노력 수준을 제어.

2. **`thinking.type: "adaptive"`** -- 소스 분석에서는 `enabled` + `budget_tokens`만 확인했으나, 실제로는 `adaptive` 타입이 사용됨. 모델이 thinking 필요 여부를 자체 판단.

3. **`max_tokens: 32000`** -- 소스에서 확인한 기본값 16384와 다름. 모델이나 설정에 따라 동적 결정되는 것으로 추정.

4. **`context_management`** -- `clear_thinking_20251015` 정책과 `keep: "all"` 설정으로 사고 컨텍스트를 관리.

5. **Web search 전용 분리 호출** -- `web_search` 도구만 포함된 별도 요청이 메인 대화 전에 실행됨. 시스템 프롬프트도 완전히 다른 전용 버전 사용.

6. **재시도 시 cache_control 변동** -- 첫 시도에서 캐시 없이 전송 후 실패하면 캐시 마커를 추가하여 재시도하는 패턴 발견. 이는 기존 캐싱 분석(19번 문서)에서 예측하지 못한 동작.

7. **Haiku 내부 호출은 최소 구성** -- thinking 없음, tools 없음, cache_control 없음, 시스템 프롬프트 1줄. 웹 콘텐츠 요약 전용으로 최적화된 경량 호출.

8. **metadata에 세션 UUID 포함** -- `user_id` 필드에 계정 해시와 세션 UUID가 결합된 형태. 세션 단위 추적이 가능한 구조.

9. **멀티턴 오버헤드 71%** -- 19턴 세션에서 전송된 2 MB 중 약 71%가 System+Tools 반복 오버헤드. 캐싱이 서버 측 처리 비용은 줄이지만 네트워크 전송량은 줄이지 않음.

10. **플러그인의 비용** -- 순정 대비 플러그인 환경은 요청당 ~30 KB 추가. 20턴 세션이면 ~600 KB의 추가 전송 발생. 이전 실험에서 관찰된 38% 지연 증가는 크기 증가(30%)보다 불균형적으로 크며, 복잡한 시스템 지시가 모델의 추론 시간 자체를 늘리는 것으로 추정.

---

## 해석: 리버스 프록시의 가치

### 프로토콜 효율성

현재 Anthropic Messages API는 **stateless**이므로 매 턴마다 전체 컨텍스트를 재전송해야 한다. 이로 인해:

- 19턴 세션에서 전송된 2 MB 중 약 71%가 반복 오버헤드
- 캐싱(`cache_control: ephemeral`)이 서버 측 처리 비용은 줄이지만 네트워크 전송량은 줄이지 않음
- 세션이 길어질수록 메시지 히스토리가 선형 성장하여 효율이 더 떨어짐

---

## 부록: 파일 구조

```
analyze-cc-prompts/
├── proxy/
│   ├── proxy.py          # 리버스 프록시 서버
│   ├── analyze.py        # 덤프 → message.html 생성기
│   ├── test.sh           # 격리된 HOME으로 Claude 실행
│   ├── .env              # ANTHROPIC_API_KEY
│   ├── message.html      # 생성된 인터랙티브 뷰어 (세션 그룹, 파이차트, 비교 모드)
│   └── dumps/            # 캡처된 req/res JSON 파일
└── 20-live-api-capture-via-proxy.md  # 이 문서
```
