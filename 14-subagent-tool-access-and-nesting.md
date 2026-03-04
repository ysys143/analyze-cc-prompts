# Subagent 도구 접근 제어와 중첩 스폰 분석

> **분석 대상**: Claude Code v2.1.66 (npm 패키지)
> **소스코드**: `cli.js` (12,829줄, 번들된 단일 파일)
> **분석 일자**: 2026-03-05
> **이전 분석 대비**: v2.1.38 (7,618줄) → v2.1.66 (12,829줄), +5,211줄 (+68%)

---

## 목차

1. [핵심 발견](#1-핵심-발견)
2. [Subagent 도구 접근 제어 매핑](#2-subagent-도구-접근-제어-매핑)
3. [중첩 스폰 가능 여부](#3-중첩-스폰-가능-여부)
4. [v2.1.38 → v2.1.66 변경사항](#4-v2138--v2166-변경사항)
5. [아키텍처 시사점](#5-아키텍처-시사점)

---

## 1. 핵심 발견

**Agent tool의 subagent_type별로 사용 가능한 도구 목록이 명시적으로 제한되어 있으며, Agent tool 자체에 대한 접근 여부가 중첩 스폰 가능 여부를 결정한다.**

- 대부분의 전문 에이전트(oh-my-claudecode:*, feature-dev:* 등)는 Agent tool이 도구 목록에 **포함되지 않아** 하위 에이전트를 spawn할 수 없다.
- `general-purpose`(Tools: *)와 일부 `dev:*` 에이전트(All tools)만 중첩 스폰이 가능하다.
- 이는 의도적인 설계로, 무한 재귀 스폰과 토큰 폭주를 방지한다.

---

## 2. Subagent 도구 접근 제어 매핑

### 2.1 빌트인 에이전트 타입

| subagent_type | 도구 목록 | Agent tool 포함 |
|---|---|---|
| `general-purpose` | `*` (전체) | **Yes** |
| `Explore` | All tools except Agent, ExitPlanMode, Edit, Write, NotebookEdit | **No** |
| `Plan` | All tools except Agent, ExitPlanMode, Edit, Write, NotebookEdit | **No** |
| `statusline-setup` | Read, Edit | No |

### 2.2 feature-dev 플러그인 에이전트

| subagent_type | 도구 목록 | Agent tool 포함 |
|---|---|---|
| `feature-dev:code-architect` | Glob, Grep, LS, Read, NotebookRead, WebFetch, TodoWrite, WebSearch, KillShell, BashOutput | **No** |
| `feature-dev:code-reviewer` | (동일) | **No** |
| `feature-dev:code-explorer` | (동일) | **No** |

### 2.3 dev 플러그인 에이전트

| subagent_type | 도구 목록 | Agent tool 포함 |
|---|---|---|
| `dev:codebase-explorer` | All tools | **Yes** |
| `dev:decision-synthesizer` | All tools | **Yes** |
| `dev:docs-researcher` | All tools | **Yes** |
| `dev:tradeoff-analyzer` | All tools | **Yes** |

### 2.4 oh-my-claudecode 에이전트 (28종)

**공통 패턴: 어떤 omc 에이전트도 Agent tool을 포함하지 않는다.**

| subagent_type | 도구 목록 | Agent tool 포함 |
|---|---|---|
| `omc:architect` | Read, Grep, Glob, Bash, WebSearch | **No** |
| `omc:architect-medium` | Read, Glob, Grep, WebSearch, WebFetch | **No** |
| `omc:architect-low` | Read, Glob, Grep | **No** |
| `omc:executor` | Read, Glob, Grep, Edit, Write, Bash, TodoWrite | **No** |
| `omc:executor-high` | Read, Glob, Grep, Edit, Write, Bash, TodoWrite | **No** |
| `omc:executor-low` | Read, Glob, Grep, Edit, Write, Bash, TodoWrite | **No** |
| `omc:explore` | Read, Glob, Grep, Bash | **No** |
| `omc:explore-medium` | Read, Glob, Grep | **No** |
| `omc:planner` | Read, Glob, Grep, Edit, Write, Bash, WebSearch | **No** |
| `omc:designer` | Read, Glob, Grep, Edit, Write, Bash | **No** |
| `omc:designer-high` | Read, Glob, Grep, Edit, Write, Bash | **No** |
| `omc:designer-low` | Read, Glob, Grep, Edit, Write, Bash | **No** |
| `omc:researcher` | Read, Glob, Grep, WebSearch, WebFetch | **No** |
| `omc:researcher-low` | Read, Glob, Grep, WebSearch, WebFetch | **No** |
| `omc:writer` | Read, Glob, Grep, Edit, Write | **No** |
| `omc:vision` | Read, Glob, Grep | **No** |
| `omc:scientist` | Read, Glob, Grep, Bash, python_repl | **No** |
| `omc:scientist-high` | Read, Glob, Grep, Bash, python_repl | **No** |
| `omc:scientist-low` | Read, Glob, Grep, Bash, python_repl | **No** |
| `omc:qa-tester` | Read, Glob, Grep, Bash | **No** |
| `omc:security-reviewer` | Read, Grep, Glob, Bash | **No** |
| `omc:security-reviewer-low` | Read, Grep, Glob, Bash | **No** |
| `omc:build-fixer` | Read, Grep, Glob, Edit, Write, Bash | **No** |
| `omc:build-fixer-low` | Read, Grep, Glob, Edit, Write, Bash | **No** |
| `omc:code-reviewer` | Read, Grep, Glob, Bash | **No** |
| `omc:code-reviewer-low` | Read, Grep, Glob, Bash | **No** |
| `omc:tdd-guide` | Read, Grep, Glob, Edit, Write, Bash | **No** |
| `omc:tdd-guide-low` | Read, Grep, Glob, Bash | **No** |
| `omc:analyst` | Read, Glob, Grep, WebSearch | **No** |
| `omc:critic` | Read, Glob, Grep | **No** |

### 2.5 기타 플러그인 에이전트

| subagent_type | 도구 목록 | Agent tool 포함 |
|---|---|---|
| `superpowers:code-reviewer` | All tools | **Yes** |
| `code-simplifier:code-simplifier` | All tools | **Yes** |
| `log-prompt-context:CLAUDE` | All tools | **Yes** |
| `log-prompt-context:doc-updater` | Read, Glob, Grep | **No** |
| `log-prompt-context:automation-scout` | Read, Glob, Grep | **No** |
| `log-prompt-context:duplicate-checker` | Read, Glob, Grep | **No** |
| `log-prompt-context:followup-suggester` | Read, Glob, Grep | **No** |
| `log-prompt-context:learning-extractor` | Read, Glob, Grep | **No** |
| `claude-code-guide` | Glob, Grep, Read, WebFetch, WebSearch | **No** |

---

## 3. 중첩 스폰 가능 여부

### 3.1 중첩 스폰 가능한 에이전트 (7종)

```
general-purpose          → Tools: * (전체)
dev:codebase-explorer    → All tools
dev:decision-synthesizer → All tools
dev:docs-researcher      → All tools
dev:tradeoff-analyzer    → All tools
superpowers:code-reviewer → All tools
code-simplifier:code-simplifier → All tools
log-prompt-context:CLAUDE → All tools
```

### 3.2 중첩 스폰 불가능한 에이전트 (나머지 전부)

`Explore`, `Plan`, 모든 `oh-my-claudecode:*`, 모든 `feature-dev:*`, 대부분의 `log-prompt-context:*`, `claude-code-guide` 등.

### 3.3 중첩 깊이 제한

시스템 프롬프트에는 명시적인 중첩 깊이 제한이 보이지 않으나, 실질적으로:
- 각 에이전트는 독립 context window를 사용
- 중첩할수록 토큰 비용이 기하급수적으로 증가
- 부모 에이전트는 자식이 완료될 때까지 블로킹 대기 (foreground) 또는 비동기 대기 (background)

---

## 4. v2.1.38 → v2.1.66 변경사항

### 4.1 규모 변화

| 항목 | v2.1.38 | v2.1.66 | 변화 |
|------|---------|---------|------|
| cli.js 줄 수 | 7,618 | 12,829 | +68% |
| 패키지 버전 | 2.1.38 | 2.1.66 | +28 릴리스 |

### 4.2 새로 추가된 에이전트 관련 기능

시스템 프롬프트 분석 기준으로 v2.1.66에서 확인된 주요 추가/변경:

- **TeamCreate/TeamDelete**: 팀 생성·삭제 도구가 시스템 프롬프트에 완전히 통합
- **SendMessage**: `message`, `broadcast`, `shutdown_request`, `shutdown_response`, `plan_approval_response` 5가지 메시지 타입 지원
- **TaskCreate/TaskUpdate/TaskGet/TaskList**: 완전한 Task 관리 도구 세트
- **EnterWorktree**: Git worktree 기반 격리 실행 지원
- **ToolSearch**: 지연 로딩 도구 검색 시스템 (deferred tools)
- **LSP**: Language Server Protocol 통합 (goToDefinition, findReferences 등 10개 operation)
- **EnterPlanMode**: 구현 전 계획 수립 모드
- **Skill**: 스킬 시스템 통합
- **Agent isolation**: `isolation: "worktree"` 파라미터로 에이전트를 독립 git worktree에서 실행 가능
- **Agent resume**: `resume` 파라미터로 이전 에이전트 세션 재개 가능
- **Background agents**: `run_in_background` 파라미터로 비동기 실행, 자동 완료 알림

### 4.3 시스템 프롬프트 구조 변화

v2.1.38의 프롬프트와 비교했을 때 주요 차이점:
- 도구 설명이 훨씬 상세해짐 (각 도구별 usage notes, examples 포함)
- 에이전트 간 통신 프로토콜이 체계화됨 (SendMessage의 5가지 타입)
- 팀 관리 워크플로우가 명시적으로 문서화됨
- "Teammate Idle State" 개념이 명시적으로 설명됨
- 도구 사용 가이드라인이 대폭 강화 (Bash 대신 전용 도구 사용 권장 등)

---

## 5. 아키텍처 시사점

### 5.1 의도적 비대칭 설계

```
┌─────────────────────────────────────────────────┐
│              Main Agent (conductor)               │
│  Tools: * (전체)                                  │
│  Agent tool 접근: Yes → 하위 에이전트 spawn 가능    │
├─────────────────────────────────────────────────┤
│    ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│    │ executor │  │ architect│  │ designer │     │
│    │ (sonnet) │  │ (opus)   │  │ (sonnet) │     │
│    │ Agent: No│  │ Agent: No│  │ Agent: No│     │
│    │ 실행만   │  │ 분석만    │  │ 디자인만  │     │
│    └──────────┘  └──────────┘  └──────────┘     │
│    중첩 spawn 불가 - 리프 노드 역할               │
└─────────────────────────────────────────────────┘
```

이 설계의 의도:
1. **토큰 비용 제어**: 전문 에이전트가 다시 에이전트를 spawn하면 비용이 기하급수적으로 증가
2. **실행 시간 예측**: 중첩이 없으면 최대 2단계(main → specialist)로 제한
3. **역할 분리 강제**: executor는 실행에만 집중, 오케스트레이션은 main agent의 책임
4. **오류 전파 단순화**: 에러가 발생하면 main agent가 직접 처리

### 5.2 TeamCreate의 차별점

Agent tool로 spawn하는 일반 subagent와 달리, TeamCreate로 생성된 팀은:
- 공유 task list로 비동기 협업
- SendMessage로 P2P 통신
- 각 teammate는 독립적인 Agent tool 호출로 생성되므로, 팀원의 도구 접근은 spawn 시 지정한 subagent_type에 의존
- 팀원이 `general-purpose`로 spawn되면 중첩 spawn 가능, 전문 타입이면 불가

### 5.3 실용적 함의

**팀원이 하위 에이전트를 spawn해야 하는 경우의 우회 방법:**
1. 팀원을 `general-purpose`로 spawn (but: 전문성 없는 범용 프롬프트)
2. 팀 리더가 직접 추가 에이전트를 spawn하여 결과를 전달 (권장)
3. 필요한 작업을 task로 만들어 다른 팀원에게 할당

---

## 부록: 도구 축약 표기법

시스템 프롬프트에서 사용되는 도구 표기:

| 표기 | 의미 |
|------|------|
| `*` | 모든 도구 접근 가능 |
| `All tools` | 모든 도구 접근 가능 (Agent 포함) |
| `All tools except X, Y` | X, Y를 제외한 모든 도구 |
| 개별 나열 | 나열된 도구만 접근 가능 |

> **참고**: `*`와 `All tools`는 실질적으로 동일하나, `All tools except ...` 형태는 명시적 제외가 있으므로 다름.
