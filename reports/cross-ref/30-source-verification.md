# 유출 TypeScript 소스 교차 검증 분석

**분석 대상 소스**: 유출 TypeScript 소스 (원본 기준, 2026-03-20 기준)
**대조 대상**: 기존 리포트 01-29 (minified cli.js v2.1.29-v2.1.80 분석)
**분석 일자**: 2026-04-02

---

## 1. 개요

기존 리포트는 minified JavaScript(`cli.js`)를 역공학해 작성됐다. 난독화 변수명 추적과 패턴 매칭으로
도출한 결론이므로 오류 가능성이 내재한다. 유출된 TypeScript 원본 소스와 대조해 세 가지를 목적으로
한다:

1. **확인**: 기존 분석이 실제 구현과 일치하는지
2. **수정**: 잘못됐거나 불완전한 내용 교정
3. **신규**: minified 분석으로는 발견하기 어려운 구현 추가 발굴

**방법론**: 기존 리포트에서 검증 가능한 클레임(함수명, 상수값, 로직 조건)을 추출하고,
유출 소스의 해당 파일을 직접 읽어 대조했다.

---

## 2. 확인된 발견

기존 리포트의 분석이 소스와 일치하는 항목이다.

| 기존 리포트 | 클레임 | 소스 파일 | 소스 내용 |
|:--|:--|:--|:--|
| 25 (progressive disclosure) | `isMcp: true` 도구는 항상 defer | `prompt.ts:68` | `if (tool.isMcp === true) return true` |
| 25 | ToolSearch 자신은 절대 defer 안 됨 | `prompt.ts:71` | `if (tool.name === TOOL_SEARCH_TOOL_NAME) return false` |
| 25 | `shouldDefer: true` 도구는 defer | `prompt.ts:107` | `return tool.shouldDefer === true` |
| 25 | `tengu_glacier_2xr` 플래그 확인 | `prompt.ts:38` | `getFeatureValue_CACHED_MAY_BE_STALE('tengu_glacier_2xr', false)` |
| 18 (autocompaction) | autocompact buffer = 13,000 토큰 | `autoCompact.ts:62` | `AUTOCOMPACT_BUFFER_TOKENS = 13_000` |
| 18 | warning threshold buffer = 20,000 | `autoCompact.ts:63` | `WARNING_THRESHOLD_BUFFER_TOKENS = 20_000` |
| 18 | output buffer = 20,000 | `autoCompact.ts:29` | `MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20_000` |
| 18 | `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` 환경변수 | `autoCompact.ts:79` | `process.env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` |
| 17 (memory layers) | `MEMORY.md` entrypoint | `memdir.ts:34` | `ENTRYPOINT_NAME = 'MEMORY.md'` |
| 17 | 200라인 이상 truncate | `memdir.ts:35` | `MAX_ENTRYPOINT_LINES = 200` |
| 19 (caching) | `context-management-2025-06-27` | `betas.ts:7` | `CONTEXT_MANAGEMENT_BETA_HEADER = 'context-management-2025-06-27'` |
| 23 (hidden API) | `claude-code-20250219` beta | `betas.ts:3` | `CLAUDE_CODE_20250219_BETA_HEADER = 'claude-code-20250219'` |
| 23 | `prompt-caching-scope-2026-01-05` | `betas.ts:17` | `PROMPT_CACHING_SCOPE_BETA_HEADER = 'prompt-caching-scope-2026-01-05'` |
| 15 (feature flags) | `tengu_` 접두어 체계 | 전체 소스 | GrowthBook 연동, 다수 파일에서 사용 확인 |
| 15 | `tengu_passport_quail` 플래그 | `paths.ts` | `isExtractModeActive()` 에서 사용 |
| 22 (oauth) | user:inference, user:profile, user:sessions:claude_code, user:mcp_servers scope | `oauth.ts:45-51` | `CLAUDE_AI_OAUTH_SCOPES` 에 포함 |
| 22 | `oauth-2025-04-20` beta header | `oauth.ts:36` | `OAUTH_BETA_HEADER = 'oauth-2025-04-20'` |

---

## 3. 수정 사항

기존 분석이 부정확하거나 불완전한 항목이다.

### 3.1 OAuth scope 수 (보고서 22)

**기존 클레임**: Claude.ai OAuth scope 4개
```
user:profile, user:inference, user:sessions:claude_code, user:mcp_servers
```

**실제 소스** (`oauth.ts:45-51`):
```typescript
export const CLAUDE_AI_OAUTH_SCOPES = [
  'user:profile',
  'user:inference',
  'user:sessions:claude_code',
  'user:mcp_servers',
  'user:file_upload',      // 기존 리포트에서 누락
] as const
```

5번째 scope `user:file_upload`가 존재한다. 추가로 Console 전용 scope `org:create_api_key`도
별도 존재하며 (`CONSOLE_OAUTH_SCOPES`), 로그인 시 전체 scope를 `ALL_OAUTH_SCOPES`로 한 번에
요청한다.

### 3.2 isDeferredTool 조건 (보고서 25)

**기존 클레임**: 3단계 판정 (`tengu_defer_all_bn4` 플래그 포함)
```javascript
// 보고서 25의 분석 (v2.1.70 cli.js 기반)
if (A.isMcp === true) return true;          // 1) MCP
if (A.name === zT) return false;            // 2) ToolSearch
if (e8("tengu_defer_all_bn4", true)) return true;  // 3) 전체 defer 플래그
return A.shouldDefer === true;              // 4) 개별 shouldDefer
```

**실제 소스** (`prompt.ts:62-108`):
```typescript
export function isDeferredTool(tool: Tool): boolean {
  if (tool.alwaysLoad === true) return false          // [신규] 명시적 opt-out
  if (tool.isMcp === true) return true               // MCP 항상 defer
  if (tool.name === TOOL_SEARCH_TOOL_NAME) return false  // ToolSearch 제외
  if (feature('FORK_SUBAGENT') && tool.name === AGENT_TOOL_NAME) {
    if (isForkSubagentEnabled()) return false        // [신규] fork 실험 예외
  }
  if ((feature('KAIROS') || feature('KAIROS_BRIEF')) && ...) return false  // [신규] Brief 예외
  if (feature('KAIROS') && ... && isReplBridgeActive()) return false       // [신규] SendUserFile 예외
  return tool.shouldDefer === true
}
```

`tengu_defer_all_bn4`는 소스에 없다. v2.1.70 minified 버전에서 실험 중이던 서버사이드 롤아웃
플래그였으며, 소스 레벨에서는 `alwaysLoad` 필드로 개별 도구가 opt-out하는 방식으로 구현됐다.

### 3.3 searchHint A/B 실험 종료 (보고서 25)

**기존 분석**: v2.1.70에서 searchHint를 deferred 목록에 표시하는 `tengu_tst_hint_m7r` 플래그
발견, 성능 개선 효과가 있을 것으로 추정.

**실제 소스** (`prompt.ts:111-117`):
```typescript
/**
 * Format one deferred-tool line for the <available-deferred-tools> user
 * message. Search hints (tool.searchHint) are not rendered —
 * the hints A/B (exp_xenhnnmn0smrx4, stopped Mar 21) showed no benefit.
 */
export function formatDeferredToolLine(tool: Tool): string {
  return tool.name  // searchHint 없이 이름만 반환
}
```

실험(`exp_xenhnnmn0smrx4`)이 2026-03-21 종료됐고, 결과가 효과 없음으로 나왔다.
현재 searchHint는 표시되지 않는다.

### 3.4 Autocompaction threshold 계산 (보고서 18)

**기존 클레임**: `Effective window = Context - output_buffer (20K)`, 이후 `autocompact = Effective - 13K`

**실제 소스** (`autoCompact.ts:33-91`):
```typescript
export function getEffectiveContextWindowSize(model: string): number {
  // reservedTokens = min(max_output_for_model, 20_000)
  const reservedTokensForSummary = Math.min(
    getMaxOutputTokensForModel(model),
    MAX_OUTPUT_TOKENS_FOR_SUMMARY,  // 20_000
  )
  let contextWindow = getContextWindowForModel(model, getSdkBetas())

  // [신규] 환경변수로 context window 상한 설정 가능
  const autoCompactWindow = process.env.CLAUDE_CODE_AUTO_COMPACT_WINDOW
  if (autoCompactWindow) {
    contextWindow = Math.min(contextWindow, parseInt(autoCompactWindow, 10))
  }
  return contextWindow - reservedTokensForSummary
}

export function getAutoCompactThreshold(model: string): number {
  const effectiveContextWindow = getEffectiveContextWindowSize(model)
  return effectiveContextWindow - AUTOCOMPACT_BUFFER_TOKENS  // -13_000
}
```

계산 구조는 일치. 추가로 `CLAUDE_CODE_AUTO_COMPACT_WINDOW` 환경변수로 컨텍스트 윈도우
상한을 강제할 수 있다.

---

## 4. 신규 발견

기존 리포트에 없는 구현이다.

### 4.1 Beta header 전체 목록 (`betas.ts`)

기존 리포트에서 확인된 것 외에 추가된 beta header들:

```typescript
// 기존 리포트에서 미확인이었던 것들
EFFORT_BETA_HEADER = 'effort-2025-11-24'
TASK_BUDGETS_BETA_HEADER = 'task-budgets-2026-03-13'
FAST_MODE_BETA_HEADER = 'fast-mode-2026-02-01'
REDACT_THINKING_BETA_HEADER = 'redact-thinking-2026-02-12'
TOKEN_EFFICIENT_TOOLS_BETA_HEADER = 'token-efficient-tools-2026-03-28'
ADVISOR_BETA_HEADER = 'advisor-tool-2026-03-01'
INTERLEAVED_THINKING_BETA_HEADER = 'interleaved-thinking-2025-05-14'

// Bun 피처 플래그에 따라 조건부 활성화
SUMMARIZE_CONNECTOR_TEXT_BETA_HEADER = 'summarize-connector-text-2026-03-13'  // feature('CONNECTOR_TEXT')
AFK_MODE_BETA_HEADER = 'afk-mode-2026-01-31'                                  // feature('TRANSCRIPT_CLASSIFIER')
CLI_INTERNAL_BETA_HEADER = 'cli-internal-2026-02-09'                          // USER_TYPE === 'ant'

// Tool Search beta (provider별 분리)
TOOL_SEARCH_BETA_HEADER_1P = 'advanced-tool-use-2025-11-20'  // Claude API, Foundry
TOOL_SEARCH_BETA_HEADER_3P = 'tool-search-tool-2025-10-19'  // Vertex AI, Bedrock
```

Bedrock은 일부 beta header를 HTTP 헤더가 아닌 `extraBodyParams`로 보내야 한다
(`BEDROCK_EXTRA_PARAMS_HEADERS`).

### 4.2 Autocompaction circuit breaker (`autoCompact.ts:62-70`)

연속 실패 시 자동으로 compaction을 중단하는 circuit breaker가 있다:

```typescript
const MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3

// 주석 (코드 내 BQ 내부 메모):
// BQ 2026-03-10: 1,279 sessions had 50+ consecutive failures (up to 3,272)
// in a single session, wasting ~250K API calls/day globally.
```

실패가 3회 연속 누적되면 해당 세션에서 autocompaction을 더 이상 시도하지 않는다.
`AutoCompactTrackingState.consecutiveFailures`로 상태가 추적되며, 성공 시 0으로 리셋된다.

### 4.3 Session Memory Compaction 우선 전략 (`autoCompact.ts:287-309`)

`autoCompactIfNeeded()` 내에서 기존 `compactConversation()` 전에 더 저비용인
`trySessionMemoryCompaction()`을 먼저 시도한다:

```typescript
// EXPERIMENT: Try session memory compaction first
const sessionMemoryResult = await trySessionMemoryCompaction(
  messages,
  toolUseContext.agentId,
  recompactionInfo.autoCompactThreshold,
)
if (sessionMemoryResult) {
  // 성공 시 전통적 compaction 생략
  return { wasCompacted: true, compactionResult: sessionMemoryResult }
}
// 실패 시 전통적 compactConversation 호출
```

**전략 우선순위** (소스 기준):
1. Session Memory Compaction (저비용, 빠름)
2. 전통적 compactConversation (느리지만 확실)
3. Reactive Compact (ant-only, `REACTIVE_COMPACT` 피처, `tengu_cobalt_raccoon` 플래그)

기존 보고서 18의 "4단계 전략"은 소스보다 세분화된 추정이었다.

### 4.4 MEMORY.md byte 한도 (`memdir.ts:38`)

기존 리포트 17은 200라인 제한만 언급했으나 byte 한도도 존재한다:

```typescript
export const MAX_ENTRYPOINT_LINES = 200
export const MAX_ENTRYPOINT_BYTES = 25_000  // 25KB
// 주석: ~125 chars/line at 200 lines. At p97 today;
// catches long-line indexes that slip past the line cap
// (p100 observed: 197KB under 200 lines).
```

두 한도 중 먼저 초과된 쪽에서 truncate하며, 경고 메시지를 MEMORY.md 내용에 추가한다.
설계 이유: 200라인 이내이면서 항목당 라인이 매우 길 경우 197KB까지 달할 수 있었다.

### 4.5 Bun 컴파일타임 feature flags (`bun:bundle`)

소스 전반에서 `import { feature } from 'bun:bundle'`을 통해 컴파일타임 dead code elimination을
한다. 이 플래그들은 서버사이드 GrowthBook 플래그(`tengu_*`)와 다른 차원의 제어다:

```typescript
feature('FORK_SUBAGENT')         // fork subagent 실험
feature('KAIROS')                // Assistant mode (long-lived sessions)
feature('KAIROS_BRIEF')          // Brief tool만 활성화
feature('EXTRACT_MEMORIES')      // 백그라운드 memory extraction
feature('REACTIVE_COMPACT')      // Reactive compaction (ant-only)
feature('PROMPT_CACHE_BREAK_DETECTION')  // 캐시 break 감지
feature('CONNECTOR_TEXT')        // Connector text summarization
feature('TRANSCRIPT_CLASSIFIER') // AFK mode
feature('NATIVE_CLIENT_ATTESTATION')  // 클라이언트 증명
feature('TOKEN_EFFICIENT_TOOLS') // 토큰 효율 도구
feature('CONTEXT_COLLAPSE')      // Context collapse 시스템
feature('TEAMMEM')               // Team memory
```

외부 빌드에서는 이 플래그들의 코드가 번들에서 제거된다. minified cli.js에서 일부 코드가
보이지 않는 이유다.

### 4.6 MCP alwaysLoad opt-out (`prompt.ts:65`)

MCP 도구라도 `_meta['anthropic/alwaysLoad'] = true`를 설정하면 deferred에서 제외된다:

```typescript
// Explicit opt-out via _meta['anthropic/alwaysLoad'] — tool appears in the
// initial prompt with full schema. Checked first so MCP tools can opt out.
if (tool.alwaysLoad === true) return false
```

MCP 서버가 특정 도구를 항상 eager로 포함하도록 선택할 수 있다.

### 4.7 OAuth 추가 발견 (`oauth.ts`)

1. **Console OAuth scope**: `org:create_api_key` (API key 생성용, claude.ai 구독 scope와 별도)
2. **OAuth CLIENT_ID**: prod = `9d1c250a-e61b-44d9-88ed-5944d1962f5e`
3. **MCP OAuth**: `MCP_CLIENT_METADATA_URL = 'https://claude.ai/oauth/claude-code-client-metadata'`
   SEP-991(CIMD) 지원 — Dynamic Client Registration 대신 사용
4. **FedStart 지원**: `CLAUDE_CODE_CUSTOM_OAUTH_URL` 환경변수로 FedStart/PubSec 배포 지원
   (허용 URL 화이트리스트: `claude.fedstart.com` 등)
5. **Xcode 통합**: `CLAUDE_CODE_OAUTH_CLIENT_ID` 환경변수로 CLIENT_ID 오버라이드 가능

### 4.8 Memory 추가 tengu 플래그 (`memdir.ts`)

```typescript
'tengu_coral_fern'   // "Searching past context" 섹션 활성화
'tengu_moth_copse'   // skipIndex 모드 (MEMORY.md 인덱스 없는 단순 저장)
'tengu_herring_clock' // team memory 코호트 추적
'tengu_memdir_loaded' // analytics 이벤트 (파일/디렉토리 수 로깅)
```

### 4.9 KAIROS mode — 장기 세션 메모리 (`memdir.ts:327-370`)

`feature('KAIROS')` + 세션이 활성 상태면 메모리 시스템이 다르게 동작한다:

```typescript
// 일반 모드: MEMORY.md를 인덱스로 직접 편집
// KAIROS 모드: 오늘 날짜 로그 파일에 append-only 기록
// ~/.claude/projects/<slug>/memory/logs/YYYY/MM/YYYY-MM-DD.md
```

Nightly `/dream` 스킬이 로그를 `MEMORY.md`와 topic 파일로 distill한다.
장기 실행 세션(Assistant mode)에서 MEMORY.md 동시 편집 충돌을 방지하기 위한 설계.

---

## 5. 미확인 항목

소스에서 대응하는 구현을 찾지 못한 난독화 함수들이다.
버전 차이(소스 vs v2.1.70 cli.js) 때문일 가능성이 높다.

| 보고서 | 난독화명 | 클레임 | 상태 |
|:--|:--|:--|:--|
| 18 | `w04()`, `dwY()`, `Wz6()`, `Uf6()` | autocompaction 함수 체인 | 소스에서 함수명 다름, 구조는 일치 |
| 17 | `dm9 = 5` | @import 최대 재귀 깊이 | 소스의 CLAUDE.md 로더에서 확인 필요 |
| 17 | `Pl = 40000` | 대용량 파일 경고 임계값 | MAX_ENTRYPOINT_BYTES(25K)와 다른 상수일 수 있음 |
| 19 | `zNz()`, `YNz()` | cache breakpoint 삽입 함수 | 소스의 `promptCacheBreakDetection.ts` 대응 |

---

## 6. 분석 소스

| 소스 파일 | 관련 보고서 | 핵심 확인 내용 |
|:--|:--|:--|
| `src/tools/ToolSearchTool/prompt.ts` | 25 | isDeferredTool 전체 로직 |
| `src/constants/betas.ts` | 19, 23 | beta header 18종 전체 목록 |
| `src/constants/oauth.ts` | 22 | OAuth scope 5종, CLIENT_ID, FedStart |
| `src/memdir/memdir.ts` | 17 | MEMORY.md 상수, KAIROS 모드, byte 한도 |
| `src/services/compact/autoCompact.ts` | 18 | 상수값, circuit breaker, session memory 우선 전략 |
