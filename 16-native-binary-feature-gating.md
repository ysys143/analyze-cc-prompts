# 16. Native Binary Feature Gating 메커니즘 분석

> 분석 대상: `@anthropic-ai/claude-code@2.1.70`
> 분석 일자: 2026-03-06

## 개요

Claude Code는 npm과 Native Binary(Bun 번들) 두 가지 배포 형태를 가진다. `/fast`, `/voice` 같은 프리미엄 기능은 **Native Binary에서만 동작**하도록 게이트가 걸려 있다. 이 문서는 그 기술적 메커니즘을 분석한다.

---

## 1. Native Binary 감지 방법

### 1.1 핵심 감지 함수 두 가지

```js
// 함수 1: Bun 런타임 위에서 실행 중인가?
function vj6() {
  return process.versions.bun !== void 0;
}

// 함수 2: Bun으로 "컴파일된 바이너리"인가? (= Native Binary)
function e5() {
  return typeof Bun < "u"
    && Array.isArray(Bun.embeddedFiles)
    && Bun.embeddedFiles.length > 0;
}
```

**차이점이 중요하다:**

| 함수 | 의미 | npm + Node.js | npm + Bun | Native Binary |
|------|------|:---:|:---:|:---:|
| `vj6()` (isRunningWithBun) | Bun 런타임 여부 | `false` | `true` | `true` |
| `e5()` (isBundledBinary) | Bun 컴파일 바이너리 여부 | `false` | `false` | `true` |

### 1.2 감지 원리: `Bun.embeddedFiles`

`Bun.embeddedFiles`는 **Bun의 단일 실행 파일 컴파일러(Single-file executable)** 전용 API다.

```bash
# Native Binary 빌드 과정 (Anthropic 빌드 서버)
bun build --compile ./src/cli.ts --outfile claude \
  --embed ./audio-capture/arm64-darwin/audio-capture.node \
  --embed ./resvg.wasm \
  ...
```

- `bun build --compile`로 빌드하면, 지정된 파일들이 바이너리 안에 **임베드**됨
- 임베드된 파일들은 런타임에서 `Bun.embeddedFiles` 배열로 접근 가능
- npm으로 설치한 경우 Node.js가 실행하므로 `Bun` 전역 객체 자체가 없음
- Bun으로 npm 패키지를 직접 실행해도 `--compile`이 아니므로 `embeddedFiles`는 빈 배열

**이것이 npm과 Native Binary를 100% 구분할 수 있는 이유다.**

---

## 2. /fast 기능 게이팅

### 2.1 게이트 흐름

```js
function yt() {  // Fast Mode 가용성 체크
  // Gate 1: 환경변수로 비활성화되었는가?
  if (!Bq()) return "Fast mode is not available";

  // Gate 2: Native Binary가 아니고 + feature flag가 켜져 있으면 차단
  if (!e5() && e8("tengu_marble_sandcastle", true))
    return "Fast mode requires the native binary · Install from: https://claude.com/product/claude-code";

  // Gate 3: 서버사이드 kill switch
  let A = e8("tengu_penguins_off", null);
  if (A !== null) return A;

  // Gate 4: Agent SDK에서는 불가
  if (u7() && My6()) { ... }

  // Gate 5: First-party API만 허용 (Bedrock/Vertex/Foundry 제외)
  if (D7() !== "firstParty") return "...not available on Bedrock, Vertex, or Foundry";

  // Gate 6: 구독/과금 상태 체크
  if (zV.status === "disabled" && e8("tengu_tangerine_ladder_boost", true)) {
    let q = c7() !== null ? "oauth" : "api-key";
    let K = Ts5(zV.reason, q);  // "requires paid subscription" 등
    return K;
  }

  return null;  // null = 사용 가능!
}
```

### 2.2 Gate 2 상세 분석 (Native Binary 체크)

```js
if (!e5() && e8("tengu_marble_sandcastle", true))
```

| 조건 | 의미 |
|------|------|
| `!e5()` | Native Binary가 **아님** (= npm 설치) |
| `e8("tengu_marble_sandcastle", true)` | Feature flag가 켜져 있음 (기본값 `true`) |

- `tengu_marble_sandcastle`는 **"npm에서 fast mode를 차단할지"**를 제어하는 서버사이드 flag
- 기본값이 `true`이므로, 서버에서 별도로 `false`를 보내지 않는 한 npm에서는 항상 차단
- Anthropic이 서버에서 이 flag를 `false`로 바꾸면 npm에서도 fast mode 사용 가능 (롤아웃 제어)

### 2.3 Fast Mode 과금 상태별 메시지

```js
function Ts5(reason, authType) {
  switch (reason) {
    case "free":
      return authType === "oauth"
        ? "Fast mode requires a paid subscription"
        : "Fast mode unavailable during evaluation. Please purchase credits.";
    case "preference":
      return "Fast mode has been disabled by your organization";
    case "extra_usage_disabled":
      return "Fast mode requires extra usage billing · /extra-usage to enable";
    case "network_error":
      return "Fast mode unavailable due to network connectivity issues";
    case "unknown":
      return "Fast mode is currently unavailable";
  }
}
```

---

## 3. /voice 기능 게이팅

Voice는 `/fast`와 다른 방식으로 게이트된다. **코드 레벨에서 native를 직접 차단하지 않고**, 네이티브 오디오 모듈의 존재 여부로 자연스럽게 분기한다.

### 3.1 오디오 모듈 로드 시도

```js
function sC1() {  // 네이티브 오디오 모듈 로드
  let A = process.platform;
  if (A !== "darwin" && A !== "linux" && A !== "win32") return null;
  try {
    if (process.env.AUDIO_CAPTURE_NODE_PATH)
      aC1 = require(process.env.AUDIO_CAPTURE_NODE_PATH);
    else {
      let K = `${process.arch}-${A}`;
      let Y = path.join(import.meta.url, "..", "audio-capture", K, "audio-capture.node");
      aC1 = require(Y);
    }
    return aC1;
  } catch { return null; }
}

function Ra6() { return sC1() !== null; }  // 오디오 모듈 사용 가능?
```

### 3.2 Voice 가용성 판단 흐름

```
1. Ra6() → 네이티브 audio-capture.node 로드 성공? → 즉시 사용 가능
2. WSL 환경? → 차단
3. Windows? → "requires the native audio module" 차단
4. Linux + arecord 있음? → SoX 대체로 사용 가능
5. macOS + rec (SoX) 있음? → SoX 대체로 사용 가능
6. SoX 없음? → "Install SoX" 안내
```

### 3.3 npm vs Native에서의 차이

| 환경 | audio-capture.node | Voice 사용 |
|------|:--:|:--:|
| **Native Binary** | 바이너리에 임베드됨 (`Bun.embeddedFiles`) | 즉시 사용 가능 |
| **npm + macOS** | 파일 없음 → SoX fallback | `brew install sox` 후 사용 가능 |
| **npm + Linux** | 파일 없음 → arecord/SoX fallback | arecord 또는 SoX 설치 후 가능 |
| **npm + Windows** | 파일 없음 → fallback 없음 | 사용 불가 |

Voice의 경우 npm에서도 SoX를 설치하면 사용 가능할 수 있으나, `audio-capture.node`가 npm 패키지에 포함되지 않으므로 Native Binary가 훨씬 유리하다.

---

## 4. 게이팅 메커니즘 비교

| 측면 | /fast | /voice |
|------|-------|--------|
| **게이팅 방식** | 명시적 코드 체크 (`e5()`) | 암시적 의존성 부재 |
| **Native 감지** | `Bun.embeddedFiles` 직접 확인 | `audio-capture.node` 로드 실패 |
| **Feature Flag** | `tengu_marble_sandcastle` | Feature flag 기반 isEnabled() |
| **npm 우회 가능?** | 불가 (서버 flag + 런타임 체크) | 부분 가능 (SoX 설치로 대체) |
| **차단 메시지** | "requires the native binary" | 플랫폼별 다양한 메시지 |

---

## 5. 전체 아키텍처

```
┌─────────────────────────────────────────────────┐
│              Claude Code 소스 코드                │
│  (동일한 TypeScript → 동일한 번들 cli.js)          │
└──────────────┬──────────────┬───────────────────┘
               │              │
      ┌────────▼────────┐  ┌─▼──────────────────┐
      │   npm 배포       │  │  Native Binary 빌드 │
      │                 │  │  bun build --compile │
      │  cli.js         │  │  + --embed files     │
      │  (JS 파일)      │  │  (단일 실행 파일)     │
      └────────┬────────┘  └─┬──────────────────┘
               │              │
      Node.js로 실행      Bun 런타임 내장 실행
               │              │
      ┌────────▼────────┐  ┌─▼──────────────────┐
      │ Runtime 환경     │  │ Runtime 환경        │
      │                 │  │                     │
      │ process.versions│  │ process.versions    │
      │   .bun = undef  │  │   .bun = "1.x"     │
      │                 │  │                     │
      │ typeof Bun      │  │ typeof Bun          │
      │   = "undefined" │  │   = "object"        │
      │                 │  │                     │
      │ Bun.embedded    │  │ Bun.embeddedFiles   │
      │   Files = N/A   │  │   = [audio.node,    │
      │                 │  │     resvg.wasm, ...] │
      └────────┬────────┘  └─┬──────────────────┘
               │              │
      ┌────────▼────────┐  ┌─▼──────────────────┐
      │ Feature Gate    │  │ Feature Gate        │
      │                 │  │                     │
      │ e5() = false    │  │ e5() = true         │
      │ Ra6() = false   │  │ Ra6() = true        │
      │                 │  │                     │
      │ /fast → 차단    │  │ /fast → 허용         │
      │ /voice → SoX?   │  │ /voice → 즉시 사용   │
      └─────────────────┘  └─────────────────────┘
```

---

## 6. 이중 안전장치: 서버 + 클라이언트

Fast mode의 게이팅은 단순한 클라이언트 체크가 아니라 **이중 안전장치**다:

### 6.1 클라이언트 사이드 (로컬)
```js
e5()  // Bun.embeddedFiles 존재 여부 → 조작 불가
```
- npm 환경에서는 `Bun` 전역 객체 자체가 존재하지 않음
- Node.js에서 `globalThis.Bun`을 모킹해도 `embeddedFiles`에 실제 파일이 없음

### 6.2 서버 사이드 (Anthropic API)
```js
e8("tengu_marble_sandcastle", true)  // 서버에서 flag 값 수신
```
- 서버가 클라이언트의 설치 유형을 알고 있음 (텔레메트리의 `is_running_with_bun` 필드)
- 서버에서 flag를 `false`로 보내면 npm에서도 허용 가능 (미래 롤아웃 시나리오)

### 6.3 우회 방지

| 우회 시도 | 결과 |
|-----------|------|
| 환경변수 `CLAUDE_CODE_DISABLE_FAST_MODE` 삭제 | Gate 2에서 `e5()` 체크로 차단 |
| `globalThis.Bun = { embeddedFiles: [...] }` 모킹 | 실제 파일 로드 실패, 다른 기능에서 크래시 |
| Feature flag 응답 가로채기 | HTTPS 통신, 인증 토큰 필요 |
| npm 패키지에서 `audio-capture.node` 수동 배치 | Voice는 가능할 수 있으나, Fast는 여전히 차단 |

---

## 7. `Bun.embeddedFiles`이 게이트 키로 적합한 이유

| 특성 | 설명 |
|------|------|
| **위조 불가** | `bun build --compile`로 빌드해야만 생성됨 |
| **런타임 레벨** | JavaScript에서 모킹해도 Bun 내부 C++ 코드가 실제 파일 존재 확인 |
| **부수효과** | 임베드 파일이 실제로 사용됨 (audio-capture.node, resvg.wasm) |
| **깔끔한 분기** | 하나의 체크로 npm vs Native를 완벽 구분 |

---

## 8. 커맨드 숨김(isHidden) 메커니즘

`/fast`와 `/voice`는 단순히 "실행 시 차단"되는 것이 아니라, **커맨드 목록에서 아예 보이지 않게** 처리된다.

### 8.1 커맨드 등록 구조

```js
// /voice 커맨드 정의
{
  type: "local",
  name: "voice",
  description: "Toggle voice mode",
  isEnabled: () => QX1(),           // 실행 가능 여부
  get isHidden() { return !sf(); }, // 목록에서 숨길지 여부
  supportsNonInteractive: false,
  userFacingName() { return "voice"; }
}

// /fast 커맨드 정의
{
  type: "local-jsx",
  name: "fast",
  get description() { return `Toggle fast mode (${modelName} only)`; },
  isEnabled: () => Bq(),            // 실행 가능 여부
  get isHidden() { return !Bq(); }, // 목록에서 숨길지 여부
  argumentHint: "[on|off]",
  userFacingName: () => "fast"
}
```

### 8.2 /voice 숨김 조건

```js
// isHidden = !sf()
function sf() {
  if (!xH()) return false;   // OAuth 로그인이 아니면 → 숨김
  return QX1();              // feature flag 체크
}

// isEnabled = QX1()
function QX1() {
  return e8("tengu_amber_quartz", false);  // 서버 feature flag (기본값: false)
}
```

**숨김 판단 흐름:**

```
/voice가 보이려면:
  1. xH() = true   → OAuth(claude.ai) 로그인 상태
  2. QX1() = true   → tengu_amber_quartz flag가 true

하나라도 false면 → isHidden = true → 커맨드 목록에서 완전히 제거
```

**`xH()` 함수 상세 - OAuth 로그인 감지:**

```js
function xH() {
  let isBedrock = process.env.CLAUDE_CODE_USE_BEDROCK;
  let isVertex  = process.env.CLAUDE_CODE_USE_VERTEX;
  let isFoundry = process.env.CLAUDE_CODE_USE_FOUNDRY;
  let hasApiKey = process.env.ANTHROPIC_AUTH_TOKEN || apiKeyHelper || ...;
  let { source } = getApiKeySource();

  // Bedrock/Vertex/Foundry이거나, API Key로 인증하면 false
  // → OAuth 로그인만 true 반환
  return !(isBedrock || isVertex || hasApiKey || (source === "ANTHROPIC_API_KEY" && !isRemote));
}
```

즉, **API Key 사용자에게는 /voice가 아예 보이지 않는다.** OAuth(claude.ai 계정)로 로그인한 사용자만 볼 수 있다.

### 8.3 /fast 숨김 조건

```js
// isHidden = !Bq()
function Bq() {
  return !toBool(process.env.CLAUDE_CODE_DISABLE_FAST_MODE);
}
```

**숨김 판단 흐름:**

```
/fast가 보이려면:
  1. CLAUDE_CODE_DISABLE_FAST_MODE 환경변수가 설정되지 않았거나 falsy

환경변수가 truthy면 → isHidden = true → 커맨드 목록에서 제거
```

`/fast`는 `/voice`와 달리 **커맨드 자체는 대부분 보인다.** 숨김은 환경변수로만 제어되고, 실제 "native binary 필요" 메시지는 실행 시점(`yt()` 함수)에서 표시된다.

### 8.4 isEnabled vs isHidden 차이

| 속성 | 역할 | false일 때 |
|------|------|-----------|
| `isHidden` | 커맨드 목록 표시 여부 | 목록에서 완전히 제거 (사용자가 존재 자체를 모름) |
| `isEnabled` | 실행 가능 여부 | 목록에는 보이지만 실행하면 에러 메시지 |

### 8.5 /voice vs /fast 숨김 전략 비교

| 측면 | /voice | /fast |
|------|--------|-------|
| **숨김 조건** | OAuth 미로그인 OR flag off | 환경변수 비활성화 |
| **숨김 기준** | 서버사이드 flag + 인증 방식 | 클라이언트 환경변수 |
| **기본 상태** | 숨김 (`tengu_amber_quartz` 기본값 `false`) | 노출 (환경변수 미설정) |
| **Native 게이트** | 실행 시 audio 모듈 로드 실패로 간접 차단 | 실행 시 `e5()` 체크로 명시적 차단 |
| **설계 의도** | 롤아웃 전까지 존재 자체를 숨김 | 존재는 알려주되 Native 설치 유도 |

---

## 9. 발견된 Feature Flag 목록 (갱신)

| Flag 이름 | 기본값 | 용도 |
|-----------|--------|------|
| `tengu_marble_sandcastle` | `true` | npm에서 Fast mode 차단 (true=차단) |
| `tengu_penguins_off` | `null` | Fast mode 서버사이드 kill switch |
| `tengu_tangerine_ladder_boost` | `true` | Fast mode 과금 상태 체크 활성화 |
| `tengu_amber_quartz` | `false` | Voice mode 활성화 (false=비활성/숨김) |
| `tengu_sotto_voce` | `false` | 간결 출력 스타일 |
| `tengu_bergotte_lantern` | `false` | 다듬어진 출력 스타일 |

---

## 10. 우회 시도 분석: Native Binary에서 파일 추출로 우회 가능한가?

### 10.1 임베드된 파일 목록

Native Binary에 임베드된 8개 파일:

```
audio-capture.node     # 오디오 캡처 (Voice)
color-diff.node        # 색상 비교
file-index.node        # 파일 인덱싱
image-processor.node   # 이미지 처리
ripgrep.node           # 코드 검색
resvg.wasm             # SVG 렌더링
tree-sitter.wasm       # 코드 파싱
tree-sitter-bash.wasm  # Bash 파싱
```

### 10.2 우회 시도별 결과

| 시도 | /fast | /voice | 이유 |
|------|:-----:|:------:|------|
| 파일 추출 + npm 폴더에 배치 | X | △ | Fast는 파일이 아닌 `Bun.embeddedFiles` API 체크 |
| `bun run cli.js`로 실행 | X | △ | `Bun.embeddedFiles`는 빈 배열 (compile 아님) |
| `globalThis.Bun` 모킹 | △ | - | 타이밍 문제 + 실제 파일 로드 실패 |
| Native Binary 통째 사용 | O | O | 당연히 작동 (정상 사용) |

### 10.3 왜 안 되는가

**`Bun.embeddedFiles`는 파일 시스템이 아니라 런타임 내부 API다.**

```
npm + Node.js 실행:
  → typeof Bun === "undefined"    ← Bun 전역 객체 자체가 없음
  → e5() = false                  ← 무조건

npm + Bun 실행 (bun run cli.js):
  → typeof Bun === "object"       ← Bun 있음
  → Bun.embeddedFiles === []      ← compile 안 했으므로 빈 배열
  → e5() = false                  ← 여전히 차단

Native Binary 실행 (bun build --compile):
  → typeof Bun === "object"       ← Bun 있음
  → Bun.embeddedFiles.length > 0  ← 빌드 시 임베드한 파일 존재
  → e5() = true                   ← 유일하게 통과
```

**Bun 객체 모킹이 어려운 이유:**
- `e5()`는 모듈 로드 초기에 평가되어 모킹할 타이밍이 없음
- 코드가 `Bun.embeddedFiles`에서 실제로 `.arrayBuffer()`를 호출하여 wasm/node 파일을 읽음
- 텔레메트리에 `is_running_with_bun` 필드가 전송되어 서버도 환경을 인지

**Voice만 부분 우회 가능한 이유:**
- `audio-capture.node`를 npm 폴더의 올바른 경로에 배치하면 `sC1()` 함수가 require() 성공
- macOS/Linux에서는 SoX(rec/arecord) 설치로도 fallback 가능
- 단, Voice는 `tengu_amber_quartz` flag + OAuth 로그인이라는 별도 게이트가 존재

---

## 결론

Native Binary에서만 `/fast`, `/voice`가 동작하는 핵심 메커니즘:

1. **`Bun.embeddedFiles`** - Bun의 단일 실행 파일 컴파일 시에만 존재하는 API를 활용하여, npm 설치와 Native Binary를 런타임에서 정확히 구분
2. **서버사이드 Feature Flag** - `tengu_marble_sandcastle` 등의 flag로 서버에서도 이중 제어
3. **임베드된 네이티브 모듈** - `audio-capture.node` 같은 바이너리 모듈이 Native에만 포함되어 Voice 등의 기능이 자연스럽게 Native 전용이 됨

이 설계는 **동일한 코드베이스**에서 배포 형태에 따라 기능을 분기하는 우아한 접근법이다. 코드 자체를 분리하지 않고, 런타임 환경의 고유 속성(`Bun.embeddedFiles`)을 게이트 키로 사용한다.

---

**작성일**: 2026-03-06
**대상 버전**: Claude Code v2.1.70
**분석 환경**: macOS ARM64, npm 패키지 소스 코드
