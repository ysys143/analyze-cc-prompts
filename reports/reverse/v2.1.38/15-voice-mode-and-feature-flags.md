# 15. Voice Mode와 Feature Flag 기반 롤링 배포

> 분석 대상: `@anthropic-ai/claude-code@2.1.70`
> 분석 일자: 2026-03-06

## 개요

Claude Code는 npm으로 단일 번들(`cli.js`)을 배포하면서도, **서버사이드 Feature Flag**을 통해 사용자별로 기능 가시성을 제어하는 롤링 배포 방식을 사용한다. `/voice` 커맨드는 이 메커니즘의 대표적 사례다.

## Voice Mode 아키텍처

### 커맨드 등록 구조

```js
// 커맨드 정의 (난독화 해제)
{
  type: "local",
  name: "voice",
  description: "Toggle voice mode",
  isEnabled: () => QX1(),          // feature flag 게이트
  get isHidden() { return !sf() }, // 로그인 상태 기반 숨김
  supportsNonInteractive: false,
  userFacingName() { return "voice" }
}
```

- `isEnabled()`: feature flag가 `false`면 커맨드 자체가 비활성
- `isHidden`: OAuth 로그인이 안 되어 있으면 커맨드 목록에서 숨김

### Voice 활성화 조건 (다중 게이트)

| 순서 | 조건 | 함수 | 실패 시 메시지 |
|------|------|------|---------------|
| 1 | Feature flag | `QX1()` / `sf()` | "Voice mode is not available." |
| 2 | OAuth 로그인 | `xH()` + `c7()?.accessToken` | "Voice mode requires a Claude.ai account." |
| 3 | 환경 체크 | `_fz()` | WSL, remote, SSH 환경 제외 |
| 4 | 오디오 모듈 | `Ra6()` | 네이티브 audio-capture.node 로드 여부 |
| 5 | SoX 설치 | `wr("rec")` | "Install SoX manually for audio recording." |
| 6 | 마이크 권한 | `requestMicrophonePermission()` | OS별 설정 안내 |

### Voice Stream (STT) 동작 방식

```
[마이크 입력] → [네이티브 audio-capture.node 또는 SoX/arecord]
      │
      ▼ (PCM linear16, 16kHz, mono)
      │
[WebSocket 연결] → wss://{claude.ai_origin}/api/ws/speech_to_text/voice_stream
      │
      │  ← TranscriptText (실시간 중간 결과)
      │  ← TranscriptEndpoint (발화 종료)
      │  ← TranscriptError (오류)
      ▼
[UI에 텍스트 표시 → 입력창에 반영]
```

**WebSocket 파라미터:**
- `encoding`: linear16
- `sample_rate`: 16000
- `channels`: 1
- `endpointing_ms`: 300 (발화 끝 감지)
- `utterance_end_ms`: 1000
- `language`: en (기본값, 변경 가능)
- `keyterms`: 커스텀 키워드 (선택)

**KeepAlive**: 8초 간격으로 `{ type: "KeepAlive" }` 전송

### 오디오 캡처 우선순위

| 플랫폼 | 1순위 | 2순위 |
|--------|-------|-------|
| macOS | 네이티브 `audio-capture.node` | SoX (`rec`) |
| Linux | 네이티브 `audio-capture.node` | ALSA (`arecord`) → SoX (`rec`) |
| Windows | 네이티브 `audio-capture.node` | 미지원 (네이티브 필수) |

네이티브 모듈 경로: `{패키지}/audio-capture/{arch}-{platform}/audio-capture.node`
- npm 2.1.70 패키지에는 포함되지 않음 (별도 배포 또는 postinstall)

## Feature Flag 시스템

### `e8()` 함수 - 서버사이드 Flag 체크

```js
e8("tengu_sotto_voce", false)      // 간결 출력 모드
e8("tengu_bergotte_lantern", false) // 다듬어진 출력 스타일
```

- 첫 번째 인자: flag 이름 (`tengu_` 접두어)
- 두 번째 인자: 기본값 (서버 응답 없을 때)
- `tengu`는 Anthropic 내부의 Claude Code 프로젝트 코드네임

### 발견된 Feature Flag 목록

| Flag 이름 | 용도 |
|-----------|------|
| `tengu_sotto_voce` | 시스템 프롬프트에서 간결한 출력 스타일 활성화 |
| `tengu_bergotte_lantern` | 다듬어진(polished) 출력 스타일 활성화 |
| `tengu_voice_toggled` | voice 토글 시 텔레메트리 이벤트명 |
| `allow_remote_control` | 정책(policy) 기반 remote-control 허용 |

### 롤링 배포 흐름

```
┌─────────────────────────────────┐
│     npm publish (cli.js)        │
│   모든 기능 코드가 번들에 포함      │
│   voice, remote-control 등      │
└──────────────┬──────────────────┘
               │
               │  npm install (모든 사용자 동일 바이너리)
               ▼
┌─────────────────────────────────┐
│     CLI 시작 / 로그인 시          │
│     Anthropic API 서버에 요청     │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│   서버가 사용자/계정/조직별로       │
│   feature flags 응답             │
│                                 │
│   { tengu_voice: true/false,    │
│     tengu_sotto_voce: true, ... │
│     allow_remote_control: true }│
└──────────────┬──────────────────┘
               │
        ┌──────┴──────┐
        │             │
     flag=true     flag=false
        │             │
        ▼             ▼
   기능 활성화     기능 숨김/비활성
   (/voice 표시)  (/voice 미표시)
```

### Policy 시스템과의 관계

조직 관리자가 설정하는 **정책(Policy)**도 별도 게이트로 작동한다:

```js
// remote-control 예시
const { waitForPolicyLimitsToLoad, isPolicyAllowed } = await import(...);
await waitForPolicyLimitsToLoad();
if (!isPolicyAllowed("allow_remote_control"))
  return "Remote Control is disabled by your organization's policy.";

// feature flag는 policy 통과 후 별도 체크
if (!await jo6())
  return "...Wait for the feature flag rollout.";
```

즉, **Policy** (조직 수준 허용/차단)와 **Feature Flag** (Anthropic의 점진적 롤아웃)는 독립된 두 개의 게이트다.

## 왜 이런 구조인가

| 이점 | 설명 |
|------|------|
| **점진적 롤아웃** | 전체 사용자가 아닌 일부에게만 먼저 배포하여 안정성 확보 |
| **즉시 롤백** | 문제 발생 시 서버 flag만 꺼면 됨. npm 재배포 불필요 |
| **A/B 테스트** | `tengu_sotto_voce` vs `tengu_bergotte_lantern` 등 출력 스타일 비교 가능 |
| **배포 단순화** | npm에는 하나의 번들만 배포. 버전 파편화 없음 |
| **조직별 제어** | Policy 시스템으로 기업 고객이 특정 기능 차단 가능 |

## 2.1.38 → 2.1.70 변경점 (Voice 관련)

| 항목 | 2.1.38 | 2.1.70 |
|------|--------|--------|
| Voice 코드 존재 | 부분적 | 전체 구현 포함 |
| WebSocket STT | 미확인 | `voice_stream` 전체 구현 |
| 네이티브 오디오 모듈 | 미확인 | `audio-capture.node` 로드 로직 |
| Remote Control | 기본 구조 | feature flag + policy 이중 게이트 |
| Feature flag 패턴 | `e8("tengu_*")` 존재 | 동일 + 더 많은 flag 사용 |
