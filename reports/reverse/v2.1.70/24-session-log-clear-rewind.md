# 24. /clear와 /rewind 시 세션 로그 동작 분석

> **분석 대상**: Claude Code v2.1.70 (`cli.js` 번들 소스 리버스 엔지니어링)
> **분석 일자**: 2026-03-07

## 개요

Claude Code는 대화 내역을 `~/.claude/projects/<project-path>/<session-uuid>.jsonl` 파일에 append-only로 기록한다. `/clear`와 `/rewind` 명령 실행 시 이 JSONL 파일에 어떤 변화가 발생하는지 소스 코드 분석을 통해 확인했다.

## 세션 로그 구조

```
~/.claude/projects/<project-path>/
  ├── {uuid}.jsonl          # 메인 세션 로그
  ├── agent-{hash}.jsonl    # subagent 세션 로그
  └── {uuid}/subagents/     # 팀 내 subagent 로그
```

각 JSONL 엔트리에는 다음 메타데이터가 포함된다:

```json
{
  "parentUuid": "...",
  "isSidechain": false,
  "userType": "external",
  "cwd": "/path/to/project",
  "sessionId": "uuid",
  "version": "2.1.70",
  "gitBranch": "main",
  "type": "user|assistant|system|progress",
  "timestamp": "2026-03-07T...",
  "uuid": "..."
}
```

## /clear 동작

소스 함수: `clearConversation` (minified: `od8`)

### 실행 순서

1. **SessionEnd 훅 실행** — `td8("clear", ...)` 호출로 등록된 SessionEnd 훅들 실행
2. **런타임 메시지 초기화** — `setMessages(() => [])` 로 메모리 상의 메시지 배열을 비움
3. **새 세션 ID 발급** — `setConversationId(randomUUID())` 로 새 UUID 생성
4. **앱 상태 리셋** — tasks, fileHistory, attribution, MCP 클라이언트 등 초기화
5. **새 JSONL 파일 생성** — 새 conversationId에 대응하는 `{new-uuid}.jsonl` 파일이 자동 생성됨
6. **SessionStart 훅 실행** — `_W("clear")` 호출로 clear 이벤트에 대한 훅 메시지를 새 세션에 삽입

### 핵심: 기존 JSONL 파일은 수정되지 않음

```
Before /clear:
  session-A.jsonl  ← 기존 대화 (100 entries)

After /clear:
  session-A.jsonl  ← 그대로 보존 (100 entries, 변경 없음)
  session-B.jsonl  ← 새 세션 파일 생성 (SessionStart 훅부터 기록)
```

기존 세션은 `/resume` 명령으로 다시 열 수 있다.

### 소스 코드 (디미니파이)

```javascript
async function clearConversation({setMessages, readFileState, getAppState, setAppState, setConversationId}) {
  // 1. SessionEnd 훅 실행
  await triggerSessionEnd("clear", {getAppState, setAppState});

  // 2. 메시지 배열 비우기
  setMessages(() => []);

  // 3. 새 세션 ID
  if (setConversationId) setConversationId(randomUUID());

  // 4. 상태 리셋
  if (setAppState) setAppState((state) => ({
    ...state,
    tasks: {},
    attribution: newAttribution(),
    fileHistory: { snapshots: [], trackedFiles: new Set, snapshotSequence: 0 },
    mcp: { clients: [], tools: [], commands: [], resources: {},
           pluginReconnectKey: state.mcp.pluginReconnectKey }
  }));

  // 5. 파일 상태 리셋, 훅 실행
  resetFileState();
  resetSomething();
  setCurrentAsParent();
  await refreshPlugins();

  // 6. clear 이벤트 훅 결과를 새 세션 메시지로 삽입
  let hookMessages = await getHookMessages("clear");
  if (hookMessages.length > 0) setMessages(() => hookMessages);
}
```

## /rewind 동작

소스 함수: `/rewind` → `openMessageSelector()` → `onRestoreMessage` 콜백

### 실행 순서

1. **메시지 선택 UI 표시** — `/rewind` 명령은 `openMessageSelector()`를 호출하여 `isMessageSelectorVisible`을 `true`로 설정
2. **사용자가 복원 지점 선택** — UI에서 되돌아갈 메시지를 선택
3. **메시지 배열 잘라내기** — `messages.slice(0, selectedIndex)` 로 선택 지점 이후 메시지를 런타임에서 제거
4. **텔레메트리 기록** — `tengu_conversation_rewind` 이벤트 발생
5. **프롬프트 복원** — 선택한 메시지에 bash-input이나 command가 있으면 입력란에 복원
6. **이미지 복원** — 선택한 메시지에 이미지가 있으면 pastedContents로 복원

### 핵심: JSONL에 이미 기록된 엔트리는 삭제되지 않음

```
Before /rewind (messages 1~10, JSONL에 10개 기록):
  session-A.jsonl: [msg1, msg2, ..., msg10]
  런타임 메시지: [msg1, msg2, ..., msg10]

After /rewind to msg5:
  session-A.jsonl: [msg1, msg2, ..., msg10]  ← 변경 없음! 10개 그대로
  런타임 메시지: [msg1, msg2, ..., msg5]     ← 5개로 잘림

이후 새 메시지 추가 시:
  session-A.jsonl: [msg1, ..., msg10, msg11(new)]  ← msg11이 append
  런타임 메시지: [msg1, ..., msg5, msg11(new)]
```

### 소스 코드 (디미니파이)

```javascript
// /rewind 커맨드 자체는 UI만 여는 단순한 함수
async function rewindCall(args, context) {
  if (context.openMessageSelector) context.openMessageSelector();
  return { type: "skip" };
}

// 메시지 선택 UI의 onRestoreMessage 콜백
onRestoreMessage: async (selectedMessage) => {
  let selectedIndex = messages.indexOf(selectedMessage);
  let truncatedMessages = messages.slice(0, selectedIndex);

  setImmediate(async () => {
    // 런타임 메시지만 잘라냄
    setMessages([...truncatedMessages]);
    resetInputState();
    clearStreamingState();

    // 텔레메트리
    track("tengu_conversation_rewind", {
      preRewindMessageCount: messages.length,
      postRewindMessageCount: selectedIndex,
      messagesRemoved: messages.length - selectedIndex,
      rewindToMessageIndex: selectedIndex
    });

    // 권한 모드 복원
    setAppState((state) => ({
      ...state,
      toolPermissionContext: selectedMessage.permissionMode
        ? { ...state.toolPermissionContext, mode: selectedMessage.permissionMode }
        : state.toolPermissionContext
    }));

    // 프롬프트 입력란 복원
    let prompt = extractPrompt(selectedMessage);
    if (prompt !== null) {
      if (isBashInput(prompt)) { setPrompt(bashPart); setMode("bash"); }
      else if (isCommand(prompt)) { setPrompt(commandWithArgs); setMode("prompt"); }
      else { setPrompt(prompt); setMode("prompt"); }
    }
  });
}
```

### /rewind의 onSummarize 옵션

메시지 선택 UI에는 `onRestoreMessage` 외에 `onSummarize` 콜백도 있다. 이 경우:
- 선택 지점까지의 대화를 LLM으로 요약(compaction)
- 요약된 메시지 + 경계 마커로 메시지 배열 교체
- JSONL에는 요약된 새 메시지들이 append됨

## isSidechain 필드

JSONL 엔트리의 `isSidechain` 필드는 rewind와 직접 관련이 없다:

| 용도 | isSidechain 값 |
|------|---------------|
| 일반 메시지 | `false` |
| subagent 메시지 | `true` |
| fork된 세션의 원본 메시지 복사 | `false` (새 sessionId) |

`isSidechain: true`인 세션은 `/resume` 목록에서 필터링된다:
```javascript
if (sessionInfo.isSidechain) {
  log(`Session ${id} filtered from /resume: isSidechain=true`);
  return null;
}
```

## 요약 비교표

| 동작 | 기존 JSONL 파일 | 새 JSONL 파일 | 런타임 메시지 | 세션 ID |
|------|----------------|--------------|-------------|---------|
| `/clear` | 수정 없음, 보존 | 새 UUID로 생성 | `[]` 초기화 | 변경 (새 UUID) |
| `/rewind` | 수정 없음, 보존 | 없음 (같은 파일) | `slice(0, idx)` | 유지 |

**핵심 원칙**: JSONL은 append-only 로그이며, 두 명령 모두 기존 데이터를 절대 삭제하거나 수정하지 않는다.

## 실증 확인

현재 프로젝트의 세션 파일 분석:
- 메인 세션 파일: `{uuid}.jsonl` (UUID 형식)
- subagent 파일: `agent-{hash}.jsonl` (agent- 접두사)
- `/clear` 수행 시 이전 세션 파일의 라인 수가 변하지 않음을 확인
- subagent JSONL은 모든 엔트리가 `isSidechain: true`로 기록됨
