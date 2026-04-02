# Claude Code 빌링 정보 관리 및 요청 삽입 분석

## 1. 개요

Claude Code는 빌링(과금) 정보를 **3개 레이어**에 걸쳐 관리한다:

1. **인증/세션 레이어** — OAuth 로그인 시 계정·조직 정보 저장
2. **API 요청 metadata 레이어** — 모든 API 호출에 `user_id` 삽입
3. **시스템 프롬프트 레이어** — `x-anthropic-billing-header`를 시스템 프롬프트 블록으로 전달

```
+------------------------------------------------------------------+
|                    빌링 정보 흐름 전체도                             |
+------------------------------------------------------------------+
|                                                                  |
|  [1] OAuth 로그인 / API Key 설정                                  |
|       |                                                          |
|       v                                                          |
|  계정 정보 로컬 저장 (~/.claude/.credentials)                       |
|  +------------------------------------------------------------+  |
|  | accountUuid, organizationUuid, emailAddress                |  |
|  | subscriptionType, billingType, hasExtraUsageEnabled         |  |
|  | subscriptionCreatedAt, accountCreatedAt                    |  |
|  +------------------------------------------------------------+  |
|       |                                                          |
|       +---> [2] metadata.user_id (모든 API 요청)                  |
|       |    "user_{apiKeyHash}_{accountUuid}_{sessionId}"          |
|       |                                                          |
|       +---> [3] x-anthropic-billing-header (시스템 프롬프트)        |
|       |    서버가 제공한 빌링 헤더를 system block으로 전달            |
|       |                                                          |
|       +---> [4] 캐시 TTL 분기 (퍼스트파티 여부)                     |
|            퍼스트파티 + 비-오버에이지 → 1시간 TTL 캐시                |
|                                                                  |
+------------------------------------------------------------------+
```

## 2. 인증 및 계정 정보 저장

### 2.1 OAuth 로그인 흐름

`qi6` (installOAuthTokens) 함수가 OAuth 토큰 설치 시 계정 프로필을 가져와 로컬에 저장한다:

```javascript
// cli.js 내 qi6 함수 (installOAuthTokens)
async function qi6(A) {
  // 1. 프로필 조회
  let q = A.profile ?? await L16(A.accessToken);

  // 2. 계정 정보 로컬 저장
  if (q) RT6({
    accountUuid:            q.account.uuid,
    emailAddress:           q.account.email,
    organizationUuid:       q.organization.uuid,
    displayName:            q.account.display_name,
    hasExtraUsageEnabled:   q.organization.has_extra_usage_enabled,
    billingType:            q.organization.billing_type,
    subscriptionCreatedAt:  q.organization.subscription_created_at,
    accountCreatedAt:       q.account.created_at
  });

  // 3. API 키 생성
  await zC8(A.accessToken);  // API key 발급

  // 4. 첫 토큰 날짜 기록 (빌링 추적용)
  await Te4();  // claudeCodeFirstTokenDate 저장
}
```

### 2.2 저장되는 계정 속성

| 속성 | 설명 | 용도 |
|------|------|------|
| `accountUuid` | 계정 고유 ID | metadata.user_id 구성 |
| `organizationUuid` | 조직 고유 ID | 빌링 주체 식별 |
| `emailAddress` | 이메일 | 상태 표시 |
| `subscriptionType` | 구독 유형 (pro/free 등) | 기능 게이팅, 상태 표시 |
| `billingType` | 과금 유형 | 캐시 TTL, 기능 분기 |
| `hasExtraUsageEnabled` | 초과 사용 활성화 여부 | 오버에이지 판단 |
| `subscriptionCreatedAt` | 구독 시작일 | 빌링 추적 |
| `accountCreatedAt` | 계정 생성일 | 빌링 추적 |
| `claudeCodeFirstTokenDate` | 첫 토큰 사용일 | API 엔드포인트에서 조회 후 저장 |

### 2.3 인증 방식별 분기

`MlY` (authStatus) 함수에서 인증 방식을 판별:

```javascript
// 인증 방식 결정 로직
if ($)              H = "third_party";      // Bedrock/Vertex/Foundry
else if (q === "claude.ai")  H = "claude.ai";
else if (q === "apiKeyHelper") H = "api_key_helper";
else if (q !== "none")       H = "oauth_token";
else if (Y === "ANTHROPIC_API_KEY" || z) H = "api_key";
else if (Y === "/login managed key")     H = "claude.ai";
```

`claude auth status --json` 출력 시 claude.ai 인증이면 추가 필드 포함:

```json
{
  "loggedIn": true,
  "authMethod": "claude.ai",
  "apiProvider": "firstParty",
  "email": "user@example.com",
  "orgId": "org-uuid-xxx",
  "orgName": "My Organization",
  "subscriptionType": "pro"
}
```

## 3. API 요청의 metadata.user_id

### 3.1 user_id 구성

`A66` 함수가 모든 API 요청에 포함되는 metadata를 생성:

```javascript
function A66() {
  let A = vy(),                    // API 키 해시 (또는 원본의 일부)
      q = E5()?.accountUuid ?? "", // 계정 UUID
      K = l1();                    // 세션 ID
  return {
    user_id: `user_${A}_account_${q}_session_${K}`
  };
}
```

### 3.2 실제 요청에서의 위치

```json
{
  "model": "claude-opus-4-5-20251101",
  "system": [...],
  "messages": [...],
  "tools": [...],
  "metadata": {
    "user_id": "user_sk-ant-xxx_account_acc-xxx_session_sess-xxx"
  },
  "stream": true
}
```

이 `user_id`는 **모든** API 호출에 포함된다:
- 메인 대화 요청 (C5q/pM1)
- 경량 내부 호출 (rJ — 제목 생성, bash 분류 등)
- API 키 검증 호출 (tkq)

### 3.3 user_id의 목적

| 구성 요소 | 목적 |
|-----------|------|
| API 키 해시 | 어떤 키로 요청했는지 추적 |
| accountUuid | 빌링 대상 계정 식별 |
| sessionId | 세션별 사용량 추적, 레이트리밋 적용 |

## 4. 시스템 프롬프트의 x-anthropic-billing-header

### 4.1 빌링 헤더 처리 로직의 존재

Claude Code 클라이언트에는 `x-anthropic-billing-header`로 시작하는 문자열을 시스템 프롬프트에서 **감지하고 별도 블록으로 분리하는 로직**이 존재한다. 그러나 이 문자열은 **클라이언트가 직접 생성하는 것이 아니다**.

프록시 캡처 실험에서 확인한 결과, API Key 직접 사용 환경에서는 이 헤더가 시스템 프롬프트에 나타나지 않았다. system 블록은 항상 `"You are Claude Code, Anthropic's official CLI for Claude."`로 시작했다.

분석 결과, `x-anthropic-billing-header`는 **클라이언트(`Y91` 함수)가 직접 생성**한다:

```javascript
function Y91(fingerprint) {
  if (!Tj3()) return "";  // feature flag 체크
  let version = `${VERSION}.${fingerprint}`;
  let entrypoint = process.env.CLAUDE_CODE_ENTRYPOINT ?? "unknown";
  return `x-anthropic-billing-header: cc_version=${version}; cc_entrypoint=${entrypoint}; cch=00000;`;
}

function Tj3() {
  if (process.env.CLAUDE_CODE_ATTRIBUTION_HEADER === "false") return false;
  return e8("tengu_attribution_header", true);  // feature flag, 기본값 true
}
```

프록시 캡처(v2.1.70)에서 보이지 않았던 원인을 정밀하게 파악했다:

**근본 원인: 계정 격리로 인한 OAuth 재인증**

프록시 실험 시 `HOME` 환경변수를 `proxy/.claude-home/`으로 격리했기 때문에, Claude Code가 새로운 OAuth 로그인을 수행했다. 그 결과:

| 항목 | 실제 홈 | 프록시 실험 홈 |
|------|--------|------------------|
| `userID` | `0d6ed8c1...` | `36b51f28...` |
| `accountUuid` | `9dac48da-6a6...` | `8490898f-8cd...` |
| `organizationUuid` | `f26071d2-547d...` | `0ea4de60-8809...` |
| `tengu_attribution_header` | `true` | `false` |

GrowthBook은 **계정/조직 단위**로 feature flag를 분배한다. 다른 계정으로 인증되면 서버가 다른 flag 값을 결정한다. 이는 단순한 A/B 테스트 분배 차이가 아니라, **다른 계정에 대해 서버가 의도적으로 다른 flag 값을 할당**한 것이다.

flag 값은 `.claude.json`의 `cachedGrowthBookFeatures` 객체에 캐시되며, `e8("tengu_attribution_header", true)` 함수가 이 캐시에서 읽는다:

```javascript
function e8(key, defaultValue) {
  let cached = readCachedGrowthBookFeatures();
  return cached[key] ?? defaultValue;
}
```

별도의 로컬 모델 실험(v2.1.62)에서는 원래 계정으로 인증되었으므로 이 플래그가 기본값(`true`)이어서 빌링 헤더가 정상적으로 나타났다:

```
[0] text='x-anthropic-billing-header: cc_version=2.1.62.3d5; cc_entrypoint=sdk-cli; cch=00000;'
    cache_control=None
```

**빌링 헤더 필드 설명:**

| 필드 | 예시 값 | 생성 방식 |
|------|---------|----------|
| `cc_version` | `2.1.62.3d5` | `{패키지 버전}.{메시지 핑거프린트}` |
| `cc_entrypoint` | `sdk-cli` | `CLAUDE_CODE_ENTRYPOINT` 환경변수 |
| `cch` | `00000` | 고정값 (예약 필드) |

메시지 핑거프린트는 `voA` 함수가 첫 번째 user 메시지의 특정 위치 문자와 버전을 SHA256 해시하여 3자리로 생성한다.

```javascript
// Mo8 함수 — 시스템 프롬프트 블록 분리 로직
function Mo8(A, q) {
  // 시스템 프롬프트 문자열 배열을 순회
  let Y, z, w = [];
  for (let O of A) {
    if (!O) continue;

    // 빌링 헤더는 별도 블록으로 분리 (캐시 없음)
    if (O.startsWith("x-anthropic-billing-header"))
      Y = O;
    // 특정 예약 문자열도 별도 분리
    else if (q91.has(O))
      z = O;
    // 나머지는 일반 시스템 프롬프트
    else
      w.push(O);
  }

  let _ = [];
  // 빌링 헤더: cacheScope null (캐시하지 않음)
  if (Y) _.push({ text: Y, cacheScope: null });
  // 예약 문자열: cacheScope "org"
  if (z) _.push({ text: z, cacheScope: "org" });
  // 나머지 프롬프트: cacheScope "org"
  let $ = w.join("\n\n");
  if ($) _.push({ text: $, cacheScope: "org" });

  return _;
}
```

### 4.2 글로벌 캐시와 빌링 헤더

글로벌 캐시가 활성화된 경우(`tengu_system_prompt_global_cache`), 시스템 프롬프트가 더 정교하게 분할된다:

```
+------------------------------------------------------------------+
|          시스템 프롬프트 블록 분할 (글로벌 캐시 활성 시)               |
+------------------------------------------------------------------+
|                                                                  |
|  Block 1: x-anthropic-billing-header                             |
|  +------------------------------------------------------------+  |
|  | cacheScope: null (캐시 안 함)                                |  |
|  | → 빌링 정보는 요청마다 달라질 수 있으므로 캐시 제외             |  |
|  +------------------------------------------------------------+  |
|                                                                  |
|  Block 2: 예약 문자열 (q91 Set)                                   |
|  +------------------------------------------------------------+  |
|  | cacheScope: null 또는 "org"                                  |  |
|  +------------------------------------------------------------+  |
|                                                                  |
|  Block 3: 정적 시스템 프롬프트 (경계 마커 이전)                      |
|  +------------------------------------------------------------+  |
|  | cacheScope: "global"                                        |  |
|  | → 모든 사용자 공통이므로 글로벌 캐시 적용                       |  |
|  +------------------------------------------------------------+  |
|                                                                  |
|  Block 4: 동적 시스템 프롬프트 (경계 마커 이후)                      |
|  +------------------------------------------------------------+  |
|  | cacheScope: null (사용자별 상이)                               |  |
|  +------------------------------------------------------------+  |
|                                                                  |
+------------------------------------------------------------------+
```

**핵심**: 빌링 헤더의 `cacheScope`가 `null`인 이유는 사용자/조직마다 다른 빌링 정보를 담고 있어 캐시하면 안 되기 때문이다.

### 4.3 빌링 헤더의 역할

`x-anthropic-billing-header`는 서버 사이드에서 다음을 위해 사용되는 것으로 추정:
- 조직/계정 레벨의 사용량 추적
- 구독 플랜별 레이트리밋 적용
- 과금 엔드포인트 라우팅

## 5. 캐시 TTL과 빌링의 관계

### 5.1 퍼스트파티 판별과 캐시 혜택

`Fa6` 함수와 `oTz` 함수가 캐시 TTL을 결정한다:

```javascript
function Fa6({ scope, querySource } = {}) {
  return {
    type: "ephemeral",
    // 퍼스트파티이고 1시간 캐시 대상이면 TTL 추가
    ...oTz(querySource) ? { ttl: "1h" } : {},
    // 글로벌 스코프면 scope 추가
    ...scope === "global" ? { scope } : {}
  };
}

function oTz(A) {
  // Bedrock + 특별 설정 시
  if (D7() === "bedrock" && _1(process.env.ENABLE_PROMPT_CACHING_1H_BEDROCK))
    return true;

  // 퍼스트파티이고 오버에이지가 아닌 경우만
  if (!(eA() && !ef.isUsingOverage))
    return false;

  // 허용 목록 확인
  let K = WB1();  // 캐시된 allowlist
  if (K === null) {
    K = e8("tengu_prompt_cache_1h_config", {}).allowlist ?? [];
    ZB1(K);  // allowlist 캐시
  }

  return A !== undefined && K.some(Y =>
    Y.endsWith("*") ? A.startsWith(Y.slice(0, -1)) : A === Y
  );
}
```

### 5.2 캐시 TTL 분기 요약

```
+------------------------------------------------------------------+
|              캐시 TTL 결정 로직                                     |
+------------------------------------------------------------------+
|                                                                  |
|  퍼스트파티 (eA() === true)?                                       |
|       |                                                          |
|       +-- YES + 오버에이지 아님 + allowlist 매칭                    |
|       |    → { type: "ephemeral", ttl: "1h" }  (1시간 캐시)        |
|       |                                                          |
|       +-- YES + 오버에이지 사용 중                                  |
|       |    → { type: "ephemeral" }             (기본 5분 캐시)      |
|       |                                                          |
|       +-- NO (Bedrock/Vertex/Foundry)                             |
|            → { type: "ephemeral" }             (기본 캐시)          |
|            (ENABLE_PROMPT_CACHING_1H_BEDROCK 설정 시 1시간)         |
|                                                                  |
+------------------------------------------------------------------+
```

**`ef.isUsingOverage`**: 구독 한도를 초과하여 "오버에이지" 상태인 경우 1시간 캐시 혜택이 제거된다. 이는 과금 효율과 관련된 것으로, 오버에이지 사용자의 캐시 비용을 통제하려는 목적이다.

## 6. 텔레메트리와 빌링 추적

### 6.1 비용 계산

응답 수신 후 `x_1` 함수로 비용을 계산하고, `c_1`으로 누적한다:

```javascript
// 스트리밍 응답 처리 중
let t6 = x_1($, r);          // 모델 + usage → 비용(USD) 계산
c_1(t6, r, w.model);          // 누적 비용 업데이트
M6 += t6;                     // 이 요청의 총 비용
```

### 6.2 요청별 추적 이벤트

```javascript
// 요청 완료 후 발행되는 텔레메트리
$_q({
  model:           e[0]?.message.model ?? w.model,
  usage:           r,                    // input/output 토큰 수
  requestId:       K6,
  costUSD:         M6,                   // 이 요청의 비용
  querySource:     w.querySource,        // "repl_main_thread", "agent:..." 등
  queryTracking:   w.queryTracking,
  permissionMode:  H6.mode,
  fastMode:        G6,
  // ... 기타 메트릭
});
```

### 6.3 응답의 service_tier

프록시 캡처에서 확인된 응답 usage 구조:

```json
{
  "usage": {
    "input_tokens": 1234,
    "output_tokens": 567,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 890,
    "service_tier": "standard",
    "inference_geo": "global"
  }
}
```

`service_tier`는 `"standard"` | `"priority"` | `"batch"` 중 하나로, 계정의 구독 레벨에 따라 서버가 결정한다.

## 7. 인증 방식별 빌링 경로

```
+------------------------------------------------------------------+
|              인증 방식별 빌링 경로                                   |
+------------------------------------------------------------------+
|                                                                  |
|  [Claude.ai 로그인 (OAuth)]                                       |
|  +------------------------------------------------------------+  |
|  | 1. OAuth 토큰 → accessToken 획득                             |  |
|  | 2. 프로필 조회 → accountUuid, orgUuid, billingType 저장       |  |
|  | 3. API key 자동 발급 (서버에서 계정에 연결)                     |  |
|  | 4. metadata.user_id에 accountUuid 포함                       |  |
|  | 5. 서버가 계정의 구독/빌링 타입으로 과금                        |  |
|  +------------------------------------------------------------+  |
|                                                                  |
|  [API Key (ANTHROPIC_API_KEY)]                                    |
|  +------------------------------------------------------------+  |
|  | 1. 환경변수에서 API key 직접 사용                              |  |
|  | 2. metadata.user_id에 key 해시 포함 (accountUuid는 빈 문자열) |  |
|  | 3. 서버가 API key에 연결된 계정으로 과금                        |  |
|  +------------------------------------------------------------+  |
|                                                                  |
|  [서드파티 (Bedrock/Vertex/Foundry)]                               |
|  +------------------------------------------------------------+  |
|  | 1. 각 클라우드 플랫폼의 인증 사용 (AWS IAM, GCP 등)           |  |
|  | 2. Anthropic이 아닌 클라우드 제공자가 과금                     |  |
|  | 3. metadata.user_id는 여전히 포함 (추적용)                     |  |
|  | 4. x-anthropic-billing-header 미사용                         |  |
|  +------------------------------------------------------------+  |
|                                                                  |
+------------------------------------------------------------------+
```

## 8. 로그인 UI에서의 빌링 구분

```javascript
// 로그인 방식 선택 UI
[
  { label: "Claude account · Claude.ai usage billing", value: "claudeai" },
  { label: "Anthropic Console account · API usage billing", value: "console" },
  { label: "3rd-party platform · Amazon Bedrock, Microsoft Foundry, or Vertex AI", value: "thirdparty" }
]
```

- **Claude account**: claude.ai 구독 기반 과금 (Pro/Team/Enterprise)
- **Console account**: Anthropic API 사용량 기반 과금 (종량제)
- **3rd-party**: 각 클라우드 플랫폼의 과금 체계 사용

## 9. 요약

| 빌링 메커니즘 | 위치 | 캐시 | 목적 |
|--------------|------|------|------|
| `metadata.user_id` | 요청 본문 최상위 | N/A | 계정+세션별 사용량 추적 |
| `x-anthropic-billing-header` | system 프롬프트 블록 #1 | `null` (캐시 안 함) | 서버 사이드 빌링 라우팅 |
| `cache_control.ttl` | system/messages 블록 | 조건부 1h | 퍼스트파티+비오버에이지 캐시 혜택 |
| `service_tier` | 응답 usage | N/A | 서버가 결정한 서비스 등급 |
| `ef.isUsingOverage` | 클라이언트 상태 | N/A | 오버에이지 시 캐시 혜택 제거 |

**핵심 발견사항**:
1. 빌링 헤더는 클라이언트(`Y91` 함수)가 **시스템 프롬프트의 첫 번째 블록**으로 생성하며, `tengu_attribution_header` feature flag(기본 `true`)로 서버가 원격 제어한다
2. 빌링 관련 블록만 `cacheScope: null`로 설정하여 **캐시에서 의도적으로 제외**한다
3. `metadata.user_id`는 `apiKey_accountUuid_sessionId` 3요소로 구성되어 다차원 추적이 가능하다
4. 오버에이지 상태(`ef.isUsingOverage`)가 캐시 TTL에 직접 영향을 미친다
5. `claudeCodeFirstTokenDate`를 서버에서 조회하여 저장하는 것은 구독 시작 시점 추적용이다
