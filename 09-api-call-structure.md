# API 호출 메시지 구조

## 1. 전체 요청 구조

Claude Code가 Claude API에 보내는 하나의 요청은 다음과 같은 구조:

```
+------------------------------------------------------------------+
|                    API Request (POST /v1/messages)                |
+------------------------------------------------------------------+
|                                                                  |
|  model: "claude-opus-4-5-20251101"                               |
|  stream: true                                                    |
|  max_tokens: 16384                                               |
|                                                                  |
|  +------------------------------------------------------------+  |
|  |  system (content block 배열)                                |  |
|  |  +------------------------------------------------------+  |  |
|  |  | [0] 핵심 시스템 프롬프트     cache: global ephemeral   |  |  |
|  |  +------------------------------------------------------+  |  |
|  |  | [1] 도구 사용 정책 / 코딩 지침                         |  |  |
|  |  +------------------------------------------------------+  |  |
|  |  | [2] 환경 정보 (CWD, OS, 날짜)  cache: ephemeral       |  |  |
|  |  +------------------------------------------------------+  |  |
|  |  | [3] MCP 서버 지침 (조건부)                             |  |  |
|  |  +------------------------------------------------------+  |  |
|  +------------------------------------------------------------+  |
|                                                                  |
|  +------------------------------------------------------------+  |
|  |  messages (대화 메시지 배열)                                 |  |
|  |  +------------------------------------------------------+  |  |
|  |  | [0] user: <system-reminder>CLAUDE.md</system-reminder>|  |  |
|  |  +------------------------------------------------------+  |  |
|  |  | [1] user: "사용자 입력 텍스트"                          |  |  |
|  |  +------------------------------------------------------+  |  |
|  |  | [2] assistant: [thinking] + [text] + [tool_use]       |  |  |
|  |  +------------------------------------------------------+  |  |
|  |  | [3] user: [tool_result]           cache: ephemeral    |  |  |
|  |  +------------------------------------------------------+  |  |
|  |  | [4] assistant: [thinking] + [text]                    |  |  |
|  |  +------------------------------------------------------+  |  |
|  |  | [5] user: "다음 사용자 입력"       cache: ephemeral    |  |  |
|  |  +------------------------------------------------------+  |  |
|  +------------------------------------------------------------+  |
|                                                                  |
|  +------------------------------------------------------------+  |
|  |  tools (도구 스키마 배열)                                    |  |
|  |  +------------------+  +------------------+                 |  |
|  |  | Read             |  | Bash             |                 |  |
|  |  | - file_path      |  | - command        |                 |  |
|  |  | - offset, limit  |  | - timeout        |                 |  |
|  |  +------------------+  +------------------+                 |  |
|  |  +------------------+  +------------------+                 |  |
|  |  | Edit             |  | Write            |                 |  |
|  |  | - file_path      |  | - file_path      |                 |  |
|  |  | - old/new_string |  | - content        |                 |  |
|  |  +------------------+  +------------------+                 |  |
|  |  +------------------+  +------------------+                 |  |
|  |  | Glob             |  | Grep             |                 |  |
|  |  | - pattern, path  |  | - pattern, path  |                 |  |
|  |  +------------------+  +------------------+                 |  |
|  |  +------------------+  +------------------+                 |  |
|  |  | Task             |  | WebFetch         |                 |  |
|  |  | - prompt, type   |  | - url, prompt    |                 |  |
|  |  +------------------+  +------------------+                 |  |
|  |  +------------------+  +------------------+                 |  |
|  |  | WebSearch        |  | TodoWrite        |                 |  |
|  |  | - query          |  | - todos          |                 |  |
|  |  +------------------+  +------------------+                 |  |
|  |  +------------------+  +------------------+                 |  |
|  |  | AskUserQuestion  |  | NotebookEdit     |                 |  |
|  |  | - question, opts |  | - notebook_path  |                 |  |
|  |  +------------------+  +------------------+                 |  |
|  +------------------------------------------------------------+  |
|                                                                  |
|  thinking: { type: "enabled", budget_tokens: 10240 }             |
|  betas: ["interleaved-thinking-...", "prompt-caching-..."]       |
|  metadata: { user_id: "user_sk-ant-xxx_acc-xxx_sess-xxx" }       |
|                                                                  |
+------------------------------------------------------------------+
```

```json
{
  "model": "claude-opus-4-5-20251101",
  "system": [ ... ],          // 시스템 프롬프트 (content block 배열)
  "messages": [ ... ],        // 대화 메시지 배열
  "tools": [ ... ],           // 도구 스키마 배열
  "max_tokens": 16384,
  "thinking": { "type": "enabled", "budget_tokens": 10240 },
  "betas": ["interleaved-thinking-2025-05-14", "prompt-caching-2024-07-31", ...],
  "metadata": { "user_id": "user_{apiKey}_{accountUuid}_{sessionId}" },
  "stream": true
}
```

Location in cli.js: C5q async generator function (~line 4789), actual call via `j1.beta.messages.create({..._1, stream: true}, {signal: z}).withResponse()`

## 2. system 필드 (시스템 프롬프트)

system 필드는 단일 문자열이 아닌 **content block 배열**로 전달된다. RN 함수(~line 4638)가 IsY와 여러 서브 함수를 호출하여 조립한다.

```
+------------------------------------------------------------------+
|                system 필드 조립 과정                               |
+------------------------------------------------------------------+
|                                                                  |
|  RN 함수 (18개 서브 함수 호출)                                     |
|  +------------------------------------------------------------+  |
|  | IsY(H)  "You are Claude Code..."       <-- 핵심 정체성      |  |
|  | xsY(H)  출력 스타일 지침                                    |  |
|  | bsY(_)  도구 사용 가이드라인                                  |  |
|  | usY(_)  코딩 지침 (over-engineering 금지 등)                  |  |
|  | BsY()   도구 사용 포맷 규칙                                  |  |
|  | msY()   메모리/CLAUDE.md 규칙                                |  |
|  | FsY()   system-reminder 설명                                |  |
|  | gsY()   슬래시 커맨드/스킬 정보                               |  |
|  | YIA     보안 정책 (상수)                                     |  |
|  | QsY()   추가 도구 지침                                       |  |
|  | UsY()   OS/환경 정보                                        |  |
|  | psY()   에이전틱 행동 가이드라인                               |  |
|  | dsY()   사고/추론 지침                                       |  |
|  | E5q()   환경 블록 (모델명, CWD, 플랫폼, 날짜)                 |  |
|  | csY()   언어 설정                                           |  |
|  | lsY()   출력 포맷                                           |  |
|  | isY()   MCP 서버 지침 (조건부)                                |  |
|  | asY()   최종 지침                                           |  |
|  +------------------------------------------------------------+  |
|       |                                                          |
|       v                                                          |
|  C5q 최종 조립                                                    |
|  +------------------------------------------------------------+  |
|  | f76(N)         파일 컨텍스트 정보                             |  |
|  | Z76({...})     환경/코딩 지침                                |  |
|  | ...RN 결과     위 18개 서브 함수 결과                          |  |
|  | rKq            도구 검색 지침 (조건부)                         |  |
|  | v5q(mcpTools)  MCP CLI 도구 지침                             |  |
|  +------------------------------------------------------------+  |
|       |                                                          |
|       v                                                          |
|  KtY 변환 (문자열 배열 -> content block 배열)                      |
|  +------------------------------------------------------------+  |
|  | { type: "text", text: "...", cache_control: {global} }      |  |
|  | { type: "text", text: "..." }                               |  |
|  | { type: "text", text: "...", cache_control: {ephemeral} }   |  |
|  +------------------------------------------------------------+  |
|                                                                  |
+------------------------------------------------------------------+
```

조립 순서 (RN 함수):
1. IsY(H) -- 핵심 정체성 ("You are Claude Code, Anthropic's official CLI for Claude")
2. xsY(H) -- 출력 스타일 지침
3. bsY(_) -- 도구 사용 가이드라인
4. usY(_) -- 코딩 지침
5. BsY() -- 도구 사용 포맷 규칙
6. msY(H,_) -- 메모리/CLAUDE.md 관련 규칙
7. FsY() -- system-reminder 설명
8. gsY(_,X) -- 슬래시 커맨드/스킬 정보
9. YIA -- 보안 정책 상수
10. QsY(_) -- 추가 도구 지침
11. UsY() -- OS/환경 정보
12. psY() -- 에이전틱 행동 가이드라인
13. dsY() -- 사고/추론 지침
14. E5q(A,q) -- 환경 블록 (모델명, CWD, 플랫폼, 날짜)
15. csY($.language) -- 언어 설정
16. lsY(H) -- 출력 포맷
17. isY(Y) -- MCP 서버 지침 (MCP 서버 연결 시)
18. asY() -- 최종 지침

최종 조립 (C5q 내부):
```javascript
systemBlocks = [
  f76(N),           // 파일 컨텍스트 정보
  Z76({...}),       // 환경/코딩 지침
  ...systemParts,   // 위 RN 함수 결과
  rKq,              // 도구 검색 지침 (조건부)
  v5q(mcpTools)     // MCP CLI 도구 지침
].filter(Boolean);
```

KtY 함수가 이 문자열 배열을 API용 content block 배열로 변환:
```json
[
  { "type": "text", "text": "..핵심 시스템 프롬프트..", "cache_control": { "type": "ephemeral", "scope": "global" } },
  { "type": "text", "text": "..코딩 지침.." },
  { "type": "text", "text": "..환경 정보..", "cache_control": { "type": "ephemeral" } }
]
```

cache_control은 gW1() 함수가 관리. 퍼스트파티 API는 `{ type: "ephemeral", ttl: "1h" }`, 아닌 경우 `{ type: "ephemeral" }`. 글로벌 캐싱은 `scope: "global"` 추가.

## 3. messages 필드 (대화 메시지)

```
+------------------------------------------------------------------+
|              messages 필드 구조 (멀티턴 대화)                       |
+------------------------------------------------------------------+
|                                                                  |
|  [0] user     CLAUDE.md 주입 (system-reminder 래핑)              |
|  +-----------+------------------------------------------------+  |
|  | role:user | <system-reminder>                              |  |
|  |           |   Contents of CLAUDE.md:                       |  |
|  |           |   ...프로젝트별 지침...                          |  |
|  |           | </system-reminder>                             |  |
|  +-----------+------------------------------------------------+  |
|                                                                  |
|  [1] user     실제 사용자 입력                                    |
|  +-----------+------------------------------------------------+  |
|  | role:user | "src/index.ts 파일 읽어줘"                       |  |
|  +-----------+------------------------------------------------+  |
|                                                                  |
|  [2] assistant  모델 응답 (thinking + text + tool_use)           |
|  +-----------+------------------------------------------------+  |
|  | role:     | +--------------------------------------------+ |  |
|  | assistant | | type: thinking                             | |  |
|  |           | | "사용자가 파일 읽기를 요청했다..."              | |  |
|  |           | +--------------------------------------------+ |  |
|  |           | | type: text                                 | |  |
|  |           | | "파일을 읽어보겠습니다."                       | |  |
|  |           | +--------------------------------------------+ |  |
|  |           | | type: tool_use                             | |  |
|  |           | | name: "Read"                               | |  |
|  |           | | id: "toolu_abc123"                         | |  |
|  |           | | input: { file_path: "/...src/index.ts" }   | |  |
|  |           | +--------------------------------------------+ |  |
|  +-----------+------------------------------------------------+  |
|                                                                  |
|  [3] user     도구 실행 결과 (Claude Code가 자동 삽입)             |
|  +-----------+------------------------------------------------+  |
|  | role:user | +--------------------------------------------+ |  |
|  |           | | type: tool_result                          | |  |
|  |           | | tool_use_id: "toolu_abc123"                | |  |
|  |           | | content: "  1  import express from..."     | |  |
|  |           | | is_error: false                            | |  |
|  |           | +--------------------------------------------+ |  |
|  |           | +--------------------------------------------+ |  |
|  |           | | type: text  (system-reminder 주입)          | |  |
|  |           | | "<system-reminder>도구 관련 알림</...>"      | |  |
|  |           | +--------------------------------------------+ |  |
|  +-----------+------------------------------------------------+  |
|                                                                  |
|  [4] assistant  후속 응답                                        |
|  +-----------+------------------------------------------------+  |
|  | role:     | +--------------------------------------------+ |  |
|  | assistant | | type: thinking                             | |  |
|  |           | | "파일 내용을 분석하면..."                      | |  |
|  |           | +--------------------------------------------+ |  |
|  |           | | type: text                                 | |  |
|  |           | | "이 파일은 Express 서버의 진입점입니다..."     | |  |
|  |           | +--------------------------------------------+ |  |
|  +-----------+------------------------------------------------+  |
|                                                                  |
|  캐시 제어: 마지막 3개 메시지에 cache_control 자동 추가             |
|  +----------------------------------------------------------+   |
|  | [N-2] cache_control: { type: "ephemeral" }               |   |
|  | [N-1] cache_control: { type: "ephemeral" }               |   |
|  | [N]   cache_control: { type: "ephemeral" }               |   |
|  +----------------------------------------------------------+   |
|                                                                  |
+------------------------------------------------------------------+
```

### 3.1 CLAUDE.md 주입

CLAUDE.md 내용은 시스템 프롬프트가 아닌 **첫 번째 user 메시지**로 주입된다. PP1 함수(~line 3124):
```json
{ "role": "user", "content": "<system-reminder>\nCLAUDE.md 내용...\n</system-reminder>" }
```

### 3.2 메시지 유형

user 메시지:
```json
{ "role": "user", "content": "사용자가 입력한 텍스트" }
```
또는 (도구 결과 포함 시):
```json
{ "role": "user", "content": [
  { "type": "tool_result", "tool_use_id": "toolu_xxx", "content": "도구 실행 결과", "is_error": false }
] }
```

assistant 메시지:
```json
{ "role": "assistant", "content": [
  { "type": "thinking", "thinking": "내부 사고 과정..." },
  { "type": "text", "text": "사용자에게 보이는 응답" },
  { "type": "tool_use", "id": "toolu_xxx", "name": "Read", "input": { "file_path": "/path/to/file" } }
] }
```

```
+------------------------------------------------------------------+
|              메시지 전처리 파이프라인                                |
+------------------------------------------------------------------+
|                                                                  |
|  내부 메시지 배열 (raw)                                           |
|       |                                                          |
|       v                                                          |
|  [1] e$ 함수: 정규화                                              |
|  +------------------------------------------------------------+  |
|  | - progress/system/API에러 메시지 필터링                       |  |
|  | - 첨부파일(hook, 팀 메시지) -> user 메시지 변환 (qeY)         |  |
|  | - 인접 같은 role 메시지 병합                                  |  |
|  +------------------------------------------------------------+  |
|       |                                                          |
|       v                                                          |
|  [2] h5q 함수: tool_use/tool_result 쌍 보장                      |
|  +------------------------------------------------------------+  |
|  | - 모든 tool_use에 대응하는 tool_result 존재 확인               |  |
|  | - 누락 시 빈 tool_result 자동 생성                            |  |
|  +------------------------------------------------------------+  |
|       |                                                          |
|       v                                                          |
|  [3] YeY 함수: trailing thinking 제거                             |
|  +------------------------------------------------------------+  |
|  | - 마지막 assistant 메시지 끝의 thinking 블록 제거              |  |
|  +------------------------------------------------------------+  |
|       |                                                          |
|       v                                                          |
|  [4] zeY 함수: 빈 content 수정                                    |
|  +------------------------------------------------------------+  |
|  | - assistant 메시지의 빈 content 배열 수정                     |  |
|  +------------------------------------------------------------+  |
|       |                                                          |
|       v                                                          |
|  [5] qtY 함수: 캐시 제어 추가                                     |
|  +------------------------------------------------------------+  |
|  | - 마지막 3개 메시지에 cache_control: ephemeral 추가           |  |
|  +------------------------------------------------------------+  |
|       |                                                          |
|       v                                                          |
|  API 전송용 messages 배열 (최종)                                   |
|                                                                  |
+------------------------------------------------------------------+
```

### 3.3 메시지 전처리 (e$ 함수)

API 호출 전에 e$ 함수가 내부 메시지 배열을 정규화:
- progress 메시지, system 메시지, API 에러 메시지 필터링
- 인접한 같은 role 메시지 병합 (user+user -> user)
- 모든 tool_use에 대응하는 tool_result 존재 보장 (h5q 함수)
- 마지막 assistant 메시지에서 trailing thinking 블록 제거 (YeY 함수)
- 빈 assistant content 수정 (zeY 함수)
- 첨부파일(hook 결과, 팀 메시지 등)을 user 메시지로 변환 (qeY 함수)

### 3.4 캐시 제어 (qtY 함수)

마지막 3개 메시지에 cache_control 추가:
```javascript
messages.map((msg, i) => {
  if (i > messages.length - 3) {
    // cache_control: { type: "ephemeral" } 추가
  }
  return msg;
});
```

### 3.5 system-reminder 주입 시점

system-reminder 태그는 여러 곳에서 주입:
- CLAUDE.md 내용 (대화 시작 시)
- 도구 결과에 추가 컨텍스트 삽입 시
- 스킬 정보, 환경 정보 등 동적 알림

## 4. tools 필드 (도구 스키마)

각 도구는 wM6 함수로 스키마 생성:
```json
{
  "name": "Read",
  "description": "Reads a file from the local filesystem...",
  "input_schema": {
    "type": "object",
    "properties": {
      "file_path": { "type": "string", "description": "..." },
      "offset": { "type": "number", "description": "..." },
      "limit": { "type": "number", "description": "..." }
    },
    "required": ["file_path"]
  },
  "cache_control": { "type": "ephemeral", "scope": "global" }
}
```

추가 필드:
- `strict: true` -- 모델이 지원할 경우
- `input_examples: [...]` -- 베타 플래그 활성화 시
- `defer_loading: true` -- 지연 로딩 도구 (tool search 통해 활성화)

지연 로딩 도구: model이 tool_reference 블록으로 참조한 도구 + 검색 도구(Uj)만 포함

## 5. 기타 요청 파라미터

| 파라미터 | 소스 | 설명 |
|---------|------|------|
| model | sF(w.model) | 모델 ID 문자열로 해석 |
| max_tokens | HEA(w.model) | 모델별 최대값, CLAUDE_CODE_MAX_OUTPUT_TOKENS 환경변수로 제한 가능 |
| thinking | 조건부 | `{ type: "enabled", budget_tokens: N }` (N은 Qd1 함수) |
| betas | ir1(w.model) + 동적 | 베타 기능 문자열 배열 |
| metadata | ho() | `{ user_id: "user_{apiKey}_{accountUuid}_{sessionId}" }` |
| tool_choice | w.toolChoice | 보통 undefined (auto), 강제 지정 시 사용 |
| context_management | wJ7() | 컨텍스트 관리 베타 활성화 시 |
| output_config.effort | u97(w.model) | 추론 노력 수준 |
| output_config.format | w.outputFormat | 구조화된 출력 포맷 |
| temperature | CLAUDE_CODE_EXTRA_BODY 또는 fallback 경로 | 메인 요청에는 미포함, fallback 비스트리밍 시 적용 |

CLAUDE_CODE_EXTRA_BODY 환경변수로 추가 파라미터를 요청 본문에 삽입 가능.

## 6. 스트리밍 처리

```
+------------------------------------------------------------------+
|                    스트리밍 응답 처리 흐름                           |
+------------------------------------------------------------------+
|                                                                  |
|  Claude API Server                                               |
|       |                                                          |
|       | SSE (Server-Sent Events)                                 |
|       v                                                          |
|  +------------------------------------------------------------+  |
|  | message_start                                               |  |
|  | - 메시지 메타데이터, usage 정보 수신                           |  |
|  +------------------------------------------------------------+  |
|       |                                                          |
|       v                                                          |
|  +------------------------------------------------------------+  |
|  | content_block_start  (반복)                                  |  |
|  | - 블록 타입: thinking / text / tool_use                      |  |
|  +---+--------------------------------------------------------+  |
|      |                                                           |
|      v                                                           |
|  +------------------------------------------------------------+  |
|  | content_block_delta  (다수 반복)                              |  |
|  | - thinking_delta: 사고 과정 스트리밍                          |  |
|  | - text_delta: 텍스트 응답 스트리밍                            |  |
|  | - partial_json: tool_use input 점진적 수신                   |  |
|  | - signature_delta: 서명 데이터                               |  |
|  +------------------------------------------------------------+  |
|      |                                                           |
|      v                                                           |
|  +------------------------------------------------------------+  |
|  | content_block_stop                                          |  |
|  | - 블록 완료, assistant 메시지에 추가                          |  |
|  +------------------------------------------------------------+  |
|       |                                                          |
|       v  (다음 content_block_start 또는 종료)                     |
|                                                                  |
|  +------------------------------------------------------------+  |
|  | message_delta                                               |  |
|  | - stop_reason: "end_turn" | "tool_use" | "max_tokens"       |  |
|  | - usage 업데이트 (output_tokens)                             |  |
|  +------------------------------------------------------------+  |
|       |                                                          |
|       v                                                          |
|  +------------------------------------------------------------+  |
|  | message_stop                                                |  |
|  | - 메시지 종료                                               |  |
|  +------------------------------------------------------------+  |
|       |                                                          |
|       v                                                          |
|  stop_reason == "tool_use"?                                      |
|  +------+  YES: 도구 실행 -> tool_result 추가 -> 다음 API 호출   |
|  |      |  NO:  사용자에게 응답 출력 완료                          |
|  +------+                                                        |
|                                                                  |
|  실패 시 폴백:                                                    |
|  +------------------------------------------------------------+  |
|  | 스트리밍 실패 -> 비스트리밍 재시도 (max_tokens: 21,333)       |  |
|  | 30초 정체 -> 텔레메트리 로깅                                  |  |
|  +------------------------------------------------------------+  |
|                                                                  |
+------------------------------------------------------------------+
```

모든 주요 API 호출은 기본적으로 스트리밍 사용:
```javascript
await client.beta.messages.create({...body, stream: true}, {signal}).withResponse()
```

스트림 이벤트 처리:
- message_start -- 초기 메시지 메타데이터, usage 정보
- content_block_start -- content block 초기화 (tool_use, text, thinking)
- content_block_delta -- 점진적 내용 추가 (partial_json, text_delta, thinking_delta, signature_delta)
- content_block_stop -- 블록 완료, assistant 메시지 yield
- message_delta -- usage 업데이트, stop_reason 캡처
- message_stop -- 메시지 종료

스트리밍 실패 시 비스트리밍 폴백: max_tokens를 21,333으로 줄여서 재시도.
스트리밍 정체 감지: 이벤트 간 30초 이상 간격 시 텔레메트리 로깅.

## 7. 경량 내부 API 호출 (rJ 함수)

```
+------------------------------------------------------------------+
|              주요 호출 vs 경량 호출 비교                             |
+------------------------------------------------------------------+
|                                                                  |
|  주요 호출 (C5q/pM1)              경량 호출 (rJ)                   |
|  +---------------------------+   +---------------------------+   |
|  | model: opus/sonnet        |   | model: haiku              |   |
|  | system: [content blocks]  |   | system: "단순 문자열"       |   |
|  | messages: [대화 전체]      |   | messages: [user 1개]      |   |
|  | tools: [10+ 도구]         |   | tools: []                 |   |
|  | thinking: enabled         |   | thinking: 0 (비활성)      |   |
|  | cache: enabled            |   | cache: disabled           |   |
|  | stream: true              |   | stream: false             |   |
|  +---------------------------+   +---------------------------+   |
|                                                                  |
|  용도:                            용도:                           |
|  - 사용자 대화 응답               - 대화 제목 생성                  |
|  - 도구 사용 및 코드 작업          - 파일 경로 추출                  |
|  - 에이전트 작업 실행              - Bash 명령어 분류                |
|                                  - 세션 품질 분류                  |
|                                  - 권한 설명                      |
|                                                                  |
+------------------------------------------------------------------+
```

대화 제목 생성, 파일 경로 추출, bash 접두사 분석 등 내부 유틸리티는 rJ 함수로 별도 경량 호출:
```javascript
{
  model: "haiku",          // 경량 모델 사용
  system: "...",           // 단순 문자열 시스템 프롬프트
  messages: [{ role: "user", content: "..." }],  // 단일 user 메시지
  tools: [],               // 도구 없음
  thinking: 0,             // 사고 없음
  enablePromptCaching: false  // 캐싱 비활성화
}
```

## 8. 실제 호출 예시 (전체)

아래는 사용자가 "파일 읽어줘"를 입력했을 때 실제로 API에 전송되는 요청의 대략적 구조:

```json
{
  "model": "claude-opus-4-5-20251101",
  "system": [
    {
      "type": "text",
      "text": "You are Claude Code, Anthropic's official CLI for Claude.\nYou are an interactive CLI tool that helps users with software engineering tasks...\n[톤/스타일 지침]\n[전문성 지침]\n[시간 추정 금지]\n...",
      "cache_control": { "type": "ephemeral", "scope": "global" }
    },
    {
      "type": "text",
      "text": "# Tool usage policy\n...[도구 사용 정책]...\n# Code References\n...[코드 참조 형식]..."
    },
    {
      "type": "text",
      "text": "Here is useful information about the environment you are running in:\n<env>\nWorking directory: /Users/user/project\nIs directory a git repo: Yes\nPlatform: darwin\nOS Version: Darwin 25.2.0\nToday's date: 2026-02-04\n</env>\nYou are powered by the model named Opus 4.5.",
      "cache_control": { "type": "ephemeral" }
    }
  ],
  "messages": [
    {
      "role": "user",
      "content": "<system-reminder>\nContents of /Users/user/project/CLAUDE.md:\n..CLAUDE.md 전체 내용..\n</system-reminder>"
    },
    {
      "role": "user",
      "content": "src/index.ts 파일 읽어줘"
    }
  ],
  "tools": [
    {
      "name": "Read",
      "description": "Reads a file from the local filesystem...",
      "input_schema": {
        "type": "object",
        "properties": {
          "file_path": { "type": "string", "description": "The absolute path to the file to read" },
          "offset": { "type": "number", "description": "The line number to start reading from" },
          "limit": { "type": "number", "description": "The number of lines to read" }
        },
        "required": ["file_path"],
        "additionalProperties": false
      },
      "cache_control": { "type": "ephemeral", "scope": "global" }
    },
    {
      "name": "Bash",
      "description": "Executes a given bash command...",
      "input_schema": { "..." }
    },
    { "name": "Glob", "..." },
    { "name": "Grep", "..." },
    { "name": "Edit", "..." },
    { "name": "Write", "..." },
    { "name": "WebFetch", "..." },
    { "name": "WebSearch", "..." },
    { "name": "Task", "..." },
    { "name": "TodoWrite", "..." },
    { "name": "AskUserQuestion", "..." },
    { "name": "NotebookEdit", "..." }
  ],
  "max_tokens": 16384,
  "thinking": {
    "type": "enabled",
    "budget_tokens": 10240
  },
  "betas": [
    "interleaved-thinking-2025-05-14",
    "prompt-caching-2024-07-31"
  ],
  "metadata": {
    "user_id": "user_sk-ant-xxx_acc-xxx_sess-xxx"
  },
  "stream": true
}
```

두 번째 턴 (도구 사용 후):
```json
{
  "model": "claude-opus-4-5-20251101",
  "system": [ "...(동일)..." ],
  "messages": [
    { "role": "user", "content": "<system-reminder>...CLAUDE.md...</system-reminder>" },
    { "role": "user", "content": "src/index.ts 파일 읽어줘" },
    {
      "role": "assistant",
      "content": [
        { "type": "thinking", "thinking": "사용자가 파일을 읽어달라고 했다..." },
        { "type": "text", "text": "파일을 읽어보겠습니다." },
        { "type": "tool_use", "id": "toolu_abc123", "name": "Read", "input": { "file_path": "/Users/user/project/src/index.ts" } }
      ]
    },
    {
      "role": "user",
      "content": [
        { "type": "tool_result", "tool_use_id": "toolu_abc123", "content": "     1\timport express from 'express';\n     2\t..." }
      ]
    }
  ],
  "tools": [ "...(동일)..." ],
  "max_tokens": 16384,
  "thinking": { "type": "enabled", "budget_tokens": 10240 },
  "stream": true
}
```

## 9. Anthropic 클라이언트 생성 (cC 함수)

SDK 클라이언트 생성 흐름:
1. `cC({maxRetries: 0, model: w.model})` -- Anthropic SDK 클라이언트 생성
2. `_O6`로 래핑 -- 재시도/모델 폴백 제너레이터 추가
3. fetchOverride 지원 -- 커스텀 HTTP 구현 가능
4. `sF` 함수 -- 모델 문자열을 실제 모델 ID로 변환 (예: "sonnet" -> "claude-sonnet-4-20250514")
