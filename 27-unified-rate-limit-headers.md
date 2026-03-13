# 27. Anthropic Unified Rate Limit 응답 헤더 분석

## 개요

Anthropic Messages API는 각 응답에 `anthropic-ratelimit-unified-*` 접두사를 가진 헤더를 포함한다. 이 헤더들은 현재 사용량과 남은 할당량을 실시간으로 알려주며, Claude Code가 스로틀링 없이 계속 실행 가능한지 판단하는 데 사용할 수 있다. 프록시를 통한 실제 캡처로 처음으로 이 헤더들의 전체 구조와 값을 확인했다.

---

## 1. 캡처 방법

기존 proxy.py는 응답 헤더를 일부만 포워딩하고 저장하지 않았다. 이번 세션에서 수정:

```python
# 수정 전: 헤더 저장 없음
res_path = dump_json(f"{ts}-res.json", {"status": ..., "events": events})

# 수정 후: 전체 헤더 저장
res_path = dump_json(f"{ts}-res.json", {
    "status": upstream_resp.status,
    "headers": dict(upstream_resp.headers),  # 추가
    "events": events,
})
```

또한 프록시 콘솔에서 rate limit 관련 헤더를 실시간으로 출력:

```python
limit_headers = {
    k: v for k, v in upstream_resp.headers.items()
    if any(kw in k.lower() for kw in ("ratelimit", "rate-limit", "limit", "usage", "retry"))
}
if limit_headers:
    pairs = ", ".join(f"{k}={v}" for k, v in limit_headers.items())
    print(f"[{ts}] LIMITS: {pairs}")
```

---

## 2. 헤더 전체 목록

실제 캡처에서 확인된 `anthropic-ratelimit-unified-*` 헤더 16종:

| 헤더 이름 | 예시 값 | 설명 |
|-----------|---------|------|
| `anthropic-ratelimit-unified-status` | `allowed` | 전체 통합 상태 |
| `anthropic-ratelimit-unified-reset` | `1773291600` | 바인딩 버킷의 리셋 시각 (Unix) |
| `anthropic-ratelimit-unified-representative-claim` | `five_hour` | 현재 바인딩(제한 기준) 버킷 |
| `anthropic-ratelimit-unified-fallback-percentage` | `0.5` | 한도 초과 시 허용 비율 |
| `anthropic-ratelimit-unified-overage-status` | `rejected` | 오버리지(초과 사용) 허용 여부 |
| `anthropic-ratelimit-unified-overage-disabled-reason` | `org_level_disabled` | 오버리지 비활성화 이유 |
| `anthropic-ratelimit-unified-5h-status` | `allowed` | 5시간 버킷 상태 |
| `anthropic-ratelimit-unified-5h-utilization` | `0.37` | 5시간 버킷 사용률 (0.0~1.0) |
| `anthropic-ratelimit-unified-5h-reset` | `1773291600` | 5시간 버킷 리셋 시각 (Unix) |
| `anthropic-ratelimit-unified-7d-status` | `allowed` | 7일 버킷 상태 |
| `anthropic-ratelimit-unified-7d-utilization` | `0.68` | 7일 버킷 사용률 |
| `anthropic-ratelimit-unified-7d-reset` | `1773374400` | 7일 버킷 리셋 시각 (Unix) |
| `anthropic-ratelimit-unified-7d_sonnet-status` | `allowed` | 7일 Sonnet 전용 버킷 상태 |
| `anthropic-ratelimit-unified-7d_sonnet-utilization` | `0.26` | 7일 Sonnet 전용 사용률 |
| `anthropic-ratelimit-unified-7d_sonnet-reset` | `1773399600` | 7일 Sonnet 버킷 리셋 시각 |

추가 헤더:

| 헤더 이름 | 예시 값 |
|-----------|---------|
| `anthropic-organization-id` | `84c5153a-d205-4085-8d27-4b1dd3d07776` |
| `request-id` | `req_011CYxbHNPKKpubbDGr1J5qz` |

---

## 3. 할당량 버킷 구조

Anthropic Unified Rate Limit은 **3개의 독립적인 시간 버킷**으로 구성된다:

```
+----------------------------------------------------------+
|              Unified Rate Limit Buckets                  |
+--------------+---------------+---------------------------+
|    5h 버킷   |   7d 버킷     |   7d_sonnet 버킷          |
|  (전체 모델) |  (전체 모델)  |  (Sonnet/Opus만 해당)     |
|              |               |                           |
|  5시간 윈도우|  7일 윈도우   |  7일 윈도우 (Sonnet 전용) |
|  고정 시작점 |  고정 시작점  |  별도 기준점              |
+--------------+---------------+---------------------------+
```

### 버킷별 리셋 윈도우 (실측값)

| 버킷 | 리셋 시각 (UTC) | 윈도우 시작 | 관찰 시각까지 남은 시간 |
|------|-----------------|-------------|------------------------|
| 5h | 2026-03-12 05:00 | 2026-03-12 00:00 | ~3분 (04:56에 캡처) |
| 7d | 2026-03-13 04:00 | 2026-03-06 04:00 | 23.1시간 |
| 7d_sonnet | 2026-03-13 11:00 | 2026-03-06 11:00 | 30.1시간 |

**5h 버킷은 5시간 고정 슬롯**으로 동작한다: 00:00~05:00 UTC, 05:00~10:00 UTC, ... 즉 sliding window가 아닌 **tumbling window**.

---

## 4. 실측 데이터: 사용률 변화

2026-03-12 UTC 04:56~05:04 세션에서 관찰된 값:

| 타임스탬프 | 모델 | tools | msgs | 5h util | 7d util | 7d_sonnet |
|-----------|------|-------|------|---------|---------|-----------|
| 04:56:26 | haiku | 0 | 1 | 0.37 | 0.68 | - |
| 04:56:36 | haiku | 101 | 1 | 0.37 | 0.68 | - |
| 04:56:49 | sonnet | 8 | 2 | 0.37 | 0.68 | 0.26 |
| 04:59:23 | sonnet | 8 | 4 | 0.38 | 0.68 | 0.26 |
| 04:59:37 | sonnet | 8 | 6 | 0.38 | 0.68 | 0.26 |
| 05:04:06 | sonnet | 8 | 8 | 0.01 | 0.68 | 0.26 |
| 05:04:07 | haiku | 101 | 3 | 0.01 | 0.68 | - |
| 05:04:08 | sonnet | 8 | 2 | 0.01 | 0.68 | 0.26 |
| 05:04:15 | sonnet | 8 | 4 | 0.01 | 0.68 | 0.26 |
| 05:04:18 | haiku | 101 | 5 | 0.01 | 0.68 | - |
| 05:04:20 | haiku | 101 | 7 | 0.01 | 0.68 | - |
| 05:04:28 | haiku | 101 | 9 | 0.01 | 0.68 | - |

### 주요 관찰사항

**[1] 5h utilization이 0.38 -> 0.01로 급락**

04:59~05:04 사이에 5h 버킷 리셋(05:00 UTC)이 발생했기 때문. 직전까지 `0.38`이었다가 리셋 후 새 윈도우에서 `0.01`로 떨어졌다. 이는 rate limit utilization이 **누적값이 아닌 현재 윈도우 내 사용량 비율**임을 확인해준다.

**[2] 7d utilization은 0.68로 고정**

이 세션의 API 호출량이 7일 버킷에 영향을 줄 만큼 크지 않아서 변화 없음. (세션 전체 ~12회 API 호출)

**[3] 7d_sonnet 헤더는 Sonnet 요청에만 등장**

haiku 모델 응답에는 `7d_sonnet-*` 헤더가 없음. Sonnet/Opus를 사용하는 요청에서만 Sonnet 전용 버킷 헤더를 반환한다.

---

## 5. 헤더 의미 해석

### `representative-claim: five_hour`

현재 **바인딩 버킷(binding bucket)**이 `five_hour`임을 나타낸다. 3개 버킷 중 가장 엄격하게 제한하는 버킷이 바인딩 버킷이 된다. 이 값이 `five_hour`이면 5h 버킷이 스로틀링을 결정하는 기준이다.

가능한 값: `five_hour`, `seven_day`, `seven_day_sonnet`

### `fallback-percentage: 0.5`

관찰된 값은 `0.5`이나, 정확한 의미는 미확인. 헤더 이름과 값만 기록.

### `overage-status: rejected` + `overage-disabled-reason: org_level_disabled`

이 조직은 **초과 사용(overage)이 비활성화**되어 있다. 한도를 초과하면 추가 비용을 내고 계속 사용하는 옵션이 없다. `org_level_disabled`는 계정/조직 설정에서 비활성화되었음을 의미하며, Anthropic 관리 콘솔에서 설정 가능한 것으로 추정된다.

### `status` 값 체계

각 버킷의 `status` 및 통합 `status`가 가질 수 있는 값:

| 값 | 의미 |
|----|------|
| `allowed` | 정상 허용 |
| `throttled` | 일부 요청 지연/제한 중 |
| `blocked` | 한도 초과로 차단 |

---

## 6. 버킷별 리셋 타이밍

### 5h 버킷: Tumbling Window (고정 슬롯)

```
UTC 기준 5시간 슬롯:
  00:00 ~ 05:00
  05:00 ~ 10:00
  10:00 ~ 15:00
  15:00 ~ 20:00
  20:00 ~ 00:00(다음날)
```

`5h-reset` 타임스탬프가 항상 이 경계에 정렬되어 있음을 실측으로 확인. Sliding window가 아니므로 슬롯 교체 직후 대량 사용이 가능하다.

### 7d 버킷: 고정 요일 기준

실측 리셋: 2026-03-13 04:00 UTC -> 시작: 2026-03-06 04:00 UTC. **7일 고정 윈도우**. 매주 특정 요일/시각에 리셋된다.

### 7d_sonnet 버킷: 7d와 별도 기준

실측 리셋: 2026-03-13 11:00 UTC -> 시작: 2026-03-06 11:00 UTC. `7d`와 7시간 차이가 나는 별도 기준점을 가진다. Sonnet/Opus 사용량만 별도로 추적한다.

---

## 7. `7d_sonnet` 헤더 출현 조건

```
haiku (tools=0, msgs=1):    5h [O]  7d [O]  7d_sonnet [X]
haiku (tools=101, msgs=1):  5h [O]  7d [O]  7d_sonnet [X]
sonnet (tools=8, msgs=2):   5h [O]  7d [O]  7d_sonnet [O]
```

**결론**: `7d_sonnet-*` 헤더는 요청 모델이 Sonnet/Opus 계열인 경우에만 반환된다. Haiku 요청에서는 이 헤더가 없으므로, Haiku는 7d_sonnet 버킷을 소모하지 않는다.

이는 Claude Code Pro/Max 플랜의 가격 구조와 일치한다: Sonnet/Opus는 별도 사용량 추적, Haiku는 상대적으로 자유롭게 사용 가능.

---

## 8. 실제 응답 헤더 전문 (첫 번째 캡처)

```json
{
  "Date": "Thu, 12 Mar 2026 04:56:27 GMT",
  "Content-Type": "application/json",
  "anthropic-ratelimit-unified-status": "allowed",
  "anthropic-ratelimit-unified-5h-status": "allowed",
  "anthropic-ratelimit-unified-5h-reset": "1773291600",
  "anthropic-ratelimit-unified-5h-utilization": "0.37",
  "anthropic-ratelimit-unified-7d-status": "allowed",
  "anthropic-ratelimit-unified-7d-reset": "1773374400",
  "anthropic-ratelimit-unified-7d-utilization": "0.68",
  "anthropic-ratelimit-unified-representative-claim": "five_hour",
  "anthropic-ratelimit-unified-fallback-percentage": "0.5",
  "anthropic-ratelimit-unified-reset": "1773291600",
  "anthropic-ratelimit-unified-overage-disabled-reason": "org_level_disabled",
  "anthropic-ratelimit-unified-overage-status": "rejected",
  "request-id": "req_011CYxbHNPKKpubbDGr1J5qz",
  "anthropic-organization-id": "84c5153a-d205-4085-8d27-4b1dd3d07776",
  "x-envoy-upstream-service-time": "878",
  "Server": "cloudflare"
}
```

---

## 9. 프록시 없이 rate limit 정보를 얻는 방법

### 9.1 macOS Keychain에서 티어 정보 조회

Claude Code OAuth 자격증명은 macOS Keychain에 저장된다. `subscriptionType`과 `rateLimitTier`는 API 호출 없이 읽을 수 있다:

```bash
security find-generic-password -s "Claude Code-credentials" -w | \
  python3 -c "
import json, sys
d = json.load(sys.stdin)['claudeAiOauth']
print('subscriptionType:', d['subscriptionType'])
print('rateLimitTier:', d['rateLimitTier'])
"
```

실측값:
```
subscriptionType: max
rateLimitTier: default_claude_max_20x
```

Keychain 항목명은 `Claude Code-credentials` 또는 `Claude Code-credentials-<uuid>` 형태로 여러 개 존재할 수 있다 (로그인 계정별).

### 9.2 OAuth accessToken으로 직접 API 호출 시도 (실패)

Keychain에서 `accessToken`을 추출하여 `Authorization: Bearer` 헤더로 직접 API를 호출하면 **401** 반환:

```json
{
  "type": "error",
  "error": {
    "type": "authentication_error",
    "message": "OAuth authentication is currently not supported."
  }
}
```

`api.anthropic.com/v1/messages`는 OAuth Bearer 토큰을 직접 받지 않는다.

### 9.3 Claude Code의 실제 인증 방식 (미확인)

Claude Code가 OAuth 토큰을 어떻게 API 인증에 활용하는지는 확인되지 않았다. 가능한 경로:

| 가설 | 설명 |
|------|------|
| 토큰 교환 | OAuth 토큰 -> 별도 엔드포인트에서 임시 `x-api-key` 발급 후 사용 |
| 전용 경로 | `claude.ai/api/...` 경유, 내부에서 Anthropic API로 포워딩 |

프록시 캡처에서 req.json은 바디만 저장했고 요청 헤더는 캡처하지 않아 실제 auth 헤더 확인 불가. proxy.py에서 요청 헤더도 저장하도록 수정하면 확인 가능.

### 9.4 결론

| 정보 | 프록시 없이 가능 | 방법 |
|------|-----------------|------|
| 구독 타입, 티어 | [O] | macOS Keychain 직접 읽기 |
| 실시간 5h/7d utilization | [X] | API 응답 헤더에만 존재, OAuth로 직접 호출 불가 |

**실시간 utilization은 프록시를 통해서만 캡처 가능하다.**

---

## 10. Claude Code에서의 활용

Claude Code는 이 헤더들을 활용하여 다음을 수행할 수 있다:

1. **자동 슬로다운**: `5h-utilization > 0.8` 이면 요청 간격 자동 조절
2. **모델 다운그레이드**: Sonnet 버킷 포화 시 Haiku로 자동 전환 (Haiku는 7d_sonnet 미소모)
3. **사전 경고**: utilization이 임계값에 가까워지면 사용자에게 알림
4. **리셋 대기**: `representative-claim`의 리셋 시각까지 대기 후 재시도

현재 Claude Code 소스(cli.js)에서 이 헤더를 처리하는 로직이 있는지는 추가 분석 필요.

---

## 11. 주요 발견 요약

1. **3개 독립 버킷** -- 5h(전체), 7d(전체), 7d_sonnet(Sonnet/Opus 전용). 각각 별도 윈도우와 리셋 기준 보유.

2. **Tumbling Window** -- 5h 버킷은 슬라이딩이 아닌 고정 슬롯(00~05, 05~10, ...). 슬롯 직후 대량 사용 가능.

3. **7d_sonnet은 Sonnet 요청에만 노출** -- Haiku는 이 버킷을 소모하지 않으며 헤더도 반환되지 않음.

4. **fallback-percentage: 0.5** -- 관찰값 0.5. 정확한 의미 미확인.

5. **overage 비활성화** -- `org_level_disabled`로 초과 사용 불가. 한도 초과 = 즉시 거절.

6. **representative-claim = 바인딩 버킷** -- 3개 버킷 중 가장 엄격한 버킷이 스로틀링 기준이 됨.

7. **실시간 추적 가능** -- 각 API 응답마다 헤더가 갱신되므로 세션 내 실시간 사용량 모니터링 가능.

---

## 12. 독립 rate limit 체커 구현 (ratelimit.py)

### 배경

기존 proxy.py를 항상 켜두지 않고, 필요할 때만 rate limit 헤더를 확인하는 독립 스크립트를 구현했다.

### 구현

`proxy/ratelimit.py`: aiohttp 미니 프록시(port 8083) + `claude -p` subprocess 자동 실행 후 통합 rate limit 헤더 테이블 출력.

### 구현 과정에서 발견한 사항

**[1] `claude`는 shell function이다**

`~/.oh-my-zsh/custom/aliases.zsh`에 정의된 shell function으로, 내부에서 다음을 수행한다:

```bash
env -u ANTHROPIC_BASE_URL -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_MODEL command claude "${args[@]}"
```

`ANTHROPIC_BASE_URL`을 unset하므로 프록시 경유가 불가능하다. 실제 바이너리를 직접 호출해야 한다:

```python
claude_bin = os.path.expanduser("~/.nvm/versions/node/v20.18.1/bin/claude")
```

**[2] `ANTHROPIC_API_KEY`를 unset해야 OAuth가 사용된다**

부모 프로세스(Claude Code 세션) 환경에 `ANTHROPIC_API_KEY`가 있으면, subprocess가 이 값을 `x-api-key` 헤더로 전송한다. 이 API key는 pay-as-you-go 크레딧이 없는 키였기 때문에 400 에러 발생.

```python
for key in ("CLAUDECODE", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"):
    env.pop(key, None)
```

제거하면 `CLAUDE_CONFIG_DIR`의 OAuth 토큰(`Authorization: Bearer sk-ant-oat01-...`)을 사용하여 정상 인증된다.

**[3] `CLAUDECODE` 환경변수 제거 필요**

Claude Code 세션 내에서 subprocess로 claude를 실행하면 중첩 세션 에러가 발생한다:

```
Error: Claude Code cannot be launched inside another Claude Code session.
```

`CLAUDECODE` 환경변수를 unset하면 우회 가능하다.

**[4] 매 fresh session마다 CLAUDE.md가 cache_write된다**

`-p` 헤드리스 모드는 `CLAUDE_CONFIG_DIR`의 CLAUDE.md를 시스템 프롬프트로 주입한다. OMC 시스템 프롬프트가 크기 때문에 매 호출마다 ~62k tokens cache_write 발생.

| 호출 타입 | input | output | cache_write | cache_read |
|-----------|-------|--------|-------------|------------|
| fresh -p  | ~10   | ~100   | ~62,000     | 0          |

CLAUDE.md를 제거하려면 인증 정보도 함께 없어지므로 현실적으로 불가능하다.

### 실측 출력 예시

```
ok

tokens — input: 10,  output: 85,  cache_write: 62909
┌─ Anthropic Unified Rate Limit ──────────────────────────────────┐
│ representative-claim : five_hour                               │
│                                                                 │
│ 5h       │ allowed   │ util: 58%    │ reset: 10:00Z             │
│ 7d       │ allowed   │ util: 9%     │ reset: 20 Mar 04:00Z      │
│                                                                 │
│ overage: rejected (org_level_disabled)                          │
│ fallback: available  (0.5%)                                     │
└─────────────────────────────────────────────────────────────────┘
```

### 사용 빈도 권장사항

| 빈도 | 평가 |
|------|------|
| 1회/시간 이하 | 안전 |
| 수분 간격 반복 | cache_write 누적으로 5h 버킷 소모 |
| 여러 유저가 공유 계정으로 실행 | 위험 — 각 유저 본인 계정(CLAUDE_CONFIG_DIR)으로 실행해야 함 |

---

## 관련 문서

- [20-live-api-capture-via-proxy.md](20-live-api-capture-via-proxy.md) -- 프록시 구조 및 API 요청 분석
- [21-billing-and-auth-management.md](21-billing-and-auth-management.md) -- 빌링 헤더 및 인증 분석
- [proxy/proxy.py](proxy/proxy.py) -- 헤더 캡처 코드
- [proxy/analyze.py](proxy/analyze.py) -- message.html 뷰어 (rate limit 헤더 시각화 포함)
