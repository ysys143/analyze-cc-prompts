# Claude Code OAuth 토큰 발급, 보관, 갱신 메커니즘 분석

## 1. 개요

Claude Code는 **OAuth 2.0 + PKCE** 기반 인증을 사용한다. 토큰 라이프사이클은 3단계로 구성된다:

```
+------------------------------------------------------------------+
|                OAuth 토큰 라이프사이클                               |
+------------------------------------------------------------------+
|                                                                  |
|  [1] 발급 (Issuance)                                              |
|  +------------------------------------------------------------+  |
|  | Browser OAuth Flow (PKCE)                                  |  |
|  |   → accessToken + refreshToken + scopes                    |  |
|  | 또는                                                        |  |
|  | CLAUDE_CODE_OAUTH_REFRESH_TOKEN 환경변수                     |  |
|  |   → bc6() 함수로 refresh → accessToken                     |  |
|  +------------------------------------------------------------+  |
|       |                                                          |
|       v                                                          |
|  [2] 보관 (Storage)                                               |
|  +------------------------------------------------------------+  |
|  | ~/.claude.json → oauthAccount (계정 메타데이터)               |  |
|  | OS Keychain    → OAuth 토큰 (accessToken, refreshToken)     |  |
|  | 파생: API Key  → zC8() 서버에서 발급, 로컬 저장              |  |
|  +------------------------------------------------------------+  |
|       |                                                          |
|       v                                                          |
|  [3] 갱신 (Renewal)                                               |
|  +------------------------------------------------------------+  |
|  | accessToken 만료 → refreshToken으로 자동 갱신                |  |
|  | API Key 만료/무효 → accessToken으로 재발급                   |  |
|  | apiKeyHelper → 5분 TTL로 동적 갱신                          |  |
|  +------------------------------------------------------------+  |
|                                                                  |
+------------------------------------------------------------------+
```

## 2. 토큰 발급 (Issuance)

### 2.1 브라우저 기반 OAuth Flow

`claude auth login` 실행 시 `uz6` 클래스(OAuthFlow)가 PKCE 기반 OAuth를 수행한다:

```
+------------------------------------------------------------------+
|              OAuth PKCE 인증 흐름                                   |
+------------------------------------------------------------------+
|                                                                  |
|  CLI (uz6 클래스)                 Browser              Auth Server |
|       |                            |                      |       |
|  [1]  | 로컬 HTTP 서버 시작         |                      |       |
|       | (localhost 콜백용)          |                      |       |
|       |                            |                      |       |
|  [2]  | code_verifier 생성 (PKCE)  |                      |       |
|       | code_challenge = SHA256(verifier)                  |       |
|       |                            |                      |       |
|  [3]  |------- 브라우저 열기 ------>|                      |       |
|       |  authorize URL:            |                      |       |
|       |  - client_id               |                      |       |
|       |  - redirect_uri            |------- 로그인 ------>|       |
|       |  - code_challenge          |                      |       |
|       |  - scope                   |<-- authorization_code |       |
|       |  - loginHint (email/sso)   |                      |       |
|       |                            |                      |       |
|  [4]  |<--- localhost 콜백 --------|                      |       |
|       | (authorization_code 수신)   |                      |       |
|       |                            |                      |       |
|  [5]  |------------ token 교환 ------------------>|       |       |
|       |  grant_type: authorization_code            |       |       |
|       |  code: authorization_code                  |       |       |
|       |  code_verifier: PKCE verifier              |       |       |
|       |                                            |       |       |
|  [6]  |<----------- 토큰 응답 --------------------|       |       |
|       |  access_token                              |       |       |
|       |  refresh_token                             |       |       |
|       |  expires_in                                |       |       |
|       |  scope                                     |       |       |
|       |                                            |       |       |
|  [7]  | qi6() → 토큰 설치                          |       |       |
|       | z.cleanup() → 로컬 서버 종료                |       |       |
|       |                                                          |
+------------------------------------------------------------------+
```

코드 흐름 (cli.js ~line 2714):
```javascript
// 1. OAuthFlow 인스턴스 생성
let z = new uz6;

// 2. OAuth 흐름 시작 (브라우저 열기 + 로컬 콜백 서버)
let w = await z.startOAuthFlow(
  async (_) => {
    process.stdout.write(`Opening browser to sign in…\n`);
    process.stdout.write(`If the browser didn't open, visit: ${_}\n`);
  },
  {
    loginWithClaudeAi: true,
    loginHint: email,     // 이메일 힌트 (선택)
    loginMethod: "sso"    // SSO 또는 기본
  }
);

// 3. 토큰 설치
await qi6(w);  // installOAuthTokens

// 4. 정리
z.cleanup();   // 로컬 서버 종료
```

### 2.2 Refresh Token 기반 발급 (Headless/CI)

환경변수 `CLAUDE_CODE_OAUTH_REFRESH_TOKEN`이 설정된 경우 브라우저 없이 토큰을 발급한다:

```javascript
let K = process.env.CLAUDE_CODE_OAUTH_REFRESH_TOKEN;
let w = process.env.CLAUDE_CODE_OAUTH_SCOPES;
// 필수 스코프: "user:inference" 등

let _ = w.split(/\s+/).filter(Boolean);
// bc6: refresh token → access token 교환
let $ = await bc6(K, { scopes: _ });
await qi6($);  // 토큰 설치
```

### 2.3 OAuth Scopes

Claude Code가 요청하는 스코프:

| Scope | 용도 |
|-------|------|
| `user:inference` | API 추론 호출 (필수) |
| `user:profile` | 프로필 정보 조회 |
| `user:sessions:claude_code` | 세션 관리 |
| `user:mcp_servers` | MCP 서버 접근 |

`uF()` 함수로 스코프 보유 여부를 확인하여 기능을 조건부 활성화한다:
- `user:profile` 스코프가 있으면 → `Te4()` (첫 토큰 날짜 조회)
- `user:inference` 스코프가 없으면 → API 호출 불가

## 3. 토큰 보관 (Storage)

### 3.1 저장 위치별 데이터

```
+------------------------------------------------------------------+
|              토큰 저장 구조                                         |
+------------------------------------------------------------------+
|                                                                  |
|  ~/.claude.json (평문 JSON)                                       |
|  +------------------------------------------------------------+  |
|  | "oauthAccount": {                                          |  |
|  |   "accountUuid": "8490898f-...",                           |  |
|  |   "emailAddress": "user@example.com",                     |  |
|  |   "organizationUuid": "0ea4de60-...",                     |  |
|  |   "hasExtraUsageEnabled": false,                          |  |
|  |   "billingType": "prepaid",                               |  |
|  |   "accountCreatedAt": "2024-03-15T...",                   |  |
|  |   "subscriptionCreatedAt": "2025-06-04T...",              |  |
|  |   "displayName": "Jaesol",                                |  |
|  |   "organizationRole": "admin",                            |  |
|  |   "workspaceRole": "workspace_developer",                 |  |
|  |   "organizationName": "My Org"                            |  |
|  | }                                                          |  |
|  |                                                            |  |
|  | "userID": "36b51f28e4f0a812..."   (해시된 식별자)            |  |
|  | "hasCompletedOnboarding": true                             |  |
|  | "penguinModeOrgEnabled": true                              |  |
|  +------------------------------------------------------------+  |
|                                                                  |
|  OS Keychain / 보안 저장소                                         |
|  +------------------------------------------------------------+  |
|  | accessToken  (OAuth access token)                          |  |
|  | refreshToken (OAuth refresh token)                         |  |
|  | scopes       (부여된 스코프 목록)                             |  |
|  | expiresAt    (access token 만료 시각)                        |  |
|  +------------------------------------------------------------+  |
|                                                                  |
|  파생 키 (서버 발급)                                               |
|  +------------------------------------------------------------+  |
|  | API Key (sk-ant-xxx)                                       |  |
|  |   → YC8(): accessToken으로 세션 생성                         |  |
|  |   → zC8(): accessToken으로 API 키 발급                      |  |
|  |   → 실제 API 호출에 사용되는 키                               |  |
|  +------------------------------------------------------------+  |
|                                                                  |
+------------------------------------------------------------------+
```

### 3.2 `qi6` (installOAuthTokens) 상세

토큰 설치 시 수행되는 5단계:

```javascript
async function qi6(A) {
  // [1] 기존 토큰 제거
  await gn6({ clearOnboarding: false });

  // [2] 프로필 조회 → 계정 메타데이터 저장
  let q = A.profile ?? await L16(A.accessToken);
  if (q) RT6({
    accountUuid:          q.account.uuid,
    emailAddress:         q.account.email,
    organizationUuid:     q.organization.uuid,
    // ... billingType, subscriptionCreatedAt 등
  });

  // [3] OAuth 토큰 저장 (보안 저장소)
  let K = $V6(A);       // accessToken, refreshToken, scopes 저장
  if (K.warning) ...;   // 저장 실패 시 경고
  Xk1();               // 토큰 캐시 무효화

  // [4] 세션 생성 + API 키 발급
  await YC8(A.accessToken);  // 세션 생성 (인증 헤더용)
  if (uF(A.scopes))         // 스코프에 inference 포함 시
    await Te4();             // 첫 토큰 날짜 조회/저장
  else
    await zC8(A.accessToken); // API 키 발급

  // [5] 쉘 설정 업데이트
  await cv1();  // PATH 등 환경 설정
}
```

### 3.3 `$V6` — 토큰 보안 저장

`$V6` 함수가 OAuth 토큰을 보안 저장소에 기록한다. 저장소 우선순위:

| 플랫폼 | 보안 저장소 | 폴백 |
|--------|-----------|------|
| macOS | Keychain (via `security` CLI) | 파일 시스템 (암호화) |
| Linux | libsecret / gnome-keyring | 파일 시스템 (권한 제한) |
| Windows | Windows Credential Manager | 파일 시스템 |

저장 실패 시 `K.warning` 경고가 발생하고 텔레메트리 이벤트 `tengu_oauth_storage_warning`이 기록된다.

### 3.4 `cx` — 토큰 읽기

```javascript
let { source, hasToken } = cx();
// source: "claude.ai" | "apiKeyHelper" | "none" | 기타
// hasToken: boolean
```

토큰 소스 우선순위:
1. `claude.ai` — OAuth로 발급된 토큰
2. `apiKeyHelper` — 외부 헬퍼가 동적 제공하는 키
3. `ANTHROPIC_API_KEY` 환경변수
4. `/login managed key` — 관리형 키

## 4. 토큰 갱신 (Renewal)

### 4.1 Access Token 자동 갱신

Access token은 만료 시간(`expiresAt`)이 있으며, 만료 전에 자동으로 갱신된다:

```
+------------------------------------------------------------------+
|              Access Token 갱신 흐름                                 |
+------------------------------------------------------------------+
|                                                                  |
|  API 요청 시도                                                     |
|       |                                                          |
|       v                                                          |
|  accessToken 유효?                                                 |
|       |                                                          |
|   YES |                          NO                               |
|       v                           |                               |
|  요청 진행                         v                               |
|                             refreshToken 보유?                     |
|                                    |                              |
|                                YES |           NO                  |
|                                    v            |                  |
|                              bc6() 호출          v                  |
|                              (refresh grant)    로그인 필요          |
|                                    |            (claude auth login) |
|                                    v                               |
|                              새 accessToken                         |
|                              $V6()로 저장                           |
|                              Xk1()로 캐시 무효화                     |
|                                    |                               |
|                                    v                               |
|                              요청 재시도                             |
|                                                                  |
+------------------------------------------------------------------+
```

### 4.2 `bc6` — Refresh Token으로 Access Token 갱신

```javascript
// refresh_token → access_token 교환
let result = await bc6(refreshToken, { scopes: [...] });
// result: { accessToken, refreshToken, scopes, profile? }
```

이 함수는 OAuth token endpoint에 `grant_type: refresh_token` 요청을 보낸다. 새로운 refresh token도 함께 반환될 수 있으며, 이 경우 기존 것을 교체한다 (Refresh Token Rotation).

### 4.3 API Key 파생 및 갱신

OAuth 토큰과 실제 API 호출에 사용되는 키의 관계:

```
+------------------------------------------------------------------+
|              API Key 파생 체인                                      |
+------------------------------------------------------------------+
|                                                                  |
|  OAuth accessToken                                                |
|       |                                                          |
|       +---> YC8(accessToken)                                      |
|       |     세션 생성 API 호출                                     |
|       |     → 인증 헤더로 세션 토큰 반환                            |
|       |                                                          |
|       +---> zC8(accessToken)                                      |
|             API 키 발급 API 호출                                   |
|             → sk-ant-xxx 형태의 API 키 반환                        |
|             → 이 키가 실제 Messages API에 사용됨                    |
|                                                                  |
|  API 키 사용 흐름:                                                 |
|  Cb({ apiKey, maxRetries, model, source }) → Anthropic SDK 클라이언트 |
|       → beta.messages.create({ ..., metadata: A66() })            |
|                                                                  |
+------------------------------------------------------------------+
```

### 4.4 apiKeyHelper 동적 갱신

`apiKeyHelper`는 외부 프로세스가 API 키를 동적으로 제공하는 메커니즘이다:

| 속성 | 값 |
|------|-----|
| TTL | 5분 (v0.2.74에서 도입) |
| 갱신 방식 | 헬퍼 프로세스 재호출 |
| 용도 | 기업 환경에서 임시 키 발급 |

```
CLI 시작 → apiKeyHelper 프로세스 호출 → API 키 수신 → 5분 후 만료 → 재호출 → ...
```

### 4.5 인증 헤더 생성 (`CO` 함수)

실제 API 요청 시 인증 헤더를 구성하는 함수:

```javascript
function CO() {
  // 1. 저장된 API 키 또는 OAuth 토큰에서 헤더 생성
  // 2. 에러 시 { error: "..." } 반환
  // 3. 성공 시 { headers: { "x-api-key": "sk-ant-xxx", ... } } 반환
}
```

## 5. 토큰 무효화 및 로그아웃

### 5.1 로그아웃 (`gn6`)

```javascript
async function DlY() {   // authLogout
  await gn6({ clearOnboarding: false });
  // gn6: OAuth 토큰 삭제, 계정 정보 초기화
  // Keychain에서 토큰 제거
  // .claude.json에서 oauthAccount 삭제
}
```

### 5.2 자동 백업

`.claude.json`은 변경 시 자동 백업된다:
```
~/.claude/backups/.claude.json.backup.{timestamp}
```
프록시 캡처 환경에서 확인된 백업 파일:
- `.claude.json.backup.1772808757880`
- `.claude.json.backup.1772810772038` 등

## 6. 보안 고려사항

### 6.1 토큰 저장 보안

| 데이터 | 저장 위치 | 보안 수준 |
|--------|----------|----------|
| accessToken | OS Keychain | 높음 (OS 수준 암호화) |
| refreshToken | OS Keychain | 높음 |
| accountUuid | ~/.claude.json | 중간 (평문, 파일 퍼미션) |
| API Key (sk-ant-*) | 메모리 / 보안 저장소 | 높음 |
| emailAddress | ~/.claude.json | 중간 (평문) |

### 6.2 PKCE의 역할

PKCE(Proof Key for Code Exchange)는 authorization code 가로채기 공격을 방지:
- CLI는 `code_verifier`(랜덤 문자열)를 생성
- `code_challenge = SHA256(code_verifier)`를 authorize URL에 포함
- Token 교환 시 `code_verifier`를 전송하여 증명
- 로컬 localhost 콜백이므로 PKCE가 필수적

### 6.3 Refresh Token Rotation

서버가 새 refresh token을 발급하면 기존 것은 자동 폐기된다. 이는 refresh token 유출 시 피해를 최소화한다.

## 7. 인증 소스 우선순위 전체도

```
+------------------------------------------------------------------+
|              인증 소스 결정 흐름                                     |
+------------------------------------------------------------------+
|                                                                  |
|  [1] 서드파티 플랫폼 설정 확인                                      |
|      ($x() → Bedrock/Vertex/Foundry)                              |
|       |                                                          |
|       +-- 설정됨 → 해당 플랫폼 인증 사용                            |
|       |                                                          |
|       +-- 미설정 ↓                                                |
|                                                                  |
|  [2] OAuth 토큰 확인                                               |
|      cx() → { source, hasToken }                                  |
|       |                                                          |
|       +-- source: "claude.ai" → OAuth 인증                        |
|       +-- source: "apiKeyHelper" → 동적 키 (5분 TTL)               |
|       |                                                          |
|       +-- 미설정 ↓                                                |
|                                                                  |
|  [3] API Key 환경변수 확인                                          |
|      O$() → ANTHROPIC_API_KEY 존재 여부                            |
|       |                                                          |
|       +-- 있음 → API Key 직접 사용                                 |
|       |                                                          |
|       +-- 없음 → 미인증 상태                                       |
|            "Not logged in. Run claude auth login"                  |
|                                                                  |
+------------------------------------------------------------------+
```

## 8. 텔레메트리 이벤트

| 이벤트 | 시점 |
|--------|------|
| `tengu_oauth_flow_start` | OAuth 흐름 시작 |
| `tengu_oauth_success` | OAuth 성공 |
| `tengu_login_from_refresh_token` | refresh token으로 로그인 |
| `tengu_oauth_storage_warning` | 토큰 저장 실패 경고 |

## 9. 요약

| 단계 | 함수 | 설명 |
|------|------|------|
| OAuth 시작 | `uz6.startOAuthFlow()` | PKCE 기반 브라우저 인증 |
| Refresh 교환 | `bc6()` | refresh_token → access_token |
| 토큰 설치 | `qi6()` | 프로필 저장 + 토큰 저장 + API 키 발급 |
| 계정 저장 | `RT6()` | oauthAccount를 .claude.json에 기록 |
| 토큰 저장 | `$V6()` | OS Keychain에 토큰 저장 |
| 캐시 무효화 | `Xk1()` | 토큰 캐시 리셋 |
| API 키 발급 | `zC8()` | accessToken → sk-ant-xxx 발급 |
| 세션 생성 | `YC8()` | accessToken → 세션 토큰 |
| 토큰 읽기 | `cx()` | 저장된 토큰 소스/존재 확인 |
| 인증 헤더 | `CO()` | API 요청용 헤더 조립 |
| 로그아웃 | `gn6()` | 토큰 + 계정 정보 삭제 |
