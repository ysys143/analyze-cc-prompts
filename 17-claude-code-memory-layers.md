# Claude Code Native Memory Layer 분석

> 분석 대상: `@anthropic-ai/claude-code@2.1.70` (`cli.js`) + [공식 문서](https://code.claude.com/docs/en/memory)

Claude Code는 **2개의 상호보완적 메모리 시스템**과 이를 지탱하는 **컴팩션/훅 메커니즘**으로 구성됩니다. 매 세션은 빈 컨텍스트 윈도우로 시작하며, 이 두 메모리 시스템이 세션 간 지식을 전달합니다.

---

## 전체 구조 요약

| | CLAUDE.md 파일 | Auto Memory |
|:--|:--|:--|
| **작성 주체** | 사용자 | Claude |
| **내용** | 지시사항, 규칙 | 학습, 패턴 |
| **범위** | 프로젝트, 사용자, 조직 | 워킹 트리 단위 |
| **로딩** | 매 세션 전체 로드 | 매 세션 (첫 200줄) |
| **용도** | 코딩 표준, 워크플로, 아키텍처 | 빌드 커맨드, 디버깅 인사이트, 선호도 |

---

## 1. CLAUDE.md 파일 시스템

### 1.1 스코프 계층 구조

CLAUDE.md는 여러 위치에 배치할 수 있으며, 더 구체적인 위치가 더 넓은 위치보다 우선합니다.

| 스코프 | 위치 | 용도 | 공유 범위 |
|:--|:--|:--|:--|
| **Managed Policy** | macOS: `/Library/Application Support/ClaudeCode/CLAUDE.md`<br/>Linux/WSL: `/etc/claude-code/CLAUDE.md`<br/>Windows: `C:\Program Files\ClaudeCode\CLAUDE.md` | IT/DevOps가 관리하는 조직 전체 지시사항 | 조직 내 모든 사용자 |
| **Project** | `./CLAUDE.md` 또는 `./.claude/CLAUDE.md` | 팀 공유 프로젝트 지시사항 | 팀 (소스 컨트롤) |
| **User** | `~/.claude/CLAUDE.md` | 모든 프로젝트에 적용되는 개인 선호 | 본인만 (전체 프로젝트) |
| **Local** | `./CLAUDE.local.md` | git에 커밋하지 않는 개인 프로젝트별 설정 | 본인만 (현재 프로젝트) |

### 1.2 로딩 메커니즘 (cli.js 분석)

`cli.js`의 `VJ` 함수(memoized)가 세션 시작 시 CLAUDE.md 파일들을 수집합니다:

```
로딩 순서:
1. Managed Policy CLAUDE.md (제외 불가)
2. Managed Policy .claude/rules/*.md
3. User CLAUDE.md (~/.claude/CLAUDE.md) + ~/.claude/rules/*.md
4. 현재 디렉토리 → 루트까지 상위 디렉토리 순회:
   - 각 디렉토리에서 CLAUDE.md, .claude/CLAUDE.md (Project)
   - 각 디렉토리에서 .claude/rules/*.md (조건부 규칙 포함)
   - 각 디렉토리에서 CLAUDE.local.md (Local)
5. --add-dir로 지정된 추가 디렉토리 (CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1일 때)
6. Auto Memory MEMORY.md (autoMemoryEnabled일 때)
```

**코드 증거** (cli.js 라인 905):
```javascript
// 각 파일의 type 라벨:
// "Project" - (project instructions, checked into the codebase)
// "Local"   - (user's private project instructions, not checked in)
// "AutoMem" - (user's auto-memory, persists across conversations)
// "User"    - (user's private global instructions for all projects)
// "Managed" - (organization-wide managed policy)
```

**컨텍스트 주입 형태** (cli.js `x84` 함수):
```
Codebase and user instructions are shown below. Be sure to adhere to these
instructions. IMPORTANT: These instructions OVERRIDE any default behavior
and you MUST follow them exactly as written.

Contents of /path/to/CLAUDE.md (project instructions, checked into the codebase):
[파일 내용]

Contents of ~/.claude/CLAUDE.md (user's private global instructions for all projects):
[파일 내용]
```

### 1.3 @import 시스템

CLAUDE.md 파일 내에서 `@path/to/file` 구문으로 외부 파일을 임포트할 수 있습니다:

```markdown
See @README for project overview and @package.json for available npm commands.
# Additional Instructions
- git workflow @docs/git-instructions.md
```

**구현 상세:**
- `Um9` 함수가 Markdown lexer로 텍스트 토큰에서 `@` 참조를 추출
- 코드 블록(`code`, `codespan`) 내부의 `@`는 무시
- 상대/절대 경로 모두 지원, `~/` 홈 디렉토리 확장
- 최대 재귀 깊이: **5 홉** (`dm9 = 5`)
- 최초 외부 임포트 발견 시 사용자 승인 다이얼로그 표시
- 허용 확장자 화이트리스트: `.md`, `.txt`, `.json`, `.yaml`, `.ts`, `.py`, `.go`, `.rs` 등 80여 개 (`Qm9` Set)

### 1.4 `.claude/rules/` 시스템

지시사항을 주제별 파일로 분리하는 모듈화 시스템:

```
your-project/
├── .claude/
│   ├── CLAUDE.md           # 메인 프로젝트 지시사항
│   └── rules/
│       ├── code-style.md   # 코드 스타일
│       ├── testing.md      # 테스팅 규칙
│       └── security.md     # 보안 요구사항
```

**경로 조건부 규칙 (Path-specific rules):**

YAML frontmatter의 `paths` 필드로 특정 파일 패턴에만 적용:

```markdown
---
paths:
  - "src/api/**/*.ts"
  - "lib/**/*.ts"
---
# API Development Rules
- All API endpoints must include input validation
```

**구현:** `B96` 함수가 재귀적으로 rules 디렉토리를 탐색하고, `pm9` 함수가 frontmatter에서 paths를 파싱합니다. 조건부 규칙(`conditionalRule: true`)은 `$X1` 함수에서 현재 작업 파일과 glob 매칭 후 로드합니다.

| 패턴 | 매칭 대상 |
|:--|:--|
| `**/*.ts` | 모든 디렉토리의 TypeScript 파일 |
| `src/**/*` | src/ 하위 모든 파일 |
| `*.md` | 프로젝트 루트의 Markdown 파일 |
| `src/components/*.tsx` | 특정 디렉토리의 React 컴포넌트 |

**심링크 지원:** `.claude/rules/`는 심링크를 지원하여 여러 프로젝트 간 규칙 공유가 가능합니다. 순환 심링크 감지 처리됨.

### 1.5 claudeMdExcludes

대형 모노레포에서 다른 팀의 CLAUDE.md를 제외하는 설정:

```json
// .claude/settings.local.json
{
  "claudeMdExcludes": [
    "**/monorepo/CLAUDE.md",
    "/home/user/monorepo/other-team/.claude/rules/**"
  ]
}
```

**구현:** `cm9` 함수에서 glob 매칭으로 절대 경로 비교. Managed Policy CLAUDE.md는 제외 불가.

### 1.6 대용량 파일 경고

`Pl = 40000` (40,000자) 이상의 CLAUDE.md 파일은 `g96` 함수에서 경고 대상으로 필터링됩니다.

---

## 2. Auto Memory 시스템

### 2.1 저장 위치

```
~/.claude/projects/<project>/memory/
├── MEMORY.md          # 인덱스 파일 (매 세션 로드)
├── debugging.md       # 상세 메모 (온디맨드 읽기)
├── api-conventions.md # API 설계 결정
└── ...                # Claude가 생성하는 토픽 파일들
```

- `<project>` 경로는 git 리포지토리에서 파생 → **같은 repo의 모든 워크트리/하위 디렉토리가 하나의 auto memory를 공유**
- git 리포가 아닌 경우 프로젝트 루트 사용
- 머신 로컬 (다른 머신/클라우드와 공유 안 됨)

### 2.2 활성화/비활성화

```json
// 프로젝트 설정
{ "autoMemoryEnabled": false }
```

또는 환경변수: `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`

**코드 증거** (cli.js `_X1` 함수):
```javascript
function _X1() {
  let A = c9();  // autoMemoryEnabled 체크
  let q = e8("tengu_swinburne_dune", false);  // 구조화된 메모리 피처 플래그
  if (A) {
    if (q) return y84("auto memory", By()).join("\n");  // 구조화된 메모리
    return bm9();  // 기본 auto memory
  }
  return null;  // 비활성화됨
}
```

### 2.3 MEMORY.md 로딩 규칙

- **첫 200줄만** 세션 시작 시 로드 (`lZ = 200`)
- 200줄 초과 시 경고 메시지 자동 추가:
  ```
  > WARNING: MEMORY.md is {N} lines (limit: 200). Only the first 200 lines
  > were loaded. Move detailed content into separate topic files and keep
  > MEMORY.md as a concise index.
  ```
- 토픽 파일(`debugging.md` 등)은 시작 시 로드되지 않음 → Claude가 필요할 때 파일 도구로 직접 읽음
- CLAUDE.md 파일은 길이 제한 없이 전체 로드 (단, 짧을수록 준수도 향상)

### 2.4 기본 Auto Memory 시스템 프롬프트

`bm9` 함수가 생성하는 시스템 프롬프트:

```markdown
# auto memory

You have a persistent auto memory directory at `{path}`.
Its contents persist across conversations.

As you work, consult your memory files to build on previous experience.

## How to save memories:
- Organize memory semantically by topic, not chronologically
- Use the Write and Edit tools to update your memory files
- `MEMORY.md` is always loaded into your conversation context
  — lines after 200 will be truncated, so keep it concise
- Create separate topic files (e.g., `debugging.md`, `patterns.md`)
  for detailed notes and link to them from MEMORY.md
- Update or remove memories that turn out to be wrong or outdated
- Do not write duplicate memories.

## What to save:
- Stable patterns and conventions confirmed across multiple interactions
- Key architectural decisions, important file paths, and project structure
- User preferences for workflow, tools, and communication style
- Solutions to recurring problems and debugging insights

## What NOT to save:
- Session-specific context (current task details, in-progress work)
- Information that might be incomplete
- Anything that duplicates or contradicts existing CLAUDE.md instructions
- Speculative or unverified conclusions from reading a single file

## Explicit user requests:
- "always use bun", "never auto-commit" → 즉시 저장
- "forget X" → 관련 엔트리 찾아 삭제
- 사용자가 메모리 기반 발언을 교정하면 → 반드시 업데이트/삭제
```

### 2.5 구조화된 메모리 시스템 (Feature Flag: `tengu_swinburne_dune`)

피처 플래그가 활성화되면 `y84` 함수로 **더 정교한 메모리 시스템**이 사용됩니다:

#### 메모리 타입 분류

| 타입 | 설명 | 저장 시점 | 사용 시점 |
|:--|:--|:--|:--|
| **user** | 사용자 역할, 목표, 책임, 지식 | 사용자 프로필 관련 정보 학습 시 | 사용자 관점에 맞춘 작업 수행 시 |
| **feedback** | 사용자의 교정/피드백 | "no not that...", "don't..." 등 교정 시 | 같은 실수 반복 방지 |
| **project** | 진행 중인 작업, 목표, 이니셔티브, 버그, 인시던트 | 누가 무엇을 왜 언제까지 하는지 학습 시 | 요청의 배경/뉘앙스 이해 시 |
| **reference** | 외부 시스템 정보 위치 포인터 | 외부 시스템/리소스 위치 학습 시 | 외부 시스템 참조 필요 시 |

#### 구조화된 메모리 파일 형식

```markdown
---
name: {{memory name}}
description: {{one-line description}}
type: {{user, feedback, project, reference}}
---

{{memory content}}
```

#### 저장하지 말아야 할 것 (명시적 제외)

- 코드 패턴, 컨벤션, 아키텍처, 파일 경로 — 코드에서 직접 파생 가능
- Git 히스토리, 최근 변경 — `git log`/`git blame`이 권위적 소스
- 디버깅 솔루션/수정 레시피 — 코드와 커밋 메시지에 이미 있음
- CLAUDE.md에 이미 있는 내용
- 임시 작업 상태

#### Plan/Task와의 구분

- **Plan**: 비트리비얼 구현 전 접근방식 정렬 → 메모리가 아닌 플랜 사용
- **Task**: 현재 대화의 작업 분해/진행 추적 → 메모리가 아닌 태스크 사용
- **Memory**: 미래 대화에서 유용할 정보만

### 2.6 세션 트랜스크립트 검색 (Feature Flag: `tengu_coral_fern`)

이 플래그가 활성화되면 메모리 시스템에 **과거 세션 트랜스크립트 검색 기능**이 추가됩니다:

```markdown
## Searching past context

When looking for past context:
1. Search topic files in your memory directory:
   Grep with pattern="<search term>" path="{memoryDir}" glob="*.md"
2. Session transcript logs (last resort — large files, slow):
   Grep with pattern="<search term>" path="{transcriptDir}/" glob="*.jsonl"

Use narrow search terms (error messages, file paths, function names)
rather than broad keywords.
```

### 2.7 메모리 접근 추적

`a$q` 모듈의 `v3z` 함수가 PostToolUse 훅으로 등록되어, Read/Edit/Write/Glob/Grep 도구 사용 시 메모리 파일 접근을 추적합니다:

- `tengu_memdir_accessed` — 메모리 디렉토리 파일 접근
- `tengu_memdir_file_read` — 메모리 파일 읽기
- `tengu_memdir_file_edit` — 메모리 파일 편집
- `tengu_memdir_file_write` — 메모리 파일 쓰기
- `tengu_session_memory_accessed` — 세션 메모리 접근
- `tengu_transcript_accessed` — 트랜스크립트 접근

---

## 3. 컴팩션 (Compaction) 메커니즘

컨텍스트 윈도우가 가득 차면 자동으로 컴팩션이 실행됩니다. 메모리 시스템과 밀접하게 연동됩니다.

### 3.1 컴팩션 프로세스

```
컨텍스트 윈도우 한계 도달
  │
  ├─> PreCompact 훅 실행 (사용자 정의 훅)
  │     - exit 0: stdout가 커스텀 컴팩트 지시사항으로 추가
  │     - exit 2: 컴팩션 차단
  │
  ├─> 요약 모델 실행 (별도 LLM 호출)
  │     - 전체 대화를 분석하여 <summary> 생성
  │     - 파일명, 코드 스니펫, 에러 메시지, 결정 등 보존
  │
  ├─> 요약으로 기존 메시지 대체
  │     - "This session is being continued from a previous
  │        conversation that ran out of context."
  │     - 트랜스크립트 경로 제공 (상세 복구용)
  │
  └─> CLAUDE.md 재로드 (디스크에서 다시 읽음)
        - CLAUDE.md는 컴팩션을 100% 생존
        - 대화 중 구두로만 준 지시사항은 손실됨
```

### 3.2 요약 프롬프트 (cli.js 라인 1211)

컴팩션 시 사용되는 요약 지시사항:

```
1. 대화의 각 메시지/섹션을 시간순으로 분석:
   - 사용자의 명시적 요청과 의도
   - 접근 방식
   - 핵심 결정, 기술 개념, 코드 패턴
   - 구체적 상세: 파일명, 전체 코드 스니펫,
     정확한 명령어, 설정 값, URL, 경로
   - 진행 상태 (완료/진행 중/미시작)
   - 에러 메시지와 해결 상태
```

### 3.3 컴팩션 후 복구 메시지

```
This session is being continued from a previous conversation that
ran out of context. The summary below covers the earlier portion.

[요약 내용]

If you need specific details from before compaction (like exact code
snippets, error messages, or content you generated), read the full
transcript at: {transcript_path}

Continue the conversation from where it left off without asking the
user any further questions. Resume directly — do not acknowledge the
summary, do not recap, do not preface with "I'll continue".
```

### 3.4 Autocompact Buffer

컨텍스트 사용량 시각화(`/context` 명령)에서 **Autocompact buffer**가 별도 항목으로 표시됩니다. 이는 컴팩션 요약을 위한 예약 공간입니다.

---

## 4. Hook 시스템과 메모리 연동

### 4.1 InstructionsLoaded 훅

어떤 CLAUDE.md/rules 파일이 로드되었는지 추적하는 훅:

```javascript
// cli.js의 eQ6 함수로 발행
eQ6(filePath, fileType, loadReason, { globs, parentFilePath })
// loadReason: "include" (import로) 또는 "session_start" (세션 시작 시)
```

디버깅 시 `InstructionsLoaded` 훅을 설정하면 경로별 규칙이나 하위 디렉토리의 지연 로드 파일이 정확히 언제 로드되는지 확인할 수 있습니다.

### 4.2 PreCompact 훅

```json
// hooks 설정
{
  "hooks": {
    "PreCompact": [{
      "command": "your-script.sh",
      "matcher": { "trigger": "manual" }  // 또는 "auto"
    }]
  }
}
```

- **exit 0**: stdout가 커스텀 컴팩트 지시사항으로 추가
- **exit 2**: 컴팩션 차단
- 기타: stderr를 사용자에게 표시하되 컴팩션 계속

### 4.3 NotificationHook 이벤트 (`Stop` 소스: `compact`)

```javascript
// Stop 훅의 source 필드로 compact 이벤트 감지 가능
matcherMetadata: {
  fieldToMatch: "source",
  values: ["startup", "resume", "clear", "compact"]
}
```

---

## 5. `/memory` 명령

세션 내에서 `/memory`를 실행하면:

1. 현재 세션에 로드된 모든 CLAUDE.md 및 rules 파일 목록 표시
2. Auto memory 토글 (on/off)
3. Auto memory 폴더 열기 링크
4. 파일 선택 시 에디터에서 열기

### `/init` 명령

코드베이스를 분석하여 시작 CLAUDE.md를 자동 생성:

```javascript
// cli.js 라인 4060-4061
// - 이미 CLAUDE.md가 있으면 개선 제안
// - 반복 금지, 자명한 지시사항 제외:
//   "Provide helpful error messages",
//   "Write unit tests for all new utilities",
//   "Never include sensitive information" 등은 작성하지 않음
```

---

## 6. 서브에이전트 메모리

서브에이전트(Agent tool로 생성)도 자체 auto memory를 유지할 수 있습니다:

- 에이전트별 메모리 디렉토리 별도 존재
- `memory_type: "agent"` vs `"auto"` 구분
- 동일한 200줄 제한 적용
- `L84` 함수 또는 `R84` 함수(구조화된 메모리)로 에이전트 메모리 프롬프트 생성

---

## 7. 텔레메트리와 메모리

cli.js에서 메모리 관련 텔레메트리 이벤트:

| 이벤트 | 설명 |
|:--|:--|
| `tengu_memdir_loaded` | 메모리 디렉토리 로드 (파일 수, 하위 디렉토리 수) |
| `tengu_memdir_accessed` | 메모리 디렉토리 접근 |
| `tengu_memdir_file_read/edit/write` | 메모리 파일 CRUD |
| `tengu_memdir_disabled` | 메모리 비활성화 (env var 또는 설정에 의해) |
| `tengu_claudemd__initial_load` | CLAUDE.md 최초 로드 통계 (파일 수, 크기, 타입별 카운트) |
| `tengu_claude_md_permission_error` | CLAUDE.md 접근 권한 에러 |
| `tengu_claude_rules_md_permission_error` | rules 파일 접근 권한 에러 |
| `tengu_session_memory_accessed` | 세션 메모리 접근 |
| `tengu_transcript_accessed` | 트랜스크립트 접근 |
| `tengu_config_parse_error` | 설정 파일 파싱 에러 |

---

## 8. 메모리 레이어 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────────┐
│                    Claude Code 세션 시작                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─── 1. CLAUDE.md 로딩 (VJ 함수, memoized) ───────────────┐  │
│  │                                                           │  │
│  │  ① Managed Policy  (/Library/Application Support/...)     │  │
│  │  ② User           (~/.claude/CLAUDE.md)                   │  │
│  │  ③ Project         (./CLAUDE.md, ./.claude/CLAUDE.md)     │  │
│  │  ④ Local           (./CLAUDE.local.md)                    │  │
│  │  ⑤ Rules           (./.claude/rules/*.md)                 │  │
│  │     └─ 조건부 규칙: paths 매칭 시에만 로드               │  │
│  │  ⑥ @import          (재귀, 최대 5홉)                      │  │
│  │                                                           │  │
│  │  → 전체 내용 컨텍스트에 주입                              │  │
│  │  → claudeMdExcludes로 제외 가능                           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─── 2. Auto Memory 로딩 ──────────────────────────────────┐  │
│  │                                                           │  │
│  │  ~/.claude/projects/<project>/memory/MEMORY.md            │  │
│  │  → 첫 200줄만 로드                                        │  │
│  │  → 토픽 파일은 온디맨드 읽기                              │  │
│  │  → 구조화된 메모리: user/feedback/project/reference 타입  │  │
│  │                                                           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─── 3. Git 상태 스냅샷 (HT8 함수) ───────────────────────┐  │
│  │  현재 브랜치, 메인 브랜치, git status --short, log -5     │  │
│  │  → 40,000자 초과 시 잘림                                  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                    세션 진행 중                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─── PostToolUse 훅 ───────────────────────────────────────┐  │
│  │  - 메모리 파일 접근 추적 (Read/Edit/Write/Glob/Grep)     │  │
│  │  - 하위 디렉토리 CLAUDE.md 지연 로드                      │  │
│  │  - 조건부 rules 활성화 (파일 매칭 시)                     │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─── Claude의 메모리 쓰기 ─────────────────────────────────┐  │
│  │  - Write/Edit 도구로 MEMORY.md 및 토픽 파일 직접 수정     │  │
│  │  - "Writing memory" / "Recalled memory" UI 표시           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                    컨텍스트 윈도우 한계                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─── 컴팩션 프로세스 ──────────────────────────────────────┐  │
│  │  ① PreCompact 훅 실행                                     │  │
│  │  ② 대화 요약 생성 (별도 LLM 호출)                         │  │
│  │  ③ CLAUDE.md 디스크에서 재로드 (100% 생존)                │  │
│  │  ④ Auto Memory MEMORY.md 재로드 (200줄)                   │  │
│  │  ⑤ 트랜스크립트 경로 제공 (상세 복구용)                   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                    세션 종료                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─── 캐시 정리 (id8 함수) ─────────────────────────────────┐  │
│  │  - VJ (CLAUDE.md 캐시) 클리어                             │  │
│  │  - oO, HT8 (git 상태) 클리어                              │  │
│  │  - 각종 내부 캐시 일괄 정리                               │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  메모리 디렉토리의 파일들은 디스크에 영구 보존                  │
│  → 다음 세션에서 다시 로드됨                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 10. 세션 트랜스크립트 검색 MCP와 미들웨어 아키텍처

### 10.1 "Grep Is Dead" 접근 방식

커뮤니티에서는 세션 트랜스크립트(`~/.claude/projects/<project>/*.jsonl`)에 인덱싱(qmd 등)을 붙여 MCP 도구로 과거 세션을 검색하는 방식이 등장했다 (참고: [Grep Is Dead: How I Made Claude Code Actually Remember Things](https://x.com/ArtemXTech/status/2028330693659332615)).

이 방식은 claude-mem 같은 "push" 모델(CLAUDE.md에 히스토리 강제 주입)과 달리, **"pull" 모델**(필요할 때만 MCP 도구 호출)이라 컨텍스트 윈도우를 오염시키지 않는다는 장점이 있다.

```
claude-mem (push, context rot 유발):
  세션 시작 → 전체 히스토리 CLAUDE.md에 강제 주입 → 항상 토큰 소비

qmd MCP (pull, 온디맨드):
  세션 시작 → 아무것도 주입 안 함
  필요할 때 → MCP 도구 호출 → 검색 결과만 컨텍스트에 추가
  사용 안 하면 → 토큰 소비 0
```

### 10.2 미들웨어의 중요성

그러나 pull 모델이라도 검색 결과를 그대로 오케스트레이터에 전달하면 결국 같은 문제가 발생한다. **검색 → 필터링 → 주입** 파이프라인에서 미들웨어 레이어가 핵심이다:

```
┌─────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  qmd/인덱스  │───→│   미들웨어 레이어  │───→│  오케스트레이터   │
│  (raw 검색)  │    │  (필터+압축+랭킹)  │    │  (컨텍스트 주입)  │
└─────────────┘    └──────────────────┘    └─────────────────┘
     10K+                1-2K                  컨텍스트에 적합
```

미들웨어가 수행해야 할 역할:

| 역할 | 설명 |
|:--|:--|
| **토큰 버짓 강제** | 반환 크기 상한 (e.g. 2000 토큰) |
| **관련성 랭킹** | 현재 쿼리와의 유사도로 정렬, 하위 컷 |
| **중복 제거** | 같은 세션에서 여러 번 나온 동일 패턴 병합 |
| **요약 압축** | raw 트랜스크립트가 아닌 핵심 문장만 추출 |
| **메타데이터 태깅** | 출처 세션, 날짜, 신뢰도를 붙여서 오케스트레이터가 판단 가능하게 |

미들웨어 없이 검색 결과를 그대로 전달하면:

| | 미들웨어 없음 | 미들웨어 있음 |
|:--|:--|:--|
| **검색 결과** | 전부 그대로 전달 | 랭킹 후 상위 N개 |
| **토큰 소비** | 예측 불가, 누적 | 예산 내 고정 |
| **관련성** | 노이즈 포함 | 현재 쿼리에 유의미한 것만 |
| **컴팩션 주기** | 빨라짐 | 영향 최소 |

OMC도 이미 비슷한 패턴을 사용한다: `formatContextSummary`가 Project Memory의 raw JSON을 컨텍스트에 적합한 크기로 포맷하고, `payloadLimits`로 크기를 제한한다. Anthropic의 `tengu_coral_fern` 프롬프트에서도 "Use **narrow** search terms rather than broad keywords"라고 명시하여 검색 단계부터 노이즈를 줄이는 것이 설계 의도임을 보여준다.

### 10.3 네이티브 업데이트 대기 권장

다만, cli.js 분석에서 확인한 두 개의 피처 플래그를 고려하면 **지금 당장 커스텀 MCP를 구축하는 것은 재고할 필요가 있다**:

- **`tengu_coral_fern`**: 과거 세션 트랜스크립트를 메모리 디렉토리 내에서 Grep으로 검색하는 기능. 이미 코드가 준비되어 있고 플래그 뒤에서 대기 중.
- **`tengu_swinburne_dune`**: user/feedback/project/reference 4가지 타입으로 분류하는 구조화된 메모리. frontmatter 기반으로 "무엇을 왜 기억하는가"를 체계화.

이 두 기능이 정식 출시되면:

1. 트랜스크립트 검색이 **네이티브로 통합**되어 별도 인덱싱 없이 동작
2. 구조화된 메모리가 검색 결과의 **관련성 판단을 자체적으로 수행**
3. 기존 Auto Memory(200줄 MEMORY.md + 토픽 파일)와 **원활하게 통합**

커스텀 MCP를 만들면 작동은 하지만, 네이티브 기능이 출시될 때 **마이그레이션 비용**이 발생하고 두 시스템이 유사한 역할을 중복 수행하게 된다. 좋은 아키텍처이긴 하나, Anthropic이 이미 같은 방향으로 준비하고 있는 상황에서는 네이티브 업데이트를 기다리는 편이 현실적이다. 결국 좋은 기억 시스템은 "얼마나 많이 기억하느냐"가 아니라 **"얼마나 적게, 정확하게 꺼내느냐"**의 문제이며, 그 판단은 네이티브 시스템이 가장 잘 할 수 있는 위치에 있다.

---

## 부록: OMC (oh-my-claudecode) 메모리 레이어 상세 분석

이 리포지토리는 Claude Code 네이티브 내부 구조를 분석하는 것이 주목적이지만, 커뮤니티에서 가장 널리 사용되는 플러그인인 OMC의 메모리 아키텍처를 부록으로 수록한다. 네이티브 메모리 시스템과의 설계 철학 차이를 비교하는 데 유용하다.

---

### A. 1. Project Memory (프로젝트 메모리)

**저장 위치:** `.omc/project-memory.json`
**수명:** 영구 (24시간 주기로 자동 리스캔)
**범위:** 프로젝트 단위

프로젝트의 기술 환경을 **자동 감지**하고 저장하는 핵심 메모리. SessionStart 시 자동으로 로드되어 컨텍스트로 주입됩니다.

| 섹션 | 내용 |
|:--|:--|
| `techStack` | 언어, 프레임워크, 패키지 매니저, 런타임 |
| `build` | 빌드/테스트/린트/dev 커맨드, npm scripts |
| `conventions` | 네이밍 스타일, 임포트 스타일, 테스트 패턴 |
| `structure` | 모노레포 여부, 워크스페이스, 주요 디렉토리, git 브랜치 전략 |
| `customNotes` | 수동/학습된 메모 (최대 20개, 카테고리별) |
| `directoryMap` | 디렉토리 구조 및 용도 매핑 |
| `hotPaths` | 자주 접근하는 파일/디렉토리 추적 (접근 횟수 + decay) |
| `userDirectives` | 사용자 지시사항 (최대 20개, 우선순위: high/normal) |

**특징:**
- **Learner 시스템**: PostToolUse 훅에서 Bash 출력, Read/Edit/Glob 패턴을 분석해 자동으로 학습 (런타임 버전, 누락 의존성, 환경변수 등)
- **Directive Detector**: 사용자 메시지에서 "always use...", "never modify...", "must include..." 같은 패턴을 감지해 자동 저장
- **PreCompact 복구**: 컴팩션 시 `systemMessage`로 재주입하여 userDirectives가 컨텍스트 손실을 생존
- **File Lock**: 동시 접근 방지를 위한 크로스프로세스 파일 락 + 인메모리 뮤텍스

**MCP 도구:**
- `project_memory_read` / `project_memory_write`
- `project_memory_add_note` / `project_memory_add_directive`

**소스 코드:**
- 타입 정의: `src/hooks/project-memory/types.ts`
- 스토리지: `src/hooks/project-memory/storage.ts`
- 자동 학습: `src/hooks/project-memory/learner.ts`
- 디렉티브 감지: `src/hooks/project-memory/directive-detector.ts`
- 컴팩션 복구: `src/hooks/project-memory/pre-compact.ts`
- MCP 도구: `src/tools/memory-tools.ts`

---

### A.2. Notepad (노트패드) — 3-Tier 메모리 시스템

**저장 위치:** `.omc/notepad.md`
**범위:** 프로젝트 단위
**형식:** Markdown

컴팩션에 강건한(compaction-resilient) 3단계 메모리:

| 계층 | 섹션 | 수명 | 최대 크기 | 설명 |
|:--|:--|:--|:--|:--|
| **Tier 1** | `## Priority Context` | 영구 | 500자 권장 | **항상** 세션 시작 시 로드됨. 가장 중요한 발견/컨텍스트만 |
| **Tier 2** | `## Working Memory` | 7일 자동 정리 | 4000자/엔트리 | 세션 메모, 타임스탬프 자동 부여. 자동 prune |
| **Tier 3** | `## MANUAL` | 영구 (정리 안 됨) | 4000자/엔트리 | 사용자 콘텐츠. 자동 정리 대상 아님 |

**전체 파일 최대 크기:** 8KB

**MCP 도구:**
- `notepad_read` (section: all/priority/working/manual)
- `notepad_write_priority` (덮어쓰기)
- `notepad_write_working` (추가, 타임스탬프 자동)
- `notepad_write_manual` (추가, 영구 보존)
- `notepad_prune` (Working Memory 정리)
- `notepad_stats` (크기, 엔트리 수, 가장 오래된 엔트리)

**소스 코드:**
- 핵심 구현: `src/hooks/notepad/index.ts`
- MCP 도구: `src/tools/notepad-tools.ts`

---

### A.3. Shared Memory (공유 메모리)

**저장 위치:** `.omc/state/shared-memory/{namespace}/{key}.json`
**수명:** TTL 기반 (최대 7일) 또는 무기한
**범위:** 네임스페이스 단위 (팀/파이프라인 간 공유)

**에이전트 간 크로스-세션 메모리 동기화**를 위한 파일시스템 기반 KV 스토어. `/team`이나 `/pipeline` 워크플로에서 에이전트들이 데이터를 주고받을 때 사용합니다.

| 필드 | 설명 |
|:--|:--|
| `key` | 식별자 (영숫자, 하이픈, 밑줄, 점. 최대 128자) |
| `value` | JSON 직렬화 가능한 임의 값 |
| `namespace` | 그룹핑 식별자 (팀명, 파이프라인 실행 ID 등) |
| `ttl` | 초 단위 TTL (최대 604800 = 7일), 생략 시 무기한 |
| `expiresAt` | TTL에서 자동 계산된 만료 시각 |

**특징:**
- 만료된 엔트리는 read 시 자동 삭제 (lazy cleanup)
- 원자적 쓰기 (tmp + rename)
- path traversal 방지를 위한 네임스페이스/키 유효성 검증
- `~/.claude/.omc-config.json`의 `agents.sharedMemory.enabled`로 on/off (기본: 활성)

**MCP 도구:**
- `shared_memory_write` / `shared_memory_read`
- `shared_memory_list` / `shared_memory_delete`
- `shared_memory_cleanup` (만료 엔트리 정리)

**소스 코드:**
- 핵심 구현: `src/lib/shared-memory.ts`
- MCP 도구: `src/tools/shared-memory-tools.ts`

---

### A.4. Notepad Wisdom (플랜별 위즈덤)

**저장 위치:** `.omc/notepads/{plan-name}/` (4개 파일)
**수명:** 영구
**범위:** 플랜(Plan) 단위

계획(plan) 실행 중 축적되는 **구조화된 지식**:

| 파일 | 카테고리 | 용도 |
|:--|:--|:--|
| `learnings.md` | 학습 | 기술적 발견, 패턴 |
| `decisions.md` | 결정 | 아키텍처/디자인 결정 |
| `issues.md` | 이슈 | 알려진 이슈, 워크어라운드 |
| `problems.md` | 문제 | 블로커, 도전 과제 |

각 엔트리는 `## YYYY-MM-DD HH:MM:SS` 형식으로 타임스탬프됩니다. PreCompact 시 자동으로 체크포인트에 export되어 컴팩션을 생존합니다.

**API:** `initPlanNotepad()`, `addLearning()`, `addDecision()`, `addIssue()`, `addProblem()`, `getWisdomSummary()`, `readPlanWisdom()`

**소스 코드:**
- 핵심 구현: `src/features/notepad-wisdom/index.ts`
- 타입 정의: `src/features/notepad-wisdom/types.ts`

---

### A.5. PreCompact Checkpoint (컴팩션 체크포인트)

**저장 위치:** `.omc/state/checkpoints/checkpoint-{timestamp}.json`
**수명:** 영구 (누적)
**범위:** 세션 단위

컨텍스트 컴팩션 **직전**에 자동으로 생성되는 상태 스냅샷:

| 보존 대상 | 내용 |
|:--|:--|
| `active_modes` | autopilot/ralph/ultrawork/ultraqa 상태 (phase, iteration, prompt) |
| `todo_summary` | pending/in_progress/completed 카운트 |
| `wisdom_exported` | Notepad Wisdom 내보내기 여부 |
| `background_jobs` | Codex/Gemini 백그라운드 작업 상태 (SQLite DB에서 조회) |

`systemMessage`로 주입되어 컴팩션 이후에도 모드 연속성을 유지합니다. 동시 컴팩션 방지를 위한 per-directory 뮤텍스도 포함합니다.

**소스 코드:**
- 핵심 구현: `src/hooks/pre-compact/index.ts`
- 컨텍스트 윈도우 복구: `src/hooks/recovery/context-window.ts`

---

### A.6. Writer Memory (창작 메모리)

**저장 위치:** `.writer-memory/memory.json` + `.writer-memory/backups/`
**수명:** 영구 (자동 백업, 최대 20개)
**범위:** 창작 프로젝트 단위

소설/시나리오 등 **창작 작업 전용** 메모리 시스템:

| 도메인 | 추적 내용 |
|:--|:--|
| Characters | 이름, 별명, 아크, 말투(반말/존댓말), 키워드, 태도, 감정 타임라인, 금기어 |
| World | 시대, 분위기, 규칙, 장소, 문화적 노트 |
| Relationships | 유형(romantic/familial/...), 다이나믹, 진화 이벤트 |
| Scenes | 컷 단위(대사/나레이션/액션/내면), 감정 태그 |
| Themes | 키워드, 관련 캐릭터/장면 |
| Synopsis | 주인공 태도, 핵심 관계, 정서 테마, 엔딩 잔상 |

**특징:** 전문 검색(`searchMemory`), 구조 검증(`validateMemory`), 원자적 저장, 자동 백업/정리

**소스 코드:**
- 핵심 구현: `skills/writer-memory/lib/memory-manager.ts`

---

### A.7. OMC 메모리 레이어 간 상호작용

```
SessionStart
  |
  +--> Project Memory 로드/리스캔 --> 컨텍스트 주입
  +--> Notepad Priority Context --> 컨텍스트 주입

PostToolUse
  |
  +--> Learner: Bash 출력에서 환경 힌트 학습 --> Project Memory 업데이트
  +--> Hot Path Tracker: 파일/디렉토리 접근 추적 --> Project Memory 업데이트
  +--> Directive Detector: 사용자 메시지에서 지시사항 감지 --> Project Memory 업데이트

PreCompact (컴팩션 직전)
  |
  +--> Project Memory userDirectives --> systemMessage로 재주입
  +--> Notepad Wisdom --> 체크포인트로 export
  +--> 활성 모드 상태 --> 체크포인트 저장
  +--> TODO 요약 --> 체크포인트 저장
  +--> 백그라운드 작업 상태 --> 체크포인트 저장

에이전트 간 통신 (/team, /pipeline)
  |
  +--> Shared Memory: namespace별 KV 스토어로 데이터 교환
```

---

### A.8. Claude Code Native와의 비교

| 관점 | Claude Code Native | OMC (oh-my-claudecode) |
|:--|:--|:--|
| **메모리 수** | 2개 (CLAUDE.md + Auto Memory) | 6개 레이어 |
| **자동 감지** | Auto Memory (Claude가 직접 Write) | Project Memory (hook에서 환경 자동 감지) |
| **구조화** | 마크다운 자유형식 (구조화 메모리는 frontmatter 타입) | JSON 스키마 (techStack, build, conventions 등) |
| **에이전트 간 공유** | 없음 (서브에이전트별 독립) | Shared Memory (namespace KV 스토어) |
| **컴팩션 생존** | CLAUDE.md: 100%, Auto Memory: 재로드 | PreCompact Checkpoint, Project Memory PreCompact 핸들러 |
| **TTL/만료** | 없음 | Shared Memory TTL, Notepad Working Memory 7일 |
| **플랜 단위 지식** | 없음 | Notepad Wisdom (learnings/decisions/issues/problems) |
| **도구 제공** | 없음 (파일 도구로 직접 접근) | 전용 MCP 도구 (project_memory_*, notepad_*, shared_memory_*) |
| **사용자 지시사항** | CLAUDE.md에 직접 작성 | Directive Detector (자동 감지) + 명시적 추가 |
| **접근 추적** | 텔레메트리만 | Hot Path Tracker (접근 횟수 + decay) |
