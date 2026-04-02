# AutoDream 백그라운드 메모리 통합 분석

분석 대상: 유출 TypeScript 소스 (v2.1.88, 유출일 2026-03-31)
분석 파일:
1. `src/services/autoDream/autoDream.ts`
2. `src/services/autoDream/config.ts`
3. `src/services/autoDream/consolidationLock.ts`
4. `src/services/autoDream/consolidationPrompt.ts`
5. `src/tasks/DreamTask/DreamTask.ts`
6. `src/utils/backgroundHousekeeping.ts`

---

## 1. 개요

AutoDream은 Claude Code의 백그라운드 메모리 통합 시스템이다.
세션이 충분히 쌓이면 자동으로 포크드 서브에이전트를 실행해
과거 세션 로그를 읽고 메모리 파일을 재작성/정리한다.

`/dream` 슬래시 커맨드로 수동 실행도 가능하다.

---

## 2. 아키텍처 개관

```
세션 종료 (stopHooks.ts)
    |
    v
executeAutoDream()
    |
    +-- isGateOpen()  <-- KAIROS, 원격 모드, 메모리 활성화 여부
    |
    +-- readLastConsolidatedAt()  <-- lock 파일 mtime
    |
    +-- 시간 게이트: hoursSince >= minHours (기본 24h)
    |
    +-- 스캔 스로틀: 마지막 스캔 후 10분 경과
    |
    +-- listSessionsTouchedSince()  <-- 세션 카운트
    |
    +-- 세션 게이트: sessionCount >= minSessions (기본 5)
    |
    +-- tryAcquireConsolidationLock()  <-- 경쟁 방지
    |
    v
runForkedAgent()  --  # Dream: Memory Consolidation 프롬프트
    |
    +-- 완료: completeDreamTask(), appendSystemMessage("Improved ...")
    +-- 실패: rollbackConsolidationLock(priorMtime)
    +-- 사용자 중단: abortController.signal 감지, 롤백 스킵
```

---

## 3. 게이트 설계

### 3.1 활성화 게이트 (isGateOpen)

```typescript
function isGateOpen(): boolean {
  if (getKairosActive()) return false  // KAIROS 모드는 자체 dream 사용
  if (getIsRemoteMode()) return false
  if (!isAutoMemoryEnabled()) return false
  return isAutoDreamEnabled()
}
```

KAIROS 모드(원격 에이전트 실행 환경)에서는 별도 dream 슬킬을 사용하므로
AutoDream 자동 트리거를 비활성화한다.

### 3.2 활성화 설정 (isAutoDreamEnabled)

```typescript
export function isAutoDreamEnabled(): boolean {
  const setting = getInitialSettings().autoDreamEnabled
  if (setting !== undefined) return setting  // 로컬 오버라이드 우선
  const gb = getFeatureValue_CACHED_MAY_BE_STALE('tengu_onyx_plover', null)
  return gb?.enabled === true  // GrowthBook 서버 기본값
}
```

`settings.json`의 `autoDreamEnabled`가 명시적으로 설정된 경우 우선 적용된다.
미설정 시 GrowthBook 피처 플래그 `tengu_onyx_plover`의 `enabled` 값으로 폴백한다.

### 3.3 스케줄링 파라미터 (getConfig)

GrowthBook `tengu_onyx_plover` 페이로드에서 스케줄링 파라미터를 읽는다:

| 파라미터 | 기본값 | 설명 |
|---------|--------|------|
| `minHours` | 24 | 마지막 통합 후 최소 경과 시간 |
| `minSessions` | 5 | 최소 신규 세션 수 |

GrowthBook 캐시 값이 잘못된 타입을 반환할 수 있으므로 per-field 방어 검증을 수행한다:

```typescript
minHours:
  typeof raw?.minHours === 'number' &&
  Number.isFinite(raw.minHours) &&
  raw.minHours > 0
    ? raw.minHours
    : DEFAULTS.minHours,
```

---

## 4. 락 파일 메커니즘

### 4.1 설계 원칙

```
~/.claude/projects/<cwd-hash>/memory/.consolidate-lock
                                         ^
                                  파일 mtime = lastConsolidatedAt
                                  파일 내용 = 보유 프로세스의 PID
```

파일 내용이 아닌 **mtime 자체가 타임스탬프**다.
별도 DB나 상태 파일 없이 OS 파일시스템 원자성을 활용한다.

### 4.2 락 획득 (tryAcquireConsolidationLock)

```
1. 기존 락 파일 stat + 내용(PID) 읽기
2. mtime < 1시간 AND PID가 살아있으면 -> 스킵 (null 반환)
3. 죽은 PID 또는 stale -> 재획득 (write own PID)
4. 경쟁 감지: writeFile 후 readFile로 재확인, PID 불일치 시 실패
5. 성공 시 priorMtime 반환 (롤백용)
```

두 프로세스가 동시에 재획득 시도 시 "마지막 write가 이기고 나머지는 re-read에서 감지" 패턴으로 경쟁을 처리한다.

### 4.3 롤백 (rollbackConsolidationLock)

포크 실패 시 mtime을 획득 전 시점으로 되돌린다:

```typescript
if (priorMtime === 0) {
  await unlink(path)     // 원래 파일 없었으면 삭제
  return
}
await writeFile(path, '')        // PID 내용 삭제 (살아있는 프로세스로 보이지 않게)
await utimes(path, t, t)         // mtime 되돌리기
```

롤백 실패 시 mtime이 now로 고정돼 `minHours` 뒤까지 재시도가 지연된다.
스캔 스로틀(10분)이 그 전까지의 백오프 역할을 한다.

---

## 5. 포크드 에이전트 실행

```typescript
const result = await runForkedAgent({
  promptMessages: [createUserMessage({ content: prompt })],
  cacheSafeParams: createCacheSafeParams(context),
  canUseTool: createAutoMemCanUseTool(memoryRoot),
  querySource: 'auto_dream',
  forkLabel: 'auto_dream',
  skipTranscript: true,              // 메인 세션 전사에 포함 안 됨
  overrides: { abortController },
  onMessage: makeDreamProgressWatcher(taskId, setAppState),
})
```

1. `skipTranscript: true` — 메인 세션 대화 흐름에 영향을 주지 않는다.
2. `canUseTool: createAutoMemCanUseTool(memoryRoot)` — extractMemories와 동일한 도구 제한 함수를 공유한다.
3. `abortController` — 사용자가 백그라운드 태스크 다이얼로그에서 중단 가능하다.

### 5.1 Bash 도구 제한

autodrean 포크에서는 프롬프트에 다음 제약이 추가된다:

```
Bash is restricted to read-only commands (ls, find, grep, cat, stat, wc, head, tail,
and similar). Anything that writes, redirects to a file, or modifies state will be denied.
```

메모리 디렉토리 수정은 FileEdit/FileWrite 도구만 허용한다.

---

## 6. 통합 프롬프트 4단계

`# Dream: Memory Consolidation` 프롬프트는 4개 페이즈로 구성된다:

| 페이즈 | 이름 | 주요 동작 |
|--------|------|----------|
| 1 | Orient | `ls` 메모리 디렉토리, 인덱스 파일 읽기, 기존 토픽 파일 훑기 |
| 2 | Gather | 일간 로그, 드리프트된 메모리, 세션 전사 grep |
| 3 | Consolidate | 메모리 파일 작성/업데이트, 절대 날짜 변환, 모순 사실 삭제 |
| 4 | Prune & Index | 인덱스 파일 `MAX_ENTRYPOINT_LINES` 이하 유지, ~25KB 제한 |

세션 전사 읽기에 대한 명시적 경고:

```
Don't exhaustively read transcripts. Look only for things you already suspect matter.
```

---

## 7. 진행 상황 추적 (DreamProgressWatcher)

포크드 에이전트의 각 어시스턴트 턴을 감시해 UI 태스크를 업데이트한다:

```typescript
for (const block of msg.message.content) {
  if (block.type === 'text') {
    text += block.text
  } else if (block.type === 'tool_use') {
    toolUseCount++
    if (block.name === FILE_EDIT_TOOL_NAME || block.name === FILE_WRITE_TOOL_NAME) {
      touchedPaths.push(input.file_path)   // 수정된 파일 목록 수집
    }
  }
}
```

수집된 `filesTouched`는 완료 후 메인 세션에 인라인 메시지로 표시된다:

```
appendSystemMessage({ ...createMemorySavedMessage(filesTouched), verb: 'Improved' })
```

---

## 8. 분석 이벤트

| 이벤트 | 발생 시점 | 포함 데이터 |
|--------|----------|------------|
| `tengu_auto_dream_fired` | 게이트 통과, 포크 시작 | `hours_since`, `sessions_since` |
| `tengu_auto_dream_completed` | 포크 정상 완료 | `cache_read`, `cache_created`, `output`, `sessions_reviewed` |
| `tengu_auto_dream_failed` | 포크 예외 발생 | (없음) |
| `tengu_auto_dream_toggled` | 사용자가 UI에서 토글 | MemoryFileSelector |

---

## 9. 버전별 도입 이력

| 버전 | 상태 | 비고 |
|------|------|------|
| v2.1.29 ~ v2.1.70 | 미존재 | 워드 리스트에 "dream" 단어만 있음 |
| v2.1.80 | 최초 도입 | 완전한 autoDream 구현 |
| v2.1.88 (유출) | 동일 | 유출 소스와 일치 |
| v2.1.90 | 동일 | `autoDreamEnabled` 스키마 설명 추가 |

v2.1.80 minified 번들에서 확인된 핵심 문자열:
1. `[autoDream] lock held by live PID` (pos 9,028,068)
2. `[autoDream] rollback failed` (pos 9,028,465)
3. `# Dream: Memory Consolidation` (pos 9,224,731)

---

## 10. 설계 원칙 정리

1. 락 파일 mtime = 타임스탬프: 별도 DB 없이 파일시스템 원자성 활용.
2. 포크드 에이전트 격리: `skipTranscript: true`로 메인 세션에 영향 없음.
3. 게이트 순서 최적화: "cheapest first" (stat 1회 -> 세션 스캔 -> 락 획득).
4. 스캔 스로틀: 시간 게이트는 통과하지만 세션이 부족할 때 매 턴 스캔 방지 (10분 쿨다운).
5. 롤백 설계: 실패 시 priorMtime 복원으로 다음 minHours 후 재시도 보장.
6. GrowthBook 이중 게이트: 서버 기본값 + 로컬 오버라이드로 점진적 롤아웃.

---

분석 소스: 유출 TypeScript 소스 v2.1.88 (`src/services/autoDream/` 디렉토리)
