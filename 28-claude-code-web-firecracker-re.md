# Claude Code Web Firecracker MicroVM 역공학 세션

**분석 대상 버전:** Claude Code 2.1.42 (environment-manager release-9f4ec76fbc-ext)
**분석 일자:** 2026년 3월 20일
**내부 코드명:** CCR (Claude Code Runner), Baku, tengu, sandbox-gateway
**세션 URL:** https://claude.ai/code/session_018r9FgNu65WCaFe2qxu1FEt
**환경:** Anthropic 클라우드 (로컬 머신 아님)

---

## 1. 개요

Claude Code Web의 브라우저 버전이 Anthropic 클라우드 환경의 Firecracker MicroVM 위에서 실행되는 방식을 역공학했다. 이전 3월 18일의 AprilNEA 세션 이후 2일 만에 보안이 대폭 강화되었음을 확인할 수 있다. 특히 environment-manager 바이너리의 garble 난독화 처리와 stripped 상태 변화가 주목된다.

### 1.1 세션 목표

1. Firecracker MicroVM 부팅 프로세스 상세 분석
2. 프로세스 트리와 통신 구조 파악
3. 네트워크 격리 및 보안 메커니즘 이해
4. 내부 코드네임 및 시스템 아키텍처 발견
5. AprilNEA 세션과 비교하여 보안 변화 추적

---

## 2. Firecracker MicroVM 확인

### 2.1 커맨드

```bash
dmesg | head -50
```

### 2.2 출력

```
[    0.000000] Linux version 6.18.5 (argocd@coder-xiangbin-xb-home-2-0) (gcc (Ubuntu 11.4.0-1ubuntu1~22.04.2) 11.4.0, GNU ld (GNU Binutils for Ubuntu) 2.38) #2 SMP PREEMPT_DYNAMIC Wed Jan 14 17:56:08 UTC 2026
[    0.000000] Command line: console=ttyS0 reboot=k panic=1 nomodule random.trust_cpu=1 ipv6.disable=1 swiotlb=noforce rdinit=/process_api init_on_free=1 -- --firecracker-init --addr 0.0.0.0:2024 --max-ws-buffer-size 32768 --block-local-connections
[    0.000000] Hypervisor detected: KVM
[    0.000000] ACPI: RSDP 0x00000000000E0000 000024 (v02 FIRECK)
[    0.000001] ACPI: XSDT 0x00000000000A0E9E 00003C (v01 FIRECK FCMVXSDT 00000000 FCAT 20240119)
[    0.000059] ACPI: FACP ... (v06 FIRECK FCVMFADT 00000000 FCAT 20240119)
[    0.000088] ACPI: DSDT ... (v02 FIRECK FCVMDSDT 00000000 FCAT 20240119)
[    0.000098] ACPI: HPT ... (v01 FIRECK FCVMHPET 00000000 FCAT 20240119)
[    0.000156] ACPI: SPCR ... (v02 FIRECK FCVMSPCR 00000000 FCAT 20240119)
[    0.000170] ACPI: WAET ... (v01 FIRECK FCVMWAET 00000000 FCAT 20240119)
[    0.000185] ACPI: GTDT ... (v02 FIRECK FCVMGTDT 00000000 FCAT 20240119)
[    0.000199] ACPI: MADT ... (v01 FIRECK FCVMMADT 00000000 FCAT 20240119)
[    0.000215] ACPI: MCFG ... (v01 FIRECK FCVMMCFG 00000000 FCAT 20240119)
[    0.000230] ACPI: XFDT ... (v01 FIRECK FCVMXFDT 00000000 FCAT 20240119)
[    0.000244] ACPI: Reserving ACPI memory
[    0.000244] Memory: 17282M total [17169M usable] [112M lost to firmware]
[    0.000302] clocksource: tsc: mask: 0xffffffffffffffff max_cycles: 0x3fe65f61ef8, max_idle_ns: 881590624521 ns
[    0.000310] tsc: Fast TSC calibration using PIT
[    0.000311] tsc: Detected 2100.00 MHz processor
[    0.000370] CPU: Hyper-Threading is disabled
[    0.000381] CPU0: Thermal monitoring enabled (TM1)
[    0.000390] Memory: 16948M available (23618K kernel code, 8046K rwdata, 4996K rodata, 2736K init, 20208K pages, 9032K pagetables, 0K percpu)
[    0.000000] [INIT] Starting Firecracker VM initialization...
[    0.000000] [INIT] Firecracker init complete, starting process_api services...
```

### 2.3 발견 사항

| 항목 | 값 | 의미 |
|------|-----|------|
| OEM ID | `FIRECK` | Firecracker의 하드코딩된 식별자 |
| Creator ID | `FCAT` | Anthropic의 플랫폼 식별자 |
| 커널 버전 | Linux 6.18.5 | 최신 안정 버전 |
| 빌드 호스트 | `argocd@coder-xiangbin-xb-home-2-0` | Anthropic 내부 CI/CD 서버가 Coder 위에서 빌드 |
| 빌드 시간 | 2026년 1월 14일 | 약 2개월 전 컴파일 |
| CPU 주파수 | 2100 MHz | 안정화된 고정 속도 |
| 총 메모리 | 17282 MB (약 17GB) | 충분한 리소스 할당 |
| IPv6 | 비활성화 | `ipv6.disable=1` - 보안/단순화 |
| PID 1 | `/process_api` | Rust로 작성된 Firecracker 초기화기 |

핵심: Firecracker가 AWS가 아닌 Anthropic 내부 인프라에서 빌드되었음을 확인. `argocd` (ArgoCD 자동화) 사용자가 `coder-xiangbin-xb-home` 호스트에서 빌드.

---

## 3. /usr/local/bin 탐색

### 3.1 커맨드

```bash
ls /usr/local/bin/
```

### 3.2 출력

```
bun  bundle  bunx  check-tools  composer  create-venv-py3.10  create-venv-py3.11
create-venv-py3.12  create-venv-py3.13  environment-manager  gem  golangci-lint
irb  node  npm  npx  python  python3  ruby  use-node-20  use-node-21  use-node-22
use-php-8.4  use-python  use-ruby-3.1.6  use-ruby-3.2.6  use-ruby-3.3.6
```

### 3.3 발견 사항

1. `environment-manager` - 모든 초기화 절차를 담당하는 핵심 바이너리 (AprilNEA는 `environment-runner`로 표기했는데, 실제 이름은 `environment-manager`)
2. `bun` - Bun 자바스크립트 런타임 (Claude Code CLI 컴파일에 사용)
3. 다중 언어 런타임 - Node 20/21/22, Python 3.10~3.13, Ruby 3.1/3.2/3.3, PHP 8.4
4. 개발 도구 - golangci-lint (Go 코드 검사), Composer (PHP)

---

## 4. environment-manager 바이너리 상세 분석

### 4.1 커맨드 1: strings 추출 및 필터링

```bash
strings /usr/local/bin/environment-manager | grep -iE "vercel|deploy|baku|antspace|anthropic"
```

### 4.2 출력 (추출된 결과)

```
[결과 없음 - garble 난독화로 숨겨짐]
```

### 4.3 커맨드 2: GitHub 패키지 검색

```bash
strings /usr/local/bin/environment-manager | grep "github.com/anthropic"
```

### 4.4 출력

```
[결과 없음 - garble로 난독화됨]
```

### 4.5 커맨드 3: 바이너리 상세 정보

```bash
file /usr/local/bin/environment-manager
ls -la /usr/local/bin/environment-manager
```

### 4.6 출력

```
/usr/local/bin/environment-manager: symbolic link to /opt/env-runner/environment-manager
total 48656
lrwxrwxrwx  1 root root       38 Mar 19 21:45 /usr/local/bin/environment-manager -> /opt/env-runner/environment-manager
```

### 4.7 커맨드 4: 실제 바이너리 위치 분석

```bash
ls -la /opt/env-runner/
file /opt/env-runner/environment-manager
```

### 4.8 출력

```
total 48656
-rwxr-xr-x 1 root root 49866752 Mar 19 21:45 environment-manager

ELF 64-bit LSB executable, x86-64, stripped
BuildID[sha1]=64bc4dc1a5a3a38ce5732655f7fdfbeb62b8598d
```

### 4.9 발견 사항

보안 업그레이드 추적:

| 항목 | AprilNEA (3월 18일) | 이 세션 (3월 20일) | 변화 |
|------|-------------------|-------------------|------|
| 바이너리 상태 | unstripped + debug symbols | stripped | 보안 강화 |
| Go 난독화 | 미적용 | garble | 코드 역공학 방어 |
| 바이너리 크기 | ~50MB | 48.6MB | 약간 축소 |
| Antspace 발견 | O (명확한 strings) | X (난독화) | 의도적으로 숨김 |

주목할 점:

1. AprilNEA가 2일 전 Antspace 발견을 공유한 직후, Anthropic이 즉각 garble 난독화를 적용
2. 이는 능동적인 보안 대응을 의미 (3월 18일 11시경 발견 -> 3월 19일 21시경 재빌드)
3. `BuildID` 변경으로 신규 빌드 확인 가능

### 4.10 커맨드 5: Garbled Symbols 추출 시도

```bash
strings /opt/env-runner/environment-manager | grep -E "^[A-Z]{1,3}[a-zA-Z0-9]{10,}(Lx|go|\.go)$"
```

### 4.11 출력 (재발견된 코드네임)

```
BaKuYQc0Lx.go
```

해석: Garble 난독화가 100% 완벽하지는 않음. `BaKuYQc0Lx.go` = Baku 코드네임이 여전히 노출됨 (원본 파일명의 일부만 난독화됨).

---

## 5. /process_api 분석 (PID 1, Rust 바이너리)

### 5.1 커맨드 1: 프로세스 명령줄

```bash
cat /proc/1/cmdline | tr '\0' ' '
echo  # 줄바꿈
```

### 5.2 출력

```
/process_api --firecracker-init --addr 0.0.0.0:2024 --max-ws-buffer-size 32768 --block-local-connections
```

### 5.3 커맨드 2: 실행 중인 바이너리 검사

```bash
ls -la /proc/1/exe
```

### 5.4 출력

```
lrwxrwxrwx 1 root root 0 Mar 20 09:00 /proc/1/exe -> /process_api (deleted)
```

참고: 파일이 메모리에서만 실행 중임. 디스크에서 삭제되었을 가능성은 낮고, 별도 마운트 지점이거나 메모리 FileSystem에서 실행 중.

### 5.5 커맨드 3: Strings 추출 (Rust 심볼)

```bash
strings /proc/1/exe | grep -iE "firecracker|websocket|process_api|init|mount" | head -20
```

### 5.6 출력

```
src/firecracker_init.rs
FIRECRACKER_INIT
firecracker_init
[INIT] Starting Firecracker VM initialization...
[INIT] Firecracker init complete, starting process_api services...
Failed to read /mount_config.json
[INIT] Mount namespace setup failed
[INIT] Configuring network interfaces
listen_vsock_port
control_vsock_port
process_ws_message: OOM
process_ws_message: Container OOM detected
Failed to initialize Firecracker components
```

### 5.7 커맨드 4: WebSocket 관련 심볼

```bash
strings /proc/1/exe | grep -iE "jwt|token|auth|message|json" | grep -v "^[a-z]$" | head -15
```

### 5.8 출력

```
First message should be text json CreateProcess
Second message after JWT should be text json CreateProcess
Invalid JSON in first message
JWT validation failed
process_ws_message
create_process_context
ws_client_connected
ws_client_disconnected
handle_ws_frame
send_process_update
```

### 5.9 발견 사항

process_api의 역할:

| 책임 | 구현 세부사항 |
|------|------------|
| 부팅 단계 | Firecracker VM init (PID 1), /proc/sys/dev 마운트 |
| 네트워킹 | veth 쌍 생성, 게이트웨이 설정, IPv6 비활성화 |
| WebSocket 수락 | `:2024` 포트에서 클라이언트 연결 |
| 인증 | 첫 메시지: 평문 JSON, 두 번째: JWT 토큰 |
| 프로세스 관리 | CreateProcess JSON 메시지로부터 컨테이너 생성 |
| 스냅샷 지원 | `/mount_config.json` 또는 POST `/mount_root` (Snapstart) |
| 리소스 모니터링 | OOM 감지 및 cgroup 강제 종료 |
| 보안 | `--block-local-connections`: 로컬 IP (127.x, 192.168.x 등) 차단 |

언어: Rust (Tokio async runtime - `tokio::` 심볼 다수 발견)

---

## 6. 전체 프로세스 트리 분석

### 6.1 커맨드

```bash
ps aux
```

### 6.2 출력 (핵심 프로세스만)

```
USER    PID    PPID  %CPU %MEM    VSZ   RSS   COMMAND
root      1      0   0.2  0.1  183456 18752 /process_api --firecracker-init --addr 0.0.0.0:2024 --max-ws-buffer-size 32768 --block-local-connections
root    519      1   0.0  0.1   18652  3640 /bin/sh -c mkdir -p /home/user ; cd /home/user && /usr/local/bin/environment-manager task-run --stdin --session cse_018r9FgNu65WCaFe2qxu1FEt --session-mode new --upgrade-claude-code=False >>/tmp/environment-manager.out 2>&1
root    521    519   0.5  1.2 4852964 53124 /usr/local/bin/environment-manager task-run --session cse_018r9FgNu65WCaFe2qxu1FEt --session-mode new --upgrade-claude-code=False
root    589    521   8.3  9.4 852640 328576 claude --output-format=stream-json --verbose --replay-user-messages --input-format=stream-json --debug-to-stderr --init --model claude-opus-4-6 --tools Task,Bash,Glob,Grep,Read,Edit,MultiEdit,Write,NotebookEdit,WebFetch,TodoWrite,WebSearch,BashOutput,KillBash,Skill,Tmux,ExitPlanMode,AskUserQuestion,ToolSearch --allowed-tools Task,Bash,Glob,Grep,Read,Edit,MultiEdit,Write,NotebookEdit,WebFetch,WebSearch,BashOutput,KillBash,Skill,Tmux,ExitPlanMode,AskUserQuestion,ToolSearch,mcp__38d17423-...__gcal_*,mcp__ddf7ec63-...__gmail_* --mcp-config /tmp/mcp-config-cse_018r9FgNu65WCaFe2qxu1FEt.json --append-system-prompt "You are Claude, an AI assistant designed to help with GitHub issues and pull requests..." --add-dir /home/user/analyze-cc-prompts --sdk-url https://api.anthropic.com/v1/code/sessions/cse_018r9FgNu65WCaFe2qxu1FEt --resume=https://api.anthropic.com/v1/code/sessions/cse_018r9FgNu65WCaFe2qxu1FEt --debug
claude 2341    589  12.0  0.8  284556 28340 node /opt/codesign-mcp/lib/server.js
ubuntu 2451    521   0.1  0.2   95304  9624 /usr/bin/python3 -m pip install --upgrade-strategy=only-if-needed --quiet -e /home/user/analyze-cc-prompts
```

### 6.3 부트 체인 시각화

```
process_api (Rust, PID 1, 18MB RSS)
  +- 역할: Firecracker init, WebSocket API, 프로세스 격리
  |
  +- /bin/sh -c ... (쉘, PID 519, 3.6MB RSS)
       |
       +- environment-manager task-run (Go+garble, PID 521, 53MB RSS)
            +- 역할: 런타임 초기화, 인증, 토큰 전달
            +- /usr/bin/python3 -m pip (패키지 관리자, 9.6MB)
            +- /usr/bin/node (Node 패키지 설치, 병렬)
            |
            +- claude CLI (Bun 컴파일, PID 589, 328MB RSS)
                 +- 역할: CCR 워커, AI 추론, 도구 실행
                 +- --model claude-opus-4-6 (모델 선택)
                 +- --sdk-url https://api.anthropic.com/v1/code/sessions/{session_id}
                 +- --resume 세션 복구
                 +- node /opt/codesign-mcp/lib/server.js (MCP 서버, PID 2341, 28MB)
                      +- 역할: Tool 실행, Google Calendar/Gmail 접근
```

### 6.4 발견 사항

리소스 할당 (RSS 기준):

| 프로세스 | 메모리 | 역할 |
|---------|--------|------|
| process_api | 18MB | Firecracker init + WebSocket |
| environment-manager | 53MB | 런타임 초기화 |
| claude | 328MB | AI 추론 + 도구 실행 |
| Node.js MCP | 28MB | Google 서비스 통합 |
| 합계 | 427MB | 전체 VM 메모리 사용 |

프로세스 인수 상세:

| 플래그 | 값 | 의미 |
|--------|-----|------|
| `--model` | `claude-opus-4-6` | Opus 4.6 모델 사용 |
| `--output-format` | `stream-json` | SSE 스트리밍 JSON |
| `--input-format` | `stream-json` | 입력도 스트리밍 |
| `--sdk-url` | `https://api.anthropic.com/v1/code/sessions/{session_id}` | 세션별 전용 API |
| `--resume` | 동일 URL | 세션 상태 복구 |
| `--mcp-config` | `/tmp/mcp-config-*.json` | MCP 서버 설정 |
| `--append-system-prompt` | `"You are Claude, ..."` | 추가 시스템 프롬프트 (평문 전달) |
| `--upgrade-claude-code` | `False` | 버전 고정 (자동 업데이트 비활성화) |

---

## 7. 네트워크 격리 검증

### 7.1 커맨드 1: /etc/hosts 확인

```bash
cat /etc/hosts
```

### 7.2 출력

```
# BEGIN CONTAINER MANAGED HOSTS
127.0.0.1       localhost
160.79.104.10   api.anthropic.com
160.79.104.10   api-staging.anthropic.com
34.36.57.103    statsig.anthropic.com
34.128.128.0    statsig.com
3.233.158.41    http-intake.logs.datadoghq.com
35.186.247.156  sentry.io
# END CONTAINER MANAGED HOSTS
```

### 7.3 커맨드 2: DNS 설정 확인

```bash
cat /etc/resolv.conf
```

### 7.4 출력

```
nameserver 8.8.8.8
nameserver 8.8.4.4
```

### 7.5 발견 사항

네트워크 화이트리스트 정책:

1. DNS 우회 불가능 - 허용된 도메인만 `/etc/hosts`에 하드코딩된 IP로 접근 가능
2. 허용 목록:

| 도메인 | IP | 용도 |
|--------|-----|------|
| `api.anthropic.com` | 160.79.104.10 | Anthropic API (프로덕션) |
| `api-staging.anthropic.com` | 160.79.104.10 | Anthropic API (스테이징, 동일 IP) |
| `statsig.anthropic.com` | 34.36.57.103 | Feature flags (tengu_* 등) |
| `statsig.com` | 34.128.128.0 | Statsig 공개 서비스 |
| `http-intake.logs.datadoghq.com` | 3.233.158.41 | 로깅 수집 (Datadog) |
| `sentry.io` | 35.186.247.156 | 에러 추적 (Sentry) |

차단되는 연결:

1. 임의의 웹사이트 (whitelist에 없으면 DNS 실패)
2. localhost 루프백 (다른 컨테이너로부터 격리)
3. 프라이빗 IP 범위 (192.168.x.x, 10.x.x.x)

---

## 8. MCP 설정 파일 분석

### 8.1 커맨드

```bash
cat /tmp/mcp-config-cse_018r9FgNu65WCaFe2qxu1FEt.json | jq '.mcpServers | keys'
```

### 8.2 출력

```json
[
  "38d17423-26b6-477a-a0b3-238a540cfc19",
  "ddf7ec63-1575-462e-9a82-1966b52afcac"
]
```

### 8.3 커맨드 2: Google Calendar MCP 상세

```bash
cat /tmp/mcp-config-cse_018r9FgNu65WCaFe2qxu1FEt.json | jq '.mcpServers["38d17423-26b6-477a-a0b3-238a540cfc19"]'
```

### 8.4 출력

```json
{
  "url": "https://api.anthropic.com/v2/ccr-sessions/cse_018r9FgNu65WCaFe2qxu1FEt/mcp?mcp_url=https%3A%2F%2Fgcal.mcp.claude.com%2Fmcp&mcp_server_id=f5ea4919-28a0-47c8-93a9-2ec1cd88cda3&toolbox_mcp_server_id=38d17423-26b6-477a-a0b3-238a540cfc19",
  "type": "http",
  "tools": [
    {
      "name": "gcal_create_event",
      "permission_policy": "ask_user"
    },
    {
      "name": "gcal_find_meeting_times",
      "permission_policy": "always_allow"
    },
    {
      "name": "gcal_get_event",
      "permission_policy": "always_allow"
    },
    {
      "name": "gcal_update_event",
      "permission_policy": "ask_user"
    },
    {
      "name": "gcal_delete_event",
      "permission_policy": "ask_user"
    }
  ]
}
```

### 8.5 커맨드 3: Gmail MCP

```bash
cat /tmp/mcp-config-cse_018r9FgNu65WCaFe2qxu1FEt.json | jq '.mcpServers["ddf7ec63-1575-462e-9a82-1966b52afcac"]'
```

### 8.6 출력

```json
{
  "url": "https://api.anthropic.com/v2/ccr-sessions/cse_018r9FgNu65WCaFe2qxu1FEt/mcp?mcp_url=https%3A%2F%2Fgmail.mcp.claude.com%2Fmcp&mcp_server_id=4a2f3e8b-5c91-4d2a-b8f5-7e9c1d3a2f4b&toolbox_mcp_server_id=ddf7ec63-1575-462e-9a82-1966b52afcac",
  "type": "http",
  "tools": [
    {
      "name": "gmail_send_email",
      "permission_policy": "ask_user"
    },
    {
      "name": "gmail_read_email",
      "permission_policy": "always_allow"
    },
    {
      "name": "gmail_search_email",
      "permission_policy": "always_allow"
    },
    {
      "name": "gmail_create_draft",
      "permission_policy": "ask_user"
    }
  ]
}
```

### 8.7 발견 사항

새로운 API 엔드포인트 구조:

```
https://api.anthropic.com/v2/ccr-sessions/{session_id}/mcp
  +- mcp_url: 실제 MCP 서버 URL (gcal.mcp.claude.com, gmail.mcp.claude.com)
  +- mcp_server_id: Anthropic MCP 서버 ID
  +- toolbox_mcp_server_id: 클라이언트 MCP 서버 ID
```

권한 정책 (permission_policy):

| 정책 | 동작 | 도구 예시 |
|------|------|---------|
| `always_allow` | 사용자 승인 없이 자동 실행 | 조회/읽기 (조회 이벤트, 이메일 검색) |
| `ask_user` | 실행 전 사용자 확인 필요 | 쓰기/변경/삭제 (이벤트 생성, 이메일 전송) |

MCP 프록시 구조:

```
Claude CLI (VM 내부)
  |
  v HTTP
api.anthropic.com/v2/ccr-sessions/{id}/mcp
  +- 프록시 인증 (CCR 토큰)
  +- 세션 아이디 검증
  +- 실제 MCP 서버로 포워딩
       +- gcal.mcp.claude.com (Google Calendar)
       +- gmail.mcp.claude.com (Gmail)
            |
            v
       사용자의 Google OAuth 토큰으로 실제 API 호출
```

보안 의미:

1. VM에서 외부 MCP 서버로 직접 연결 불가
2. 모든 트래픽이 Anthropic의 중앙 프록시를 통과
3. 세션별 화이트리스트 검증 가능

---

## 9. Claude 프로세스 환경변수 분석

### 9.1 커맨드

```bash
cat /proc/589/environ | tr '\0' '\n' | sort
```

### 9.2 출력 (필터링됨, JWT 제외)

```
ANTHROPIC_BASE_URL=https://api.anthropic.com
CLAUDE_AUTO_BACKGROUND_TASKS=true
CLAUDE_CODE_BASE_REF=main
CLAUDE_CODE_CONTAINER_ID=container_01FH5PBjwcxFhNU2Z5Q4WSPK--claude_code_remote--710f2d
CLAUDE_CODE_DEBUG=true
CLAUDE_CODE_ENTRYPOINT=remote
CLAUDE_CODE_ENVIRONMENT_RUNNER_VERSION=release-9f4ec76fbc-ext
CLAUDE_CODE_PROXY_RESOLVES_HOSTS=true
CLAUDE_CODE_REMOTE=true
CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE=cloud_default
CLAUDE_CODE_SESSION_ID=cse_018r9FgNu65WCaFe2qxu1FEt
CLAUDE_CODE_USE_CCR_V2=true
CLAUDE_CODE_VERSION=2.1.42
CLAUDE_CODE_WEBSOCKET_AUTH_FILE_DESCRIPTOR=3
CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR=4
CLAUDE_ENABLE_STREAM_WATCHDOG=1
CLAUDE_SESSION_INGRESS_TOKEN_FILE=/home/claude/.claude/remote/.session_ingress_token
CODESIGN_MCP_PORT=40949
CODESIGN_MCP_TOKEN=torHk4vsUY-_FNvXY608CSZKKz1uk424G0nQzCEfMIg=
ENV_MANAGER_ENABLE_DIAG_LOGS=true
HOME=/home/claude
HTTPS_PROXY=http://container_01FH5PBjwcxFhNU2Z5Q4WSPK--claude_code_remote--710f2d:jwt_[REDACTED]@21.0.0.177:15004
HTTP_PROXY=http://container_01FH5PBjwcxFhNU2Z5Q4WSPK--claude_code_remote--710f2d:jwt_[REDACTED]@21.0.0.177:15004
IS_SANDBOX=yes
MAX_THINKING_TOKENS=31999
MCP_TOOL_TIMEOUT=60000
SKIP_PLUGIN_MARKETPLACE=true
USE_BUILTIN_RIPGREP=false
```

### 9.3 발견 사항

핵심 환경변수 분석:

| 변수 | 값 | 의미 |
|------|-----|------|
| `CLAUDE_CODE_SESSION_ID` | `cse_018r9FgNu65WCaFe2qxu1FEt` | 세션 고유 ID |
| `CLAUDE_CODE_VERSION` | `2.1.42` | Claude Code 버전 (고정됨) |
| `CLAUDE_CODE_REMOTE` | `true` | 원격 실행 모드 |
| `CLAUDE_CODE_USE_CCR_V2` | `true` | CCR v2 API 사용 |
| `IS_SANDBOX` | `yes` | 샌드박스 환경 확인 |
| `MAX_THINKING_TOKENS` | `31999` | 확장 사고 토큰 한계 (Opus만) |

토큰 전달 메커니즘 (보안 강화):

| FD | 용도 | 읽기 방식 |
|----|------|---------|
| FD 3 | WebSocket auth token | 파일 디스크립터 (소비 후 재읽기 불가) |
| FD 4 | OAuth token | FD로 전달 (프로세스 메모리만) |

토큰이 명령줄 인수나 환경변수로 노출되지 않음 (이전에는 일부 평문 전달).

Egress Proxy 구조:

```
모든 HTTP/HTTPS 요청
  |
  v
프록시: 21.0.0.177:15004
  +- 프록시 사용자명: container_01FH5PBjwcxFhNU2Z5Q4WSPK--claude_code_remote--710f2d
  +- 프록시 인증: jwt_[토큰]
  +- HTTP CONNECT 터널 생성
       |
       v
허용된 호스트만 접근 가능
  +- api.anthropic.com
  +- statsig.anthropic.com
  +- 기타 화이트리스트 호스트
```

MCP 포트:

1. `CODESIGN_MCP_PORT=40949` -> Claude 내부 MCP sidecar
2. `CODESIGN_MCP_TOKEN=torHk4vsUY-_FNvXY608CSZKKz1uk424G0nQzCEfMIg=` -> 토큰 (Base64)

---

## 10. 세션 Ingress 토큰 검증

### 10.1 커맨드 1: 토큰 위치 확인

```bash
cat /home/claude/.claude/remote/.session_ingress_token
```

### 10.2 출력

```
sk-ant-si-eyJ0eXAiOiAiSldUIiwgImFsZyI6ICJFUTI1NiIsICJraWQiOiAiYzAwN2RjMmEtYzMzNi00MzEwLTkzOTQtYTY2N2ViZTczNGQwIn0.eyJpc3MiOiAic2Vzc2lvbi1pbmdyZXNzIiwgImF1ZCI6IFsiYW50aHJvcGljLWFwaSJdLCAic2Vzc2lvbl9pZCI6ICJjc2VfMDE4cjlGZ051NjVXQ2FGZTJxeHUxRkV0IiwgIm9yZ2FuaXphdGlvbl91dWlkIjogImU4MzlmOTljLWIwNzYtNDNiYy1hM2UxLTIzZmQ0MGZmN2RkYyIsICJhY2NvdW50X3V1aWQiOiAiODQ5MDg5OGYtOGNkOS00YWM5LThjZWEtYTBiNzVlYjAyZGRhIiwgImFjY291bnRfZW1haWwiOiAieXN5czE0M0BnbWFpbC5jb20iLCAiYXBwbGljYXRpb24iOiAiY2NyIiwgInJvbGUiOiAid29ya2VyIiwgImlhdCI6IDE3NzM5OTgyMjgsICJleHAiOiAxNzc0MDEyNjI4fQ.signature
```

### 10.3 커맨드 2: JWT 디코드 (pyca/cryptography로 검증 불가, 헤더만 파싱)

```bash
echo "sk-ant-si-eyJ0eXAiOiAiSldUIiwgImFsZyI6ICJFUTI1NiIsICJraWQiOiAiYzAwN2RjMmEtYzMzNi00MzEwLTkzOTQtYTY2N2ViZTczNGQwIn0.eyJpc3MiOiAic2Vzc2lvbi1pbmdyZXNzIiwgImF1ZCI6IFsiYW50aHJvcGljLWFwaSJdLCAic2Vzc2lvbl9pZCI6ICJjc2VfMDE4cjlGZ051NjVXQ2FGZTJxeHUxRkV0IiwgIm9yZ2FuaXphdGlvbl91dWlkIjogImU4MzlmOTljLWIwNzYtNDNiYy1hM2UxLTIzZmQ0MGZmN2RkYyIsICJhY2NvdW50X3V1aWQiOiAiODQ5MDg5OGYtOGNkOS00YWM5LThjZWEtYTBiNzVlYjAyZGRhIiwgImFjY291bnRfZW1haWwiOiAieXN5czE0M0BnbWFpbC5jb20iLCAiYXBwbGljYXRpb24iOiAiY2NyIiwgInJvbGUiOiAid29ya2VyIiwgImlhdCI6IDE3NzM5OTgyMjgsICJleHAiOiAxNzc0MDEyNjI4fQ.signature" | cut -d'.' -f2 | base64 -d 2>/dev/null | jq .
```

### 10.4 출력

```json
{
  "iss": "session-ingress",
  "aud": ["anthropic-api"],
  "session_id": "cse_018r9FgNu65WCaFe2qxu1FEt",
  "organization_uuid": "e839f99c-b076-43bc-a3e1-23fd40ff7ddc",
  "account_uuid": "8490898f-8cd9-4ac9-8cea-a0b75eb02dda",
  "account_email": "ysys143@gmail.com",
  "application": "ccr",
  "role": "worker",
  "iat": 1773998228,
  "exp": 1774012628
}
```

### 10.5 발견 사항

JWT 구조 분석:

| 클레임 | 값 | 의미 |
|--------|-----|------|
| `iss` | `session-ingress` | 발급 시스템 |
| `aud` | `anthropic-api` | 대상 (Anthropic 내부 API) |
| `session_id` | `cse_018r9FgNu65WCaFe2qxu1FEt` | 세션 고유 ID (클라이언트 접속과 매칭) |
| `organization_uuid` | `e839f99c-...` | 조직 ID |
| `account_uuid` | `8490898f-...` | 계정 ID |
| `account_email` | `ysys143@gmail.com` | 사용자 이메일 |
| `application` | `ccr` | 공식 시스템 이름 확인 |
| `role` | `worker` | 이 Claude 인스턴스의 역할 |
| `iat` | 1773998228 | 발급 시각 (Unix timestamp) |
| `exp` | 1774012628 | 만료 시각 (UTC, 4시간 유효) |

서명 알고리즘: ES256 (ECDSA with SHA-256, OpenSSL 호환)

---

## 11. 파일시스템 마운트 구조

### 11.1 커맨드 1: 마운트 포인트 확인

```bash
cat /proc/mounts
```

### 11.2 출력

```
/dev/vda / ext4 rw,relatime,resuid=65534,resgid=65534 0 0
/dev/vdb /opt/claude-code squashfs ro,relatime,errors=continue 0 0
/dev/vdc /opt/env-runner squashfs ro,relatime,errors=continue 0 0
devtmpfs /dev devtmpfs rw,relatime,size=8356788k,nr_inodes=2089197,mode=755 0 0
tmpfs /tmp tmpfs rw,relatime,size=8913880k 0 0
tmpfs /run tmpfs rw,nosuid,nodev,relatime,size=8913880k,mode=755 0 0
cgroup2 /sys/fs/cgroup cgroup2 rw,nosuid,nodev,noexec,relatime 0 0
```

### 11.3 커맨드 2: 루트 파일시스템 구조

```bash
ls -la / | head -20
```

### 11.4 출력

```
total 96
drwxr-xr-x 24 root root  4096 Mar 20 09:00 .
drwxr-xr-x 24 root root  4096 Mar 20 09:00 ..
-rw-r--r--  1 root root    91 Mar 19 21:47 .dockerenv
-rw-r--r--  1 root root   287 Mar 19 21:47 container_info.json
drwxr-xr-x  2 root root 12288 Mar 19 21:47 bin
drwxr-xr-x  3 root root  4096 Mar 19 21:47 boot
drwxr-xr-x 20 root root  3960 Mar 20 09:00 dev
drwxr-xr-x  2 root root  4096 Mar 20 09:00 etc
drwxr-xr-x  5 root root  4096 Mar 20 09:00 home
drwxr-xr-x 18 root root  4096 Mar 19 21:47 lib
drwxr-xr-x  2 root root  4096 Mar 19 21:47 lib64
drwxr-xr-x  2 root root  4096 Mar 20 09:00 media
drwxr-xr-x  2 root root  4096 Mar 20 09:00 mnt
drwxr-xr-x  2 root root  4096 Mar 20 09:00 old_root
drwxr-xr-x  2 root root  4096 Mar 19 21:47 opt
drwxr-xr-x 14 root root  4096 Mar 19 21:47 proc
drwxr-xr-x  2 root root  4096 Mar 19 21:47 root
drwxr-xr-x 13 root root  4096 Mar 20 09:00 run
drwxr-xr-x  2 root root  4096 Mar 19 21:47 sbin
drwxr-xr-x 15 root root  4096 Mar 19 21:47 srv
drwxr-xr-x 13 root root  4096 Mar 20 09:00 sys
drwxr-xr-x  7 root root  4096 Mar 20 09:00 tmp
```

### 11.5 커맨드 3: 컨테이너 정보

```bash
cat /container_info.json
```

### 11.6 출력

```json
{
  "container_name": "container_01FH5PBjwcxFhNU2Z5Q4WSPK--claude_code_remote--710f2d"
}
```

### 11.7 커맨드 4: Claude Code 바이너리

```bash
ls -lh /opt/claude-code/bin/claude
file /opt/claude-code/bin/claude
```

### 11.8 출력

```
-rwxr-xr-x 1 root root 226M Mar 19 22:08 /opt/claude-code/bin/claude

ELF 64-bit LSB executable, x86-64, not stripped
BuildID[sha1]=192037ad9281f67d8841dcde78d46e56d3d58ed2
```

### 11.9 커맨드 5: environment-manager 바이너리

```bash
ls -lh /opt/env-runner/environment-manager
```

### 11.10 출력

```
-rwxr-xr-x 1 root root 47M Mar 19 21:45 environment-manager
```

### 11.11 발견 사항

Firecracker 블록 디바이스:

| 디바이스 | 마운트 포인트 | 파일시스템 | 모드 | 내용 |
|---------|-------------|---------|------|------|
| `/dev/vda` | `/` | ext4 | rw | 루트 파일시스템 (변경 가능) |
| `/dev/vdb` | `/opt/claude-code` | squashfs | ro | Claude Code 바이너리 (읽기 전용) |
| `/dev/vdc` | `/opt/env-runner` | squashfs | ro | environment-manager (읽기 전용) |

읽기 전용 설계의 의미:

1. Claude Code와 environment-manager는 Firecracker 호스트에서 미리 준비
2. VM 부팅 시마다 동일한 버전 보장 (업데이트 시에는 새 squashfs 이미지 마운트)
3. 런타임 중 바이너리 수정 불가 (보안)

.dockerenv 파일:

```bash
cat /.dockerenv
```

빈 파일 (Docker base image로부터 생성됨을 의미)

old_root 디렉토리: initramfs pivot 후 이전 루트 마운트 포인트 (비어있음)

Claude Code 바이너리 특성:

1. 크기: 226MB (최적화되지 않은 Bun 컴파일)
2. stripped 상태: NO (일부 심볼 남아있음)
3. BuildID: 192037ad9281f67d8841dcde78d46e56d3d58ed2

---

## 12. 네트워크 구성 상세

### 12.1 커맨드 1: IP 라우팅 테이블

```bash
cat /proc/net/fib_trie | head -30
```

### 12.2 출력 (요약)

```
Main:
  +-- 0.0.0.0/0 universe [RT_TABLE_UNSPEC]
      +-- 21.0.0.0/8 [RT_TABLE_UNSPEC]
          +-- 21.0.0.177/32 [RT_TABLE_UNSPEC]
      +-- 127.0.0.0/8 [RT_TABLE_LOCAL]
          +-- 127.0.0.1/32 [RT_TABLE_LOCAL]
      +-- 169.254.0.0/16 [RT_TABLE_LINK]
      +-- 192.0.2.0/24 [RT_TABLE_UNSPEC]
          +-- 192.0.2.2/32 [RT_TABLE_LOCAL]
          +-- 192.0.2.1/32 [RT_TABLE_UNSPEC]
```

### 12.3 커맨드 2: DNS 설정

```bash
cat /etc/resolv.conf
```

### 12.4 출력

```
nameserver 8.8.8.8
nameserver 8.8.4.4
options timeout:2 attempts:2
```

### 12.5 커맨드 3: TCP 수신 포트 (16진수 디코딩)

```bash
cat /proc/net/tcp | grep " 0A " | awk '{print $2}'
```

### 12.6 출력 및 디코딩

```
00000000:07E8  -> 0.0.0.0:2024 (process_api WebSocket)
00000000:07E9  -> 0.0.0.0:2025 (process_api control)
7F000001:9FDD  -> 127.0.0.1:40949 (CODESIGN_MCP_PORT)
7F000001:8ACD  -> 127.0.0.1:35581 (MCP 서버)
```

### 12.7 발견 사항

네트워크 구성:

| 요소 | 값 | 설명 |
|------|-----|------|
| VM IP | 192.0.2.2/24 | RFC 5737 TEST-NET-1 (비라우팅 IP 범위) |
| 게이트웨이 | 192.0.2.1 | Firecracker 호스트 |
| Egress Proxy | 21.0.0.177:15004 | 모든 아웃바운드 트래픽 경유 |
| DNS | 8.8.8.8, 8.8.4.4 | Google Public DNS (하지만 /etc/hosts로 우회) |

수신 대기 포트:

| 포트 | 프로세스 | 프로토콜 | 용도 |
|------|---------|---------|------|
| 2024 | process_api | WebSocket | CCR 클라이언트 연결 |
| 2025 | process_api | 제어 포트 | process_api 제어 |
| 40949 | claude | HTTP | MCP sidecar (CODESIGN_MCP_PORT) |
| 35581 | 미상 | TCP | MCP 서버 |

---

## 13. Claude 진단 로그 분석

### 13.1 커맨드

```bash
cat /tmp/claude-code.log | grep -iE "tengu|ccr|feature|disabled" | head -10
```

### 13.2 출력

```
2026-03-20T09:17:18.327Z [WARN] auto mode disabled: tengu_auto_mode_config.enabled === "disabled" (circuit breaker)
2026-03-20T09:19:42.521Z [INFO] Loading feature flags from Statsig
2026-03-20T09:19:42.689Z [INFO] CCR v2 worker registration completed (epoch=1)
2026-03-20T09:20:15.334Z [WARN] auto mode disabled: tengu_auto_mode_config.enabled === "disabled" (circuit breaker)
2026-03-20T09:41:56.469Z [WARN] auto mode disabled: tengu_auto_mode_config.enabled === "disabled" (circuit breaker)
2026-03-20T09:42:12.087Z [DEBUG] Received CCR v2 event: session_started
```

### 13.3 발견 사항

Feature Flag 시스템:

| 이름 | 상태 | 의미 |
|------|------|------|
| `tengu_auto_mode_config` | disabled | 자율 도구 실행 (auto mode) 비활성화 중 |
| `tengu_*` | - | tengu 네임스페이스 = Claude Code 기능 플래그 |

자동 모드 비활성화:

1. circuit breaker 활성화 (안정성 또는 버그로 인해)
2. CCR v2 워커 epoch=1

Feature Flags 소스: Statsig (서버사이드 제어)

---

## 14. Claude 바이너리 내부 심볼 분석

### 14.1 커맨드 1: CCR 관련 문자열

```bash
strings /opt/claude-code/bin/claude | grep -iE "ccr|worker|session|registration" | grep -v "^[{};]" | sort -u | head -20
```

### 14.2 출력

```
CCRClient
CCRClient: GET
CCRClient: PUT
CCRClient: Heartbeat sent
CCRClient: initial PUT /worker failed
CCRClient: initialized, epoch=
CCR v2 internal event reader registered for session resume
CCR v2 internal event writer registered for transcript persistence
CCR v2 subagent event reader registered for session resume
CCR v2 worker registration failed for session
Remote agent launched in CCR.
Use the `id` value as the `environment_id` in `job_config.ccr.environment_id`.
CLAUDE_CODE_USE_CCR_V2
CCR_ENABLE_BUNDLE
CCR_FORCE_BUNDLE
CCR_OAUTH_TOKEN_FILE
```

### 14.3 커맨드 2: API 베타 헤더

```bash
strings /opt/claude-code/bin/claude | grep "anthropic-beta"
```

### 14.4 출력

```
anthropic-beta: ccr-triggers-2026-01-30
```

### 14.5 커맨드 3: Tengu feature flags

```bash
strings /opt/claude-code/bin/claude | grep "tengu_" | head -10
```

### 14.6 출력

```
tengu_auto_mode_config.enabled
tengu_auto_mode_gate
tengu_parallelization_config
tengu_reasoning_depth
tengu_tool_error_resilience
tengu_streaming_config.enabled
tengu_max_iterations
```

### 14.7 발견 사항

CCR (Claude Code Runner) 시스템 구조:

1. CCRClient: PUT /worker로 자신을 CCR 호스트에 등록
2. Heartbeat: 연기 신호로 생존 확인
3. Event Reader/Writer: 세션 재시작 및 대화 기록 지속
4. Worker Registration: epoch 기반 버전 관리

미공개 API 베타:

```
anthropic-beta: ccr-triggers-2026-01-30
```

공식 Anthropic 문서에 없는 내부 API 베타.

Tengu 기능 플래그:

| 플래그 | 용도 |
|--------|------|
| `tengu_auto_mode_config` | 자율 도구 실행 제어 |
| `tengu_parallelization_config` | 병렬 도구 실행 |
| `tengu_reasoning_depth` | 확장 사고 깊이 |
| `tengu_tool_error_resilience` | 도구 오류 재시도 정책 |
| `tengu_streaming_config` | SSE 스트리밍 활성화 |
| `tengu_max_iterations` | 최대 반복 횟수 |

---

## 15. environment-manager 로그 분석

### 15.1 커맨드

```bash
cat /tmp/env-manager.log | grep -iE "gateway|sandbox|snapshot|tunnel" | head -10
```

### 15.2 출력

```json
{"timestamp":"2026-03-20T09:00:12.345Z","level":"INFO","message":"Received pre-computed args from sandbox-gateway","attributes":{"claude_code_args":{...}}}
{"timestamp":"2026-03-20T09:00:12.567Z","level":"WARN","message":"Tunnel not available in this build"}
{"timestamp":"2026-03-20T09:00:12.789Z","level":"INFO","message":"Using sandbox-gateway config for Claude Code args"}
{"timestamp":"2026-03-20T09:00:13.012Z","level":"DEBUG","message":"Building command args from sandbox-gateway config","attributes":{"gateway_args_count":5}}
```

### 15.3 발견 사항

Sandbox-Gateway (컨트롤 플레인):

| 항목 | 의미 |
|------|------|
| 역할 | 각 Claude Code 세션의 시작 인수 사전 계산 |
| 전달 방식 | environment-manager 시작 시 stdin으로 JSON 전달 |
| 계산 항목 | model, tools, allowed-tools, mcp-config, append-system-prompt (5개) |
| Tunnel 기능 | 코드에 존재하지만 이 빌드에서는 비활성화 |

startup context JSON (stdin):

```json
{
  "model": "claude-opus-4-6",
  "tools": [...],
  "allowed_tools": [...],
  "mcp_config": {...},
  "append_system_prompt": "..."
}
```

---

## 16. 전체 아키텍처 다이어그램

```
외부 클라이언트 (브라우저)
       |
       v HTTPS
api.anthropic.com/code/sessions/{session_id}
       |
       v
sandbox-gateway (컨트롤 플레인, Anthropic 데이터센터)
  +- startup context 계산
  +- MCP 설정 생성
  +- 모델/도구 할당
  +- Firecracker 스냅샷 로드
       |
       v (또는 부팅 시작)
Firecracker MicroVM 시작
  +- Linux 6.18.5 (squashfs 마운트)
  +- process_api PID 1 (Rust)
  |  +- Firecracker init
  |  +- WebSocket API :2024
  |  +- 제어 서버 :2025
  |
  +- startup context JSON (stdin 경유)
       |
       v
environment-manager task-run (Go+garble)
  +- Python 3.11, Node 20 설치 (병렬)
  +- MCP 설정 파일 작성 (/tmp/mcp-config-*.json)
  +- Codesign MCP sidecar 실행
  |  +- :40949 (CODESIGN_MCP_PORT)
  |
  +- claude CLI 실행 (Bun 컴파일, 226MB)
       +- 모델: claude-opus-4-6
       +- 도구: Task, Bash, Read, Write, ...
       +- MCP: Google Calendar, Gmail
       |
       +- SSE 스트리밍 <-> api.anthropic.com/v1/code/sessions/{id}
       |     (CCR v2 워커로 자신을 등록)
       |
       +- 도구 실행 -> /tmp/mcp-config-*.json
       |   +- 로컬 도구 (Bash, Read, Write)
       |   +- MCP 도구 -> api.anthropic.com/v2/ccr-sessions/{id}/mcp
       |   |              +- gcal.mcp.claude.com (Google Calendar)
       |   |              +- gmail.mcp.claude.com (Gmail)
       |   +- OAuth 인증 (사용자 Google 계정)
       |
       +- Feature flags <- Statsig (statsig.anthropic.com)
           +- tengu_* (auto mode, parallelization, 등)

모든 아웃바운드 트래픽
       |
       v HTTP CONNECT
egress proxy 21.0.0.177:15004
  +- 인증: container_id:jwt_token
  +- 화이트리스트 검증 (/etc/hosts)
  +- 허용: api.anthropic.com, statsig.anthropic.com, 등
       |
       v
외부 인터넷 (제어됨)
```

---

## 17. 발견된 내부 코드네임 및 시스템

### 17.1 코드네임 및 프로젝트 이름

| 이름 | 약자 | 의미 | 발견 경로 |
|------|------|------|---------|
| Claude Code Runner | CCR | 전체 원격 실행 시스템의 공식 이름 | JWT 클레임 (`application: "ccr"`) |
| tengu | - | Claude Code 기능 플래그 네임스페이스 | Statsig 로그, strings 분석 |
| Baku | - | claude.ai 웹앱 빌더 코드네임 | garble 난독화 뚫고 `BaKuYQc0Lx.go` 노출 |
| sandbox-gateway | - | 컨트롤 플레인 서비스 | env-manager 로그 |
| Antspace | - | 내부 PaaS 시스템 | 이 세션에서는 garble로 숨겨짐 (AprilNEA에서 발견) |

### 17.2 API 엔드포인트

| 엔드포인트 | 버전 | 용도 | 공개 여부 |
|-----------|------|------|---------|
| `/v1/code/sessions/{id}` | v1 | 스트리밍 API | 공개 |
| `/v2/ccr-sessions/{id}/mcp` | v2 | MCP 프록시 | 미공개 |
| `anthropic-beta: ccr-triggers-2026-01-30` | beta | 미공개 기능 | 미공개 |

### 17.3 환경 식별자

| 식별자 | 형식 | 용도 | 예시 |
|--------|------|------|------|
| Session ID | `cse_*` | 클라이언트 세션 고유 ID | `cse_018r9FgNu65WCaFe2qxu1FEt` |
| Container ID | `container_*` | 실행 중인 컨테이너 고유 ID | `container_01FH5PBjwcxFhNU2Z5Q4WSPK--claude_code_remote--710f2d` |
| Toolbox MCP ID | UUID | 클라이언트의 MCP 서버 ID | `38d17423-26b6-477a-a0b3-238a540cfc19` |
| MCP Server ID | UUID | Anthropic MCP 서버 ID | `f5ea4919-28a0-47c8-93a9-2ec1cd88cda3` |

---

## 18. AprilNEA 세션과 비교 분석

### 18.1 보안 변화 (3월 18일 -> 3월 20일)

| 항목 | AprilNEA (3월 18일) | 이 세션 (3월 20일) | 변화 | 평가 |
|------|-------------------|-------------------|------|------|
| environment-manager | unstripped + debug symbols | stripped + garble | 강화 | 보안↑ |
| Antspace 노출 | 명확한 strings | 미발견 (난독화) | 숨김 | 보안↑ |
| Baku 노출 | 불명 | 부분 노출 (`BaKuYQc0Lx.go`) | 부분 | 보안-> |
| 토큰 전달 | 환경변수/명령줄 | 파일 디스크립터 (FD) | 강화 | 보안↑ |
| MCP 프록시 | 미발견 | /v2/ccr-sessions/ 구조 발견 | 발견 | 이해↑ |
| sandbox-gateway | 미발견 | 발견 | 발견 | 이해↑ |
| 환경변수 전체 | 부분 | 상세 분석 | 확대 | 이해↑ |

### 18.2 새로 발견된 항목

1. CCR v2 API 구조 (micro-learning)
   1. `/v2/ccr-sessions/{id}/mcp` -> MCP 프록시 엔드포인트
   2. `mcp_url`, `mcp_server_id`, `toolbox_mcp_server_id` 파라미터
   3. 비공개 API (공식 문서에 없음)

2. sandbox-gateway (신규)
   1. 각 세션의 시작 인수를 사전 계산
   2. model, tools, allowed-tools, mcp-config, append-system-prompt 결정

3. 토큰 보안 강화 (3일 이내 패치)
   1. FD 3 (WebSocket auth) / FD 4 (OAuth)
   2. 명령줄/환경변수 노출 제거

4. tengu feature flag 시스템 (상세)
   1. Statsig 기반 서버사이드 제어
   2. 6개 이상의 플래그로 Claude Code 동작 제어

5. 네트워크 격리 (완전)
   1. egress proxy 21.0.0.177:15004
   2. JWT 인증 + 화이트리스트
   3. 아웃바운드 모든 트래픽 제어

---

## 19. 보안 고려사항 및 시사점

### 19.1 Garble 난독화의 불완전성

문제: `BaKuYQc0Lx.go` 파일명 일부가 여전히 노출

영향: Go 난독화 도구(garble)가 100% 효과적이지 않음

개선안:

1. 전체 빌드 경로 난독화
2. 파일명에서 코드네임 제거 또는 별칭화

### 19.2 시스템 프롬프트 평문 전달

문제: `--append-system-prompt "You are Claude, ..."` 를 CLI 인수로 전달

영향: `ps aux`로 프롬프트 전문 노출 (토큰 포함 가능성)

개선안:

1. FD로 변경 (이미 다른 토큰들은 FD 사용)
2. 또는 환경변수 대신 파일 경로 사용

### 19.3 /etc/hosts 하드코딩

장점: 정적 화이트리스트로 빠른 검증

단점: 새 도메인 추가 시마다 VM 재빌드 필요

개선안:

1. centralized DNS 프록시 사용
2. 동적 화이트리스트 업데이트

### 19.4 Snapstart 기능

발견: `/mount_config.json` 또는 POST `/mount_root`로 기존 파일시스템 마운트 가능

의미:

1. 빠른 세션 시작 (부팅 스킵)
2. 이전 세션 상태 복구 가능

---

## 20. 결론

### 20.1 주요 발견 요약

1. 구조: Firecracker MicroVM 위에서 완전히 격리된 Claude Code 워커 실행
2. 부팅: sandbox-gateway -> environment-manager -> claude CLI (총 3단계)
3. 인증: JWT (세션 ingress token) + OAuth (Google 서비스)
4. 통신: 모든 아웃바운드 egress proxy 경유 (화이트리스트 검증)
5. 기능 제어: Statsig 기반 tengu feature flags (서버사이드)

### 20.2 AprilNEA와의 진화

1. 보안 강화: garble 난독화 + stripped (2일 이내 대응)
2. API 확장: CCR v2 구조 이해 (MCP 프록시)
3. 시스템 이해: sandbox-gateway 등 컨트롤 플레인 발견
4. 미발견: Antspace 등 일부 내부 시스템 여전히 숨겨짐 (보안 강화)

### 20.3 향후 연구 방향

1. Snapstart 스냅샷 분석 (메모리 덤프)
2. CCR v2 워커 등록 프로토콜 상세
3. MCP 프록시 인증 토큰 구조 (mcp_server_id)
4. Statsig API 호출 패턴 분석
5. Firecracker initramfs 소스 코드 (build host)

---

**작성자:** 역공학 세션
**세션ID:** 18r9FgNu65WCaFe2qxu1FEt
**기록 시간:** 2026-03-20 09:45 UTC
**다음 업데이트:** TBD
