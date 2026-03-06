# Claude Code 외부에서 숨은 캐시/컨텍스트 API 재현 실험

## 1. 개요

이 문서는 `ANTHROPIC_API_KEY`를 사용해 **Claude Code 바깥(curl 직접 호출)** 에서 다음 필드들이 동작하는지 검증한 결과를 정리한다.

- `context_management`
- `cache_control.scope = "global"`
- `cache_reference`
- `cache_edits`

실험은 `20-live-api-capture-via-proxy.md`에서 확인된 **proxy 캡처 변형(시스템 2블록, attribution header 비활성 케이스)** 을 기준으로 payload를 맞춘 뒤 수행했다.

---

## 2. 시뮬레이션 기준 (캡처 변형 반영)

`20번` 문서 기준으로, 시스템 프롬프트는 고정된 “최신 1개 정답”이 아니라 **feature flag(`tengu_attribution_header`) 상태에 따른 변형**이 존재한다.

### 2.1 시스템 블록 구조 변경

| 항목 | 변형 A (attribution header ON) | 변형 B (attribution header OFF) |
|------|----------------------|-------------|
| System block 0 | `x-anthropic-billing-header: ...` (cache 없음) | `You are Claude Code, Anthropic's official CLI for Claude.` (cache 있음) |
| System block 1 | `You are a Claude agent, built on Anthropic's Claude Agent SDK.` (cache 있음) | 전체 행동 지침 (cache 있음) |
| System block 2 | 전체 행동 지침 (cache 있음) | 없음 |
| 블록 수 | 3 | 2 |

> 주의: 위 차이는 단순 버전 업그레이드로 단정할 수 없고, `20번` 문서 분석대로 계정/조직별 GrowthBook flag 분배에 따른 차이일 수 있다.

### 2.2 반영 내용

1. 이번 재현은 **변형 B(2블록)** 기준으로 시스템 프롬프트 구성
2. `x-anthropic-billing-header`는 시스템 텍스트가 아닌 HTTP 헤더로 전달
3. `context_management` 케이스는 `thinking: {"type":"adaptive"}` 포함

---

## 3. 테스트 케이스

기본 공통 헤더:

- `anthropic-version: 2023-06-01`
- `x-api-key: $ANTHROPIC_API_KEY`
- `x-anthropic-billing-header: cc_version=2.1.70; cc_entrypoint=external; cch=00000;`

### 3.1 케이스 목록

| 케이스 | 목적 | anthropic-beta |
|--------|------|----------------|
| A | `context_management` 허용 여부 | `claude-code-20250219,context-management-2025-06-27` |
| B | `scope=global` 허용 여부 | `claude-code-20250219,context-management-2025-06-27,prompt-caching-scope-2026-01-05` |
| C | `cache_reference` + `cache_edits` 허용 여부 | `claude-code-20250219,prompt-caching-scope-2026-01-05` |
| D | `scope=global`의 beta 의존성 확인 | `claude-code-20250219,context-management-2025-06-27` |
| E | `cache_edits` 단독 허용 여부 | `claude-code-20250219,prompt-caching-scope-2026-01-05` |
| F | `context_management`의 beta 의존성 확인 | `claude-code-20250219` |

---

## 4. 실행 결과

### 4.1 핵심 결과표

| 케이스 | HTTP | 결과 |
|--------|------|------|
| A (`context_management` + CM beta + thinking adaptive) | 200 | 성공 |
| B (`scope=global` + scope beta) | 200 | 성공 |
| C (`tool_result.cache_reference` 포함) | 400 | `cache_reference: Extra inputs are not permitted` |
| D (`scope=global` + scope beta 없음) | 400 | `cache_control...scope: Extra inputs are not permitted` |
| E (`cache_edits` 블록) | 400 | `Input tag 'cache_edits' ... does not match expected tags` |
| F (`context_management` + CM beta 없음) | 400 | `context_management: Extra inputs are not permitted` |

### 4.2 관찰된 에러 전문(요약)

- `clear_thinking_20251015`는 thinking 비활성 상태에서 400 발생  
  (`...requires thinking to be enabled or adaptive`)
- `cache_reference`는 현재 공개 스키마에서 거부
- `cache_edits` 타입은 현재 공개 메시지 content tag 목록에 없음

---

## 5. 결론

### 5.1 Claude Code 외부에서도 사용 가능한 것

1. `context_management`  
   - 조건: `context-management-2025-06-27` beta 헤더 + thinking enabled/adaptive
2. `cache_control.scope = "global"`  
   - 조건: `prompt-caching-scope-2026-01-05` beta 헤더

### 5.2 Claude Code 외부에서 현재 거부되는 것

1. `tool_result.cache_reference`
2. `cache_edits` content block

즉, `scope/global`과 `context_management`는 **beta 게이트 기반으로 외부 재현 가능**했고,  
`cache_reference`/`cache_edits`는 **공개 Messages API 스키마에서 비허용**으로 확인됐다.

---

## 6. 해석

실험 결과는 다음 가설과 일치한다.

- `context_management`, `prompt-caching-scope`는 공개/반공개 beta 게이트로 열려 있음
- `cache_reference`, `cache_edits`는 Claude Code 내부(first-party 경로) 전용 처리일 가능성이 높음

따라서 "숨은 API" 중에서도 외부에서 재현 가능한 범위와 불가능한 범위를 분리해서 다뤄야 한다.

---

## 7. 서버의 "Claude Code 내부 요청" 판별 메커니즘 분석

서버는 **단일 신호가 아니라 다층 신호의 조합**으로 요청의 출처를 판별한다. 캡처 데이터(20번 문서)와 소스 코드(cli.js v2.1.70)에서 확인된 판별 레이어는 6개이다.

### 7.1 레이어 1: `anthropic-beta` 헤더 — 1차 게이트키퍼

```
claude-code-20250219    ← 항상 포함 (haiku 제외)
```

이것이 **가장 핵심적인 식별자**이다. `ya8()` 함수에서:

```javascript
if (!K) q.push(uq1);  // haiku가 아니면 항상 claude-code-20250219 추가
```

본 문서의 실험에서 모든 케이스에 `claude-code-20250219`를 포함했음에도 `cache_reference`와 `cache_edits`가 거부된 것은, 이 헤더가 **필요조건이지 충분조건이 아님**을 의미한다.

서버는 이 beta 태그를 보고:
- "이 요청은 Claude Code에서 왔다"고 **식별**
- 그 위에 **추가 검증**을 수행

### 7.2 레이어 2: API Key의 내부 속성 — 서버 측 인가

```javascript
function ha() {
  let A = process.env.ANTHROPIC_BASE_URL;
  if (!A) return true;  // 기본 = api.anthropic.com = firstParty
  return ["api.anthropic.com"].includes(new URL(A).host);
}

function lF() {
  if (D7() !== "firstParty") return false;
  if (!ha()) return false;
  // + OAuth accessToken + 특정 scope + enterprise/max subscription 체크
}
```

클라이언트 측에서는 `D7()`, `ha()`, `lF()` 등으로 **자체 검증 후 기능을 on/off** 한다. 하지만 진짜 게이트는 **서버 측**이다.

본 실험에서 같은 API Key로 `cache_reference`를 보냈는데 거부된 이유:

| 요청 출처 | API Key | 서버 판정 |
|-----------|---------|-----------|
| Claude Code 내부 | OAuth에서 파생된 키 | **first-party 내부 키**로 인식 → 허용 |
| curl 직접 호출 | 같은 키 | 키 자체는 동일하나 **추가 신호 부재** → 거부 |

서버는 API Key만으로는 구분하지 않고, **키 + beta 헤더 + 요청 구조의 조합**을 검증한다.

### 7.3 레이어 3: `User-Agent` 헤더 — 클라이언트 핑거프린트

```javascript
function Sy() {
  return `claude-cli/${VERSION} (external, ${process.env.CLAUDE_CODE_ENTRYPOINT}${agentSdk}${clientApp})`;
}
// 예: "claude-cli/2.1.70 (external, cli)"
```

프록시가 헤더를 캡처하지 않아 직접 확인은 못했지만, 소스에서 `User-Agent`를 명시적으로 구성하는 코드가 확인된다. 서버는 이를 **보조 신호**로 사용할 수 있다.

### 7.4 레이어 4: `metadata.user_id` — 세션 바인딩

```
user_{sha256(apiKey)}_account_{accountUuid}_session_{sessionUuid}
```

캡처된 실제 값:
```
user_36b51f28...c913_account__session_7f5456e6-...-975559967185
```

이 형식은 Claude Code만 생성한다. 서버는:
- `user_` 접두사 + `_account_` + `_session_` 패턴 매칭
- 세션 UUID의 유효성 검증
- API Key 해시와 실제 키의 일치 여부 확인

을 통해 **요청이 진짜 Claude Code 세션에서 왔는지** 교차 검증할 수 있다.

### 7.5 레이어 5: `x-anthropic-billing-header` — 클라이언트 어트리뷰션

```javascript
function Y91(fingerprint) {
  if (!Tj3()) return "";  // tengu_attribution_header feature flag
  return `x-anthropic-billing-header: cc_version=${VERSION}.${fingerprint}; cc_entrypoint=${entrypoint}; cch=00000;`;
}
```

이 헤더는 system prompt의 **첫 번째 블록**으로 삽입되며:
- `cc_version`: 패키지 버전 + 메시지 핑거프린트 (SHA256 3자리)
- `cc_entrypoint`: `cli`, `sdk-cli`, `agent` 등
- `cch`: 고정값 `00000` (예약)

서버는 이 블록을 파싱하여:
1. 클라이언트 버전 검증
2. 핑거프린트로 메시지 무결성 확인
3. 진입점(entrypoint) 기반 차등 처리

가 가능하다. 단, `tengu_attribution_header` feature flag가 `false`인 환경에서는 이 블록이 생성되지 않으므로(20번 문서 참조), 이 레이어가 필수 판별 요소는 아닐 수 있다.

### 7.6 레이어 6: 요청 구조 자체 — 암묵적 핑거프린트

Claude Code의 요청은 **구조적으로 고유한 패턴**을 가진다:

| 신호 | Claude Code 내부 | 외부 curl 모방 |
|------|-----------------|---------------|
| `thinking.type` | `"adaptive"` | 복제 가능 |
| `context_management.edits` | `clear_thinking_20251015` | 복제 가능 |
| `output_config.effort` | `"medium"` | 복제 가능 |
| `cache_control` 패턴 | sys[0]+sys[1] ephemeral + 마지막 msg | 복제 가능 |
| `cache_reference` in tool_result | `tool_use_id` 기반 자동 생성 | 복제해도 **서버가 거부** |
| beta 헤더 **조합** | 정확한 조건 분기 | 조합은 복제 가능하나 서버가 추가 검증 |

### 7.7 종합: 서버의 판별 흐름 (추정)

```
요청 수신
  │
  ├─ [1] anthropic-beta에 "claude-code-20250219" 있는가?
  │     NO → 일반 API 요청으로 처리 (cache_reference 등 미공개 필드 거부)
  │     YES ↓
  │
  ├─ [2] API Key가 first-party 경로인가?
  │     (OAuth 발급 키의 내부 메타데이터 / 키 타입 검증)
  │     NO → beta 게이트 기능만 허용 (context_management, scope=global)
  │     YES ↓
  │
  ├─ [3] 요청 서명 검증 (User-Agent, metadata.user_id 패턴, billing header)
  │     FAIL → 제한된 기능만 허용
  │     PASS ↓
  │
  └─ [4] 전체 first-party 기능 허용
        (cache_reference, cache_edits, 1h TTL 등)
```

### 7.8 기능별 판별 레이어 매핑

| 기능 | beta 게이트만? | first-party 전용? | 외부 재현 | 판별 근거 |
|------|:---:|:---:|:---:|------|
| `context_management` | **O** (`mq1`) | X | **가능** | beta 헤더만으로 충분 |
| `scope=global` | **O** (`Kh6`) | X | **가능** | beta 헤더만으로 충분 |
| `cache_reference` | ? | **O** | **불가** | beta 외 추가 서버 측 인가 필요 |
| `cache_edits` | ? | **O** | **불가** | beta 외 추가 서버 측 인가 필요 |

### 7.9 결론

서버의 판별은 **2단계 구조**이다:

1. **공개/반공개 beta** (`context_management`, `scope=global`): `anthropic-beta` 헤더만 있으면 누구나 사용 가능. 서버는 "누가 보냈는지" 신경 쓰지 않음.

2. **first-party 전용** (`cache_reference`, `cache_edits`): beta 헤더 + **서버 측에서 API Key 또는 요청의 내부 속성을 독립 검증**. 클라이언트 코드에서 `D7() === "firstParty" && querySource === "repl_main_thread"` 조건으로 게이팅하지만, 이를 우회해서 보내도 **서버가 독립적으로 거부**함. 이는 서버에 별도의 allowlist나 키 메타데이터 기반 인가 로직이 존재함을 시사한다.

> **참고**: 클라이언트 측 게이팅(`D7()`, `ha()`)은 **불필요한 에러를 방지하기 위한 사전 필터**이고, 진짜 보안/인가는 서버에서 수행된다. 클라이언트 코드를 수정하여 이 필터를 우회해도 서버가 거부한다는 점이 실험으로 확인되었다.

---

*실험 일자: 2026-03-07*
*기준 모델: `claude-sonnet-4-6`*
*실행 방식: curl 직접 호출 (Claude Code 외부)*
*판별 메커니즘 분석 추가: 2026-03-07*
