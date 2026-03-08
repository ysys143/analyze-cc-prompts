# Always-On Memory Agent vs Claude Code Memory System 비교

> Google ADK 기반 [Always-On Memory Agent](https://github.com/GoogleCloudPlatform/generative-ai/tree/main/gemini/agents/always-on-memory-agent)와 Claude Code의 네이티브 메모리 시스템을 아키텍처 관점에서 비교한다.

---

## 1. 설계 철학의 근본적 차이

| | Always-On Memory Agent | Claude Code |
|:--|:--|:--|
| **패러다임** | 독립 서비스 (24/7 상시 가동) | 세션 기반 (대화마다 시작/종료) |
| **메모리 모델** | 중앙집중형 DB (SQLite) | 분산 파일 시스템 (Markdown + JSON) |
| **정보 흐름** | Push → Ingest → Store → Query | Pull (필요할 때 파일 도구로 읽기) |
| **기억의 주체** | 전용 에이전트 3개가 분업 | Claude 자신이 직접 Read/Write |
| **설계 목표** | "AI에게 기억을 줘서 망각을 없앤다" | "최소한의 정확한 기억만 유지한다" |

Always-On Memory Agent는 **"모든 것을 기억하겠다"**는 접근이고, Claude Code는 **"꼭 필요한 것만 기억하겠다"**는 접근이다. 이 차이가 이후 모든 설계 결정을 결정한다.

---

## 2. 아키텍처 비교

### 2.1 Always-On Memory Agent

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ IngestAgent  │     │ Consolidate  │     │  QueryAgent  │
│ (입수)       │     │   Agent      │     │  (질의)      │
│              │     │ (30분 주기)   │     │              │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       ▼                    ▼                    ▼
┌─────────────────────────────────────────────────────────┐
│                     SQLite (memory.db)                   │
│  memories: summary, entities, topics, importance        │
│  consolidations: cross-cutting insights                 │
└─────────────────────────────────────────────────────────┘
       ▲
       │ (파일 드롭 / HTTP POST / 대시보드 업로드)
┌──────┴───────┐
│   27종 파일   │
│ txt,pdf,mp3  │
│ mp4,png,...  │
└──────────────┘
```

- **3개의 전문 에이전트**가 역할을 분담 (Ingest, Consolidate, Query)
- **ConsolidateAgent**가 30분마다 자동 실행 → 인간 뇌의 수면 중 기억 정리를 모방
- 모든 메모리가 **하나의 SQLite DB**에 통합 저장
- HTTP API로 외부에서 정보 주입 가능

### 2.2 Claude Code

```
┌─── 세션 시작 시 로딩 ──────────────────────────────────┐
│                                                         │
│  CLAUDE.md (전체 로드)                                   │
│   ├─ Managed Policy    (/Library/.../CLAUDE.md)         │
│   ├─ User              (~/.claude/CLAUDE.md)            │
│   ├─ Project            (./CLAUDE.md)                   │
│   ├─ Local              (./CLAUDE.local.md)             │
│   ├─ Rules              (.claude/rules/*.md)            │
│   └─ @imports            (재귀, 최대 5홉)                │
│                                                         │
│  Auto Memory (첫 200줄만)                                │
│   └─ ~/.claude/projects/<project>/memory/MEMORY.md      │
│                                                         │
│  Git Status 스냅샷                                       │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─── 세션 중 ────────────────────────────────────────────┐
│  Claude가 Write/Edit 도구로 MEMORY.md 및 토픽 파일 수정  │
│  필요 시 토픽 파일을 Read로 직접 읽기                     │
│  컴팩션 시 CLAUDE.md 재로드 + MEMORY.md 재로드            │
└─────────────────────────────────────────────────────────┘
```

- **에이전트 분업 없음** — Claude 자신이 기억의 생성/조회/정리를 모두 수행
- **파일 기반** — SQLite 같은 DB 없이 Markdown 파일로 관리
- **200줄 하드 리밋** — 컨텍스트 오염을 구조적으로 방지
- **토픽 파일은 온디맨드** — 항상 로드하지 않고 필요할 때만 Read

---

## 3. 핵심 메커니즘 비교

### 3.1 정보 입수 (Ingestion)

| | Always-On Memory Agent | Claude Code |
|:--|:--|:--|
| **입력 소스** | 27종 파일 (텍스트, 이미지, 오디오, 비디오, PDF) | 사용자 대화 + 코드베이스 |
| **입수 방식** | IngestAgent가 자동 처리 (파일 워처, HTTP API) | Claude가 대화 중 판단하여 Write |
| **구조화** | 자동 추출 (summary, entities, topics, importance) | 시맨틱 토픽별 마크다운 |
| **멀티모달** | 네이티브 지원 (이미지→설명, 오디오→전사) | 텍스트 중심 |
| **트리거** | 파일 드롭 즉시 / API 호출 즉시 | Claude의 자체 판단 |

Always-On Memory Agent는 **수동적 입수** (파일이 오면 처리)이고, Claude Code는 **능동적 판단** (기억할 가치가 있는지 Claude가 결정)이다.

### 3.2 기억 정리 (Consolidation)

| | Always-On Memory Agent | Claude Code |
|:--|:--|:--|
| **메커니즘** | ConsolidateAgent (30분 주기 자동) | 없음 (수동 정리만) |
| **방식** | 미통합 메모리 검토 → 연결 식별 → 크로스커팅 인사이트 생성 → 압축 | 사용자/Claude가 MEMORY.md 직접 편집 |
| **비유** | 수면 중 기억 정리 (뇌의 consolidation) | 의식적 메모 정리 |
| **자동화** | 완전 자동 | 프롬프트로 유도 ("Update or remove memories that turn out to be wrong") |

이것이 가장 큰 구조적 차이다. Always-On Memory Agent는 **별도 에이전트가 주기적으로 기억을 재구성**하지만, Claude Code는 **정리 프로세스가 없다**. Claude Code의 Auto Memory는 쓰면 그대로 남는다.

### 3.3 질의 (Query)

| | Always-On Memory Agent | Claude Code |
|:--|:--|:--|
| **방식** | QueryAgent가 전체 메모리 + 통합 인사이트를 읽고 답변 | 세션 시작 시 MEMORY.md 200줄 자동 로드 |
| **출처 추적** | 소스 인용 포함 | 없음 |
| **검색** | 자연어 질의 → 전체 DB 스캔 | Grep으로 메모리 디렉토리 검색 (Feature Flag: `tengu_coral_fern`) |
| **온디맨드 조회** | API 엔드포인트 (`/query?q=...`) | 파일 도구로 토픽 파일 직접 Read |

---

## 4. 저장소 설계

| | Always-On Memory Agent | Claude Code |
|:--|:--|:--|
| **스토리지** | SQLite (`memory.db`) | 파일시스템 (Markdown) |
| **스키마** | 구조화 (summary, entities, topics, importance, timestamp) | 비구조화 (자유 마크다운) 또는 반구조화 (frontmatter 타입) |
| **용량 제한** | 없음 (SQLite 한도까지) | MEMORY.md 200줄, 토픽 파일 무제한 (단, 읽을 때 컨텍스트 소비) |
| **만료/TTL** | 없음 | 없음 (OMC의 Shared Memory만 TTL 지원) |
| **백업** | 없음 (DB 파일 자체 백업) | git에 포함 가능 (CLAUDE.md), 또는 로컬만 (Auto Memory) |
| **공유** | 단일 인스턴스 (로컬) | CLAUDE.md: 팀 공유 (소스 컨트롤), Auto Memory: 머신 로컬 |

---

## 5. 컨텍스트 윈도우 관리

이 부분에서 두 시스템의 철학 차이가 가장 극명하게 드러난다.

### Always-On Memory Agent
- **컨텍스트 윈도우 개념이 사실상 없다** — 에이전트가 매 질의마다 전체 메모리를 읽음
- 메모리가 커지면 ConsolidateAgent가 압축하지만, **근본적으로는 "다 읽기"**
- Gemini Flash-Lite의 저비용 + 저지연에 의존하여 무차별 전체 스캔 가능

### Claude Code
- **컨텍스트 윈도우가 핵심 제약** — 200줄 리밋, 컴팩션, 온디맨드 읽기 모두 이 제약에서 파생
- "얼마나 적게, 정확하게 꺼내느냐"가 설계 원칙
- 컴팩션 시 CLAUDE.md 100% 생존, Auto Memory 재로드 → 지시사항 불변성 보장

```
Always-On Memory Agent:
  메모리 ──[전부]──→ QueryAgent 컨텍스트 ──→ 응답
  (크기 무관)         (매번 전체 로드)

Claude Code:
  CLAUDE.md ──[전체]──→ 컨텍스트
  MEMORY.md ──[200줄]──→ 컨텍스트           ──→ 응답
  토픽 파일 ──[온디맨드]──→ 컨텍스트 (필요할 때만)
```

---

## 6. 스코프와 범위

| | Always-On Memory Agent | Claude Code |
|:--|:--|:--|
| **메모리 범위** | 단일 인스턴스 (모든 입력이 하나의 DB) | 다중 스코프 (Managed → User → Project → Local) |
| **팀 공유** | 없음 (로컬 서비스) | CLAUDE.md: 소스 컨트롤로 팀 공유 |
| **조직 정책** | 없음 | Managed Policy CLAUDE.md (IT/DevOps 관리, 제외 불가) |
| **프로젝트 격리** | 없음 (단일 DB) | git 리포 단위로 Auto Memory 격리 |
| **조건부 적용** | 없음 | `.claude/rules/*.md`의 YAML frontmatter `paths` 필드로 파일 패턴별 규칙 적용 |

Claude Code의 **계층적 스코프 시스템**은 소프트웨어 개발 팀의 현실을 반영한다: 조직 정책 > 프로젝트 규칙 > 개인 선호. Always-On Memory Agent는 개인용 메모리 서비스로 설계되어 이런 계층이 없다.

---

## 7. 운영 특성

| | Always-On Memory Agent | Claude Code |
|:--|:--|:--|
| **가동 방식** | 24/7 상시 서버 | 세션 기반 (CLI 실행 시만) |
| **리소스 소비** | 상시 (파일 워처, 30분 주기 정리, HTTP 서버) | 세션 중만 |
| **모델** | Gemini Flash-Lite (저비용, 상시 가동 최적화) | Claude Opus/Sonnet (고성능, 세션 단위) |
| **확장성** | 수평 확장 어려움 (단일 SQLite) | 파일 기반이라 git/파일시스템으로 자연스럽게 확장 |
| **UI** | Streamlit 대시보드 | CLI + `/memory` 명령 |

---

## 8. 강점과 약점

### Always-On Memory Agent의 강점
- **멀티모달 입수**: 이미지, 오디오, 비디오까지 자동 처리
- **자동 정리**: ConsolidateAgent가 기억을 주기적으로 재구성
- **크로스커팅 인사이트**: 서로 다른 소스의 정보를 연결하여 새로운 통찰 생성
- **간단한 API**: HTTP 엔드포인트로 외부 시스템과 쉽게 연동

### Always-On Memory Agent의 약점
- **컨텍스트 오염 위험**: 메모리가 커지면 전체 스캔 비용 증가, 관련 없는 정보가 응답에 영향
- **구조적 필터링 부재**: 미들웨어 레이어 없이 전체 메모리를 QueryAgent에 전달
- **팀/조직 지원 없음**: 개인용 서비스로만 설계
- **상시 가동 비용**: 24/7 서버 유지 필요

### Claude Code의 강점
- **컨텍스트 효율성**: 200줄 하드 리밋 + 온디맨드 읽기로 컨텍스트 오염 최소화
- **계층적 스코프**: 조직 → 프로젝트 → 개인으로 자연스러운 정책 상속
- **팀 협업**: CLAUDE.md를 소스 컨트롤에 커밋하여 팀 전체가 동일한 규칙 공유
- **컴팩션 내성**: CLAUDE.md 100% 생존, Auto Memory 재로드로 긴 세션에서도 지시사항 유지
- **조건부 규칙**: 파일 패턴별로 다른 규칙 적용 (API 코드 vs 프론트엔드 코드)

### Claude Code의 약점
- **자동 정리 부재**: 기억이 쌓이기만 하고 자동으로 재구성되지 않음
- **텍스트 중심**: 멀티모달 메모리 미지원
- **크로스커팅 인사이트 없음**: 서로 다른 메모리 간 연결을 자동으로 발견하지 않음
- **검색 한계**: 현재는 Grep 기반 단순 검색 (향후 `tengu_coral_fern`으로 개선 예정)

---

## 9. 핵심 인사이트

### 9.1 "기억한다"의 의미가 다르다

Always-On Memory Agent에서 "기억"은 **정보의 축적과 검색**이다. 더 많이 기억할수록 좋다.

Claude Code에서 "기억"은 **행동의 지시와 맥락**이다. 정확하게 기억할수록 좋다.

이는 각 시스템의 목적에서 비롯된다:
- Always-On Memory Agent: **범용 지식 관리** ("내가 읽은 논문에서 뭐라고 했지?")
- Claude Code: **개발 워크플로 최적화** ("이 프로젝트에서는 어떤 규칙을 따라야 하지?")

### 9.2 Consolidation의 가치

Always-On Memory Agent의 ConsolidateAgent는 흥미로운 개념이다. 인간의 수면 중 기억 정리를 모방하여, 원시 메모리를 주기적으로 재구성한다. Claude Code에는 이에 해당하는 메커니즘이 없다.

그러나 Claude Code의 맥락에서 consolidation이 꼭 필요한지는 의문이다:
- CLAUDE.md는 사용자가 **의식적으로 큐레이션**하는 지시사항이므로 자동 정리가 불필요
- Auto Memory는 200줄 리밋으로 **물리적으로 비대해질 수 없음**
- 코드베이스 자체가 **권위적 소스**이므로 기억보다 코드를 직접 읽는 것이 정확

### 9.3 Push vs Pull의 트레이드오프

```
Always-On Memory Agent (Push):
  장점: 항상 모든 맥락이 준비되어 있음
  단점: 관련 없는 정보도 컨텍스트에 포함 → noise

Claude Code (Pull):
  장점: 필요한 것만 가져옴 → 컨텍스트 효율적
  단점: 가져오는 것을 잊으면 기억이 없는 것과 같음
```

Claude Code는 이 trade-off를 CLAUDE.md(Push, 항상 로드)와 Auto Memory 토픽 파일(Pull, 온디맨드)의 이중 구조로 해결한다. **규칙은 Push, 지식은 Pull**.

### 9.4 소프트웨어 개발 맥락에서의 적합성

소프트웨어 개발에서는 Claude Code의 접근이 더 적합하다:
1. **코드가 곧 기억** — git history, 파일 구조, 테스트가 이미 "기억"의 역할을 함
2. **팀 규칙이 개인 기억보다 중요** — 조직 정책/프로젝트 규칙이 개인의 과거 경험보다 우선
3. **컨텍스트 윈도우는 유한** — 무한히 기억하는 것보다 정확하게 꺼내는 것이 가치 있음

반면, **리서치/지식 관리** 맥락에서는 Always-On Memory Agent의 접근이 유리하다:
1. 다양한 소스(논문, 이미지, 영상)에서 정보를 수집해야 함
2. 서로 다른 소스 간 연결(크로스커팅 인사이트)이 핵심 가치
3. "무엇을 기억해야 하는지" 사전에 알 수 없음

---

## 10. 결론

두 시스템은 **같은 문제("AI의 망각")를 정반대 방향에서 접근**한다.

| | Always-On Memory Agent | Claude Code |
|:--|:--|:--|
| **철학** | 모든 것을 기억하고 정리한다 | 최소한만 기억하고 나머지는 코드에서 읽는다 |
| **최적 사용처** | 범용 지식 관리, 리서치 | 소프트웨어 개발 워크플로 |
| **핵심 혁신** | Consolidation (자동 기억 재구성) | 계층적 스코프 + 컨텍스트 효율성 |

궁극적으로 좋은 메모리 시스템의 기준은 **"얼마나 많이 기억하느냐"가 아니라 "얼마나 정확하게, 적시에, 최소한의 비용으로 꺼내느냐"**이다. 이 기준에서 Claude Code의 설계는 소프트웨어 개발이라는 도메인에 잘 맞춰져 있고, Always-On Memory Agent는 범용 지식 축적이라는 다른 도메인에 맞춰져 있다. 경쟁이 아니라 **상호 보완적 설계**다.
