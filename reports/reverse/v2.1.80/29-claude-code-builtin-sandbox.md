# Claude Code CLI 내장 샌드박스 기술 분석 리포트

**분석 대상 버전**: npm @anthropic-ai/claude-code v2.1.80, v2.1.70  
**분석 일자**: 2026-03-20  
**분석 방식**: cli.js (minified) + native 바이너리 추출 코드 + package.json 역공학

---

## 요약

Claude Code CLI는 **OS 레벨 격리 기술(seccomp + bubblewrap)을 사용한 진정한 샌드박스** 시스템을 내장하고 있다. 
단순 권한 체크(HITL soft control)가 아니라 Linux에서는 seccomp + bubblewrap, macOS에서는 native sandbox를 통해 
도구 실행을 격리한다. 이는 시스템 보안을 위한 핵심 기능이다.

---

## 1. 샌드박스 아키텍처 개요

### 1.1 플랫폼별 격리 메커니즘

| 플랫폼 | 격리 기술 | 상태 | 설명 |
|--------|---------|------|------|
| **Linux** | seccomp + bubblewrap (bwrap) | 활성 | OS 레벨 프로세스 격리 + 시스템콜 제어 |
| **macOS** | Native sandbox | 활성 | Xcode sandbox 또는 macOS native API 사용 |
| **Windows** | (미확인) | - | 별도 구현 또는 제한 모드 |

### 1.2 3계층 접근 제어

```
[사용자 정의]  <- 설정에서 allowWrite, denyRead 등 구성
       |
       v
[Tool 권한 규칙] <- Edit(...) allow, Read(...) deny 동적 설정
       |
       v
[OS 격리 경계]  <- seccomp 필터 + bwrap 마운트 포인트 강제
```

---

## 2. 샌드박스 설정 스키마

### 2.1 Zod 스키마 정의 (cli.js 분석)

위치: `cli.js` pos ~896279

```javascript
// 추출된 스키마 구조 (재구성)
const SandboxFilesystemConfig = {
  allowWrite: z.array(z.string()).optional()
    .describe("Additional paths to allow writing within the sandbox. 
              Merged with paths from Edit(...) allow permission rules."),
  denyWrite: z.array(z.string()).optional()
    .describe("Additional paths to deny writing within the sandbox. 
              Merged with paths from Edit(...) deny permission rules."),
  denyRead: z.array(z.string()).optional()
    .describe("Additional paths to deny reading within the sandbox. 
              Merged with paths from Read(...) deny permission rules."),
  allowRead: z.array(z.string()).optional()
    .describe("Paths to re-allow reading within denyRead regions. 
              Takes precedence over denyRead for matching paths."),
  allowManagedReadPathsOnly: z.boolean().optional()
    .describe("When true (set in managed settings), 
              only allowRead paths from policySettings are used.")
}

// 네트워크 설정
const SandboxNetworkConfig = {
  allowUnixSockets: z.array(z.string()).optional()
    .describe("macOS only: Unix socket paths to allow. 
              Ignored on Linux (seccomp cannot filter by path)."),
  allowAllUnixSockets: z.boolean().optional()
    .describe("If true, allow all Unix sockets 
              (disables blocking on both platforms)."),
  allowLocalBinding: z.boolean().optional()
    .describe("Allow local TCP/UDP binding"),
  httpProxyPort: z.number().optional(),
  socksProxyPort: z.number().optional()
}
```

### 2.2 설정에서 인식되는 샌드박스 옵션

위치: `cli.js` pos ~930226

```
sandbox: Set([
  "network",                      // 네트워크 격리 설정
  "ignoreViolations",             // 위반 무시 규칙
  "excludedCommands",             // 샌드박스 우회 도구 목록
  "autoAllowBashIfSandboxed",     // bash 자동 허용
  "enableWeakerNestedSandbox",    // 약한 중첩 격리 (성능 vs 보안)
  "enableWeakerNetworkIsolation"  // 약한 네트워크 격리 (macOS trustd)
])
```

---

## 3. Linux 샌드박스: seccomp + bubblewrap

### 3.1 bubblewrap + seccomp 검증 로직

위치: `cli.js` pos ~4946563

Linux 샌드박스는 두 가지 핵심 도구의 존재를 검증한다:

1. **bubblewrap (bwrap)**: 프로세스 namespace 격리
   - 독립적인 파일시스템 마운트 포인트 생성
   - 네트워크 namespace 격리
   - PID namespace 격리

2. **seccomp**: 커널 시스템콜 필터링
   - Unix socket 생성 차단 (`socket(AF_UNIX, ...)`)
   - 불필요한 시스템콜 제한

3. **socat**: Unix socket <-> TCP 브리징
   - 격리된 프로세스가 호스트 프록시와 통신 가능

### 3.2 Seccomp 필터 세부사항

#### 지원 아키텍처

native 바이너리에서 추출:

- **x64 (x86_64)**: 완전 지원
- **arm64 (aarch64)**: 완전 지원
- **32-bit x86 (ia32)**: 미지원
  - 이유: `socketcall()` 시스템콜로 bypass 가능
  - 현재 필터는 `socket(AF_UNIX, ...)`만 차단
  - 32-bit에서는 `socketcall()`로 동일 기능 수행 가능

#### BPF 필터 파일 위치

vendor 패키지에서 제공되는 사전 컴파일 BPF 필터:

```
vendor/seccomp/{x64,arm64}/
  ├── unix-block.bpf          # eBPF 필터 규칙
  └── apply-seccomp           # seccomp 적용 바이너리
```

검색 순서:
1. 명시적 경로 (`--bpf-path`)
2. 현재 바이너리 상대 경로
3. 전역 npm 설치 경로 (`/usr/lib`, `/opt/homebrew`)
4. 사용자 npm 경로 (`~/.npm`)

#### seccomp 필터 적용

프로세스 실행 시:

```
도구 실행 요청
    |
    v
BPF 필터 파일 찾기 (find_bpf_filter)
    |
    v
apply-seccomp 바이너리 찾기 (find_apply_seccomp)
    |
    v
seccomp 적용 성공 -> 도구 격리 실행
    |
    v
seccomp 파일 없음 -> 경고 + 제한 모드
```

### 3.3 Bubblewrap 마운트 포인트 관리

bwrap은 도구 실행 시 임시 마운트 포인트를 생성하고,
프로세스 종료 후 자동으로 정리한다:

```
프로세스 시작
    |
    v
bwrap으로 격리된 환경 생성 (마운트 포인트 생성)
    |
    v
도구 실행
    |
    v
프로세스 종료 -> 마운트 포인트 정리
    |
    v
cleanup_bwrap_mount_points() 호출:
  - 빈 파일 삭제
  - 빈 디렉토리 제거
  - Set에서 추적 삭제
```

**설정 신호**: 환경변수 `SANDBOX_RUNTIME=1`

### 3.4 HTTP/SOCKS 프록시 브릿징 (Linux)

bwrap 격리 환경 내 도구가 호스트 프록시에 접근하기 위해
socat을 사용한 Unix socket 브리징:

```
[격리된 도구]
    |
    | HTTP_PROXY=unix:/tmp/claude-http-XXXX.sock
    |
    v
[socat Unix socket]
    |
    | TCP 브리징
    |
    v
[호스트 HTTP 프록시 localhost:3128]
```

**특징**:
- Unix socket 기반: 파일 시스템 보안 활용
- 로컬호스트 우회: NO_PROXY 설정으로 로컬 서버 직접 접근
- Keepalive: 연결 안정성 (keepidle=10, keepintvl=5, keepcnt=3)

---

## 4. macOS 샌드박스

### 4.1 enableWeakerNetworkIsolation 옵션

macOS 전용 보안 옵션:

```javascript
enableWeakerNetworkIsolation: boolean
  "macOS only: Allow access to com.apple.trustd.agent in the sandbox. 
   Needed for Go-based CLI tools (gh, gcloud, terraform, etc.) to 
   verify TLS certificates when using httpProxyPort with a MITM proxy 
   and custom CA. 
   **Reduces security** — opens a potential downgrade vector."
```

**상황**:
1. Go 기반 도구 (gh, gcloud, terraform)
2. MITM 프록시 + 커스텀 CA 사용
3. TLS 인증서 검증 필요

**해결책**:
- `com.apple.trustd.agent` 접근 허용
- macOS의 인증서 저장소와 통신 가능

**비용**:
- 샌드박스 격리 약화
- MITM 공격 가능성 증가

**기본값**: false (보안 우선)

### 4.2 macOS Native Sandbox

- XNU 커널의 Sandbox.framework 사용
- 중첩 샌드박스 지원 (`enableWeakerNestedSandbox`)
- 성능 vs 보안 트레이드오프

---

## 5. 환경 변수를 통한 격리 신호

### 5.1 SANDBOX_RUNTIME=1

도구 프로세스가 샌드박스 내에서 실행되고 있음을 나타낸다.

**도구의 대응**:
- 네트워크 요청을 프록시로 라우팅
- 파일시스템 접근 제한 존중
- 권한 필요 작업 회피

### 5.2 TMPDIR 격리

```
TMPDIR=/tmp/claude        # 샌드박스 내 임시 디렉토리
CLAUDE_TMPDIR=...         # 설정으로 커스터마이즈 가능
```

### 5.3 NO_PROXY (로컬호스트 우회)

```
NO_PROXY=localhost,127.0.0.1,::1,*.local,.local,
         169.254.0.0/16,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
```

**의도**:
- 로컬 서버 직접 접근 가능
- 호스트의 로컬 개발 서버 활용 가능

---

## 6. 도구 실행 제어

### 6.1 autoAllowBashIfSandboxed

이미 샌드박스 내에 있는 경우 bash 명령 자동 허용:

```
도구 실행 요청 (bash)
    |
    v
현재 환경이 SANDBOX_RUNTIME=1인가?
    |
    YES -> 자동 허용 (중복 격리 회피)
    NO -> 새 샌드박스 생성
```

**목적**: 성능 최적화 (중첩 샌드박스 방지)

### 6.2 excludedCommands

특정 명령어는 샌드박스 우회:

```javascript
excludedCommands: ["docker", "kubectl", ...]
```

**사유**:
- 도구 자체가 컨테이너 사용
- 샌드박스 호환성 부족
- 특정 시스템콜 필요

### 6.3 allowUnsandboxedCommands (기본: true)

```javascript
allowUnsandboxedCommands: z.boolean()
  .describe("Allow commands to run outside the sandbox via 
            dangerouslyDisableSandbox parameter. 
            When false, the dangerouslyDisableSandbox parameter 
            is completely ignored and all commands must run sandboxed.")
```

**정책**:
- true (기본): 도구는 `dangerouslyDisableSandbox` 사용 가능
- false: 모든 도구 강제 샌드박스 (관리된 환경)

---

## 7. 컨테이너 환경 감지

### 7.1 Docker 감지

```
1. /.dockerenv 파일 존재 확인
   -> true: Docker 확실

2. /proc/self/cgroup에 "docker" 문자열
   -> true: Docker 또는 유사 격리
```

### 7.2 Container 환경 감지

```
/run/.containerenv 파일 확인
-> systemd-nspawn, podman 등
```

**영향**:
- 컨테이너 내에서 bwrap 재격리 불가
- Fallback 필요 (권한 기반 제어만)

---

## 8. 권한 병합 및 우선순위

### 8.1 경로 권한 우선순위

```
allowRead > denyRead
  (명시적 허용이 거부보다 우선)

사용자 설정 + Tool 규칙 병합
  (Edit(...) allow와 설정 allowWrite 병합)
```

### 8.2 Unix Socket 제어 (macOS)

```javascript
allowUnixSockets: ["/path/to/socket1", "/path/to/socket2"]
  // Linux seccomp은 경로 필터링 불가 (시스템콜 레벨)
  // macOS만 경로별 제어

allowAllUnixSockets: true
  // 모든 소켓 허용 (보안 약화)
```

---

## 9. 검증 및 디버그

### 9.1 요구사항 확인

**Linux**:
```
✓ bubblewrap (bwrap) 설치
✓ socat 설치
✓ seccomp BPF 필터 파일 존재
✓ apply-seccomp 바이너리 존재
```

실패 시: 경고 또는 에러로 보고

### 9.2 디버그 활성화

```bash
export SRT_DEBUG=1
# [SandboxDebug] 로그 출력
# - BPF 필터 파일 위치
# - seccomp 적용 결과
# - bwrap 마운트 포인트
# - 브리지 프로세스 상태
```

---

## 10. 결론 및 보안 평가

### 10.1 샌드박스 유형: Hard Sandbox

Claude Code CLI는 **OS 레벨 격리** 를 사용한다:

- ❌ 소프트 제어 (권한 체크만)
- ✅ **seccomp 필터** (커널 시스템콜 제한)
- ✅ **bubblewrap** (네임스페이스 격리)
- ✅ **Native sandbox** (macOS)

### 10.2 보안 게층

```
게층 4 [OS 격리]
  ├─ seccomp (시스템콜 제한)
  ├─ bwrap (namespace 격리)
  └─ macOS sandbox.framework
  
게층 3 [네트워크 격리]
  ├─ socat 브리징 (Unix socket)
  └─ HTTP/SOCKS 프록시 라우팅
  
게층 2 [도구 권한]
  ├─ Edit(...) 동적 allow/deny
  └─ Read(...) 동적 denyRead
  
게층 1 [정책 설정]
  ├─ allowWrite, denyRead
  └─ excludedCommands
```

### 10.3 제한사항

| 항목 | 제한 | 영향 |
|------|------|------|
| 아키텍처 | 32-bit x86 미지원 | 레거시 시스템 불가 |
| BPF 파일 | 사전 컴파일 필수 | 파일 누락 시 기능 저하 |
| macOS | trustd 격리 약화 | MITM 공격 위험 가능 |
| 컨테이너 | Docker 내 bwrap 실패 | 컨테이너 내 제한 모드 |

### 10.4 신뢰도

**높음**:
- Anthropic이 공식 제공하는 seccomp + bubblewrap
- `@anthropic-ai/sandbox-runtime` 패키지로 관리
- 네이티브 바이너리 지원 (컴파일된 BPF)
- 여러 보안 게층 조합

---

## 분석 소스

1. `/Users/jaesolshin/Documents/GitHub/analyze-cc-prompts/npm_2.1.80/cli.js` 
   - 크기: 12.8MB (minified)
   - 키워드 matches: sandbox=463, seccomp=56, bwrap=9

2. `/Users/jaesolshin/Documents/GitHub/analyze-cc-prompts/native/native_v2.1.29_extracted.js`
   - 크기: 12.9MB
   - 키워드 matches: sandbox=567, seccomp=109, bwrap=13

3. `/Users/jaesolshin/Documents/GitHub/analyze-cc-prompts/npm_2.1.80/package.json`
   - 의존성: 없음 (standalone bundle)
   - 옵션: @img/sharp (이미지 처리)

4. vendor/ 디렉토리:
   - tree-sitter-bash (코드 파싱)
   - ripgrep (파일 검색)
   - resvg.wasm (SVG 렌더링)
   - (seccomp 바이너리는 런타임에 로드)

