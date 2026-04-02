# --bare 모드 동작 분석

분석 대상: 유출 TypeScript 소스 (v2.1.88), npm 번들 v2.1.90
핵심 파일:
1. `src/utils/envUtils.ts` — isBareMode() 정의
2. `src/entrypoints/cli.tsx` — 조기 활성화 로직
3. `src/constants/prompts.ts` — 시스템 프롬프트 교체
4. `src/utils/auth.ts` — 인증 게이트
5. 그 외 ~30개 게이트 산재

---

## 1. 개요

`--bare` 플래그는 Claude Code를 최소 모드로 실행한다.
훅, LSP, 플러그인 자동 탐색, 키체인 읽기, 백그라운드 프리페치, 메모리 시스템, CLAUDE.md 자동 탐색을 모두 건너뛴다.

`CLAUDE_CODE_SIMPLE=1` 환경 변수와 완전히 동일하다.

---

## 2. 정의 및 활성화

### 2.1 isBareMode() 함수

```typescript
// src/utils/envUtils.ts
/**
 * --bare / CLAUDE_CODE_SIMPLE — skip hooks, LSP, plugin sync, skill dir-walk,
 * attribution, background prefetches, and ALL keychain/credential reads.
 * Auth is strictly ANTHROPIC_API_KEY env or apiKeyHelper from --settings.
 * Explicit CLI flags (--plugin-dir, --add-dir, --mcp-config) still honored.
 * ~30 gates across the codebase.
 */
export function isBareMode(): boolean {
  return (
    isEnvTruthy(process.env.CLAUDE_CODE_SIMPLE) ||
    process.argv.includes('--bare')
  )
}
```

### 2.2 조기 활성화 (Early Activation)

```typescript
// src/entrypoints/cli.tsx
// --bare: set SIMPLE early so gates fire during module eval / commander
// option building (not just inside the action handler).
if (args.includes('--bare')) {
  process.env.CLAUDE_CODE_SIMPLE = '1';
}
```

Commander 파싱보다 먼저 환경 변수를 설정한다. macOS keychain prefetch가 모듈 import 시점에 실행되기 때문이다. `process.argv`를 직접 파싱해 플래그를 조기 감지한다.

### 2.3 npm 번들 (v2.1.90) 확인

```javascript
// pos 48170
function f9() {
  return Q6(process.env.CLAUDE_CODE_SIMPLE) || process.argv.includes("--bare")
}

// pos 13063420 — 모듈 로딩 전 조기 처리
if (q.includes("--bare")) process.env.CLAUDE_CODE_SIMPLE = "1";
```

---

## 3. 시스템 프롬프트 완전 교체

bare 모드의 가장 큰 변화다. 전체 시스템 프롬프트를 축소하는 것이 아니라 2줄 stub으로 교체한다.

```typescript
// src/constants/prompts.ts
if (isEnvTruthy(process.env.CLAUDE_CODE_SIMPLE)) {
  return [
    `You are Claude Code, Anthropic's official CLI for Claude.\n\nCWD: ${getCwd()}\nDate: ${getSessionStartDate()}`,
  ]
}
```

일반 모드에서 시스템 프롬프트에 포함되는 항목들:

1. 전체 도구 문서 (Bash, FileEdit, FileWrite, WebSearch 등)
2. 메모리 파일 내용
3. Git 컨텍스트
4. CLAUDE.md 내용
5. 사용자 컨텍스트 (이름, 선호도)
6. 팁, 릴리즈 노트

bare 모드에서는 에이전트 정체성 + CWD + 날짜만 남는다.

---

## 4. 비활성화 항목 전체 목록

### 4.1 CLAUDE.md 자동 탐색

```typescript
// src/context.ts
const shouldDisableClaudeMd =
  isEnvTruthy(process.env.CLAUDE_CODE_DISABLE_CLAUDE_MDS) ||
  (isBareMode() && getAdditionalDirectoriesForClaudeMd().length === 0)
```

`--add-dir`을 명시적으로 전달한 경우에만 CLAUDE.md를 읽는다.

### 4.2 훅 (Hooks)

```typescript
// src/utils/hooks.ts
// executeHooks: 도구 호출 전/후 훅
// executeOutsideReplHooks: 세션 레벨 훅
// 두 함수 모두 CLAUDE_CODE_SIMPLE 시 즉시 반환

// src/utils/sessionStart.ts
if (isBareMode()) {
  return []  // processSessionStartHooks, processSetupHooks 모두 빈 배열 반환
}
```

### 4.3 LSP (Language Server Protocol)

```typescript
// src/services/lsp/manager.ts
// LSP는 에디터 통합(진단, hover, go-to-def)을 위한 것
// 스크립트 -p 호출에서는 불필요
if (isBareMode()) {
  return
}
```

### 4.4 스킬/플러그인/MCP 자동 탐색

```typescript
// src/skills/loadSkillsDir.ts
// 관리 디렉토리, 사용자 디렉토리, 프로젝트 디렉토리 파일시스템 탐색 스킵
// 명시적 --add-dir 경로만 로드

// src/main.tsx
// MCP 자동 탐색 (.mcp.json, 사용자 설정, 플러그인) 스킵
// --mcp-config 명시 시만 동작
const mcpConfigPromise = (strictMcpConfig || isBareMode()
  ? Promise.resolve({ servers: {} })
  : getClaudeCodeMcpConfigs(dynamicMcpConfig))
```

### 4.5 인증 — 키체인/OAuth 완전 차단

| 기능 | bare 모드 |
|------|----------|
| macOS keychain 서브프로세스 | 실행 안 함 |
| OAuth 플로우 | 비활성화 |
| `~/.claude/settings.json` apiKey 읽기 | 스킵 |
| `ANTHROPIC_API_KEY` 환경 변수 | 유일하게 허용 |
| `--settings`의 `apiKeyHelper` | 허용 |
| Bedrock/Vertex/Foundry 프로바이더 자격증명 | 영향 없음 |

```typescript
// src/utils/secureStorage/keychainPrefetch.ts
export function startKeychainPrefetch(): void {
  if (process.platform !== 'darwin' || prefetchPromise || isBareMode()) return
```

### 4.6 자동 메모리 시스템

```typescript
// src/memdir/paths.ts
// extractMemories, autoDream, /remember, /dream, 팀 동기화 모두 비활성화
if (isEnvTruthy(process.env.CLAUDE_CODE_SIMPLE)) {
  return false
}
```

### 4.7 백그라운드 프리페치

```
스킵 항목:
1. initUser
2. getUserContext
3. 팁 데이터
4. 파일 카운트
5. 모델 기능 정보
6. 변경 감지기
7. 할당량 상태
8. Fast mode 적격성
9. startDeferredPrefetches()
10. startBackgroundHousekeeping() (메모리 추출, 셸 스냅샷, 오래된 메시지 정리)
```

### 4.8 기타 비활성화 항목

| 항목 | 설명 |
|------|------|
| UDS 메시징 서버 | 스크립트 호출은 주입 메시지를 받지 않음 |
| 팀메이트 스냅샷 | 에이전트 스웜 불필요 |
| 세션 메모리 초기화 | `initSessionMemory()` 미실행 |
| 플러그인 버전 동기화 | 설치/업그레이드 북키핑 불필요 |
| Claude.ai MCP 커넥터 | 연결에 6-14초 소요, 스크립트에서 불필요 |
| 스킬 변경 감지기 | `skillChangeDetector.initialize()` 미실행 |
| 릴리즈 노트/최근 활동 | 대화형 UI 데이터, 세션 JSONL 읽기 스킵 |
| 어태치먼트 | 큐 명령 어태치먼트(태스크 알림)만 반환 |

---

## 5. 명시적 플래그는 여전히 동작

bare 모드에서도 다음 명시적 CLI 플래그는 정상 동작한다:

1. `--mcp-config` — 명시한 MCP 서버만 로드
2. `--add-dir` — 지정 디렉토리의 스킬/CLAUDE.md 로드
3. `--plugin-dir` — 지정 플러그인 디렉토리 로드
4. `--settings` — 지정 설정 파일의 `apiKeyHelper` 읽기
5. `--messaging-socket-path` — UDS 메시징 서버 재활성화

---

## 6. 코디네이터 모드와의 조합

bare 모드 + 코디네이터 모드 동시 활성화 시, 워커는 축소된 도구 세트만 받는다:

```
일반 모드: 전체 도구 + MCP + 스킬
bare 코디네이터: Bash + Read + Edit 만 허용
```

코디네이터 시스템 프롬프트에서:

```
Workers have access to Bash, Read, and Edit tools, plus MCP tools from configured MCP servers.
```

---

## 7. 분석 이벤트

모든 bare 모드 API 호출에 `is_simple: true` 필드가 포함된다:

```typescript
// src/main.tsx
is_simple: isBareMode() || undefined,
```

---

## 8. 설계 원칙

1. **조기 활성화**: 모듈 초기화 전에 환경 변수 주입 — 모듈 레벨 부작용 차단
2. **시스템 프롬프트 교체 (not 축소)**: early return으로 2줄 stub 반환 — 조건부 섹션 제거보다 단순
3. **분산 게이트 (~30개)**: 중앙 컨트롤러 없음 — 각 서브시스템이 독립적으로 `isBareMode()` 체크
4. **명시적 오버라이드 우선**: `--mcp-config`, `--add-dir` 등은 bare 게이트를 우회
5. **Coworker 호환성**: 어태치먼트에서 큐 명령(태스크 알림)은 bare 모드에서도 유지 — 멀티에이전트 통신 보존

---

분석 소스: 유출 TypeScript 소스 v2.1.88, npm 번들 v2.1.90
