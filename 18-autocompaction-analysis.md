# Claude Code Autocompaction 로직 심층 분석 (v2.1.70)

## 개요

Claude Code는 context window 한계에 도달하기 전에 대화를 자동으로 요약/압축하는 autocompaction 시스템을 가지고 있다. 이 문서는 minified cli.js(v2.1.70)를 리버스 엔지니어링하여 내부 동작을 분석한 결과를 정리한다.

## 1. 세 가지 Compaction 시스템

Claude Code 환경에는 세 가지 독립적인 compaction 메커니즘이 존재한다. 흥미로운 점은, Anthropic이 SDK와 API 레벨에서 이미 compaction 솔루션을 제공하고 있음에도 Claude Code는 **자체 구현을 고집**한다는 것이다. 이는 범용 솔루션의 한계와 CLI 도구 특유의 요구사항 사이의 간극을 보여준다.

### 1.1 Client-side Autocompact (Claude Code 자체 구현)

Claude Code가 매 턴마다 실행하는 자체 compaction. 현재 프로덕션에서 실제로 동작하는 핵심 시스템.

- 함수 체인: `w04()` → `dwY()` → `Wz6()` → `Uf6()`
- 트리거 조건: `kV(messages) >= autoCompactThreshold`
- 완전한 클라이언트 제어: 커스텀 프롬프트, PreCompact 훅, Session Memory 연동

### 1.2 Server-side Compaction API (`compact-2026-01-12` beta)

Anthropic API의 베타 기능. Claude Code는 이것을 **직접 사용하지 않으나**, 내장 claude-api 스킬의 문서/예시에 포함되어 있다.

- beta 헤더: `compact-2026-01-12`
- 요청 파라미터: `context_management: { edits: [{ type: "compact_20260112" }] }`
- 서버가 자동 판단: threshold(기본 ~150K) 초과 시 응답에 `type: "compaction"` 블록 포함
- 클라이언트는 이 compaction 블록을 다음 요청에 그대로 포함해야 함
- 서버가 이전 히스토리를 compaction 블록의 요약으로 대체

작동 원리:
```
턴1: messages=[user1, assistant1, user2] + context_management → 응답: [text, compaction_block]
턴2: messages=[user1, assistant1(+compaction_block), user2, assistant2, user3]
     → 서버가 compaction_block 이전 내용을 요약으로 교체하여 처리
턴3: 토큰이 다시 threshold에 근접하면 새 compaction_block 생성
     → 이 과정이 반복되어 무한 대화 가능
```

스트리밍에서는 `compaction_delta` 이벤트로 점진적 수신:
```javascript
case "compaction_delta":
  content[index] = { ...block, content: (block.content || "") + delta.content };
```

### 1.3 SDK `compactionControl` (Anthropic SDK 내장)

SDK의 ToolRunner에 내장된 자동 compaction. Claude Code는 이것도 사용하지 않음.

```javascript
// SDK IcA 함수
compactionControl: {
  enabled: true,
  contextTokenThreshold: CcA,  // CcA=1 (기본값)
  model: "...",
  summaryPrompt: hcA  // "Write a continuation summary..."
}
```

SDK가 매 iteration마다 토큰을 체크하고, threshold 초과 시 별도 API 호출로 요약 생성 후 messages를 교체.

### Claude Code가 자체 구현을 사용하는 이유

| 기능 | Server-side API | SDK compactionControl | CC 자체 구현 |
|------|----------------|----------------------|-------------|
| 요약 프롬프트 | 서버 기본 | hcA (단순) | tr9/er9 (9섹션, 상세) |
| 메시지 보존 | 서버 판단 | 없음 | SwY()로 정밀 선택 |
| Hook 지원 | 없음 | 없음 | PreCompact 훅 |
| Session Memory | 없음 | 없음 | RG1() 연동 |
| Transcript 보존 | 없음 | 없음 | 전체 기록 유지 |
| 캐시 최적화 | 서버 내부 | 없음 | cache_edits, cacheSafeParams |

> **함의**: Claude Code가 자체 compaction을 유지하는 핵심 이유는 **요약 품질에 대한 통제권**이다. 코딩 어시스턴트에서 compaction 후 "이전에 어떤 파일을 수정했는지", "어떤 에러를 만났는지", "사용자가 뭘 원했는지"를 잃어버리면 치명적이다. 범용 서버사이드 compaction은 이런 도메인 특화 정보의 우선순위를 모른다. 9개 섹션 프롬프트(`tr9`)는 사실상 "코딩 어시스턴트가 기억해야 할 것들"의 체크리스트이며, 이것이 Claude Code의 compaction이 범용 API보다 나은 결과를 내는 핵심 차별점이다.
>
> 또한 PreCompact 훅은 **사용자가 compaction 과정에 개입할 수 있는 유일한 인터페이스**다. exit code 2로 차단하거나, 출력으로 커스텀 지시를 추가할 수 있다. 이는 서버사이드 방식에서는 불가능한, Claude Code만의 확장점이다.

## 2. Context Window와 Threshold 계산

### 2.1 Context Window 결정 (`YM()`)

```javascript
function YM(model, betas) {
  // 모델명에 [1m] 태그가 있으면
  if (Cy(model)) return 1_000_000;
  // beta에 "context-1m-2025-08-07" 포함 + (sonnet-4 또는 opus-4-6)
  if (betas?.includes("context-1m-2025-08-07") && gtK(model)) return 1_000_000;
  // sonnet-4-6 + 별도 feature flag
  if (Us1(model)) return 1_000_000;
  // 그 외: 기본값
  return 200_000;  // utK
}
```

**1M 활성화 조건 (`gtK`):**
- `claude-sonnet-4` 또는 `opus-4-6` 모델 + beta 플래그 필요
- `yJ6()` (비활성화 플래그)가 false여야 함

### 2.2 핵심 상수

```
QwY = 20,000   // max output 상한 (effective window 계산용)
NR8 = 13,000   // autocompact threshold buffer
pwY = 20,000   // warning threshold buffer
UwY = 20,000   // error threshold buffer
VR8 = 3,000    // blocking limit buffer
WoA = 180,000  // microcompact용 예약 상수 (미사용)
ZoA = 40,000   // microcompact용 예약 상수 (미사용)
```

### 2.3 Threshold 계산 공식

#### Effective Window (`EY6`)
```javascript
function EY6(model) {
  let outputBuffer = Math.min(Ud6(model), QwY);  // min(maxOutput, 20000)
  return YM(model, betas) - outputBuffer;
}
// 200K: 200,000 - 20,000 = 180,000
// 1M:   1,000,000 - 20,000 = 980,000
```

`Ud6(model)`은 모델의 max output tokens 반환:
- opus-4-5/4-6, sonnet-4, haiku-4: default=32000, upperLimit=64000
- opus-4-1: default=16000, upperLimit=32000
- 기타: default=8192, upperLimit=8192
- `CLAUDE_CODE_MAX_OUTPUT_TOKENS` 환경변수로 오버라이드 가능

#### Auto Compact Threshold (`od6`)
```javascript
function od6(model) {
  let effectiveWindow = EY6(model);      // 180,000
  let threshold = effectiveWindow - NR8;  // 180,000 - 13,000 = 167,000

  // 환경변수 오버라이드
  let pctOverride = process.env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE;
  if (pctOverride) {
    let pct = parseFloat(pctOverride);
    if (!isNaN(pct) && pct > 0 && pct <= 100) {
      let pctThreshold = Math.floor(effectiveWindow * (pct / 100));
      return Math.min(pctThreshold, threshold);  // 상한 제한
    }
  }
  return threshold;
}
```

#### 전체 Threshold 계산 (`Wz6`)
```javascript
function Wz6(currentTokens, model) {
  let autoCompactThreshold = od6(model);
  let denominator = kS() ? autoCompactThreshold : EY6(model);
  let percentLeft = Math.max(0, Math.round((denominator - currentTokens) / denominator * 100));

  let warningThreshold = denominator - pwY;  // 147,000 (200K 기준)
  let errorThreshold = denominator - UwY;    // 147,000

  return {
    percentLeft,
    isAboveWarningThreshold: currentTokens >= warningThreshold,
    isAboveErrorThreshold: currentTokens >= errorThreshold,
    isAboveAutoCompactThreshold: kS() && currentTokens >= autoCompactThreshold,
    isAtBlockingLimit: currentTokens >= blockingLimit
  };
}
```

### 2.4 수치 정리

**200K Context Window:**
```
contextWindow           = 200,000
effectiveWindow         = 180,000
autoCompactThreshold    = 167,000
warningThreshold        = 147,000  (UI 경고 시작)
errorThreshold          = 147,000
blockingLimit           = 197,000  (200K - VR8)
Autocompact buffer      = 33,000   (context bar에 표시)
```

**1M Context Window:**
```
contextWindow           = 1,000,000
effectiveWindow         = 980,000
autoCompactThreshold    = 967,000
warningThreshold        = 947,000
errorThreshold          = 947,000
blockingLimit           = 997,000
Autocompact buffer      = 33,000
```

## 3. 토큰 카운트 (`kV()`)

### 3.1 카운트 방식

```javascript
function kV(messages) {
  // 뒤에서부터 마지막 API usage가 있는 메시지를 찾음
  let q = messages.length - 1;
  while (q >= 0) {
    let msg = messages[q];
    let usage = Wl(msg);  // API usage 추출
    if (msg && usage) {
      // 같은 체인(query chain)의 첫 메시지로 거슬러 올라감
      let chainId = Q84(msg);
      if (chainId) {
        let w = q - 1;
        while (w >= 0) {
          let prevChainId = Q84(messages[w]);
          if (prevChainId === chainId) q = w;
          else if (prevChainId !== undefined) break;
          w--;
        }
      }
      // 첫 체인 메시지의 usage + 이후 메시지의 추정 토큰
      return qp6(usage) + Ap6(messages.slice(q + 1));
    }
    q--;
  }
  return Ap6(messages);  // usage 없으면 전체 추정
}
```

### 3.2 `qp6` - API Usage에서 토큰 합산

```javascript
function qp6(usage) {
  return usage.input_tokens
       + (usage.cache_creation_input_tokens ?? 0)
       + (usage.cache_read_input_tokens ?? 0)
       + usage.output_tokens;
}
```

**중요**: 이 합계에는 시스템 프롬프트, 도구 정의, 메모리 파일, 메시지 히스토리, 출력 토큰이 **모두** 포함된다.

Anthropic API의 usage 필드:
- `input_tokens`: 캐시 미적중 입력 토큰
- `cache_creation_input_tokens`: 이번에 캐시에 쓴 토큰
- `cache_read_input_tokens`: 캐시에서 읽은 토큰
- 세 개 합 = 총 입력 토큰

### 3.3 `Ap6` - 텍스트 기반 토큰 추정

```javascript
function Ap6(messages) {
  let total = 0;
  for (let msg of messages) total += estimateMessageTokens(msg);
  return total;
}
// 텍스트 길이 * 1.333 (4/3)으로 대략적 추정
// 이미지/문서: 고정 2000 토큰
```

## 4. 트리거 판단 흐름

### 4.1 Autocompact 활성화 확인 (`kS`)

```javascript
function kS() {
  if (process.env.DISABLE_COMPACT) return false;
  if (process.env.DISABLE_AUTO_COMPACT) return false;
  return settings.autoCompactEnabled;
}
```

### 4.2 트리거 판단 (`dwY`)

```javascript
async function dwY(messages, model, querySource) {
  // compact 중이거나 session_memory 쿼리면 skip
  if (querySource === "session_memory" || querySource === "compact") return false;
  if (!kS()) return false;

  let currentTokens = kV(messages);
  let threshold = od6(model);
  let effectiveWindow = EY6(model);

  debug(`autocompact: tokens=${currentTokens} threshold=${threshold} effectiveWindow=${effectiveWindow}`);

  let { isAboveAutoCompactThreshold } = Wz6(currentTokens, model);
  return isAboveAutoCompactThreshold;
}
```

### 4.3 Autocompact 실행 (`w04`)

```javascript
async function w04(messages, context, cacheSafeParams, querySource, prevCompactTracking) {
  if (process.env.DISABLE_COMPACT) return { wasCompacted: false };

  let model = context.options.mainLoopModel;
  if (!await dwY(messages, model, querySource)) return { wasCompacted: false };

  let trackingInfo = {
    isRecompactionInChain: prevCompactTracking?.compacted === true,
    turnsSincePreviousCompact: prevCompactTracking?.turnCounter ?? -1,
    previousCompactTurnId: prevCompactTracking?.turnId,
    autoCompactThreshold: od6(model),
    querySource
  };

  // Session Memory compact 먼저 시도
  let smResult = await RG1(messages, context.agentId, trackingInfo.autoCompactThreshold);
  if (smResult) return { wasCompacted: true, compactionResult: smResult };

  // 일반 compact 수행
  try {
    let result = await Uf6(messages, context, cacheSafeParams, true, undefined, true, trackingInfo);
    return { wasCompacted: true, compactionResult: result };
  } catch (e) {
    return { wasCompacted: false };
  }
}
```

## 5. Compaction 실행 상세 (`Uf6`)

### 5.1 전체 흐름

```
Uf6() 진입
  ↓
kV() → 현재 토큰 수 계산
  ↓
cf6() → PreCompact 훅 실행
  ├─ exit code 0: 성공 (custom instructions 추가 가능)
  ├─ exit code 2: compaction 차단
  └─ 기타: stderr 표시 후 계속
  ↓
Z54() → 요약 요청 프롬프트 생성 (tr9 + analysis instruction + custom instructions)
  ↓
zP4() → API 호출
  ├─ tengu_compact_cache_prefix 활성: dS()로 캐시 공유 시도
  ├─ 실패 시 fallback: 일반 API 호출 (df6)
  └─ 스트리밍으로 요약 생성
  ↓
fG1() → 응답에서 요약 텍스트 추출
  ↓
Ao9() → <analysis> 태그 제거, <summary> 태그 추출
  ↓
Ip6() → 요약을 시스템 메시지로 포맷팅
  ↓
wn() → 최종 메시지 배열 조립
  ↓
텔레메트리 로깅 (tengu_compact 이벤트)
```

### 5.2 메시지 배열 교체 (`wn`)

```javascript
function wn(compactionResult) {
  return [
    compactionResult.boundaryMarker,     // compact_boundary 시스템 메시지
    ...compactionResult.summaryMessages,  // 요약 (새로 생성)
    ...compactionResult.messagesToKeep,   // 보존할 최근 메시지 (SwY로 선정)
    ...compactionResult.attachments,      // 시스템 첨부 (에이전트 정보 등)
    ...compactionResult.hookResults       // session_start 훅 결과
  ];
}
```

**기존 메시지 전체가 이 배열로 교체된다.** 중간 프루닝이 아닌 전체 교체.

### 5.3 보존 메시지 선택 (`SwY`)

```javascript
function SwY(messages, summarizedUpToIdx) {
  let config = EwY();  // {minTokens, maxTokens, minTextBlockMessages}
  let startIdx = summarizedUpToIdx >= 0 ? summarizedUpToIdx + 1 : messages.length;
  let totalTokens = 0, textMsgCount = 0;

  // 뒤에서부터 최근 메시지를 카운트
  for (let i = startIdx; i < messages.length; i++) {
    totalTokens += estimateTokens(messages[i]);
    if (hasTextContent(messages[i])) textMsgCount++;
  }

  // maxTokens 초과 시 즉시 반환
  if (totalTokens >= config.maxTokens) return JR8(messages, startIdx);
  // minTokens && minTextBlockMessages 충족 시 반환
  if (totalTokens >= config.minTokens && textMsgCount >= config.minTextBlockMessages)
    return JR8(messages, startIdx);

  // 부족하면 더 이전 메시지까지 포함
  for (let i = startIdx - 1; i >= 0; i--) {
    totalTokens += estimateTokens(messages[i]);
    if (hasTextContent(messages[i])) textMsgCount++;
    startIdx = i;
    if (totalTokens >= config.maxTokens) break;
    if (totalTokens >= config.minTokens && textMsgCount >= config.minTextBlockMessages) break;
  }

  return JR8(messages, startIdx);  // tool_use/tool_result 쌍 보존
}
```

`JR8`: tool_use와 tool_result 쌍이 깨지지 않도록 경계를 조정하는 함수.

### 5.4 요약 후 포맷팅 (`Ip6`)

```javascript
function Ip6(summaryText, isContinuation, transcriptPath, hasRecentMessages) {
  let result = `This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion of the conversation.

${formatSummary(summaryText)}`;

  if (transcriptPath)
    result += `\nIf you need specific details from before compaction, read the full transcript at: ${transcriptPath}`;

  if (hasRecentMessages)
    result += `\nRecent messages are preserved verbatim.`;

  if (isContinuation)
    result += `\nContinue the conversation from where it left off without asking the user any further questions. Resume directly — do not acknowledge the summary, do not recap what was happening, do not preface with "I'll continue" or similar. Pick up the last task as if the break never happened.`;

  return result;
}
```

### 5.5 Compact Boundary 메시지 (`dd6`)

```javascript
function dd6(trigger, preTokens, parentUuid, userContext, messagesSummarized) {
  return {
    type: "system",
    subtype: "compact_boundary",
    content: "Conversation compacted",
    isMeta: false,
    timestamp: new Date().toISOString(),
    uuid: generateUUID(),
    level: "info",
    compactMetadata: {
      trigger: trigger,        // "auto" 또는 "manual"
      preTokens: preTokens,    // compact 전 토큰 수
      userContext: userContext,
      messagesSummarized: messagesSummarized
    }
  };
}
```

## 6. 요약 프롬프트 구조

### 6.1 첫 압축 프롬프트 (`tr9`)

전체 대화를 요약. Analysis instruction(`or9` 또는 `sr9`) + 9개 섹션 구조:

```
Your task is to create a detailed summary of the conversation so far, paying close attention
to the user's explicit requests and your previous actions.

<<ANALYSIS_INSTRUCTION>>

Your summary should include the following sections:

1. Primary Request and Intent: Capture all of the user's explicit requests and intents in detail
2. Key Technical Concepts: List all important technical concepts, technologies, and frameworks
3. Files and Code Sections: Enumerate specific files and code sections examined, modified, or created.
   Pay special attention to the most recent messages and include full code snippets where applicable.
4. Errors and fixes: List all errors and how you fixed them. Pay special attention to user feedback.
5. Problem Solving: Document problems solved and ongoing troubleshooting.
6. All user messages: List ALL user messages that are not tool results. Critical for understanding feedback.
7. Pending Tasks: Outline any pending tasks explicitly asked to work on.
8. Current Work: Describe in detail precisely what was being worked on immediately before this summary.
   Include file names and code snippets.
9. Optional Next Step: List the next step related to the most recent work.
   IMPORTANT: ensure this step is DIRECTLY in line with the user's most recent explicit requests.
   Include direct quotes from the most recent conversation.

IMPORTANT: Do NOT use any tools. You MUST respond with ONLY the <summary>...</summary> block.
```

### 6.2 재압축 프롬프트 (`er9`)

이전 요약 이후의 최근 메시지만 대상:
```
Your task is to create a detailed summary of the RECENT portion of the conversation —
the messages that follow earlier retained context. The earlier messages are being kept
intact and do NOT need to be summarized.
```

동일한 9개 섹션이지만 "최근 메시지만" 대상.

### 6.3 Analysis Instruction 선택 (`P54`)

```javascript
function P54(defaultInstruction) {
  return featureFlag("tengu_lean_cast") ? sr9 : defaultInstruction;
}
```

- **`or9` (상세 분석)**: 각 메시지를 시간순으로 꼼꼼히 분석. 파일명, 코드, 함수 시그니처 등 구체적 디테일.
- **`sr9` (경량 분석, `tengu_lean_cast` 시)**: coverage 위주. "코드나 파일 내용은 `<summary>`에 남기고, `<analysis>`는 계획용 scratchpad로만 사용"

### 6.4 요약 응답 처리 (`Ao9`)

```javascript
function Ao9(rawText) {
  // <analysis> 태그 제거 (내부 사고 과정)
  text = text.replace(/<analysis>[\s\S]*?<\/analysis>/, "");
  // <summary> 태그에서 내용 추출
  let match = text.match(/<summary>([\s\S]*?)<\/summary>/);
  if (match) text = `Summary:\n${match[1].trim()}`;
  // 중복 줄바꿈 정리
  return text.replace(/\n\n+/g, "\n\n").trim();
}
```

## 7. Session Memory Compact (`RG1`)

`tengu_session_memory` + `tengu_sm_compact` 플래그가 모두 활성화되면 autocompact 전에 먼저 시도:

```javascript
async function RG1(messages, agentId, threshold) {
  if (!isSessionMemoryCompactEnabled()) return null;

  // session memory 로드
  let sessionMemory = await loadSessionMemory();
  if (!sessionMemory || isEmpty(sessionMemory)) return null;

  // session memory 기반으로 경량 compact 수행
  let result = buildSessionMemoryCompact(messages, sessionMemory, ...);
  let postCompactTokens = estimateTokens(result);

  // compact 후에도 threshold 초과하면 null 반환 (일반 compact로 fallback)
  if (threshold !== undefined && postCompactTokens >= threshold) return null;

  return result;
}
```

## 8. Microcompact 인프라

### 8.1 현재 상태

```javascript
// CF() - microcompact 함수 (현재 noop)
async function CF(messages, context, cacheSafeParams) {
  return xP4(), { messages: messages };  // 그대로 반환
}
```

### 8.2 상태 관리 시스템

```javascript
var HR8 = false;  // microcompact 활성 상태

function ld6() { HR8 = true;  bP4(); }  // compact 완료 후 활성화
function xP4() { HR8 = false; bP4(); }  // CF() 호출 시 비활성화
function uP4() { return HR8; }          // 상태 조회
function bP4() { listeners.forEach(cb => cb()); }  // 변경 알림

// compact 후 상태 관리
var BP4 = null;   // microcompact state handler
var rf6 = null;   // cached MC state
var jR8 = null;   // compact result (1회 소비)

function FP4() { let r = jR8; jR8 = null; return r; }  // 읽고 삭제
function SF() { if (rf6 && BP4) BP4.resetCachedMCState(rf6); jR8 = null; }  // 리셋
```

### 8.3 Compact 후 Cache Edit 흐름

```
1. Compact 발생 → ld6(): HR8=true, jR8에 결과 저장
2. 다음 API 호출 (message normalization 단계):
   → J6 = FP4()  → jR8 읽고 null로 리셋 (1회 소비)
   → E6 = QP4()  → pinnedEdits 읽기
   → zNz()에 전달 → cache_edits 블록을 메시지에 삽입
3. API 서버가 cache_edits를 처리하여 옛 캐시 정리
4. 다음 턴부터 jR8=null이므로 cache_edits 없음
```

### 8.4 미사용 상수

```
WoA = 180,000  // 아마 microcompact 트리거 threshold
ZoA = 40,000   // 아마 microcompact 버퍼
```

## 9. 실행 순서 (매 턴)

메인 루프에서의 실행 순서:

```
1. query_context_loading_start
2. 컨텍스트 로딩
3. query_context_loading_end

4. query_microcompact_start
5. CF() → microcompact (현재 noop)
6. query_microcompact_end

7. query_autocompact_start
8. w04() → autocompact 판단 및 실행
   ├─ dwY(): threshold 체크
   ├─ RG1(): session memory compact 시도
   └─ Uf6(): 일반 compact 수행
9. query_autocompact_end

10. query_setup_start
11. 쿼리 설정
12. query_setup_end

13. query_tool_schema_build_start
14. 도구 스키마 빌드
15. query_tool_schema_build_end

16. query_message_normalization_start
17. zNz() → 메시지 정규화 (cache_control, cache_edits 삽입)
18. query_message_normalization_end

19. query_client_creation_start
20. API 호출
```

## 10. UI 표시

### 10.1 Context Left 퍼센티지

```javascript
// Wz6()에서 계산
// autoCompact 활성 시 분모 = autoCompactThreshold (167K)
// autoCompact 비활성 시 분모 = effectiveWindow (180K)
percentLeft = max(0, round((denominator - currentTokens) / denominator * 100))
```

**UI 경고 조건:**
- `isAboveWarningThreshold` (tokens >= 147K)일 때만 표시
- autoCompact 활성: `"Context left until auto-compact: ${percentLeft}%"`
- autoCompact 비활성: `"Context low (${percentLeft}% remaining) · Run /compact to compact & continue"`

### 10.2 Context Bar

```javascript
// 카테고리별 토큰 계산
categories = [
  { name: "System prompt", tokens: systemPromptTokens },
  { name: "System tools", tokens: builtInToolTokens - skillTokens },
  { name: "MCP tools", tokens: mcpToolTokens },
  { name: "Custom agents", tokens: agentTokens },
  { name: "Memory files", tokens: claudeMdTokens },
  { name: "Skills", tokens: skillTokens },
  { name: "Messages", tokens: messageTokens },
];

// Autocompact buffer
if (autoCompactEnabled && threshold !== undefined)
  buffer = contextWindow - threshold;  // 200K - 167K = 33K
else
  buffer = VR8;  // 3K

// Free space
freeSpace = Math.max(0, contextWindow - usedTokens - buffer);
```

## 11. 환경변수 레퍼런스

| 환경변수 | 효과 | 기본값 |
|----------|------|--------|
| `DISABLE_COMPACT` | 모든 압축 비활성화 (수동 포함) | 미설정 |
| `DISABLE_AUTO_COMPACT` | 자동 압축만 비활성화 | 미설정 |
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | effectiveWindow의 N%에서 트리거 | 미설정 (기본 ~92.8%) |
| `CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` | blocking limit 커스텀 | 미설정 |
| `ENABLE_CLAUDE_CODE_SM_COMPACT` | session memory 압축 강제 활성화 | 미설정 |
| `DISABLE_CLAUDE_CODE_SM_COMPACT` | session memory 압축 강제 비활성화 | 미설정 |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | max output 토큰 오버라이드 | 모델별 |

## 12. 왜 120-130K 메시지에서 Compact가 발생하는가

### 12.1 `kV()`는 전체 API 요청 토큰을 측정

사용자가 보는 "메시지 토큰"과 `kV()`가 측정하는 값은 다르다:

```
kV() = input_tokens + cache_creation + cache_read + output_tokens
       ↑ 시스템 프롬프트, 도구 정의, 메모리, 메시지 히스토리 전부 포함
```

### 12.2 시스템 오버헤드

| 구성요소 | 토큰 (추정) | 비고 |
|----------|-----------|------|
| 시스템 프롬프트 | ~3-5K | 고정 |
| Built-in 도구 | ~10-15K | 도구 수에 비례 |
| MCP 도구 | ~10-20K | pencil, context7, playwright 등 |
| Memory (CLAUDE.md) | ~5-8K | oh-my-claudecode 설정이 길면 더 큼 |
| Skills | ~2-3K | 로드된 스킬 수에 비례 |
| **소계** | **~30-50K** | 설정에 따라 크게 변동 |

### 12.3 실제 계산

```
메시지 히스토리:  ~130K
시스템 오버헤드:  ~30K
출력 토큰:       ~7K
─────────────────────
kV() 합계:       ~167K  ← autoCompactThreshold 도달!
```

### 12.4 변동 요인

| 요인 | 일찍 트리거 | 늦게 트리거 |
|------|-----------|-----------|
| 출력 토큰 | thinking 긴 응답 (~30K) | 짧은 응답 (~2K) |
| MCP 도구 | 모두 loaded | deferred 상태 |
| 서버 compaction | 비활성 | 150K에서 선제 개입 |
| Session Memory | 비활성/실패 | 성공 시 경량 compact |
| CLAUDE.md 크기 | 크면 오버헤드 증가 | 작으면 여유 |

## 13. 재압축 감지 및 텔레메트리

```javascript
// compact 후 다음 턴에서도 여전히 threshold 초과하면 재압축
telemetry("tengu_compact", {
  preCompactTokenCount: beforeTokens,
  postCompactTokenCount: afterTokens,
  truePostCompactTokenCount: realAfterTokens,
  autoCompactThreshold: threshold,
  willRetriggerNextTurn: afterTokens >= threshold,  // 재압축 예고
  isAutoCompact: isAuto,
  isRecompactionInChain: tracking.isRecompactionInChain,
  turnsSincePreviousCompact: tracking.turnsSincePreviousCompact,
});
```

## 14. PreCompact 훅

```javascript
async function cf6(hookInput, signal) {
  let input = {
    hook_event_name: "PreCompact",
    trigger: hookInput.trigger,  // "auto" 또는 "manual"
    custom_instructions: hookInput.customInstructions
  };

  let results = await executeHooks(input, signal);

  // exit code 2 → compaction 차단
  // 성공 출력 → custom instructions로 추가
  return {
    newCustomInstructions: successOutputs.join("\n"),
    userDisplayMessage: statusMessages.join("\n")
  };
}
```

---

## 용어 정리

| 코드명 | 실제 의미 |
|--------|----------|
| `kV()` | 현재 총 토큰 수 (API usage 기반) |
| `EY6()` | effective window (context - output buffer) |
| `od6()` | autocompact threshold |
| `Wz6()` | threshold 비교 및 상태 계산 |
| `kS()` | autocompact 활성화 여부 |
| `dwY()` | autocompact 트리거 판단 |
| `w04()` | autocompact 실행 진입점 |
| `Uf6()` | 실제 compaction 수행 |
| `CF()` | microcompact (현재 noop) |
| `RG1()` | session memory compact |
| `SwY()` | 보존할 메시지 선택 |
| `JR8()` | tool_use/result 쌍 보존 경계 조정 |
| `zP4()` | compact용 API 호출 |
| `Ip6()` | 요약을 시스템 메시지로 포맷 |
| `Ao9()` | <analysis>/<summary> 태그 파싱 |
| `wn()` | 최종 메시지 배열 조립 |
| `dd6()` | compact boundary 메시지 생성 |
| `cf6()` | PreCompact 훅 실행 |
| `NE()` | 마지막 API usage에서 총 토큰 추출 |
| `Ap6()` | 텍스트 기반 토큰 추정 |

---

*분석 대상: Claude Code v2.1.70 (npm @anthropic-ai/claude-code)*
*분석 일자: 2026-03-06*
