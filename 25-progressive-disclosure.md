# Deferred Tool & ToolSearch — Progressive Disclosure 분석

> Claude Code는 **progressive disclosure** 패턴으로 도구 schema를 관리한다. 모델에게 도구 이름만 먼저 노출하고, ToolSearch로 명시적으로 요청한 도구의 full schema만 API 요청에 포함시키는 방식이다. 구현 메커니즘으로는 **lazy loading**에 해당한다. v2.1.38에서는 MCP 도구만 deferred였으나, v2.1.70에서는 피처 플래그 `tengu_defer_all_bn4`를 통해 **모든 내장 도구까지 deferred로 전환**하는 대규모 변경이 이루어졌다.

## 용어 정리

| 용어 | 관점 | 설명 |
|:--|:--|:--|
| **Progressive disclosure** | 설계 의도 | 모델(agent)에게 정보를 단계적으로 공개 — 이름 먼저, schema는 필요할 때. Claude Code 엔지니어가 실제로 사용하는 용어 |
| **Lazy loading** | 구현 메커니즘 | 자원을 필요한 시점에 로드하는 기술 패턴. 토큰 절감이 주목적 |

---

## 1. Eager vs Deferred 도구 개념

| 구분 | Eager 도구 | Deferred 도구 |
|:--|:--|:--|
| **로딩 시점** | 매 API 요청마다 `tools` 배열에 포함 | ToolSearch로 검색/선택한 후에만 포함 |
| **컨텍스트 비용** | 매 요청마다 schema 토큰 소비 | 사용 시에만 토큰 소비 |
| **안내 방식** | 시스템 프롬프트에 전체 description 포함 | `<available-deferred-tools>` 태그로 이름만 나열 |
| **사용 가능성** | 즉시 호출 가능 | ToolSearch로 먼저 로드해야 호출 가능 |

**ToolSearch의 역할**: deferred 도구의 "게이트키퍼"로, 모델이 deferred 도구를 사용하려면 반드시 ToolSearch를 먼저 호출해야 한다. ToolSearch 자체는 **절대로 deferred되지 않는다**.

---

## 2. 버전별 비교

| 항목 | v2.1.38 (2월) | v2.1.70 (3월) |
|:--|:--|:--|
| `isDeferredTool` 함수 | `BW()` — MCP만 | `qG()` — 3단계 판정 |
| `tengu_defer_all_bn4` | 없음 | 있음 (기본값 `true`) |
| `shouldDefer` 사용 횟수 | 3회 | 21회 |
| `searchHint` 사용 횟수 | 0회 | 29회 (도구별 검색 힌트) |
| `select:` 다중 선택 | 미지원 | `select:Read,Edit,Grep` 지원 |
| deferred 안내 메시지 | 고정 텍스트 | 피처플래그로 분기 (`tengu_glacier_2xr`) |
| eager 도구 수 (API 트래픽) | 22개 (전부) | 21개 (플래그 미활성 시) |
| 현재 세션 (플래그 활성) | — | 최소한만 eager (Bash, Read, Edit 등 ~8개) |

---

## 3. 핵심 코드 분석

### 3.1 isDeferredTool 함수 진화

#### v2.1.38: `BW()` — MCP만 체크

```javascript
// cli.js:1417
function BW(A) {
  if (A.isMcp === true) return true;
  return false;
}
```

단순하다. MCP 서버에서 온 도구(`isMcp === true`)만 deferred 대상이다. 내장 도구(Bash, Read, Edit 등)는 항상 eager.

#### v2.1.70: `qG()` — 3단계 판정 로직

```javascript
// cli.js:1520
function qG(A) {
  if (A.isMcp === true) return true;          // 1) MCP 도구 → 항상 deferred
  if (A.name === zT) return false;            // 2) ToolSearch 자신 → 절대 eager
  if (e8("tengu_defer_all_bn4", true))        // 3) 피처플래그 (기본 true)
    return true;                              //    → 모든 도구 deferred
  return A.shouldDefer === true;              // 4) 개별 shouldDefer 표시
}
```

핵심 변화:
1. **ToolSearch 자체는 절대 deferred 안 됨** — 이것이 빠지면 deferred 도구를 로드할 방법이 없어진다
2. **`tengu_defer_all_bn4` 플래그가 `true`(기본값)이면 모든 도구가 deferred** — 내장 도구까지 포함
3. 플래그가 꺼져 있어도 `shouldDefer === true`인 개별 도구는 deferred 가능

### 3.2 searchHint — 도구 검색 지원 메타데이터 (v2.1.70 신규)

v2.1.70에서는 각 도구에 `searchHint` 필드가 추가되어, ToolSearch가 더 정확하게 도구를 찾을 수 있게 했다:

```javascript
// 도구 정의 예시
o9 = {
  name: "Read",
  searchHint: "read files, images, PDFs, notebooks",
  // ...
}
```

**전체 searchHint 목록** (29개):

| 도구 | searchHint |
|:--|:--|
| TodoWrite | manage the session task checklist |
| Read | read files, images, PDFs, notebooks |
| (structured output) | return the final response as structured JSON |
| Agent | delegate work to a subagent |
| Skill | invoke a slash-command skill |
| Write | create or overwrite files |
| Grep | search file contents with regex (ripgrep) |
| Glob | find files by name pattern or wildcard |
| NotebookEdit | edit Jupyter notebook cells (.ipynb) |
| WebFetch | fetch and extract content from a URL |
| TaskStop | kill a running background task |
| TaskOutput | read output/logs from a background task |
| WebSearch | search the web for current information |
| ExitPlanMode | present plan for approval and start coding |
| AskUserQuestion | prompt the user with a multiple-choice question |
| LSP | code intelligence (definitions, references, symbols, hover) |
| (MCP resource list) | list resources from connected MCP servers |
| (MCP resource read) | read a specific MCP resource by URI |
| EnterPlanMode | switch to plan mode to design an approach before coding |
| EnterWorktree | create an isolated git worktree and switch into it |
| TaskCreate | create a task in the task list |
| TaskGet | retrieve a task by ID |
| TaskUpdate | update a task |
| TaskList | list all tasks |
| TeamCreate | create a multi-agent swarm team |
| TeamDelete | disband a swarm team and clean up |
| SendMessage | send messages to agent teammates (swarm protocol) |
| Edit | modify file contents in place |
| Bash | execute shell commands |

피처 플래그 `tengu_tst_hint_m7r`(기본 `false`)가 `true`일 때, `<available-deferred-tools>` 목록에 searchHint가 표시된다:

```javascript
// cli.js:1520
function op6(A) {
  if (e94() && A.searchHint)
    return `${A.name} — ${A.searchHint}`;
  return A.name;
}
```

### 3.3 ToolSearch 도구 구현

ToolSearch는 3가지 검색 모드를 지원한다:

#### (1) 키워드 검색 (fuzzy matching)
```
query: "slack message"
→ deferred 도구 중 "slack", "message" 키워드로 스코어링
→ 상위 max_results개 반환
```

스코어링 로직 (`Us9` 함수):
- 도구 이름 파트 정확 일치: +10점 (MCP: +12)
- 도구 이름 파트 부분 일치: +5점 (MCP: +6)
- 도구 전체 이름 포함: +3점
- searchHint 일치: +4점
- 프롬프트 텍스트 일치: +2점

#### (2) 직접 선택 (`select:` 구문)
```
query: "select:NotebookEdit"         // 단일
query: "select:Read,Edit,Grep"       // 다중 (v2.1.70 신규)
```

#### (3) 필수 키워드 (`+` prefix)
```
query: "+slack send"
→ "slack"이 반드시 매칭되는 도구만 필터링 → "send"로 랭킹
```

#### 반환 형식

ToolSearch의 반환값은 특별하다 — `tool_reference` 타입으로 반환:

```javascript
// 매칭된 도구가 있을 때
{
  type: "tool_result",
  tool_use_id: q,
  content: A.matches.map((K) => ({
    type: "tool_reference",    // ← 핵심: 이 타입이 도구를 "로드"시킨다
    tool_name: K
  }))
}
```

`tool_reference` 응답을 받으면, Claude Code 클라이언트가 해당 도구의 full schema를 **다음 API 요청의 `tools` 배열에 추가**한다.

### 3.4 `<available-deferred-tools>` 태그 주입

deferred 도구 목록은 첫 번째 user 메시지 앞에 시스템 리마인더로 삽입된다:

#### v2.1.38

```javascript
// cli.js:5776-5778
if (z1) f = [c6({content: `<available-deferred-tools>
${z1}
</available-deferred-tools>`, isMeta: true}), ...f]
```

#### v2.1.70

```javascript
// cli.js:6072-6074
if (H6) V = [t1({content: `<available-deferred-tools>
${H6}
</available-deferred-tools>`, isMeta: true}), ...V]
```

v2.1.70에서는 피처플래그 `tengu_glacier_2xr`에 따라 안내 문구가 달라진다:

```javascript
function Bs9() {
  return e8("tengu_glacier_2xr", false)
    ? "Deferred tools are announced via system-reminder messages in the conversation
       as they become available — look for those messages for the list of tools you
       can discover."
    : "Look for <available-deferred-tools> messages in the conversation for the list
       of tools you can discover.";
}
```

### 3.5 API 요청에서의 도구 필터링

실제 API 요청을 보낼 때, deferred 도구는 기본적으로 제외되되, 모델이 이미 사용 중인 도구는 포함된다:

#### v2.1.38

```javascript
// cli.js:5776 (lOq 함수 내)
let O = await XU1(w.model, Y, w.getToolPermissionContext, w.agents, "query");
// O가 true면 ToolSearch 활성화

if (O) {
  let z1 = tBA(A);  // 이전 메시지에서 사용된 도구 이름 추출
  _ = Y.filter((Y1) => {
    if (!BW(Y1)) return true;           // eager 도구 → 포함
    if (Y1.name === dM) return true;    // ToolSearch → 포함
    return z1.has(Y1.name);             // 이미 사용된 deferred 도구 → 포함
  });
} else {
  _ = Y.filter((z1) => z1.name !== dM); // deferred 없으면 ToolSearch 제거
}
```

핵심 포인트:
- `tBA(A)`: 대화 이력에서 모델이 이미 호출한 도구 이름을 추출
- 한번 ToolSearch로 로드된 도구는 이후 요청에서도 `tools` 배열에 계속 포함

---

## 4. API 트래픽 증거

### 4.1 구버전 덤프 (2026-03-06, proxy — v2.1.70 기반이나 플래그 미활성)

```
파일: 2026-03-06T152636.670-req.json
도구 수: 21
도구 목록: Agent, TaskOutput, Bash, Glob, Grep, ExitPlanMode, Read, Edit,
          Write, NotebookEdit, WebFetch, WebSearch, TaskStop,
          AskUserQuestion, Skill, EnterPlanMode, TaskCreate, TaskGet,
          TaskUpdate, TaskList, EnterWorktree
```

- 21개 도구가 모두 eager로 포함
- `<available-deferred-tools>` 태그가 메시지에 **없음**
- `tengu_defer_all_bn4` 플래그가 아직 활성화되지 않은 상태로 추정
- ToolSearch가 `tools` 배열에 포함되지 않음 → deferred 대상이 MCP뿐이고, MCP 서버가 없어서 ToolSearch 자체가 비활성

### 4.2 현재 세션 (2026-03-09, 본 대화)

현재 세션의 `<available-deferred-tools>` 태그에 나열된 deferred 도구:

```
AskUserQuestion, CronCreate, CronDelete, CronList, EnterPlanMode,
EnterWorktree, ExitPlanMode, LSP, NotebookEdit, SendMessage,
TaskCreate, TaskGet, TaskList, TaskOutput, TaskStop, TaskUpdate,
TeamCreate, TeamDelete, WebFetch, WebSearch,
mcp__mermaid__generate_mermaid_diagram,
mcp__pencil__batch_design, mcp__pencil__batch_get, ...
mcp__plugin_playwright_playwright__browser_*, ...
```

현재 eager로 남아있는 도구 (시스템 프롬프트에 full schema 포함):
- **Agent** (subagent 위임)
- **Bash** (셸 명령 실행)
- **Glob** (파일 패턴 검색)
- **Grep** (내용 검색)
- **Read** (파일 읽기)
- **Edit** (파일 편집)
- **Write** (파일 생성)
- **Skill** (스킬 실행)
- **ToolSearch** (deferred 도구 검색 — 항상 eager)

→ **22개 → ~9개**로 eager 도구가 대폭 축소됨

### 4.3 v2.1.38과 현재 세션 비교

| 구분 | v2.1.38 (2월) | 현재 (3월, 플래그 활성) |
|:--|:--|:--|
| eager 도구 | 22개 (전부) | ~9개 (핵심만) |
| deferred 도구 | MCP만 (0-수십개) | 40+개 (내장 + MCP) |
| ToolSearch 활성 | MCP 있을 때만 | 항상 활성 |
| `<available-deferred-tools>` | MCP 도구명만 | 내장 + MCP 도구명 |

---

## 5. 피처 플래그 체계

Claude Code는 서버사이드 피처 플래그로 동적 도구 로딩 동작을 제어한다:

| 플래그 | 기본값 | 역할 |
|:--|:--|:--|
| `tengu_defer_all_bn4` | `true` | **모든 도구** deferred 전환 (핵심 플래그) |
| `tengu_tst_hint_m7r` | `false` | searchHint를 deferred 목록에 표시 |
| `tengu_glacier_2xr` | `false` | deferred 도구 안내 메시지 방식 변경 |
| `tengu_kv7_prompt_sort` | `false` | 도구 목록 알파벳 정렬 |
| `tengu_tst_names_in_messages` | `false` | 메시지 내 도구명 주입 |
| `tengu_summarize_tool_results` | `false` | 도구 결과 요약 가이드 주입 |

이 플래그들은 점진적 롤아웃을 위해 설계되었다:
1. 먼저 `shouldDefer`로 개별 도구를 선택적 deferred (보수적)
2. `tengu_defer_all_bn4`로 전체 전환 (공격적)
3. `tengu_tst_hint_m7r`로 검색 성능 개선
4. `tengu_glacier_2xr`로 안내 방식 최적화

---

## 6. 도구명 변경 추적

v2.1.38 → v2.1.70 사이에 발생한 도구 이름 변경:

| 변경 유형 | 상세 |
|:--|:--|
| **이름 변경** | `Task` → `Agent` (subagent 실행 도구) |
| **분리** | 기존 `Task` 역할 → `TaskCreate`, `TaskGet`, `TaskUpdate`, `TaskList`, `TaskOutput`, `TaskStop` |
| **deferred 이동** | `TeamCreate`, `TeamDelete`, `SendMessage`, `TodoWrite` → deferred로 전환 |
| **신규 추가** | `EnterWorktree`, `CronCreate`, `CronDelete`, `CronList`, `LSP` |

v2.1.38 도구 목록 (eager 22개):
```
Task, Bash, Glob, Grep, Read, Edit, Write, NotebookEdit,
WebFetch, WebSearch, AskUserQuestion, Skill, EnterPlanMode,
ExitPlanMode, TodoWrite, TeamCreate, TeamDelete, SendMessage,
ToolSearch, + MCP 도구들
```

v2.1.70 도구 목록 (proxy 덤프, 플래그 미활성 시 eager 21개):
```
Agent, TaskOutput, Bash, Glob, Grep, ExitPlanMode, Read, Edit,
Write, NotebookEdit, WebFetch, WebSearch, TaskStop,
AskUserQuestion, Skill, EnterPlanMode, TaskCreate, TaskGet,
TaskUpdate, TaskList, EnterWorktree
```

---

## 7. 토큰 절감 효과 추정

### 도구 schema의 토큰 비용

각 도구는 API 요청의 `tools` 배열에 JSON schema로 포함된다. schema에는 다음이 포함:
- `name`: 도구 이름
- `description`: 전체 설명 프롬프트 (수백~수천 자)
- `input_schema`: JSON Schema (파라미터 정의)

도구별 추정 토큰:

| 도구 | 프롬프트 길이 | 추정 토큰 |
|:--|:--|:--|
| Bash | ~3,000자 | ~750 |
| Read | ~2,000자 | ~500 |
| Agent | ~5,000자+ | ~1,500 |
| Edit | ~1,500자 | ~400 |
| 평균 | ~2,000자 | ~500-800 |

### 절감 계산

| 시나리오 | eager 수 | schema 토큰 | 절감 |
|:--|:--|:--|:--|
| v2.1.38 (전부 eager) | 22개 | ~13,000-17,000 | 기준선 |
| v2.1.70 (플래그 활성) | ~9개 | ~5,000-7,000 | ~8,000-10,000 토큰/요청 |
| **요청당 절감** | | | **~40-60%** |

실제 절감은 대화 길이에 따라 복합적:
- **짧은 대화 (5턴)**: ~40,000-50,000 토큰 절감
- **긴 대화 (50턴)**: ~400,000-500,000 토큰 절감
- **캐시 프롬프트 사용 시**: 읽기 캐시로 실질 비용은 더 낮지만, 최초 캐시 생성 비용은 동일

deferred 도구가 실제로 사용되면 해당 시점부터 eager와 동일한 비용이 발생하므로, 절감 효과는 "사용하지 않는 도구"의 수에 비례한다.

---

## 8. 동적 도구 업데이트 메커니즘

대화 중에 MCP 서버가 연결/해제되면, `deferred_tools_delta` 이벤트로 도구 목록이 업데이트된다:

```javascript
// cli.js:6551-6555
case "deferred_tools_delta": {
  let K = [];
  if (A.addedLines.length > 0)
    K.push(`The following deferred tools are now available via ToolSearch:
${A.addedLines.join('\n')}`);
  if (A.removedNames.length > 0)
    K.push(`The following deferred tools are no longer available
(their MCP server disconnected). Do not search for them —
ToolSearch will return no match:
${A.removedNames.join('\n')}`);
  return r5([t1({content: K.join('\n\n'), isMeta: true})]);
}
```

MCP 서버가 아직 연결 중(`pending`)이면, ToolSearch가 이를 알려준다:

```javascript
// ToolSearch 반환값에 pending 서버 포함
if (A.pending_mcp_servers && A.pending_mcp_servers.length > 0)
  K += `. Some MCP servers are still connecting:
${A.pending_mcp_servers.join(", ")}.
Their tools will become available shortly — try searching again.`;
```

---

## 9. 참조 파일 위치

| 파일 | 주요 내용 | 핵심 라인 |
|:--|:--|:--|
| `npm_2.1.38/cli.js` | v2.1.38 `isDeferredTool` (`BW`), ToolSearch 프롬프트 | L1417-1500 |
| `npm_2.1.38/cli.js` | v2.1.38 `<available-deferred-tools>` 주입 | L5776-5779 |
| `npm_2.1.70/cli.js` | v2.1.70 `isDeferredTool` (`qG`), searchHint, 피처플래그 | L1520 |
| `npm_2.1.70/cli.js` | v2.1.70 ToolSearch 구현 (`ap6`) | L1520-L1600+ |
| `npm_2.1.70/cli.js` | v2.1.70 `<available-deferred-tools>` 주입 | L6072-6074 |
| `npm_2.1.70/cli.js` | deferred_tools_delta 이벤트 처리 | L6551-6556 |
| `proxy/dumps/2026-03-06*.json` | 플래그 미활성 시 eager 21개 도구 확인 | — |

---

## 10. 요약

1. **v2.1.38**: MCP 도구만 deferred. 내장 도구 22개는 항상 eager. ToolSearch는 MCP 서버가 있을 때만 활성화.

2. **v2.1.70**: `tengu_defer_all_bn4` 플래그(기본 `true`)로 **모든 내장 도구까지 deferred 가능**. searchHint 29개 추가, 다중 select 지원 등 ToolSearch 기능 강화.

3. **현재 세션**: eager ~9개 + deferred 40+개 구성. 요청당 ~40-60% 토큰 절감 추정.

4. **점진적 롤아웃**: 6개의 피처 플래그로 동작을 세밀하게 제어. 서버사이드에서 원격으로 롤백 가능.

5. **핵심 설계 원칙**: ToolSearch는 절대 deferred되지 않음. 이미 사용된 도구는 후속 요청에서 자동으로 eager에 복원.
