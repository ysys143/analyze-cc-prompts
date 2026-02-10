# Claude Code Agent Teams 내부 아키텍처 심층 분석 보고서

> **분석 대상**: Claude Code v2.1.38 (npm 패키지)
> **소스코드**: `npm_2.1.38/cli.js` (7,618줄, 번들된 단일 파일)
> **공식 문서**: https://code.claude.com/docs/en/agent-teams
> **분석 일자**: 2026-02-10
> **분석 팀**: 3명의 전문 연구 에이전트 (comm-researcher, arch-researcher, compare-researcher) + 리드

---

## 목차

1. [조사 방법론](#1-조사-방법론)
2. [팀 아키텍처 총론](#2-팀-아키텍처-총론)
3. [내부 통신 프로토콜](#3-내부-통신-프로토콜)
4. [팀 저장 구조와 파일 시스템](#4-팀-저장-구조와-파일-시스템)
5. [Task 관리 시스템](#5-task-관리-시스템)
6. [Teammate 스폰 메커니즘](#6-teammate-스폰-메커니즘)
7. [도구 접근 제어와 Delegate 모드](#7-도구-접근-제어와-delegate-모드)
8. [Subagent vs Agent Teams 심층 비교](#8-subagent-vs-agent-teams-심층-비교)
9. [문서에 없는 발견 사항](#9-문서에-없는-발견-사항)
10. [아키텍처 다이어그램](#10-아키텍처-다이어그램)
11. [부록: 함수 매핑 테이블](#11-부록-함수-매핑-테이블)

---

## 1. 조사 방법론

### 1.1 원본 프롬프트

이 보고서는 다음 프롬프트에 의해 시작되었습니다:

> 에이전트 팀을 만들어서 Claude Code Agent Teams의 내부 구조를 조사해줘.
>
> 베이스 경로: /Users/jaesolshin/Documents/GitHub/analyze-cc-prompts/
> 참고 문서: https://code.claude.com/docs/en/agent-teams
> 소스코드: npm_2.1.38/ 폴더의 소스코드를 직접 탐색해서 문서에 없는 구현 세부사항을 찾아줘.
>
> 첫 번째 teammate는 에이전트 간 내부 통신 프로토콜을 조사하고(mailbox 시스템, message/broadcast 메커니즘, 자동 전달 방식), 두 번째는 팀 아키텍처와 저장 구조를 조사하고(config.json, task list, 파일 락킹), 세 번째는 subagent와 agent teams의 차이를 context 관리·토큰 비용·조율 방식 관점에서 심층 비교 분석해줘.
>
> 중요: 각 teammate는 조사 완료 후 다른 teammate에게 직접 메시지를 보내서 발견 내용을 공유하고, 상대의 발견에 대해 질문·반박·교차 검증을 수행해야 해. 리드에게만 보고하는 게 아니라 팀원 간 P2P 대화가 있어야 함.

### 1.2 조사 팀 구성

| 에이전트 | 역할 | 담당 영역 |
|---------|------|----------|
| **comm-researcher** | 통신 프로토콜 연구원 | Mailbox, 메시지/브로드캐스트, 자동 전달, 프로토콜 메시지 |
| **arch-researcher** | 팀 아키텍처 연구원 | config.json, task 저장, 파일 락킹, 스폰, 라이프사이클 |
| **compare-researcher** | 비교 분석 연구원 | Subagent vs Teams (context, 토큰, 조율) |
| **team-lead** | 리드 | 조율, 종합, 최종 보고서 작성 |

### 1.3 조사 방법

1. **키워드 검색**: `mailbox`, `SendMessage`, `teammate`, `team_context`, `idle`, `shutdown` 등의 키워드로 관련 코드 위치 파악
2. **함수 추적**: `oSY`, `aSY`, `sSY`, `tSY`, `eSY`, `AhY`, `qhY` 등 SendMessage의 각 타입별 핸들러 함수를 식별하고 내부 로직 분석
3. **데이터 흐름 추적**: `f9()` (메시지 기록) → 파일 시스템 → `Ld()` (메시지 읽기) → `K2z()` (시스템 리마인더 주입) 순서로 메시지 전달 경로 재구성
4. **공식 문서 대조**: https://code.claude.com/docs/en/agent-teams 의 공식 설명과 소스 구현 비교
5. **구조체 분석**: Zod 스키마 정의와 JSON Schema 정의를 통해 메시지 포맷 역공학
6. **P2P 교차 검증**: 각 연구원이 조사 완료 후 다른 2명에게 직접 메시지를 보내 발견 공유 및 상호 질문/반박 수행
7. **4차에 걸친 보충 보고서**: 교차 검증을 통해 원본 보고서의 오류 수정 및 새로운 발견 추가

### 1.4 메타적 자기 참조

이 보고서 자체가 Agent Teams의 동작 실례입니다. 팀 생성(TeamCreate), 태스크 할당(TaskCreate/TaskUpdate), 에이전트 스폰(Task tool with team_name), P2P 메시지(SendMessage), idle 알림 수신, 최종 정리(TeamDelete)까지 전체 라이프사이클을 체험하면서 조사했습니다.

### 1.5 분석의 한계

1. **코드 난독화**: minified JavaScript로 인해 변수/함수명이 원래 의미를 잃었으나, 문자열 리터럴과 구조적 분석으로 대부분 복원
2. **동적 동작**: 런타임에서만 확인 가능한 동작(실제 폴링 타이밍, 동시성 문제 등)은 코드 분석만으로 완벽히 검증 불가
3. **Tmux 경로**: tmux 기반 실행의 상세 동작은 실행 환경 의존적이라 코드 분석에 한계
4. **버전 특이성**: v2.1.38 기준 분석이며 이후 버전에서 변경될 수 있음

---

## 2. 팀 아키텍처 총론

### 2.1 아키텍처 구성 요소

공식 문서에서 4가지 구성 요소를 명시합니다:

| 구성 요소 | 역할 | 저장 위치 |
|----------|------|----------|
| **Team Lead** | 팀을 생성하고, teammate를 스폰하며, 작업을 조율하는 메인 세션 | `~/.claude/teams/{team-name}/config.json` |
| **Teammates** | 각각 독립적으로 작업하는 별도 Claude Code 인스턴스 | config.json `members` 배열 |
| **Task List** | 팀원이 claim하고 완료하는 공유 작업 목록 | `~/.claude/tasks/{team-name}/` |
| **Mailbox** | 에이전트 간 통신을 위한 메시징 시스템 | `~/.claude/teams/{team-name}/inboxes/` |

### 2.2 도구 체계

Agent Teams 활성화 시 추가되는 도구 3개:

```
TeamCreate  - 팀 생성 (팀 파일 + 태스크 디렉토리 동시 생성)
TeamDelete  - 팀 정리 (멤버 전원 종료 후에만 가능)
SendMessage - 메시지 전송 (DM, 브로드캐스트, 프로토콜)
```

이 도구들은 `l8()` (팀 모드 활성 여부) 확인 후에만 노출됩니다:

```javascript
// cli.js 내부
...l8()?[zhY(),whY(),HhY()]:[]...
// zhY() = TeamCreateTool, whY() = TeamDeleteTool, HhY() = SendMessageTool
```

### 2.3 실행 엔진의 동일성 (교차 검증으로 확인)

**핵심 발견**: Subagent와 Teams의 in-process teammate는 **동일한 실행 엔진 `ZR()` 함수**를 공유합니다.

```
Subagent:  Task tool → dR() generator → ZR() (main agent loop)
Teammate:  Spawn → nM6() → GVY() → ZR() (main agent loop)
```

차이는 실행 엔진이 아니라 **통신/조율 레이어**에만 존재합니다. 이는 compare-researcher와 arch-researcher 간 교차 검증에서 확인된 사항입니다.

---

## 3. 내부 통신 프로토콜

### 3.1 Mailbox 시스템

#### 저장 방식: 파일 기반 JSON

Mailbox는 메모리나 IPC가 아닌 **파일 시스템 기반**으로 구현됩니다.

- **Inbox 경로**: `~/.claude/teams/{team-name}/inboxes/{agent-name}.json`
- **경로 생성**: `as(agentName, teamName)` 함수
- **이름 정제**: `i_1(name)` → `name.replace(/[^a-zA-Z0-9_-]/g, "-")`
- **디렉토리 생성**: `eZY(teamName)` → `mkdirSync({recursive: true})`

#### 메시지 포맷

각 inbox 파일은 JSON 배열이며, 개별 메시지 객체:

```json
{
  "from": "agent-name",
  "text": "메시지 내용 (프로토콜 메시지는 JSON 직렬화)",
  "timestamp": "2026-02-10T03:10:00.000Z",
  "color": "blue",
  "summary": "메시지 요약",
  "read": false
}
```

프로토콜 메시지(shutdown, plan_approval 등)는 `text` 필드에 `JSON.stringify()`된 구조체가 들어갑니다.

#### 핵심 Mailbox 함수

| 원본 함수명 | 난독화명 | 역할 |
|---|---|---|
| writeToMailbox | `f9()` | 수신자 inbox에 메시지 쓰기 |
| readMailbox | `Ld()` | 에이전트 inbox 전체 읽기 |
| readUnreadMessages | `z51()` | 안 읽은 메시지만 필터링 |
| markMessageAsReadByIndex | `JQ1()` | 특정 인덱스 메시지 읽음 처리 |
| markMessagesAsRead | `XQ1()` | 전체 읽음 처리 |
| markMessagesAsReadByPredicate | `QvA()` | 조건부 읽음 처리 |
| clearMailbox | `AfY()` | inbox 비우기 (`[]`로 초기화) |
| getInboxPath | `as()` | inbox 파일 경로 계산 |
| formatTeammateMessages | `qfY()` | 메시지를 `<teammate-message>` XML 태그로 래핑 |

### 3.2 SendMessage 도구: 5가지 메시지 타입

`SendMessage`는 `zod`의 `discriminatedUnion`으로 정의된 5가지 메시지 타입을 지원합니다:

```javascript
// 입력 스키마 (Zod)
z.discriminatedUnion("type", [
  pSY,  // "message" - DM
  dSY,  // "broadcast" - 전체 메시지
  cSY,  // "shutdown_request" - 종료 요청
  lSY,  // "shutdown_response" - 종료 응답
  iSY   // "plan_approval_response" - 계획 승인/거부
])
```

JSON Schema:

```json
{
  "type": { "enum": ["message", "broadcast", "shutdown_request", "shutdown_response", "plan_approval_response"] },
  "recipient": { "type": "string" },
  "content": { "type": "string" },
  "summary": { "type": "string" },
  "request_id": { "type": "string" },
  "approve": { "type": "boolean" }
}
```

#### 3.2.1 message (DM)

```
발신자 → oSY(input, context)
  │
  ├─ 1. AppState에서 teamContext 취득
  ├─ 2. 수신자 이름 정규화: qi4(recipient) → '@' 접두사 제거
  ├─ 3. 발신자 이름 결정: g5() || (Dz() ? "teammate" : K2)
  ├─ 4. 발신자 색상 취득: b$()
  ├─ 5. 메시지 객체 구성: { from, text, summary, timestamp, color }
  └─ 6. f9(recipientName, message, teamName) → 수신자의 inbox 파일에 직접 쓰기
```

#### 3.2.2 broadcast

```
발신자 → aSY(input, context)
  │
  ├─ 1. config.json에서 전체 멤버 목록 조회: M51(teamName)
  ├─ 2. 발신자 자신을 제외한 멤버 필터링
  ├─ 3. 각 멤버에 대해 f9() 개별 호출
  └─ 결과: { recipients: [...], message: "Message broadcast to N teammate(s)" }
```

**broadcast = N개의 개별 DM** (for 루프로 각 멤버의 inbox에 개별 쓰기). 공식 문서의 "비용이 N에 비례"하는 이유.

#### 3.2.3 shutdown_request

```
리드 → sSY(input, context)
  │
  ├─ 1. 고유 request_id 생성: vP1("shutdown", recipientName)
  │     → "shutdown-{timestamp}@{target}" 형식
  ├─ 2. 구조화된 종료 요청 메시지 구성: lP1({requestId, from, reason})
  ├─ 3. JSON.stringify 후 f9()로 수신자 mailbox에 기록
  └─ 결과: { request_id, target }
```

#### 3.2.4 shutdown_response (approve)

```
팀원 → tSY(input, context)
  │
  ├─ 1. 팀/에이전트 정보 조회
  ├─ 2. backendType 확인 (in-process vs tmux)
  ├─ 3. 승인 메시지 구성: mvA({requestId, from, paneId, backendType})
  ├─ 4. f9()로 team-lead의 mailbox에 승인 전달
  ├─ 5-a. In-process인 경우:
  │       → AppState.tasks[taskId].abortController.abort()
  │       → 해당 에이전트 루프 즉시 종료
  └─ 5-b. Tmux인 경우:
          → setImmediate(() => nK(0, "other"))
          → 프로세스 종료 예약
```

#### 3.2.5 shutdown_response (reject)

```
팀원 → eSY(input)
  │
  ├─ 1. 거부 메시지 구성: FvA({requestId, from, reason})
  ├─ 2. f9()로 team-lead의 mailbox에 거부 전달
  └─ 결과: 팀원은 계속 작업
```

#### 3.2.6 plan_approval_response

```
리드 → AhY(input, context) [승인] / qhY(input, context) [거부]
  │
  ├─ 1. 리드 권한 검증: PM(teamContext) → 팀 리드만 가능
  ├─ 2-a. 승인 시:
  │       permissionMode를 현재 세션의 모드에서 결정
  │       → "plan"이나 "delegate"면 "default"로, 아니면 그대로
  │       → f9()로 팀원에게 승인 + permissionMode 전달
  └─ 2-b. 거부 시:
          → f9()로 팀원에게 거부 + 피드백 전달
```

### 3.3 메시지 전달 메커니즘: 3중 폴링

Agent Teams의 메시지 전달은 **Polling 기반**입니다. `fs.watch()` 같은 이벤트 기반이 아닌 `setTimeout` 기반 폴링:

| 폴링 레이어 | 구현 | 간격 | 역할 |
|------------|------|------|------|
| **`WVY()`** | while 루프 + setTimeout | 500ms (`JVY=500`) | In-process teammate의 메시지 수신 |
| **print.ts** | setTimeout 루프 | 500ms | Team lead의 메시지 수신 |
| **InboxPoller (`TVq()`)** | React useCallback + interval | 500ms | UI 측 메시지 표시 |

동일한 mailbox를 3개 레이어에서 독립적으로 폴링합니다. 폴링은 `setTimeout` 기반이므로 CPU를 소비하지 않습니다 (event loop idle). 500ms 간격 = 초당 2회 폴링. 10개 팀원이어도 초당 ~20회 파일 시스템 체크로 무시할 수 있는 수준.

#### In-process Teammate 폴링 우선순위 (5단계)

`WVY()` 함수의 메시지 처리 순서:

1. `pendingUserMessages` (AppState 내 메모리 큐) 먼저 체크
2. `shutdown_request` 메시지 우선 처리
3. `team-lead` 메시지 우선 (`from === K2`)
4. 그 외 unread 메시지
5. 미할당 task 자동 체크 (`ib4()`)

#### Team Lead 폴링 (print.ts)

- 500ms 간격 (`setTimeout(Y1, 500)`) while 루프
- `z51("team-lead", teamName)`으로 unread 메시지 읽기
- 읽은 후 `XQ1()`로 전체 읽음 처리
- `shutdown_approved` 메시지 처리: 팀 config에서 멤버 제거

#### InboxPoller (`TVq()`)

- React useCallback + interval 기반
- 프로토콜 메시지 분류 처리:
  - permission_request/response
  - sandbox_permission_request/response
  - shutdown_request/approved
  - team_permission_update
  - mode_set_request
  - plan_approval_response
  - 일반 메시지

### 3.4 메시지의 Conversation 주입

수신된 메시지는 `<teammate-message>` XML 태그로 래핑되어 대화에 주입됩니다:

```xml
<teammate-message teammate_id="agent-name" color="blue" summary="요약">
메시지 내용
</teammate-message>
```

주입 경로:
- **Team lead**: print.ts에서 `lB({mode: "prompt", value: wrappedMessages})`
- **In-process teammate**: `WVY()`에서 반환 → `GVY()`에서 `_EA()`로 래핑 후 다음 prompt로 전달
- **시스템 context**: `gw("teammate_mailbox", ...)` → context provider로 등록

`K2z()` 함수가 메시지 타입별 처리를 담당:

```javascript
// cli.js 라인 6090 부근
function K2z(A) {
  if (l8()) {
    if (A.type === "teammate_mailbox")
      return [c6({ content: Uzz().formatTeammateMessages(A.messages), isMeta: true })];
    if (A.type === "team_context")
      return [c6({ content: `<system-reminder>
# Team Coordination

You are a teammate in team "${A.teamName}".

**Your Identity:**...`, isMeta: true })];
  }
}
```

### 3.5 Idle Notification

#### 발생 조건
- In-process teammate가 하나의 prompt 처리를 완료했을 때
- `GVY()` 함수 내에서 `lb4()` 호출

#### Idle Notification 구조

```json
{
  "type": "idle_notification",
  "from": "agent-name",
  "timestamp": "ISO 8601",
  "idleReason": "available | interrupted | failed",
  "summary": "작업 요약 또는 DM 내용 요약",
  "completedTaskId": "...",
  "completedStatus": "...",
  "failureReason": "..."
}
```

#### 중복 방지

```javascript
if (!isIdle) sendIdleNotification(...);
else log("Skipping duplicate idle notification");
```

이미 idle인 상태에서 다시 idle이 되면 알림을 스킵합니다.

#### Idle 관련 시스템 프롬프트 규칙

- idle은 정상 상태이며 에러가 아님
- idle 팀원에게 메시지를 보내면 즉시 깨어남
- idle notification에 반드시 반응할 필요 없음
- Peer DM 요약은 정보 제공용

### 3.6 프로토콜 메시지 전체 목록 (14종)

| 타입 | 용도 | 스키마 |
|---|---|---|
| `idle_notification` | 에이전트 유휴 상태 알림 | `Tx4` |
| `task_completed` | 태스크 완료 알림 | - |
| `shutdown_request` | 종료 요청 | `Tx4` (ShutdownRequestMessageSchema) |
| `shutdown_approved` | 종료 승인 | `vx4` |
| `shutdown_rejected` | 종료 거부 | `Ex4` |
| `plan_approval_request` | 계획 승인 요청 | `Vx4` |
| `plan_approval_response` | 계획 승인/거부 응답 | `Nx4` |
| `permission_request` | 권한 요청 (도구 사용) | - |
| `permission_response` | 권한 승인/거부 | - |
| `sandbox_permission_request` | 샌드박스 권한 요청 | - |
| `sandbox_permission_response` | 샌드박스 권한 응답 | - |
| `team_permission_update` | 팀 권한 변경 알림 | - |
| `mode_set_request` | 모드 변경 요청 | `kx4` |
| `teammate_terminated` | 에이전트 종료 알림 | - |

### 3.7 동시성 제어와 전달 보장

#### 파일 잠금
- **라이브러리**: `proper-lockfile` (`_Q1.lockSync`)
- **Read-Modify-Write 패턴**: 잠금 → 읽기 → 수정 → 쓰기 → 해제
- **잠금 파일 경로**: `{inbox-path}.lock`
- **같은 수신자에 동시 전송**: lockSync로 직렬화 (대기 후 순차 처리)
- **다른 수신자에 동시 전송**: 각 수신자 파일이 분리되어 충돌 없음

#### 전달 보장 특성
- **At-least-once**: 파일 시스템에 기록되므로 유실 가능성 낮음
- **영속적 저장**: 프로세스 재시작 후에도 메시지 유지
- **읽음 추적**: `read` 필드로 처리 상태 관리
- **순서 보장 없음**: 각 메시지는 독립적으로 전달
- **재시도 없음**: 파일 잠금 경쟁 시 catch로 에러만 로깅

---

## 4. 팀 저장 구조와 파일 시스템

### 4.1 디렉토리 구조

```
~/.claude/
├── teams/
│   └── {team-name}/
│       ├── config.json          # 팀 설정 및 멤버 목록
│       └── inboxes/
│           ├── team-lead.json   # 리드의 inbox
│           ├── agent-1.json     # 팀원 1의 inbox
│           └── agent-2.json     # 팀원 2의 inbox
└── tasks/
    └── {team-name}/
        ├── .lock                # proper-lockfile용 락 파일
        ├── .highwatermark       # 최대 task ID 추적
        ├── 1.json               # Task #1
        ├── 2.json               # Task #2
        └── ...
```

### 4.2 config.json 전체 스키마

```javascript
{
  name: string,              // 정규화된 팀 이름 (cRA() 함수: 특수문자→하이픈, 소문자화)
  description: string,       // 팀 설명 (optional)
  createdAt: number,         // Date.now() 타임스탬프
  leadAgentId: string,       // "team-lead@{team-name}" 형식
  leadSessionId: string,     // UUID (U6() 함수)
  members: [
    {
      agentId: string,         // "{name}@{team-name}" (pv() 함수)
      name: string,            // 사람이 읽을 수 있는 이름
      agentType: string,       // 역할/타입
      model: string,           // AI 모델 ID
      prompt: string,          // 초기 프롬프트 (팀원만)
      color: string,           // 표시 색상
      planModeRequired: boolean,
      joinedAt: number,        // Date.now()
      tmuxPaneId: string,      // tmux pane ID 또는 "in-process"
      cwd: string,             // 작업 디렉토리
      subscriptions: [],       // 빈 배열 (확장용 예비 필드)
      backendType: string      // "in-process" | "tmux" | "iterm2"
    }
  ]
}
```

### 4.3 멤버 이중 저장 구조

팀원은 두 곳에 동시 기록됩니다:

1. **config.json의 `members` 배열** — 디스크 기반, 팀원 검색 시 사용
2. **AppState.teamContext.teammates** — 메모리 내, 런타임에서 사용

```javascript
// AppState 내 teamContext 구조 (메모리)
{
  teamName: "my-project",
  teamFilePath: "~/.claude/teams/my-project/config.json",
  leadAgentId: "agent-id",
  teammates: {
    "agent-id": {
      name: "team-lead",
      agentType: "team-lead",
      color: "#...",
      tmuxSessionName: "",
      tmuxPaneId: "",
      cwd: "/path/to/project",
      spawnedAt: 1707561600000
    }
  }
}
```

### 4.4 AgentId 체계

- **생성**: `pv(name, teamName)` → `"{name}@{teamName}"`
- **파싱**: `c31(agentId)` → `{agentName, teamName}`
- **requestId**: `vP1(prefix, target)` → `"{prefix}-{timestamp}@{target}"`
- **팀 이름 정규화**: `cRA()` → `name.replace(/[^a-zA-Z0-9]/g, "-").toLowerCase()`

### 4.5 config.json 동시성 문제 (교차 검증 발견)

**config.json 쓰기에는 파일 락킹이 없습니다:**

```javascript
function mEA(teamName, config) {
  mkdirSync(path, {recursive: true});
  writeFileSync(path, JSON.stringify(config, null, 2));
  // ← NO file locking!
}
```

- Task 파일: `PC1.default.lockSync()` 사용 → **안전**
- config.json: raw `writeFileSync` → **race condition 이론적 가능**
- 실제 위험도: 낮음 (주로 lead만 수정하지만, 동시 멤버 추가/제거 시 문제 가능)

### 4.6 팀 생성 흐름 (TeamCreate)

```
사용자/리드: TeamCreate({ team_name: "my-project", description: "..." })
     │
     v
1. 이미 팀을 리드하고 있으면 에러: "Already leading team"
2. 팀 이름 중복 검사 (FSY() → iX() 존재 확인 후 새 이름 생성 tO6())
3. 팀 이름 정규화: cRA(name) → 소문자 + 특수문자를 '-'로 치환
4. agentId 생성: pv(K2, name) → 고유 ID
5. 디렉토리 생성: mkdirSync(~/.claude/teams/{normalized-name}/)
6. config.json 작성: mSY() → JSON.stringify(P, null, 2)
7. 태스크 디렉토리 초기화: aq6() (.lock 파일 생성, 기존 .json 삭제)
8. 태스크 디렉토리 생성: GC1() → ~/.claude/tasks/{normalized-name}/
9. AppState 업데이트: teamContext 설정
```

### 4.7 팀 삭제 (TeamDelete)

```
1. 활성 멤버 확인: iX(w) → M51(K)로 config.json 읽기
2. team-lead 제외한 멤버 필터링: members.filter(O => O.name !== K2)
3. 멤버가 남아있으면 실패: "Cannot cleanup team with N active member(s): names"
4. 디렉토리 삭제: OR4(w) → teams/ 및 tasks/ 디렉토리 모두 삭제
5. 상태 정리: fu4() (색상 캐시), D67() (팀 이름 변수)
6. AppState 정리: teamContext: undefined, inbox: {messages: []}
```

---

## 5. Task 관리 시스템

### 5.1 Task JSON 스키마

각 task는 `{id}.json` 파일로 독립 저장:

```javascript
{
  id: string,
  subject: string,
  description: string,
  activeForm: string?,        // 진행 중 표시 텍스트 (예: "코드 분석 중")
  owner: string?,             // 담당 에이전트 이름
  status: "pending" | "in_progress" | "completed",
  blocks: string[],           // 이 task가 블로킹하는 task IDs
  blockedBy: string[],        // 이 task를 블로킹하는 task IDs
  metadata: Record<string, unknown>?
}
```

### 5.2 핵심 Task 함수

| 함수 | 난독화명 | 동작 |
|------|---------|------|
| createTask | `n_1(A, q)` | lockSync → highwatermark 확인 → ID 증가 → JSON 파일 작성 |
| readTask | `lg(A, q)` | 개별 JSON 파일 읽기 + 스키마 검증 (`kf5`) |
| updateTask | `JS(A, q, K)` | 읽기 → 병합 → JSON 파일 다시 쓰기 |
| deleteTask | `sq6(A, q)` | 파일 삭제 + blocks/blockedBy에서 참조 제거 |
| listTasks | `WX(A)` | 디렉토리의 모든 .json 파일 읽기 |
| claimTask | `o7A()` | 개별 task 파일에 lockSync → 소유권/상태/블로킹 확인 → 쓰기 |
| checkBusyAgent | `Cf5()` | 전체 `.lock` 파일에 lockSync → 모든 task 스캔 |

### 5.3 파일 락킹 메커니즘

**라이브러리**: `proper-lockfile` (NPM 패키지)

| 대상 | 락킹 파일 | 방식 |
|------|----------|------|
| Task 초기화 (`aq6`) | `.lock` | lockSync → 기존 task 파일 정리 → unlock |
| Task 생성 (`n_1`) | `.lock` | lockSync → highwatermark → ID 할당 → 쓰기 → unlock |
| Task 클레임 (`o7A`) | 개별 `{id}.json` | lockSync → 상태 확인 → owner 설정 → unlock |
| 바쁜 에이전트 체크 (`Cf5`) | `.lock` | lockSync → 모든 task 스캔 |

- `.highwatermark` 파일로 task ID 충돌 방지 (삭제 후에도 ID 재사용 않음)
- 클레임은 원자적: 락 → 읽기 → 소유권/상태/블로킹 확인 → 쓰기 → 언락

### 5.4 자기 조율 (Self-Coordination) 메커니즘

공식 문서의 "self-coordination"의 **실제 구현**은 idle 폴링 루프 내 `ib4()` 함수입니다:

```
teammate idle → 500ms 대기 → mailbox 확인 → ib4() 미할당 task 자동 claim → 작업 시작
```

`ib4()` 함수의 동작:
1. `WX()`로 전체 task 목록 조회
2. `status === "pending"` && `!owner` && `blockedBy` 비어 있는 task 탐색
3. `o7A()`로 원자적 claim (lockSync 보호)
4. claim 성공 시 해당 task 작업 시작

Subagent에는 이런 자율적 작업 탐색 메커니즘이 없습니다.

### 5.5 Hook 시스템

#### TeammateIdle Hook
- **트리거**: 팀원이 idle 상태로 전환될 때
- **입력**: `{ teammate_name, team_name }` JSON
- **Exit code 행동**:
  - 0: 정상 (stdout/stderr 미표시)
  - 2: stderr를 팀원에게 표시 + idle 전환 방지 (계속 작업)
  - 기타: stderr를 사용자에게만 표시
- **실행**: `wyA()` (executeTeammateIdleHooks)
- **포맷팅**: `tRA()` → `"TeammateIdle hook feedback: {blockingError}"`

#### TaskCompleted Hook
- **트리거**: task가 completed로 마크될 때
- **입력**: `{ task_id, task_subject, task_description, teammate_name, team_name }` JSON
- **Exit code 행동**:
  - 0: 정상 (stdout/stderr 미표시)
  - 2: stderr를 모델에 표시 + task 완료 방지
  - 기타: stderr를 사용자에게만 표시
- **실행**: `Cg1()` (executeTaskCompletedHooks)
- **포맷팅**: `yg1()` → `"TaskCompleted hook feedback: {blockingError}"`

#### Hook 실행 인프라
- 모든 hook은 `OhY` (`child_process.spawn`)으로 실행
- 2가지 hook 타입:
  - `command`: 셸 명령 실행
  - `agent`: AI 에이전트 기반 검증 (별도의 작은 에이전트 루프, 50턴 제한)

---

## 6. Teammate 스폰 메커니즘

### 6.1 팀원 실행 모드 (Backend Type)

| 방식 | backendType | 설명 |
|------|-------------|------|
| **In-Process** | `"in-process"` | 동일 Node.js 프로세스 내 실행. 메모리 공유하되 논리적 분리. |
| **Tmux Split-Pane** | `"tmux"` | 별도 tmux 패인에서 독립 프로세스로 실행. |
| **iTerm2 Pane** | `"iterm2"` | iTerm2의 split pane에서 독립 프로세스로 실행. |

### 6.2 스폰 라우팅

`iVY()` 함수에서 백엔드를 선택:

```
isInProcessEnabled()? → lVY() (in-process)
use_splitpane !== false? → dVY() (split-pane tmux/iTerm2)
else → cVY() (별도 tmux 윈도우)
```

#### 모드 결정 (`Rm()` 함수)

```javascript
function Rm() {
  if (w4()) return true;  // non-interactive → in-process
  let mode = xVY();       // config의 teammateMode
  if (mode === "in-process") return true;
  if (mode === "tmux") return false;
  return !rM6();  // tmux 안이면 tmux, 밖이면 in-process
}
```

설정 우선순위:
1. CLI 플래그 (`--teammate-mode`) → `qW1` 변수
2. settings.json의 `teammateMode`
3. 기본값: `"auto"` (tmux 세션 안 → tmux, 밖 → in-process)

### 6.3 In-process 스폰 (`lVY()`)

1. 이름 중복 확인 (`FEA()`) — 같은 이름이면 `-2`, `-3` 접미사
2. `LP1()`: AppState에 task 등록 + AbortController 생성
3. `nM6()`: 비동기 에이전트 루프 시작 (`GVY().catch(...)`)
4. config.json에 멤버 추가 (`mEA()`)
5. **프로세스 생성 없음** — 같은 Node.js 프로세스 내에서 `AsyncLocalStorage` 기반 격리로 동시 실행

### 6.4 Pane 스폰 (`dVY()`)

1. 이름 정규화 (`BEA()` — @ 제거)
2. Backend 선택 (`zt()` 함수):
   - tmux 세션 내부 → tmux 사용
   - iTerm2 + it2 CLI → iTerm2 사용
   - iTerm2 + tmux → tmux 폴백
   - 그 외 → tmux 필요
3. Pane 생성: `Nu4(name, color)` → `createTeammatePaneInSwarmView()`
4. CLI 명령 조립:
   ```
   cd {cwd} && CLAUDECODE=1 CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
   {cli-path} --agent-id {id} --agent-name {name} --team-name {team}
   --agent-color {color} --parent-session-id {sessionId} [--model ...]
   [--dangerously-skip-permissions]
   ```
5. pane에 명령 전송: `vu4(paneId, command)`
6. config.json 업데이트

Tmux 사용 시 플랫폼별 설치 안내:
```
macOS:  brew install tmux
Linux:  sudo apt install tmux
Windows: WSL 필요 → sudo apt install tmux
```

### 6.5 권한 상속

#### Pane Teammate
- lead의 `toolPermissionContext.mode` 확인
- `bypassPermissions` → `--dangerously-skip-permissions` 플래그 전달
- `acceptEdits` → `--permission-mode acceptEdits` 플래그 전달
- `planModeRequired` 팀원은 권한 플래그 생략 (plan 모드 강제)

#### In-process Teammate
- `permissionMode` 필드로 설정
- `planModeRequired` → `"plan"`, 아니면 `"default"`
- **동적 권한 변경**: lead가 plan approval 하면 `"plan"` → `"default"` 전환
- `dontAsk` 모드는 hook agent에서만 사용 (agent stop hook)

---

## 7. 도구 접근 제어와 Delegate 모드

### 7.1 팀 도구 노출 가드

Agent Teams 활성화 여부에 따라 도구가 조건부 노출됩니다:

```javascript
// l8() = isTeamModeActive()
...l8()?[zhY(),whY(),HhY()]:[]...
// zhY() = TeamCreate, whY() = TeamDelete, HhY() = SendMessage
```

`l8()`이 false이면 팀 관련 도구가 아예 모델에 노출되지 않습니다.

### 7.2 Subagent 도구 결정

- `subagent_type` 파라미터로 지정 (예: "code", "plan", "explore")
- 각 타입별로 사전 정의된 도구 셋
- `YP6()` 함수에서 필터링

### 7.3 이중 도구 필터링

Agent Teams의 도구 접근은 두 계층이 독립적으로 동작하며 조합됩니다:
1. `l8()` 가드: 팀 전용 도구 (TeamCreate, TeamDelete, SendMessage) 추가/제거
2. `subagent_type` 기반 필터링: 각 에이전트 타입별 도구 셋 제한

### 7.4 Delegate 모드

Delegate 모드에서는 리드가 코드 작업을 하지 않고 순수 조율만 수행합니다. `R_6` Set으로 허용 도구가 제한됩니다:

```javascript
// delegate 모드 시 허용 도구 (cli.js 라인 6176 부근)
"You are in delegate mode for team \"{teamName}\". In this mode, you can ONLY use the following tools:
- TeammateTool: For spawning teammates, sending messages, and team coordination
- TaskCreate: For creating new tasks
- TaskGet: For retrieving task details
- TaskUpdate: For updating task status and adding comments..."
```

활성화 방법: 팀 시작 후 Shift+Tab으로 delegate 모드 전환.

---

## 8. Subagent vs Agent Teams 심층 비교

### 8.1 핵심 아키텍처 비교

| 차원 | Subagent (Task tool) | Agent Teams |
|------|---------------------|-------------|
| **실행 엔진** | `dR()` → `ZR()` | `GVY()` → `ZR()` (**동일**) |
| **Context** | `forkContext`로 선택적 공유 | 완전 독립 (prompt만 전달) |
| **통신 매체** | 인메모리 (async iterator yield) | 파일 기반 mailbox (JSON) |
| **통신 방향** | 단방향 (call → result) | 양방향 N:N (DM, broadcast) |
| **조율** | main agent 중앙 제어 | 공유 TaskList + `ib4()` 자기 조율 |
| **토큰 비용** | 낮음 (결과만 caller에 반환) | 높음 (N개 독립 context) |
| **메시지 레이턴시** | ~0ms (동기, 인메모리) | 최대 500ms (폴링) |
| **프로세스 모델** | 동기 또는 background | in-process / tmux / iTerm2 |
| **중첩 가능** | O (subagent → subagent) | X (1 leader : N teammates) |
| **Resume** | agentId 기반 transcript 복원 | 없음 (프로세스 수명 종속) |
| **CLAUDE.md** | 독립 system prompt | 독립 session으로 자체 로딩 |
| **max_turns** | 파라미터로 제어 가능 | teammate별 독립 (무제한) |
| **결과 크기 제한** | `maxResultSizeChars: 100,000자` | 없음 (메시지 단위) |
| **자율성** | 없음 — 부모가 시작하고 결과를 받음 | 높음 — 독립적으로 태스크 발견/클레임/실행 |
| **지속성** | 없음 — 호출마다 새로 생성 | 높음 — 팀 존속 기간 내 유지 |
| **협업** | 불가 — 형제 서브에이전트와 통신 불가 | 가능 — SendMessage로 P2P 통신 |
| **저장소** | 없음 (메모리 내) | 파일 시스템 (teams/tasks 디렉토리) |

### 8.2 Context 관리 상세 비교

#### Subagent의 forkContext

```
forkContext === true:
  → main agent의 전체 대화 이력이 subagent에 전달
  → "### FORKING CONVERSATION CONTEXT ###" 경계 마커 삽입
  → model은 반드시 'inherit'으로 강제 (context length mismatch 방지)

forkContext === false (기본값):
  → prompt만 전달 (새로운 context window)
  → c6({content: A}) 형태로 단일 메시지 생성
```

CLAUDE.md, MCP, Skills 로딩:
- Subagent는 독립적 system prompt를 받음: `sfY()` → `NQ1()` 호출
- MCP 서버 연결: `ofY()` 함수로 agent definition의 `mcpServers` 배열에 따라 독립 연결
- Skills: `A.skills` 배열에 따라 `hv(ZO())`로 프리로드
- Agent definition의 `hooks`도 독립적으로 등록: `Bn7()` 함수

#### Teams의 Context 초기화

```
Teammate spawn:
  → 완전히 새로운 인스턴스 (process 또는 in-process)
  → 초기 prompt만 inbox 메시지로 전달: f9(name, {from: "team-lead", text: prompt})
  → 각 teammate는 CLAUDE.md를 독립적으로 로딩
  → lead의 대화 이력은 전달되지 않음
  → tmux backend: 별도 CLI 프로세스로 실행 (CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1)
  → in-process backend: 동일 프로세스 내 AsyncLocalStorage 기반 격리
```

### 8.3 Task tool 내부의 분기점

**동일한 Task tool이 subagent와 teammate를 모두 처리합니다.** `name`과 `team_name` 파라미터의 유무로 분기:

```javascript
// rj1.call 함수 핵심 분기:
if (G && $) {  // team_name + name 존재
  return Iu4({name, prompt, team_name, ...});  // → teammate 생성
}
// 그 외 → 일반 subagent
if (U) {  // background 실행
  return p01(O1, async () => { for await (... of dR(l)) ... });
} else {  // 동기 실행
  for await (let J1 of dR(l)) { ... }
  return UEA(N1, ...);  // 결과 추출
}
```

### 8.4 결과 반환 방식 비교

#### Subagent
- `UEA()` 함수가 마지막 assistant 메시지의 **텍스트 블록만** 추출
- tool_use 블록은 결과에서 **제거**
- **별도의 "요약" LLM 호출 없음** — 단순히 마지막 텍스트 추출
- 100,000자 크기 제한 (`maxResultSizeChars: 1e5`)
- `classifyHandoffIfNeeded()` 함수를 통해 추가적인 분류 정보가 결과에 첨부될 수 있음

#### Teams
- SendMessage로 양방향 자유 전송
- 크기 제한 없음 (메시지 단위)
- `<teammate-message>` 태그로 래핑되어 conversation에 주입

### 8.5 실행 흐름 비교

#### Subagent 실행 흐름
```
부모 에이전트
  │
  ├─ Task(prompt="...", subagent_type="code")
  │     │
  │     ├─ classifyHandoffIfNeeded() → 핸드오프 분류
  │     ├─ 서브에이전트 루프 시작 (ZR 함수)
  │     ├─ 최대 턴 제한 내 실행
  │     ├─ 결과를 tool_result로 반환
  │     └─ 서브에이전트 종료
  │
  ├─ (부모 에이전트 결과 처리 후 계속)
  └─ ...
```

#### Agent Teams 실행 흐름
```
팀 리드
  │
  ├─ TeamCreate({ team_name: "project" })
  ├─ TaskCreate({ subject: "Task A" })
  ├─ Task(team_name: "project", name: "worker-1", prompt="...")
  │     │
  │     ├─ 팀원 스폰 (in-process 또는 tmux)
  │     ├─ config.json에 멤버 추가
  │     ├─ 팀원 독립 실행 시작
  │     └─ 리드에게 즉시 제어권 반환
  │
  ├─ (리드는 다른 팀원 스폰 가능)
  ├─ 팀원들 → TaskList → 태스크 클레임 → 작업 → TaskUpdate
  ├─ 팀원들 ↔ SendMessage로 상호 통신
  ├─ 팀원들 → idle 상태 ↔ 메시지 수신 시 재가동
  ├─ 리드 → SendMessage(shutdown_request) → 팀원 종료
  └─ 리드 → TeamDelete() → 정리
```

### 8.6 중첩/재귀 제한

#### Subagent
```javascript
if (MM() && G) {  // MM() = isInProcessTeammate()
  if ($)  // name 존재 = teammate spawn 시도
    throw Error("In-process teammates cannot spawn other teammates.");
  if (w === true)  // background 시도
    throw Error("In-process teammates cannot spawn background agents.");
}
```

- **Subagent는 다른 subagent를 생성할 수 있음** (동기 모드에서)
- In-process teammate는 추가 teammate spawn 제한
- In-process teammate는 background agent 제한

#### Teams
```javascript
let O = $.teamContext?.teamName;
if (O) throw Error(`Already leading team "${O}". A leader can only manage one team at a time.`);
```

- 한 agent는 하나의 팀만 lead 가능
- teammate는 TeamCreate tool 사용 불가
- **No nested teams**

### 8.7 비용 비교 (3가지 백엔드별)

| 비용 항목 | Subagent | Teams (in-process) | Teams (tmux pane) |
|----------|---------|-------------------|------------------|
| 메모리 지속시간 | 작업 중만 | **idle 포함 상시** | 별도 프로세스 |
| 메시지 레이턴시 | 즉시 (동기) | 메모리 큐 (~빠름) | **500ms 폴링** |
| 파일 I/O | transcript만 | 메모리+파일 이중 | **순수 파일** |
| 프로세스 오버헤드 | 없음 | 없음 (공유) | **전체 CLI 초기화** |
| GC 가능 시점 | 완료 즉시 | **shutdown 후** | 프로세스 종료 |
| 메시지 폴링 | 없음 (동기) | **500ms 간격** | **500ms 간격** |
| 파일 락킹 | 없음 | proper-lockfile | proper-lockfile |
| config.json I/O | 없음 | 멤버 변경 시 전체 다시 쓰기 | 동일 |
| idle 알림 | 없음 | **매 턴 후 (중복 방지 포함)** | 동일 |

### 8.8 Resume/Recovery 비교

#### Subagent Resume
```javascript
resume: u.string().optional()
  .describe("Optional agent ID to resume from.")

// resume 처리:
if (z) {  // z = resume ID
  let r = P.tasks[z];
  if (r && r.status === "running")
    throw Error(`Cannot resume agent ${z}: it is still running.`);
  let s = await sP1(xZ(z));  // transcript 읽기
  y = BQ1(mQ1(wP6(s)));  // 메시지 파싱
}
```

- agentId 기반으로 이전 transcript를 로드하여 이어서 실행
- 실행 중인 agent는 resume 불가

#### Teams의 Session Resume
- Teams 자체에는 별도 resume 메커니즘 없음
- 개별 teammate의 session은 해당 프로세스 수명에 종속
- in-process teammate는 leader의 process와 함께 종료
- `/resume` 및 `/rewind`는 in-process teammate를 복원하지 않음

### 8.9 시나리오별 최적 선택

| 시나리오 | 추천 | 이유 |
|---------|------|------|
| 단일 파일 검색/분석 | **Subagent** | 낮은 오버헤드, 결과만 필요 |
| 코드 리뷰 | **Subagent** | 독립적 분석, 결과 요약으로 충분 |
| 빠른 context 포함 분석 | **Subagent (forkContext)** | caller context 접근 필요 |
| 멀티 파일 리팩토링 | **Teams** | 병렬 작업, 상호 조율 |
| 풀스택 기능 개발 | **Teams** | FE/BE 분리, 의존성 관리 |
| 경쟁 가설 검증 | **Teams** | P2P 토론, 상호 반박 가능 |
| 장시간 복잡 프로젝트 | **Teams** | idle/wake-up, 태스크 관리 |

---

## 9. 문서에 없는 발견 사항

교차 검증을 통해 공식 문서에 기술되지 않은 다음 구현 세부사항을 발견했습니다:

### 9.1 실행 엔진 동일성
공식 문서는 subagent와 teams를 별개 시스템처럼 설명하지만, 실제로는 **동일한 `ZR()` 실행 엔진**을 공유합니다. 차이는 통신/조율 레이어에만 존재합니다.

### 9.2 3중 폴링 아키텍처
문서에는 "메시지가 자동으로 전달된다"고만 되어 있지만, 실제로는 500ms 간격의 3개 독립 폴링 루프(WVY, print.ts, InboxPoller)가 동일 mailbox를 감시합니다.

### 9.3 config.json 락킹 부재
Task 파일은 `proper-lockfile`로 보호되지만, **config.json은 락킹 없이 `writeFileSync`**를 사용합니다. 이론적으로 동시 멤버 추가/제거 시 race condition이 가능합니다.

### 9.4 inbox 이중 구조
- **In-process teammate**: `AppState.tasks[taskId].pendingUserMessages` (메모리 배열) + `Ld()` mailbox (파일)
- **Tmux/iTerm2 pane**: 순수 파일 시스템 기반 `f9()` 함수만 사용

In-process teammate는 메모리 내 큐를 우선 사용하므로 pane teammate보다 메시지 전달이 빠릅니다. 특히 team-lead → in-process 경로는 메모리 큐(`pendingUserMessages`)를 사용하여 응답 속도가 더 빠릅니다.

### 9.5 Subagent의 forkContext 옵션
문서에는 "subagent는 자체 context window를 가진다"고만 되어 있지만, `forkContext: true` 옵션으로 **전체 대화 이력을 subagent에 전달**할 수 있습니다. 이 경우 model은 `'inherit'`으로 강제됩니다.

### 9.6 Subagent 결과 "요약"의 실체
공식 문서는 "결과가 요약되어 반환"이라고 하지만, 실제로는 **별도의 요약 LLM 호출 없이** 마지막 assistant 메시지의 텍스트 블록만 추출합니다 (100,000자 제한).

### 9.7 Task tool의 이중 역할
동일한 Task tool(`rj1`)이 `name + team_name` 파라미터 유무에 따라 subagent와 teammate spawn을 모두 처리합니다.

### 9.8 In-process teammate의 제한
In-process teammate는:
- 다른 teammate를 spawn할 수 없음 (`"In-process teammates cannot spawn other teammates."`)
- Background agent를 spawn할 수 없음 (`"In-process teammates cannot spawn background agents."`)
- 동기 subagent만 생성 가능

### 9.9 자기 조율의 실체: `ib4()` 함수
문서에서 "자기 조율"이라고 부르는 것의 실제 구현은 idle 폴링 루프 내 `ib4()` 함수가 미할당 task를 자동으로 claim하는 것입니다.

### 9.10 config.json의 subscriptions 필드
멤버 객체에 `subscriptions: []` 필드가 존재하지만, 현재 빈 배열로만 사용됩니다. 향후 pub/sub 패턴 확장을 위한 예비 필드로 추정됩니다.

### 9.11 Agent Hook 타입
TeammateIdle과 TaskCompleted hook에는 `command` 타입 외에 **`agent` 타입**이 있으며, 이는 별도의 작은 에이전트 루프(50턴 제한)로 조건을 검증합니다. 문서에서는 이 agent hook 타입에 대한 상세 설명이 없습니다.

### 9.12 shutdown 처리의 백엔드별 차이
- In-process: `AbortController.abort()` (메모리 내 시그널)
- Tmux/iTerm2: `setImmediate(() => process.exit())` (프로세스 종료)
- Pane teammate의 종료: `nK(0, "other")` (프로세스 종료)

### 9.13 이름 중복 처리
teammate 이름이 중복될 경우 `FEA()` 함수가 자동으로 `-2`, `-3` 접미사를 추가합니다.

### 9.14 5단계 메시지 처리 우선순위
`WVY()` 폴링 루프는 메시지를 5단계 우선순위로 처리합니다: pendingUserMessages → shutdown_request → team-lead 메시지 → 일반 unread → unclaimed tasks. 문서에는 이 우선순위가 명시되지 않습니다.

### 9.15 도구 노출 가드
`l8()` 함수가 팀 모드 활성 여부를 판단하며, 이 가드가 false이면 TeamCreate/TeamDelete/SendMessage 도구가 모델에 아예 노출되지 않습니다.

### 9.16 Delegate 모드의 도구 제한
Delegate 모드에서 리드는 `R_6` Set으로 정의된 조율 전용 도구만 사용 가능합니다. 코드 작성/편집 도구가 제거되어 순수 오케스트레이션만 수행합니다.

---

## 10. 아키텍처 다이어그램

### 10.1 전체 시스템 구조

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Claude Code Process                          │
│                                                                     │
│  ┌──────────────┐   SendMessage   ┌──────────────────────────────┐ │
│  │              │ ←─────────────→ │        Mailbox System        │ │
│  │  Team Lead   │   (f9/Ld/z51)   │ ~/.claude/teams/{name}/      │ │
│  │  (ZR() loop) │                 │   inboxes/{agent}.json       │ │
│  │              │   TaskList      │                              │ │
│  │              │ ←─────────────→ │        Task System           │ │
│  └──────┬───────┘   (n_1/lg/JS)   │ ~/.claude/tasks/{name}/      │ │
│         │                         │   {id}.json + .lock          │ │
│         │ spawn                   │   .highwatermark             │ │
│         │                         └──────────────────────────────┘ │
│   ┌─────┴─────┐                                                    │
│   │           │                                                    │
│   ▼           ▼                                                    │
│ ┌───────┐ ┌───────────┐                                           │
│ │In-proc│ │ Pane spawn│──→ [별도 CLI 프로세스]                     │
│ │(lVY)  │ │ (dVY/cVY) │     --agent-id --agent-name               │
│ │       │ │           │     --team-name --parent-session-id        │
│ │nM6()  │ │tmux/iTerm2│                                           │
│ │→GVY() │ │  pane     │                                           │
│ │→ZR()  │ │           │                                           │
│ └───────┘ └───────────┘                                           │
│                                                                     │
│  ┌──────────────────────────────────────────┐                      │
│  │           Polling Layers (500ms)          │                      │
│  │  WVY() : in-process teammate polling      │                      │
│  │  print.ts : team lead polling             │                      │
│  │  TVq() : React UI inbox poller            │                      │
│  └──────────────────────────────────────────┘                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 10.2 메시지 흐름

```
Agent A                    File System                    Agent B
  │                            │                            │
  │  f9(B, {text, from})       │                            │
  │──────────────────────────→ │                            │
  │  lockSync(B.inbox.lock)    │                            │
  │  read B.inbox.json         │                            │
  │  append message            │                            │
  │  write B.inbox.json        │                            │
  │  unlock                    │                            │
  │                            │     z51(B) [500ms poll]    │
  │                            │ ←──────────────────────────│
  │                            │     read B.inbox.json      │
  │                            │     filter read===false    │
  │                            │ ──────────────────────────→│
  │                            │     markAsRead(index)      │
  │                            │ ←──────────────────────────│
  │                            │                            │
  │                            │     <teammate-message>     │
  │                            │     wrap & inject to conv  │
  │                            │                            │
```

### 10.3 팀 라이프사이클

```
[1] TeamCreate (QSY.call())
    ├── teams/{name}/ 디렉토리 생성
    ├── config.json 작성 (lead만 포함)
    ├── tasks/{name}/ 디렉토리 생성 + .lock + .highwatermark
    └── AppState.teamContext 설정

[2] Teammate Spawn (Task tool → Iu4() → iVY())
    ├── In-process: AppState에 task 등록 + 에이전트 루프 시작
    ├── Pane: tmux/iTerm2 pane 생성 + CLI 인스턴스 시작
    ├── config.json에 멤버 추가 (mEA())
    └── 초기 프롬프트 → inbox 메시지 전달 (f9())

[3] Active Phase
    ├── Task 생성/할당/완료 (개별 .json + file lock)
    ├── 메시지 교환 (f9() → mailbox → z51() → 500ms polling)
    ├── Idle 상태 전환 (매 턴 후 lb4() → DQ1() idle notification)
    ├── Wake-up (메시지 수신 시 자동)
    └── Self-coordination (ib4() 미할당 task 자동 claim)

[4] Shutdown
    ├── lead → shutdown_request 메시지 전송 (sSY())
    ├── teammate → shutdown_response approve/reject (tSY()/eSY())
    ├── In-process: AbortController.abort() → 루프 종료
    ├── Pane: process.exit() 또는 tmux kill-pane
    ├── config.json에서 멤버 제거
    └── task 해제 (Mr() - owner 초기화)

[5] TeamDelete (USY.call())
    ├── active member 확인 (team-lead 제외 멤버 남아있으면 실패)
    ├── teams/{name}/ 디렉토리 삭제 (OR4())
    ├── tasks/{name}/ 디렉토리 삭제
    ├── 색상 캐시 초기화 (fu4())
    └── AppState 정리 (teamContext: undefined, inbox: {messages: []})
```

---

## 11. 부록: 함수 매핑 테이블

### 11.1 Mailbox 관련

| 원본 추정명 | 난독화명 | 역할 |
|---|---|---|
| writeToMailbox | `f9()` | 수신자 inbox에 메시지 쓰기 |
| readMailbox | `Ld()` | 에이전트 inbox 전체 읽기 |
| readUnreadMessages | `z51()` | 안 읽은 메시지 필터링 |
| markMessageAsReadByIndex | `JQ1()` | 인덱스 기반 읽음 처리 |
| markMessagesAsRead | `XQ1()` | 전체 읽음 처리 |
| markMessagesAsReadByPredicate | `QvA()` | 조건부 읽음 처리 |
| clearMailbox | `AfY()` | inbox 비우기 |
| getInboxPath | `as()` | inbox 파일 경로 계산 |
| formatTeammateMessages | `qfY()` | XML 태그 래핑 |
| wrapSingleMessage | `_EA()` | 단일 메시지 `<teammate-message>` 래핑 |
| createIdleNotification | `DQ1()` | idle notification 생성 |
| sanitizeName | `i_1()` | 이름 정제 (특수문자 제거) |
| handleTeammateMailbox | `K2z()` | 메시지 타입별 conversation 주입 |

### 11.2 Team 관련

| 원본 추정명 | 난독화명 | 역할 |
|---|---|---|
| TeamCreate.call | `QSY.call()` | 팀 생성 |
| TeamDelete.call | `USY.call()` | 팀 삭제 |
| TeamCreateTool | `zhY()` | TeamCreate 도구 정의 |
| TeamDeleteTool | `whY()` | TeamDelete 도구 정의 |
| SendMessageTool | `HhY()` | SendMessage 도구 정의 |
| isTeamModeActive | `l8()` | 팀 모드 활성 확인 |
| normalizeTeamName | `cRA()` | 팀 이름 정규화 |
| createTeamConfig | `mSY()` | config 파일 생성 |
| readTeamConfig | `M51()` | config 파일 읽기 |
| updateTeamConfig | `mEA()` | config 파일 업데이트 |
| createAgentId | `pv()` | agentId 생성 |
| parseAgentId | `c31()` | agentId 파싱 |
| createRequestId | `vP1()` | requestId 생성 |
| isTeamLead | `PM()` | 팀 리드 권한 확인 |

### 11.3 Task 관련

| 원본 추정명 | 난독화명 | 역할 |
|---|---|---|
| createTask | `n_1()` | task 생성 (lock + highwatermark) |
| readTask | `lg()` | task 읽기 + 스키마 검증 |
| updateTask | `JS()` | task 업데이트 (read-modify-write) |
| deleteTask | `sq6()` | task 삭제 + 참조 정리 |
| listTasks | `WX()` | 전체 task 목록 |
| claimTask | `o7A()` | task 클레임 (atomic lock) |
| initTaskList | `aq6()` | task 디렉토리 초기화 |
| createTaskDir | `GC1()` | task 디렉토리 생성 |
| checkBusyAgent | `Cf5()` | 에이전트 중복 작업 체크 |
| taskSchema | `kf5` | task JSON 스키마 (Zod) |

### 11.4 Spawn 관련

| 원본 추정명 | 난독화명 | 역할 |
|---|---|---|
| spawnTeammate | `Iu4()` → `iVY()` | 스폰 진입점 |
| spawnInProcess | `lVY()` | in-process 스폰 |
| spawnInPane | `dVY()` | split-pane 스폰 |
| spawnInWindow | `cVY()` | tmux window 스폰 |
| isInProcessEnabled | `Rm()` | 모드 결정 |
| getTeammateMode | `xVY()` → `bQ1()` | 설정에서 teammateMode 읽기 |
| selectBackend | `zt()` | tmux/iTerm2 선택 |
| registerInProcessTask | `LP1()` | AppState에 task 등록 |
| startAgentLoop | `nM6()` | 에이전트 루프 시작 |
| runTeammateLoop | `GVY()` | teammate 실행 루프 |
| mainAgentLoop | `ZR()` | 공유 실행 엔진 |
| idlePolling | `WVY()` | idle 상태 폴링 |
| autoClaimTask | `ib4()` | 미할당 task 자동 claim |
| checkDuplicateName | `FEA()` | 이름 중복 확인 |
| normalizePaneName | `BEA()` | pane 이름에서 @ 제거 |
| createPane | `Nu4()` | tmux/iTerm2 pane 생성 |
| sendCommandToPane | `vu4()` | pane에 CLI 명령 전송 |

### 11.5 SendMessage 관련

| 원본 추정명 | 난독화명 | 역할 |
|---|---|---|
| sendDirectMessage | `oSY()` | 1:1 DM 전송 |
| sendBroadcast | `aSY()` | 전체 브로드캐스트 |
| sendShutdownRequest | `sSY()` | 종료 요청 |
| handleShutdownApprove | `tSY()` | 종료 승인 처리 |
| handleShutdownReject | `eSY()` | 종료 거부 처리 |
| handlePlanApprovalApprove | `AhY()` | 계획 승인 처리 |
| handlePlanApprovalReject | `qhY()` | 계획 거부 처리 |
| normalizeRecipient | `qi4()` | 수신자 이름 정규화 (@제거) |
| getSenderName | `g5()` | 발신자 이름 결정 |
| getSenderColor | `b$()` | 발신자 색상 취득 |
| createShutdownRequest | `lP1()` | shutdown_request JSON 생성 |
| createShutdownApproved | `mvA()` | shutdown_approved JSON 생성 |
| createShutdownRejected | `FvA()` | shutdown_rejected JSON 생성 |

### 11.6 SendMessage Zod 스키마

| 메시지 타입 | 스키마 변수명 |
|---|---|
| message (DM) | `pSY` |
| broadcast | `dSY` |
| shutdown_request | `cSY` |
| shutdown_response | `lSY` |
| plan_approval_response | `iSY` |

### 11.7 Hook 관련

| 원본 추정명 | 난독화명 | 역할 |
|---|---|---|
| executeTeammateIdleHooks | `wyA()` | TeammateIdle hook 실행 |
| executeTaskCompletedHooks | `Cg1()` | TaskCompleted hook 실행 |
| formatTeammateIdleHook | `tRA()` | TeammateIdle hook 결과 포맷 |
| formatTaskCompletedHook | `yg1()` | TaskCompleted hook 결과 포맷 |
| spawnHookProcess | `OhY` | child_process.spawn으로 hook 실행 |

### 11.8 Subagent 관련 (비교용)

| 원본 추정명 | 난독화명 | 역할 |
|---|---|---|
| TaskTool.call | `rj1.call()` | Task tool 실행 진입점 |
| subagentGenerator | `dR()` | subagent async iterator 생성 |
| extractResult | `UEA()` | 마지막 텍스트 블록 추출 |
| classifyHandoff | `classifyHandoffIfNeeded()` | 핸드오프 분류 |
| forkContextMessages | `Nn7()` | fork context 메시지 구성 |
| isInProcessTeammate | `MM()` | in-process teammate 여부 확인 |
| filterToolsByType | `YP6()` | subagent_type별 도구 필터링 |

---

## 교차 검증 결과 요약

### 검증 내역

| 검증 쌍 | 주제 | 결과 |
|---|---|---|
| comm ↔ arch | f9() 파일 I/O 기반 확인 | 일치 |
| comm ↔ arch | proper-lockfile 동시성 패턴 | 일치 |
| comm ↔ arch | WVY() 5단계 폴링 우선순위 | 일치 |
| comm ↔ arch | config.json 락킹 부재 확인 | 일치 |
| comm ↔ arch | in-process 이중 inbox 구조 | 일치 (arch가 보완) |
| comm ↔ compare | DM P2P 직접 전달 | 일치 |
| comm ↔ compare | broadcast = N개 개별 f9() 호출 | 일치 |
| comm ↔ compare | Subagent async iterator vs Teams 파일 폴링 | 일치 |
| comm ↔ compare | 3중 폴링 레이어 역할 분리 | 일치 |
| arch ↔ compare | GVY() idle 폴링 메커니즘 | 일치 |
| arch ↔ compare | 자동 task claim (ib4()) | 일치 |
| arch ↔ compare | idle 알림 중복 방지 | 일치 |
| arch ↔ compare | config.json 비일관적 락킹 | 일치 |

**불일치 사항: 0건** — 3명의 연구원이 독립적으로 분석한 모든 발견이 상호 일치함을 확인.

---

## 라이선스 및 면책

이 보고서는 Claude Code v2.1.38 npm 패키지의 번들된 소스코드를 분석한 결과입니다. 난독화된 변수명/함수명은 역공학을 통해 추정한 것이며, 실제 내부 명칭과 다를 수 있습니다. Anthropic의 공식 문서와 상이한 부분은 소스코드 구현을 우선으로 기술했습니다.
