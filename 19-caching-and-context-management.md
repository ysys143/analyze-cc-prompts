# Claude Code 캐싱 및 Context Management 분석 (v2.1.70)

## 개요

Claude Code는 Anthropic API의 prompt caching을 적극 활용하여 비용과 latency를 줄인다. 동시에 compaction 시 캐시 무효화를 최소화하는 전략을 사용한다. 이 문서는 캐싱 메커니즘, context_management API, 그리고 이 둘의 상호작용을 분석한다.

## 1. Prompt Caching 기본 구조

### 1.1 Claude Code가 endpoint에 보내는 캐시 구조

Claude Code는 매 턴마다 전체 메시지 배열을 API endpoint에 보낸다. 이때 **마지막 메시지의 마지막 콘텐츠 블록**에 `cache_control` 마커를 삽입하여, 해당 지점까지의 prefix를 캐시 단위로 만든다.

```
[시스템 프롬프트(global cache)] [msg1] [msg2] ... [msgN-1] [msgN ← cache_control]
         ↑ wNz()로 별도 캐싱                                      ↑ zNz()로 삽입
```

API에는 Automatic(API가 breakpoint 결정)과 Explicit(개발자가 블록별 마커 삽입) 두 가지 캐싱 모드가 있다. Claude Code는 **Explicit 모드**를 사용하며, API가 허용하는 최대 4개 breakpoint 중 **1개만** 사용한다.

> **설계 의도**: 대화형 CLI에서 메시지는 항상 끝에 추가된다. 마지막 메시지 1개만 마킹하면 `msg1`부터 `msgN`까지의 전체 prefix가 자동으로 캐시 단위가 된다. 다음 턴에서 `msgN+1`이 추가되면 `msg1~msgN`까지는 기존 캐시에서 읽히고, `msgN+1`만 새로 처리된다. Automatic 모드는 어떤 prefix가 캐시되는지 예측할 수 없지만, Explicit 1개로 동일한 효과를 달성하면서 캐시 히트 여부를 결정론적으로 예측할 수 있다.

실제 API 응답에서 캐시 효과를 확인할 수 있다:

```json
{
  "input_tokens": 1234,              // 캐시 미적중 입력 (새 메시지 부분)
  "cache_creation_input_tokens": 0,   // 이번에 캐시에 쓴 토큰
  "cache_read_input_tokens": 50000,   // 캐시에서 읽은 토큰 (기존 prefix)
  "output_tokens": 500
}
```

총 입력 = `input_tokens + cache_creation + cache_read`

#### Claude Code가 의존하는 API 스펙 제약 조건

Claude Code의 캐싱 전략은 다음 API 스펙 위에서 동작한다. 이 제약 조건들은 Claude Code의 구현 선택을 이해하는 데 필요한 배경이다:

| API 스펙 | 값 | Claude Code에서의 의미 |
|----------|-----|----------------------|
| 최대 explicit breakpoint | 4개 | 1개만 사용 — 나머지 3개는 불필요 (prefix가 순차 성장) |
| Lookback window | breakpoint 이전 20블록 | 단일 메시지 블록이 20개 넘는 경우 거의 없어 영향 없음 |
| 최소 캐시 토큰 | Opus 4096, Sonnet 4.6/Haiku 2048, Sonnet 4/4.5 1024 | 시스템 프롬프트만 ~30K이므로 항상 초과 |
| Cache write 비용 | 기본 input의 1.25x | 1회 write 후 이후 모든 턴에서 0.1x read로 회수 |
| Cache read 비용 | 기본 input의 0.1x (90% 할인) | 10턴 세션에서 ~79% 비용 절감의 근거 |
| 기본 TTL | 5분 | Claude Code는 조건부로 1시간 TTL을 사용 (1.3절 참조) |
| Cache 무효화 트리거 | `tool_choice` 변경, thinking params 변경, 시스템 프롬프트 변경, 메시지 중간 삽입/삭제 | CLAUDE.md 수정, MCP 도구 변경, thinking budget 조정 시 전면 무효화 가능 |
| Thinking 블록 | explicit cache_control 부여 불가 | Claude Code의 thinking 제외 로직(1.2절)이 API 제약과 일치 |
| Workspace isolation | workspace별 캐시 격리 (2026.02.05~) | 팀 내 다른 개발자가 캐시를 밀어내지 않음. global scope 캐시는 공유 가능 |

### 1.2 Claude Code의 Cache Breakpoint 전략

메시지 정규화 함수 `zNz()`에서 cache_control을 삽입:

```javascript
function zNz(messages, enableCaching, querySource, enableCacheEditing,
             cacheEditBlock, pinnedEdits, skipCacheWrite) {

  // skipCacheWrite면 마지막에서 두 번째, 아니면 마지막 메시지에 cache_control
  let cacheTargetIdx = skipCacheWrite ? messages.length - 2 : messages.length - 1;

  return messages.map((msg, idx) => {
    let isTarget = (idx === cacheTargetIdx);
    if (msg.type === "user") return formatUserMessage(msg, isTarget, enableCaching, querySource);
    return formatAssistantMessage(msg, isTarget, enableCaching, querySource);
  });
}
```

> **설계 의도**: `skipCacheWrite`가 `true`인 경우(compact 호출 시)에는 마지막에서 두 번째 메시지에 breakpoint를 둔다. compact 결과는 일시적이므로 캐시에 쓰면 다음 일반 턴에서 prefix가 달라져 miss가 발생한다. "캐시 오염 방지"를 위해 compact 호출만 예외 처리한다.

#### User 메시지 (`sTz`)

```javascript
function sTz(msg, isCacheTarget, enableCaching, querySource) {
  if (isCacheTarget && enableCaching) {
    // 마지막 콘텐츠 블록에 cache_control 부여
    return {
      role: "user",
      content: msg.content.map((block, i) => ({
        ...block,
        ...(i === msg.content.length - 1 ? { cache_control: Fa6({ querySource }) } : {})
      }))
    };
  }
  return { role: "user", content: msg.content };
}
```

#### Assistant 메시지 (`tTz`)

```javascript
function tTz(msg, isCacheTarget, enableCaching, querySource) {
  if (isCacheTarget && enableCaching) {
    return {
      role: "assistant",
      content: msg.content.map((block, i) => ({
        ...block,
        // 마지막 블록 + thinking/redacted_thinking이 아닌 경우만
        ...(i === msg.content.length - 1
            && block.type !== "thinking"
            && block.type !== "redacted_thinking"
            ? { cache_control: Fa6({ querySource }) }
            : {})
      }))
    };
  }
  return { role: "assistant", content: msg.content };
}
```

**핵심: Thinking 블록에는 절대 `cache_control`을 붙이지 않는다.**

> **설계 의도**: `tTz()`가 thinking/redacted_thinking을 명시적으로 제외하는 이유는 두 가지다. 첫째, API 스펙상 thinking 블록에는 explicit `cache_control`을 부여할 수 없다. 둘째, thinking 블록은 크고(10-50K 토큰) 서버가 다음 턴에서 수정/제거할 수 있어, 만약 breakpoint가 thinking 뒤에 있으면 prefix가 불안정해진다. Claude Code는 thinking 이전의 text/tool_use 블록을 마지막으로 찾아 cache_control을 부여함으로써 안정적인 prefix를 보장한다.

#### tool_result에 cache_reference 부여

`zNz()` 내부에서 cache breakpoint 이전의 모든 `tool_result`에 `cache_reference`를 자동 부여한다:

```javascript
// YNz - tool_result 타입 체크
function YNz(block) {
  return block !== null
    && typeof block === "object"
    && "type" in block
    && block.type === "tool_result"
    && "tool_use_id" in block;
}

// zNz() 내부 - cache breakpoint 이전의 tool_result에 cache_reference 부여
// 1. 먼저 cache_control이 붙은 마지막 메시지 인덱스(J)를 찾음
let J = -1;
for (let M = 0; M < O.length; M++) {
  let D = O[M];
  if (Array.isArray(D.content)) {
    for (let X of D.content)
      if (X && typeof X === "object" && "cache_control" in X) J = M;
  }
}

// 2. breakpoint 이전의 모든 user 메시지에서 tool_result를 찾아 cache_reference 추가
if (J >= 0)
  for (let M = 0; M < J; M++) {
    let D = O[M];
    if (D.role !== "user" || !Array.isArray(D.content)) continue;
    for (let P = 0; P < D.content.length; P++) {
      let W = D.content[P];
      if (W && YNz(W)) {
        D.content[P] = Object.assign({}, W, { cache_reference: W.tool_use_id });
      }
    }
  }
```

> **설계 의도**: `cache_reference`는 서버 캐시에서 특정 콘텐츠를 식별하는 키다. tool_result에 `tool_use_id`를 `cache_reference`로 설정하면, 나중에 `cache_edits`를 통해 **특정 tool_result만 서버 캐시에서 제거**할 수 있다. 전체 캐시를 무효화하지 않고 "파일 읽기 결과가 오래됨 → 해당 tool_result만 evict" 같은 정밀한 캐시 관리가 가능해진다.

### 1.3 Fa6 - Cache Control 객체 생성

`Fa6()`는 `cache_control` 객체를 생성한다. 단순히 `{type: "ephemeral"}`만 반환하는 것이 아니라, querySource와 scope에 따라 TTL과 스코프를 조건부로 추가한다:

```javascript
function Fa6({ scope, querySource } = {}) {
  return {
    type: "ephemeral",
    ...(oTz(querySource) ? { ttl: "1h" } : {}),      // 조건부 1h TTL
    ...(scope === "global" ? { scope: scope } : {})    // 글로벌 스코프
  };
}
```

#### `oTz()` - 1시간 TTL 조건 판단

```javascript
function oTz(querySource) {
  // Bedrock에서 명시적으로 1h 캐싱을 활성화한 경우
  if (D7() === "bedrock" && _1(process.env.ENABLE_PROMPT_CACHING_1H_BEDROCK))
    return true;

  // 프리미엄 사용자이면서 overage 상태가 아닌 경우만
  if (!(eA() && !ef.isUsingOverage)) return false;

  // allowlist 기반 querySource 매칭
  let allowlist = WB1();
  if (allowlist === null) {
    allowlist = e8("tengu_prompt_cache_1h_config", {}).allowlist ?? [];
    ZB1(allowlist);  // 캐시에 저장
  }

  return querySource !== undefined
    && allowlist.some(pattern =>
      pattern.endsWith("*")
        ? querySource.startsWith(pattern.slice(0, -1))
        : querySource === pattern
    );
}
```

> **설계 의도**: 1시간 TTL은 cache write 비용이 2배이지만, 프리미엄 사용자가 5분 이상 idle 후 재접속해도 캐시가 유지된다. 일반 사용자의 5분 TTL에서는 화장실 다녀오면 캐시 miss가 발생하지만, 1h TTL에서는 그대로 cache hit. **비용 2x이지만 재접속 latency 제거 + 사용자 경험 향상**이라는 트레이드오프. Overage 상태(사용량 초과)에서는 비용 절감을 위해 1h TTL을 비활성화한다.

### 1.4 시스템 프롬프트 캐싱 (`wNz`)

시스템 프롬프트는 별도의 캐싱 함수를 통해 처리된다:

```javascript
function wNz(systemPrompt, enableCaching, options) {
  return Mo8(systemPrompt, {
    skipGlobalCacheForSystemPrompt: options?.skipGlobalCacheForSystemPrompt
  }).map((block) => ({
    type: "text",
    text: block.text,
    ...(enableCaching && block.cacheScope !== null
      ? { cache_control: Fa6({ scope: block.cacheScope, querySource: options?.querySource }) }
      : {})
  }));
}
```

**`Mo8()`**은 시스템 프롬프트를 여러 블록으로 분할하며, 각 블록에 `cacheScope`를 부여한다:
- `cacheScope: "global"` → 조직/워크스페이스 전체에서 공유 가능한 캐시
- `cacheScope: null` → 캐시하지 않음

> **설계 의도**: 시스템 프롬프트는 세션 간, 심지어 동일 조직의 다른 사용자 세션에서도 동일할 수 있다. `global` scope로 캐시하면 조직 내 첫 사용자가 cache write를 하고, 이후 모든 사용자가 cache read(0.1x)로 시스템 프롬프트를 재사용한다. **조직 규모가 클수록 비용 절감 효과가 기하급수적**으로 증가한다.

### 1.5 모델별 캐시 제어 (`okq`)

```javascript
function okq(model) {
  // 전체 비활성화
  if (_1(process.env.DISABLE_PROMPT_CACHING)) return false;

  // Haiku만 비활성화
  if (_1(process.env.DISABLE_PROMPT_CACHING_HAIKU)) {
    if (model === yj()) return false;  // yj() = Haiku 모델 ID
  }

  // Sonnet만 비활성화
  if (_1(process.env.DISABLE_PROMPT_CACHING_SONNET)) {
    if (model === Ef()) return false;  // Ef() = Sonnet 모델 ID
  }

  // Opus만 비활성화
  if (_1(process.env.DISABLE_PROMPT_CACHING_OPUS)) {
    if (model === YV()) return false;  // YV() = Opus 모델 ID
  }

  return true;
}
```

호출 위치:
```javascript
// API 요청 빌더에서
let enableCaching = options.enablePromptCaching ?? okq(model);
```

> **설계 의도**: 디버깅이나 벤치마크 시 특정 모델의 캐시만 선택적으로 비활성화할 수 있다. 실무 시나리오: Haiku는 토큰 단가가 매우 낮아($0.25/1M input) cache write 비용(1.25x = $0.3125)이 cache read 절감($0.025)보다 상대적으로 커서, 짧은 세션에서는 캐시가 오히려 비용 증가를 유발할 수 있다. `DISABLE_PROMPT_CACHING_HAIKU=1`로 이를 방지 가능.

## 2. `context_management` API

### 2.1 두 가지 Beta

Claude Code 환경에서 관련되는 두 가지 beta가 있다:

| Beta | 코드명 | 용도 |
|------|--------|------|
| `context-management-2025-06-27` | `mq1` | thinking 관리, cache editing |
| `compact-2026-01-12` | (문서에만 존재) | server-side compaction |

### 2.2 Claude Code가 사용하는 `context_management`

```javascript
// GoA() - context_management 빌더
function GoA({ hasThinking }) {
  let edits = [];
  if (hasThinking && featureFlag("tengu_marble_anvil"))
    edits.push({ type: "clear_thinking_20251015", keep: "all" });
  return edits.length > 0 ? { edits } : undefined;
}
```

API 요청에 포함:
```javascript
{
  model: "...",
  messages: [...],
  // context_management는 beta 헤더 포함 시에만 전송
  ...(C6 && isBeta && betas.includes("context-management-2025-06-27")
      ? { context_management: C6 }
      : {})
}
```

현재 `keep: "all"`이므로 thinking을 제거하지 않는다. 향후 `keep: "none"` 등으로 이전 턴의 thinking을 서버사이드에서 제거 가능.

### 2.3 Server-side Compaction API (Claude Code 미사용)

`compact-2026-01-12` beta는 서버가 자동으로 히스토리를 요약하는 API다. Claude Code는 이것을 사용하지 않고 **자체 compaction 로직**(별도 문서에서 분석)을 구현했다. 다만 Claude Code의 claude-api 스킬 문서에 이 API의 사용법이 포함되어 있어, 내부적으로 인지하고 있는 대안임을 알 수 있다.

> **함의**: Claude Code가 server-side compaction을 쓰지 않는 이유는 자체 compaction에서 `cacheSafeParams`를 통한 기존 prefix 캐시 재사용, `cache_edits`를 통한 정밀 캐시 관리 등 세밀한 제어가 가능하기 때문이다. Server-side compaction은 이런 제어를 API에 위임한다.

## 3. Cache Editing 메커니즘

### 3.1 Cache Editing Beta

```javascript
// firstParty + repl_main_thread일 때만 활성화
let enableCacheEditing = D && provider === "firstParty" && querySource === "repl_main_thread";
if (enableCacheEditing) {
  betas.push(X);  // cache editing beta header
  debug("Cache editing beta header enabled for cached microcompact");
}
```

> **설계 의도**: Cache editing은 서버 캐시를 직접 조작하는 강력한 기능이므로, first-party(Anthropic 직접 API) + 메인 REPL 쓰레드에서만 활성화한다. Third-party provider(AWS Bedrock, GCP Vertex)에서는 사용 불가.

### 3.2 Cache Edit 블록 삽입

`zNz()`에서 cache_edits를 메시지에 삽입:

```javascript
// pinnedEdits: 이전 compact에서 저장된 편집들
for (let edit of pinnedEdits) {
  let targetMessage = normalizedMessages[edit.userMessageIndex];
  if (targetMessage && targetMessage.role === "user") {
    let dedupedEdit = deduplicateEdits(edit.block);
    if (dedupedEdit.edits.length > 0) Do8(targetMessage.content, dedupedEdit);
  }
}

// 현재 턴의 cache edit (compact 직후 1회)
if (currentCacheEditBlock) {
  let deduped = deduplicateEdits(currentCacheEditBlock);
  if (deduped.edits.length > 0) {
    // 마지막 user 메시지에 삽입
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        Do8(messages[i].content, deduped);
        savePinnedEdit(i, currentCacheEditBlock);
        break;
      }
    }
  }
}
```

### 3.3 `Do8` - Cache Edit 블록 삽입 위치

```javascript
function Do8(content, editBlock) {
  // tool_result 블록 뒤에 삽입 (있으면)
  let lastToolResultIdx = -1;
  for (let i = 0; i < content.length; i++) {
    if (content[i]?.type === "tool_result") lastToolResultIdx = i;
  }

  if (lastToolResultIdx >= 0) {
    let insertIdx = lastToolResultIdx + 1;
    content.splice(insertIdx, 0, editBlock);
    // 삽입이 마지막이면 더미 텍스트 추가 (API 요구사항)
    if (insertIdx === content.length - 1) content.push({ type: "text", text: "." });
  } else {
    // tool_result 없으면 마지막에서 하나 앞에 삽입
    content.splice(Math.max(0, content.length - 1), 0, editBlock);
  }
}
```

### 3.4 Cache Reference Deduplication

```javascript
function deduplicateEdits(editBlock) {
  let seen = new Set();
  let filtered = editBlock.edits.filter(edit => {
    if (seen.has(edit.cache_reference)) return false;
    seen.add(edit.cache_reference);
    return true;
  });
  return { ...editBlock, edits: filtered };
}
```

## 4. Compaction과 Caching의 상호작용

### 4.1 Compact 시 캐시 공유 (`tengu_compact_cache_prefix`)

Compact API 호출 시 기존 캐시를 재사용하는 최적화:

```javascript
async function zP4({ messages, summaryRequest, appState, context, preCompactTokenCount, cacheSafeParams }) {
  let useCacheSharing = featureFlag("tengu_compact_cache_prefix");

  if (useCacheSharing) {
    try {
      // 기존 캐시를 활용한 compact 호출
      let result = await dS({
        promptMessages: [summaryRequest],
        cacheSafeParams: cacheSafeParams,  // system prompt, context 등 보존
        querySource: "compact",
        skipCacheWrite: true,  // compact 결과는 캐시에 안 씀
        maxTurns: 1
      });

      if (validResult(result)) {
        telemetry("tengu_compact_cache_sharing_success", {
          cacheHitRate: cacheRead / (cacheRead + cacheCreation + input)
        });
        return result;
      }
    } catch (e) {
      telemetry("tengu_compact_cache_sharing_fallback", { reason: "error" });
    }
  }

  // Fallback: 일반 compact API 호출
  return normalCompactCall(messages, summaryRequest, ...);
}
```

> **설계 의도**: Compact API 호출도 결국 전체 메시지를 서버에 보내야 한다. `cacheSafeParams`로 시스템 프롬프트와 context를 보존하면, compact 호출 시에도 기존 prefix 캐시를 활용할 수 있다. 170K 토큰 대화의 compact 호출에서 대부분을 cache read(0.1x)로 처리하면, compact 자체의 비용도 크게 줄어든다.

`cacheSafeParams`의 구성:
```javascript
cacheSafeParams = {
  systemPrompt,           // 시스템 프롬프트 (변하지 않음)
  userContext,            // 유저 컨텍스트
  systemContext,          // 시스템 컨텍스트
  toolUseContext,         // 도구 사용 컨텍스트
  forkContextMessages     // 기존 메시지
}
```

### 4.2 Compact 후 캐시 초기화

```javascript
// compact 완료 후 (수동이든 자동이든)
ld6();                    // HR8 = true (microcompact 활성)
V_.cache.clear?.();       // 클라이언트 캐시 초기화
oO.cache.clear?.();       // 보조 캐시 초기화
```

`V_.cache`는 도구/시스템 관련 캐시. Compact 후 메시지 구조가 변경되므로 관련 캐시를 모두 무효화.

### 4.3 Compact 직후 첫 턴 (Cache Edit 전송)

```javascript
// 메인 루프에서
let cacheEditBlock = D ? FP4() : null;  // compact 결과에서 cache edit 읽기 (1회)
let pinnedEdits = D ? QP4() : [];       // 이전 pinned edits

// zNz()에서 이것들을 메시지에 삽입
// → API 서버가 옛 캐시 레퍼런스 삭제
```

### 4.4 Prefill 비용 분석

#### Compact 전 (정상 상태)

```
[시스템(30K) + 도구(15K) + 메모리(5K) + 메시지(120K)] = 170K 토큰
                ↓
대부분 cache hit → prefill 빠름 (~0.5s)
```

**비용 계산** (Sonnet 4.6 기준, $3/1M input):
- Cache read 170K × $3 × 0.1 = **$0.051/턴**

#### Compact 직후

```
[시스템(30K) + 도구(15K) + 메모리(5K) + 요약(5-10K) + 최근메시지(수K)] = ~55K 토큰
                ↓
전체 cache miss → 하지만 토큰 자체가 대폭 감소 → prefill ~1-2s
```

**비용 계산**:
- Cache miss 55K × $3 × 1.0 = **$0.165** (1회)
- 이후 cache write로 저장

#### Compact 후 2번째 턴

```
[시스템(30K) + 도구(15K) + 메모리(5K) + 요약(5-10K) + 메시지(+α)] = ~60K
                ↓
새 prefix 캐시 히트 → prefill 정상화 (~0.3s)
```

**비용 계산**:
- Cache read 60K × $3 × 0.1 = **$0.018/턴**

> **함의**: Compact 후 1회 cache miss($0.165)가 발생하지만, 이후 턴당 비용이 $0.051 → $0.018로 **65% 감소**한다. 3턴만 지나면 compact 비용을 회수하고, 이후는 순절감. **전체 교체 전략이 경제적으로도 합리적**이라는 수치적 근거.

#### TTL과 Compact 타이밍의 관계

| TTL | Compact 후 시나리오 | 결과 |
|-----|---------------------|------|
| 5분 | Compact 후 5분 이내 다음 턴 | 새 prefix cache hit |
| 5분 | Compact 후 5분 초과 idle | Cache miss → 다시 cache write |
| 1시간 | Compact 후 긴 idle 후 복귀 | 여전히 cache hit |

> **함의**: 1h TTL 사용자는 compact 후에도 여유롭게 캐시가 유지되지만, 5분 TTL 사용자는 compact 직후 빠르게 다음 턴을 보내야 새 캐시가 유효하다.

### 4.5 "중간 프루닝"을 하지 않는 이유

만약 대화 중간 메시지를 삭제하면:

```
[시스템(30K) + msg1 + msg2 + 삭제 + msg5 + msg6] = 여전히 ~140K
```

- msg1~msg2까지는 기존 prefix cache hit
- msg2 이후 전체 cache miss (prefix 변경)
- 토큰은 많은데 miss도 많음 = **최악의 조합**

**비용으로 증명:**
- 중간 프루닝: 40K cache hit(0.1x) + 100K cache miss(1x) = $0.012 + $0.300 = **$0.312**
- 전체 교체(compact): 55K cache miss(1x, 1회) = **$0.165**, 이후 55K × 0.1x = **$0.017/턴**
- 중간 프루닝이 **1회 비용만으로도 1.9x 더 비싸고**, 이후에도 매 턴 비쌈

Claude Code는 이 문제를 피하기 위해 **전체 교체** 방식을 사용:
- 중간 프루닝 금지
- 앞부분 전체를 요약으로 교체
- 토큰 대폭 감소로 cache miss 비용 상쇄

## 5. `context_management`의 Thinking 관리

### 5.1 `clear_thinking_20251015`

```javascript
function GoA({ hasThinking }) {
  let edits = [];
  if (hasThinking && featureFlag("tengu_marble_anvil"))
    edits.push({ type: "clear_thinking_20251015", keep: "all" });
  return edits.length > 0 ? { edits } : undefined;
}
```

현재 `keep: "all"` → 모든 thinking 유지 (사실상 noop).

향후 가능한 옵션:
- `keep: "none"` → 이전 턴 thinking 전부 제거
- `keep: "last"` → 마지막 턴만 유지
- 이렇게 하면 thinking 토큰(10-50K)을 context에서 제거하여 공간 확보

### 5.2 활성화 조건

```javascript
// tengu_marble_anvil 플래그 + 모델이 thinking 지원
let enableContextManagement =
  (process.env.USE_API_CONTEXT_MANAGEMENT) ||
  (supportsThinking(model) && featureFlag("tengu_marble_anvil"));

if (enableContextManagement) betas.push("context-management-2025-06-27");
```

### 5.3 API 응답에서 context_management 처리

```javascript
// message_delta 이벤트에서
case "message_delta":
  message.context_management = event.context_management;
  message.usage.output_tokens = event.usage.output_tokens;
```

Assistant 메시지에 `context_management` 필드가 보존되어 transcript에 기록.

## 6. Microcompact와 Cache Editing의 관계

### 6.1 현재 상태

```
CF() (microcompact) = noop
  ↓
하지만 compact 후:
  ld6() → HR8=true
  ↓
다음 API 호출 시:
  FP4() → jR8에서 cache edit 블록 읽기 (1회)
  ↓
zNz() → 메시지에 cache_edits 삽입
  ↓
API 서버 → 옛 캐시 레퍼런스 삭제
```

### 6.2 미래 예상

`CF()`가 실제 로직을 가지게 되면:

```
CF(messages)
  → 토큰 체크 (WoA=180K?)
  → 대화 중간의 불필요한 콘텐츠 식별 (큰 tool_result 등)
  → cache_edits 생성 → API 서버에서 해당 부분 캐시 제거
  → 메시지 자체도 축약 (tool_result 요약 등)
  → prefix 구조 유지하면서 토큰 감소
```

이것이 "full compact 없이도 context를 관리하는" 경량 메커니즘이 될 것.

> **설계 의도**: Full compaction은 효과적이지만 1회 cache miss + compact API 호출 비용이 든다. Microcompact + cache editing은 prefix 구조를 유지하면서 부분적으로 토큰을 줄이므로, cache hit를 유지한 채 context를 관리할 수 있다. "전체 교체 vs 부분 정리"의 두 가지 도구를 상황에 따라 선택하는 전략.

## 7. 성능 최적화 전략 정리

### 7.1 Claude Code가 사용하는 캐싱 최적화

| 전략 | 구현 | 효과 |
|------|------|------|
| Prefix caching | 마지막 메시지에 `cache_control` (Explicit 1개) | 이전 메시지 모두 캐시 히트 |
| Thinking 제외 | thinking 블록에 `cache_control` 안 붙임 (API 제약 + 설계) | 불안정 prefix 방지 |
| 1h TTL (프리미엄) | `oTz()` 체크 → 조건부 1시간 캐시 | idle 후 재접속 latency 제거 |
| Global scope 시스템 캐싱 | `wNz()` → `Mo8()` 분할 → global scope | 조직 간 시스템 프롬프트 공유 |
| Compact cache sharing | `cacheSafeParams`로 기존 캐시 활용 | compact API 호출 비용 절감 |
| Skip cache write | compact 결과는 캐시에 안 씀 | 캐시 오염 방지 |
| Cache editing | compact 후 `cache_edits`로 옛 캐시 정리 | 서버 캐시 일관성 |
| tool_result cache_reference | breakpoint 이전 tool_result에 ID 부여 | 부분적 캐시 eviction 가능 |
| Pinned edits | compact의 cache edit을 다음 턴에도 유지 | 캐시 정리 지속 |
| 전체 교체 (중간 프루닝 금지) | `wn()`으로 메시지 배열 전체 교체 | 1회 miss만, 중간 miss 방지 |
| 모델별 캐시 제어 | `okq()` + 환경변수 | 디버깅/벤치마크 유연성 |
| Tool result 잘림 (요약 없음) | `d54()`, `rt1` 버퍼 (30K자/32MB) | 메시지 크기 제한 (8절) |
| Deferred tools | `qG()` → 이름만 목록, schema 미포함 | tools 파라미터 토큰 88% 절감 (9절) |

### 7.2 Compact 전후 비용 비교 (200K, Sonnet 4.6 $3/1M)

| 지표 | Compact 직전 | Compact 직후 | 2턴 후 정상화 |
|------|-------------|-------------|-------------|
| 총 토큰 | ~170K | ~55K | ~60K |
| Cache hit | 90%+ | 0% | 90%+ |
| Prefill 시간 | ~0.5s | ~1-2s | ~0.3s |
| 비용/턴 | $0.051 (cache read) | $0.165 (cache miss, 1회) | $0.018 (cache read) |
| 누적 10턴 비용 | $0.51 | - | $0.165 + $0.162 = $0.33 |

> **함의**: Compact 후 10턴 누적 비용이 compact 전 대비 **35% 절감**. 토큰이 줄어든 만큼 output도 더 빠르게 시작되므로 체감 속도도 향상.

### 7.3 Claude Code가 API best practices를 준수하는 방식

API 문서가 권장하는 캐시 최적화 원칙과 Claude Code 구현의 대응 관계:

| API 권장 사항 | Claude Code의 구현 |
|---------------|-------------------|
| Prefix 안정성 유지 (순서 고정) | 시스템 프롬프트 → 도구 정의 → 메모리 → 메시지 순서가 세션 내 불변 |
| Lookback window 내 블록 수 관리 | 단일 메시지의 콘텐츠 블록이 20개를 초과하는 경우 없음 |
| 무효화 트리거 최소화 | `tool_choice`, thinking params를 세션 중 변경하지 않는 구조 |
| Workspace isolation 활용 | `wNz()`의 global scope로 조직 내 시스템 프롬프트 공유 |
| Thinking에 cache_control 미부여 | `tTz()`에서 thinking/redacted_thinking 블록을 명시적으로 제외 |

### 7.4 캐시 동작에 영향을 미치는 사용자 행동

분석에서 도출되는, 사용자 행동과 캐시 성능의 관계:

| 사용자 행동 | 캐시에 미치는 영향 | 관련 코드 |
|------------|-------------------|-----------|
| 세션 중 CLAUDE.md 수정 | 시스템 프롬프트 변경 → 전체 prefix 무효화 | `wNz()` 재실행 |
| MCP 도구 다수 로드 | deferred 사용 시 이름만 포함되어 영향 적음. 로드 시 `tools` 파라미터 증가 | `qG()`, `op6()` (9절) |
| 수동 `/compact` 빈번 사용 | 매 compact마다 1회 cache miss 발생 | `skipCacheWrite: true` |
| 5분 이상 idle 후 재접속 | 기본 TTL 만료 → cache miss (1h TTL 사용자 제외) | `oTz()` TTL 분기 |
| `DISABLE_PROMPT_CACHING=1` 설정 | 모든 캐시 비활성화 → 순수 처리 비용 측정 가능 | `okq()` 체크 |
| Extended thinking 사용 | thinking 토큰이 context에 누적 → compact 트리거 가속 | `kV()` 토큰 카운트 |

## 8. Tool Result 처리와 메시지 축적

### 8.1 Tool Result는 요약 없이 잘림(truncation)만 적용

tool_result는 LLM 기반 요약 없이, **문자 수/줄 수 기반 잘림**만 거친 뒤 메시지 배열에 원본 그대로 쌓인다:

| 도구 | 제한 | 기본값 | 최대값 | 환경변수 오버라이드 |
|------|------|--------|--------|-------------------|
| Bash | 문자 수 | 30,000자 | 150,000자 | `BASH_MAX_OUTPUT_LENGTH` |
| Read | 줄 수 + 줄당 문자 | 2,000줄, 줄당 2,000자 | - | - |
| 일반 버퍼 | 바이트 | 32MB | - | - |

```javascript
// Bash 출력 잘림 (d54)
function d54(output) {
  let maxChars = VK1();  // 기본 30,000자, BASH_MAX_OUTPUT_LENGTH로 오버라이드 가능
  if (output.length <= maxChars)
    return { truncatedContent: output, isImage: false };

  let kept = output.slice(0, maxChars);
  let removedLines = output.slice(maxChars).split("\n").length;
  return {
    truncatedContent: kept + `\n... [${removedLines} lines truncated] ...`,
    wasTruncated: true
  };
}

// 스트리밍 출력 버퍼 (rt1) - 32MB 상한
class rt1 {
  constructor(maxSize = 33554432) { this.maxSize = maxSize; }
  append(data) {
    if (this.content.length + data.length > this.maxSize) {
      this.content += data.slice(0, this.maxSize - this.content.length);
      this.isTruncated = true;
    } else this.content += data;
  }
  toString() {
    if (!this.isTruncated) return this.content;
    let removedKB = Math.round((this.totalBytesReceived - this.maxSize) / 1024);
    return this.content + `\n... [output truncated - ${removedKB}KB removed]`;
  }
}
```

### 8.2 메시지 축적 흐름

```
Bash/Read/Grep 실행 → 원시 출력 (수 MB 가능)
  ↓
rt1 버퍼 (32MB 상한 잘림)
  ↓
d54() (30,000자 잘림 + "[N lines truncated]" 메시지 부착)
  ↓
<local-command-stdout>잘린 결과</local-command-stdout>
  ↓
tool_result 블록으로 메시지 배열에 추가
  ↓
이후 모든 턴에서 그대로 전송 (compaction 전까지)
```

> **설계 의도**: 개별 tool_result에 대한 LLM 요약은 비용과 latency를 추가하므로, 단순 잘림으로 처리한다. 잘린 결과라도 토큰으로는 수천~수만이 되어 context를 빠르게 소모하는데, 이것이 microcompact(`CF()`)가 미래에 "큰 tool_result를 선택적으로 요약/제거"하는 역할을 할 수 있다고 예측하는 근거다. 현재는 full compaction이 유일한 정리 수단이다.

### 8.3 전체 메시지 배열 구성 (매 턴 API에 전송되는 것)

```
시스템 프롬프트 [text + cache_control(global)]     ← wNz()로 캐싱
도구 정의 (tools 파라미터)                          ← loaded 도구만 (deferred 제외)
───
<available-deferred-tools> 목록 (8절 참조)          ← 첫 번째 user 메시지로 삽입
user: "코드를 분석해줘"
assistant: [thinking(50K)] [text] [tool_use "Read(file.ts)"]
user: [tool_result "파일 내용 30K자 잘림"]           ← 그대로 유지
assistant: [thinking(30K)] [text] [tool_use "Edit(...)"]
user: [tool_result "편집 완료"]
assistant: [thinking(20K)] [text + cache_control]    ← 마지막에만 breakpoint
───
user: "다음 질문"                                    ← 새 턴에서 추가
```

이전 턴의 thinking(50K+30K+20K=100K) + tool_result 전부가 **매 턴 전송**된다. 이것이 extended thinking과 큰 tool_result가 compaction을 가속시키는 구조적 원인이다.

## 9. ToolSearch와 Deferred Tools — 캐시 prefix 최적화

### 9.1 Deferred Tools의 목적

Claude Code는 도구가 많아지면 **모든 도구 정의(schema)를 `tools` 파라미터에 넣는 대신, 대부분을 "deferred" 상태로** 두고 모델이 필요할 때 `ToolSearch`로 로드하게 한다. 이는 시스템 프롬프트의 `tools` 토큰을 줄여 **캐시 prefix를 안정화**시키는 전략이다.

### 9.2 Deferred 판정 — `qG()`

```javascript
function qG(tool) {
  if (tool.isMcp === true) return true;            // 모든 MCP 도구는 무조건 deferred
  if (tool.name === "ToolSearch") return false;     // ToolSearch 자체는 항상 활성
  if (e8("tengu_defer_all_bn4", true)) return true; // feature flag 기본값 true → 전부 defer
  return tool.shouldDefer === true;                 // 개별 도구의 shouldDefer 플래그
}
```

> **설계 의도**: `tengu_defer_all_bn4`의 기본값이 `true`이므로, **ToolSearch를 제외한 사실상 모든 도구가 deferred**된다. 내장 도구(Read, Edit, Bash 등)도 포함이다. 이렇게 하면 `tools` 파라미터에는 ToolSearch 1개의 schema만 들어가고, 나머지는 모델이 `ToolSearch`를 호출해야 활성화된다.

### 9.3 메시지 배열에서의 위치

Deferred 도구 목록은 **메시지 배열의 맨 앞에 user 메시지로 삽입**된다:

```javascript
// API 요청 빌더에서 (zNz 이후, 실제 전송 직전)
if (toolSearchEnabled && !isSubAgent()) {
  let deferredList = tools.filter(qG).map(op6).sort().join("\n");
  if (deferredList)
    messages = [
      t1({
        content: `<available-deferred-tools>\n${deferredList}\n</available-deferred-tools>`,
        isMeta: true
      }),
      ...messages
    ];
}
```

도구 이름(+ 선택적 searchHint)만 포함되며, **전체 schema는 포함되지 않는다**:

```javascript
function op6(tool) {
  // searchHint가 활성화되어 있으면 이름 + 힌트
  if (e94() && tool.searchHint)
    return `${tool.name} — ${tool.searchHint}`;
  // 아니면 이름만
  return tool.name;
}
```

실제로 모델이 보는 형태:
```
<available-deferred-tools>
Bash
Edit
Glob
Grep
LSP
Read
Write
mcp__slack__read_channel
mcp__github__create_issue
TodoWrite — manage the session task checklist
</available-deferred-tools>
```

### 9.4 ToolSearch 호출 시 동작 — `ap6`

두 가지 모드:

#### `select:` 모드 (직접 선택)

```javascript
// "select:Read,Edit,Grep" → 콤마 분리 → 각각 이름으로 lookup
let match = query.match(/^select:(.+)$/i);
if (match) {
  let names = match[1].split(",").map(n => n.trim());
  let found = names.map(n => C3(deferredTools, n) ?? C3(allTools, n))
                    .filter(Boolean);
  // 찾은 도구가 활성화됨 (tools 파라미터에 schema 추가)
  return found;
}
```

#### keyword 모드 (검색)

```javascript
async function Us9(query, deferredTools, allTools, maxResults) {
  let terms = query.toLowerCase().split(/\s+/);
  let required = [];  // "+" 접두사: 반드시 매칭되어야 하는 키워드
  let optional = [];  // 일반 키워드: 스코어링에 사용

  for (let tool of filteredTools) {
    let parts = parseName(tool.name);  // "mcp__slack__read" → ["mcp","slack","read"]
    let desc = await getCachedDescription(tool);
    let hint = tool.searchHint;
    let score = 0;

    for (let term of terms) {
      if (parts.includes(term))                score += isMcp ? 12 : 10;  // 정확 매칭
      else if (parts.some(p => p.includes(term))) score += isMcp ? 6 : 5; // 부분 매칭
      if (hint?.includes(term))                score += 4;  // searchHint 매칭
      if (desc.includes(term))                 score += 2;  // description 매칭
    }
    return { name: tool.name, score };
  }
  // score > 0만, 내림차순 정렬, maxResults(기본 5)개 반환
}
```

> **설계 의도**: MCP 도구에 더 높은 가중치(12 vs 10)를 주는 이유는 MCP 도구 이름이 `mcp__server__tool` 형태로 구조화되어 있어 파트 매칭이 더 신뢰성 있기 때문이다.

### 9.5 ToolSearch 활성화 조건

```javascript
function ib() {
  // first-party API가 아니면 비활성화
  if (D7() === "firstParty" && !ha()) return false;

  let mode = gr8();  // "tst" (활성) | "tst-auto" (자동) | "standard" (비활성)
  return mode === "tst" || mode === "tst-auto";
}

function gr8() {
  let env = process.env.ENABLE_TOOL_SEARCH;
  if (isTrue(env))  return "tst";       // 명시적 활성화
  if (isFalse(env)) return "standard";  // 명시적 비활성화
  return "tst";                          // 기본값: 활성화
}
```

### 9.6 캐싱과의 관계 — 토큰 절감 효과

Deferred tools의 핵심 가치는 **`tools` 파라미터의 토큰을 줄여 캐시 prefix를 안정화**시키는 것이다:

```javascript
// 토큰 계산 시 deferred vs loaded 분리
for (let tool of mcpTools) {
  if (tool.isLoaded)  loadedTokens += tool.tokens;
  else if (isDeferred) deferredTokens += tool.tokens;
}
```

| 시나리오 | `tools` 파라미터 토큰 | `<available-deferred-tools>` 토큰 | 합계 |
|---------|----------------------|----------------------------------|------|
| Deferred 미사용 (30개 도구) | ~15,000 (~500/도구) | 0 | ~15,000 |
| Deferred 사용 (3개 로드) | ~1,500 | ~300 (이름만) | **~1,800** |

> **설계 의도**: ~88% 토큰 절감. 더 중요한 것은 **prefix 안정성**이다. Deferred 미사용 시 MCP 도구가 추가/제거될 때마다 `tools` 파라미터가 변경되어 전체 캐시가 무효화된다. Deferred 사용 시 `tools`에는 ToolSearch 1개만 있으므로, MCP 도구 변경이 `tools` 파라미터에 영향을 주지 않는다. `<available-deferred-tools>` 목록은 메시지 배열의 앞부분이므로 prefix 내에서 변경이 발생해도 뒤쪽 메시지의 캐시에는 영향이 적다.

## 10. 내부 메시지 규격과 API 규격 변환

### 10.1 Claude Code의 내부 메시지 규격

Claude Code는 **독자적인 내부 메시지 규격**으로 대화를 관리하고, API 호출 직전에 Anthropic Messages API 규격으로 변환한다.

내부 메시지 생성 — `t1()`:

```javascript
function t1({ content, isMeta, isVisibleInTranscriptOnly, isCompactSummary,
              summarizeMetadata, toolUseResult, mcpMeta, uuid, timestamp, ... }) {
  return {
    type: "user",                    // 내부 타입 (API의 "role"과 별개)
    message: {
      role: "user",                  // API 호환 role
      content: content || sE         // API 호환 content
    },
    // ─── 내부 전용 필드 (API에 전송되지 않음) ───
    isMeta,                          // 메타 메시지 (deferred tools 목록 등)
    isVisibleInTranscriptOnly,       // transcript에만 기록
    isCompactSummary,                // compaction 요약 메시지
    uuid,                            // 내부 추적 ID
    timestamp,                       // 기록 시각
    toolUseResult,                   // tool 실행 메타데이터
    mcpMeta,                         // MCP 관련 메타데이터
    ...
  };
}
```

API에 없는 내부 전용 메시지 타입도 존재한다:

| 내부 type | subtype | API 전송 여부 | 용도 |
|-----------|---------|--------------|------|
| `user` | - | **전송** | 사용자 입력 + tool_result |
| `assistant` | - | **전송** | 모델 응답 (thinking + text + tool_use) |
| `system` | `compact_boundary` | **미전송** → compaction 경계 마커로 사용 | compact 경계 표시 |
| `system` | `local_command` | **미전송** → user 메시지로 병합 | 로컬 명령 출력 |
| `system` | `file_snapshot` | **미전송** (isMeta) | 파일 스냅샷 |
| `system` | `api_error` | **미전송** | API 오류 기록 |
| `progress` | - | **미전송** (필터링 제거) | 진행 상황 표시 |

### 10.2 내부 → API 변환 파이프라인

```
내부 transcript 배열 (user, assistant, system, progress 혼재)
  ↓
mD() — 메시지 필터링/변환
  - progress 타입: 제거
  - system 타입: user 메시지로 병합 (compact_boundary 제외)
  - 연속 user 메시지: 하나로 병합 (lo8)
  - assistant의 tool_use: 내부 caller 필드 제거 (AEq)
  - ToolSearch 비활성 시: 도구 참조 블록 제거 (Po8)
  ↓
정규화 (qEq, qNz 등)
  ↓
deferred tools 목록 삽입 (<available-deferred-tools> → 메시지 배열 맨 앞)
  ↓
zNz() — cache_control 삽입 + cache_reference 부여
  ↓
wNz() — 시스템 프롬프트 캐싱 (global scope)
  ↓
최종 API 요청: 표준 Anthropic Messages API 규격
```

> **설계 의도**: 내부 규격에서 `isMeta`, `isVisibleInTranscriptOnly`, `isCompactSummary` 등의 플래그로 메시지의 "성격"을 관리하고, `mD()`에서 이를 기반으로 API에 보낼 것과 transcript에만 남길 것을 분리한다. `system` 타입 메시지가 `user`로 병합되는 이유는 API가 `user`/`assistant` 교대만 허용하기 때문이다.

### 10.3 API에 전송되는 최종 형태

변환 후 **표준 Anthropic Messages API 규격과 동일**하다:

```javascript
{
  model: "claude-opus-4-6",
  system: [                                              // wNz() 결과
    { type: "text", text: "시스템 프롬프트...",
      cache_control: { type: "ephemeral", scope: "global" } }  // global scope 캐싱
  ],
  messages: [
    { role: "user",      content: [{ type: "text", text: "<available-deferred-tools>..." }] },
    { role: "user",      content: [{ type: "text", text: "코드를 분석해줘" }] },
    { role: "assistant", content: [
      { type: "thinking", thinking: "..." },
      { type: "text", text: "분석 결과..." },
      { type: "tool_use", id: "toolu_...", name: "Read", input: { file_path: "..." } }
    ]},
    { role: "user",      content: [
      { type: "tool_result", tool_use_id: "toolu_...", content: "파일 내용...",
        cache_reference: "toolu_..." }                   // cache editing beta
    ]},
    { role: "assistant", content: [
      { type: "thinking", thinking: "..." },
      { type: "text", text: "완료했습니다",
        cache_control: { type: "ephemeral" } }           // ← 유일한 breakpoint
    ]}
  ],
  tools: [/* ToolSearch + 로드된 도구의 schema만 */],
  context_management: { edits: [{ type: "clear_thinking_20251015", keep: "all" }] },
  // + betas, metadata, thinking config 등
}
```

## 11. 캐싱 관련 Beta 헤더와 공식 API 필드 분류

### 11.1 Claude Code가 사용하는 Beta 헤더

```javascript
var uq1 = "claude-code-20250219";              // Claude Code 전용 식별
var aBA = "interleaved-thinking-2025-05-14";    // thinking 인터리빙
var Sa  = "context-1m-2025-08-07";              // 1M context window
var mq1 = "context-management-2025-06-27";      // context management (thinking 관리)
var Kh6 = "prompt-caching-scope-2026-01-05";    // cache scope (global)
var tBA = "tool-search-tool-2025-10-19";        // ToolSearch
var AgA = "fast-mode-2026-02-01";               // Fast mode
var X   = (난독화됨);                             // cache editing
```

### 11.2 캐싱 관련 필드의 공식 문서 여부

| 필드 | 공식 API 문서 | 상태 | Claude Code 사용 위치 |
|------|-------------|------|---------------------|
| `cache_control: { type: "ephemeral" }` | **있음** | GA (정식) | `Fa6()` → `sTz()`, `tTz()` |
| `cache_control.ttl: "1h"` | **있음** | GA | `Fa6()` → `oTz()` 조건부 |
| `cache_control.scope: "global"` | **미공개** | 미공개 Beta (`Kh6`) | `Fa6()` → `wNz()` 시스템 프롬프트 |
| `cache_reference` | **미공개** | 미공개 Beta (first-party only) | `zNz()` → tool_result에 부여 |
| `cache_edits` (블록) | **미공개** | 미공개 Beta (first-party only) | `Do8()` → compact 후 삽입 |
| `context_management.edits` | **beta** 문서 | 공개 Beta (`mq1`) | `GoA()` → thinking 관리 |

> **함의**: Claude Code는 공식 GA 기능(`cache_control`, `ttl`)과 공개 beta(`context_management`) 위에, **미공개 beta 3개**(`scope: "global"`, `cache_reference`, `cache_edits`)를 추가로 사용한다. `scope: "global"`은 beta 헤더 `prompt-caching-scope-2026-01-05`(`Kh6`)로 활성화되며, 공식 prompt caching 문서(platform.claude.com)에 기재되어 있지 않다. `cache_reference`와 `cache_edits`는 `D7() === "firstParty"` (Anthropic 직접 API)이면서 `querySource === "repl_main_thread"` (메인 REPL)인 경우에만 활성화된다. Third-party provider(Bedrock, Vertex)나 서브에이전트에서는 사용되지 않는다.

### 11.3 Beta 활성화 조건 분기

```javascript
// API 요청 빌더에서 beta 헤더 구성
let betas = [];

// 항상 포함
betas.push(uq1);                    // claude-code 식별

// thinking 사용 시
if (hasThinking) betas.push(aBA);   // interleaved-thinking

// context management 사용 시
if (enableContextManagement) betas.push(mq1);  // context-management

// ToolSearch 활성 시
if (toolSearchEnabled) betas.push(Kh6);  // prompt-caching-scope

// Cache editing: first-party + main thread에서만
if (D && D7() === "firstParty" && querySource === "repl_main_thread")
  betas.push(X);                    // cache editing (미공개)

// Fast mode: 특정 모델 + fastMode 활성 시
if (Bq() && MJ() && !pB() && FO(model) && fastMode)
  betas.push(AgA);                  // fast-mode
```

> **설계 의도**: Beta 헤더는 조건부로만 포함되므로, 불필요한 beta가 요청에 들어가 예기치 않은 동작을 유발하는 것을 방지한다. 특히 cache editing beta는 first-party에서만 동작하므로, Bedrock/Vertex 사용자의 요청에 포함되면 오류가 발생할 수 있다.

---

*분석 대상: Claude Code v2.1.70 (npm @anthropic-ai/claude-code)*
*분석 일자: 2026-03-06*
*보강 일자: 2026-03-06 (cli.js 추가 발굴 + API 스펙 검증 기반)*
