# Claude Code WebFetch 도구 분석

Claude Code CLI에 내장된 `web_fetch` 도구의 내부 구현 분석.

## 개요

**분석 대상**: `/Users/jaesolshin/.nvm/versions/node/v20.18.1/lib/node_modules/@anthropic-ai/claude-code/cli.js`

**버전**: 2.1.29

## TypeScript 인터페이스 정의

`sdk-tools.d.ts`에 정의된 인터페이스:

```typescript
export interface WebFetchInput {
  /**
   * The URL to fetch content from
   */
  url: string;

  /**
   * The prompt to run on the fetched content
   */
  prompt: string;
}
```

## 권한 시스템 (Permission System)

WebFetch는 **도메인 기반 권한 규칙**을 사용합니다.

### 권한 형식

```javascript
// .claude/settings.local.json 또는 프로젝트 설정에서
{
  "toolPermissions": [
    "WebFetch(domain:example.com)",           // 특정 도메인
    "WebFetch(domain:github.com)",            // GitHub 허용
    "WebFetch(domain:*.google.com)"          // 와일드카드 서브도메인
  ]
}
```

### 권한 검증 로직

```javascript
customValidation: {
  WebFetch: (A) => {
    // URL 직접 입력 방지
    if (A.includes("://") || A.startsWith("http"))
      return {
        valid: false,
        error: "WebFetch permissions use domain format, not URLs",
        suggestion: 'Use "domain:hostname" format',
        examples: ["WebFetch(domain:example.com)", "WebFetch(domain:github.com)"]
      };

    // "domain:" 접두사 필수
    if (!A.startsWith("domain:"))
      return {
        valid: false,
        error: 'WebFetch permissions must use "domain:" prefix',
        suggestion: 'Use "domain:hostname" format',
        examples: ["WebFetch(domain:example.com)", "WebFetch(domain:*.google.com)"]
      };

    return { valid: true };
  }
}
```

## 내부 구현

### 1. Domain Preflight Check

도메인 허용 여부를 사전에 확인하는 API 호출:

```javascript
// 도메인 체크 API 엔드포인트
const response = await fetch(
  `https://api.anthropic.com/v1/domain_info?domain=${encodeURIComponent(hostname)}`
);

if (response.status === 200) {
  const data = await response.json();
  return data.can_fetch === false ? { status: "blocked" } : { status: "allowed" };
}
```

### 2. HTTP Client (Axios 기반)

```javascript
async function fetchWithRedirects(url, signal, maxContentLength) {
  try {
    return await axios.get(url, {
      signal,
      maxRedirects: 0,
      responseType: "arraybuffer",
      maxContentLength: MAX_CONTENT_LENGTH,
      headers: { Accept: "text/markdown, text/html, */*" }
    });
  } catch (error) {
    // 리다이렉션 처리
    if ([301, 302, 307, 308].includes(error.response.status)) {
      const redirectUrl = error.response.headers.location;
      if (redirectUrl) {
        return {
          type: "redirect",
          originalUrl: url,
          redirectUrl: redirectUrl,
          statusCode: error.response.status
        };
      }
    }
    throw error;
  }
}
```

### 3. 캐시 시스템 (LRU Cache)

```javascript
// LRU 캐시 설정
const cache = new LRUCache({
  maxSize: 100 * 1024 * 1024,  // 100MB
  sizeCalculation: (value) => Buffer.byteLength(value.content),
  ttl: 1000 * 60 * 60  // 1시간
});
```

### 4. 처리 파이프라인

```
URL → [Fetch] → [Content-Type Detection] → [Parse] → [Prompt Application] → Result
           ↓
        [Cache Check]
           ↓
        [Redirect Handling]
```

## 출력 스키마

```typescript
{
  bytes: number;        // fetched content size in bytes
  code: number;         // HTTP response code (e.g., 200)
  codeText: string;     // HTTP response code text (e.g., "OK")
  result: string;       // processed result after applying prompt
  durationMs: number;   // time taken for fetch + processing
  url: string;          // the URL that was actually fetched
}
```

## 리다이렉션 처리

WebFetch는 **자동 리다이렉션을 수행하지 않습니다**. 대신 리다이렉션 정보를 반환하고 사용자에게 새 요청을 안내합니다:

```javascript
// 리다이렉션 응답
{
  type: "redirect",
  originalUrl: "http://example.com",
  redirectUrl: "https://example.com",
  statusCode: 301
}

// 사용자에게 전달되는 메시지
I need to fetch content from the redirected URL.
Please use WebFetch again with these parameters:
- url: "${redirectUrl}"
- prompt: "${prompt}"
```

## 도구 속성

```javascript
{
  name: "WebFetch",
  maxResultSizeChars: 100000,  // 100KB
  isConcurrencySafe: true,       // 병렬 실행 가능
  isReadOnly: true,              // 읽기 전용

  // 권한 체크
  async checkPermissions(input, context) {
    // 1. 사전 허용된 도메인/경로 확인
    // 2. deny/ask/allow 규칙 적용
    // 3. behavior 반환
  }
}
```

## 환경 변수

```bash
# WebFetch 프리플라이트 체크 건너뛰기 (엔터프라이즈 환경용)
export CLOUDCODE_SKIP_WEBFETCH_PREFLIGHT=true
```

## WebSearch와의 차이

| 항목 | WebFetch | WebSearch |
|------|----------|-----------|
| **목적** | 특정 URL 컨텐츠 가져오기 | 검색 엔진으로 검색 |
| **입력** | url + prompt | query |
| **권한** | domain:hostname 형식 | 와일드카드 지원 안 함 |
| **출력** | 처리된 결과 | 검색 결과 리스트 |
| **캐시** | LRU 캐시 있음 | 캐시 없음 |

## 사용 예시

```typescript
// Claude Code에서의 사용
{
  "type": "tool_use",
  "id": "toolu_...",
  "name": "WebFetch",
  "input": {
    "url": "https://example.com/docs",
    "prompt": "Extract the main sections and summarize them"
  }
}
```

## 관련 API 엔드포인트

- `https://api.anthropic.com` - 메인 API
- `https://api.anthropic.com/api/oauth/claude_cli/create_api_key` - CLI 키 생성
- `https://mcp-proxy.anthropic.com` - MCP 프록시

## 참고 사항

1. **보안**: 인증된 URL이나 프라이빗 페이지는 실패할 수 있음
2. **크기 제한**: `maxResultSizeChars: 100000` (100KB)
3. **병렬성**: `isConcurrencySafe: true` - 여러 요청 병렬 가능
4. **읽기 전용**: `isReadOnly: true` - 시스템 수정 없음
