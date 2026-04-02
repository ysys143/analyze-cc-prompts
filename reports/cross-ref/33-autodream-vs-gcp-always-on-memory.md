# AutoDream vs GCP Always-On Memory Agent 비교 분석

분석 대상:
1. Claude Code AutoDream — 유출 TypeScript 소스 v2.1.88
2. GCP Always-On Memory Agent — GoogleCloudPlatform/generative-ai (2026-04-02 기준)
   저장소: `gemini/agents/always-on-memory-agent/`

---

## 1. 개요

두 시스템은 "LLM 에이전트에게 지속적 메모리를"이라는 동일한 문제를 다른 방향에서 접근한다.

AutoDream은 Claude Code 세션의 후처리기로 설계됐다.
GCP Always-On은 독립 프로세스로 상시 구동되는 메모리 서비스다.

---

## 2. 아키텍처 근본 철학

| 항목 | AutoDream (Claude Code) | GCP Always-On Memory Agent |
|------|------------------------|---------------------------|
| 실행 모델 | 세션 종료 후 포크드 서브에이전트 | 독립 Python 프로세스, 24/7 구동 |
| 트리거 | 세션 종료 훅 + 시간/세션 게이트 | asyncio 타이머 (기본 30분) + HTTP POST |
| 메모리 저장소 | 마크다운 파일 (`~/.claude/memory/`) | SQLite DB (3개 테이블) |
| 검색 방식 | 파일시스템 구조 + grep | LLM이 전체 테이블 풀스캔 |
| 에이전트 구조 | 단일 포크드 에이전트 | 오케스트레이터 + 전문 에이전트 3개 |
| 사용 모델 | Claude (포크드) | Gemini 3.1 Flash-Lite |

---

## 3. 통합(Consolidation) 흐름 비교

```
AutoDream                           GCP Always-On
--------------------                --------------------
세션 쌓임 (>=5개)                    메모리 쌓임 (>=2개)
     |                                    |
24h 경과                             30분 경과
     |                                    |
포크드 에이전트 1회 실행              consolidate_agent 호출
     |                                    |
마크다운 파일 직접 편집               DB rows + 연결 그래프 업데이트
(FileEdit/FileWrite 도구)            (store_consolidation())
     |                                    |
mtime 락 파일로 완료 기록             consolidated=1 플래그 기록
```

---

## 4. 메모리 저장 구조 비교

### 4.1 AutoDream — 자유 형식 마크다운

```
~/.claude/memory/
  MEMORY.md           <- 인덱스 (150자 이하 한 줄 포인터)
  user_role.md        <- 사용자 프로필
  feedback_testing.md <- 피드백 및 선호도
  project_auth.md     <- 프로젝트 컨텍스트
```

구조는 LLM 판단에 위임한다. 파일명과 섹션이 자연스러운 인덱스 역할을 한다.

### 4.2 GCP Always-On — 구조화된 SQLite 스키마

```sql
memories (
  id, source, raw_text, summary,
  entities TEXT,       -- JSON 배열
  topics TEXT,         -- JSON 배열
  connections TEXT,    -- JSON [{linked_to, relationship}]
  importance REAL,     -- LLM이 0~1 점수 부여
  consolidated INTEGER -- 처리 완료 플래그
)

consolidations (
  id, source_ids TEXT, -- 원본 memory ID 배열
  summary, insight,    -- 교차 인사이트
  created_at
)

processed_files (path, hash, processed_at)
```

LLM이 수집 시점에 엔티티/토픽 추출, 중요도 점수, 양방향 연결 그래프까지 직접 구조화한다.

---

## 5. LLM 호출 비용 비교

| 단계 | AutoDream | GCP Always-On |
|------|-----------|---------------|
| 수집(ingest) | 없음 (기존 API 응답 재활용) | 별도 LLM 호출 (ingest_agent) |
| 통합(consolidate) | 포크드 에이전트 1회 | 별도 LLM 호출 (consolidate_agent) |
| 조회(query) | 세션 시작 시 컨텍스트 파일 주입 | 별도 LLM 호출 (query_agent) |
| 정기 비용 | 세션당 0 (게이트 통과 시만 과금) | 30분마다 LLM 호출 가능 |

GCP는 수집-통합-조회 모두 독립 LLM 호출이다.
AutoDream은 수집 단계가 없고 조회는 파일 읽기로 해결한다.

---

## 6. 벡터 DB 부재라는 공통 선택

두 시스템 모두 벡터 DB와 임베딩을 사용하지 않는다.

### 6.1 AutoDream의 접근

1. 메모리를 마크다운 파일로 구조화 → 파일명/섹션이 자연스러운 인덱스
2. grep으로 좁은 검색
3. MEMORY.md 인덱스 파일로 전체 조망 (25KB 이하 유지)

### 6.2 GCP의 접근

1. LLM이 전체 테이블을 읽고 인컨텍스트에서 시맨틱 매칭
2. "벡터 DB 없이 LLM 자체가 검색 엔진" 철학을 명시적으로 표방
3. `read_all_memories`가 모든 row를 반환 → 컨텍스트에 주입

두 접근 모두 "LLM은 구조화된 텍스트를 이해할 수 있다"는 전제에 기반한다.
단, GCP의 풀스캔 방식은 메모리가 많아지면 컨텍스트 한도에 걸릴 수 있다.

---

## 7. 사용 맥락 비교

| 항목 | AutoDream | GCP Always-On |
|------|-----------|---------------|
| 대상 | Claude Code 내장 기능 (CLI 도구) | 독립 서비스로 배포 가능한 레퍼런스 아키텍처 |
| 입력 소스 | 세션 전사 파일 (.jsonl) | inbox 디렉토리 + HTTP API |
| 멀티모달 지원 | 없음 | 이미지/오디오/비디오/PDF 등 27가지 |
| 외부 API | 없음 (내부 전용) | HTTP REST API + Streamlit 대시보드 |
| 배포 방식 | Claude Code 내부 자동 실행 | `python agent.py --watch ./inbox --port 8888` |

---

## 8. 설계 철학 요약

### AutoDream: 최소 비용, 파일시스템 네이티브

1. 기존 세션 인프라에 기생 — 별도 프로세스 없음
2. 마크다운 파일 = 사람이 직접 읽고 편집 가능한 메모리
3. 게이트(시간 + 세션 수)로 비용 억제 — 대부분의 세션 종료에서 0 비용
4. 파일시스템 락으로 분산 안전성 확보

### GCP Always-On: 최대 구조화, 서비스형

1. 메모리를 독립 DB 서비스로 분리 — 어떤 클라이언트도 HTTP로 접근 가능
2. 수집 시점에 구조화 (엔티티, 중요도, 연결 그래프) — 나중에 재처리 불필요
3. 24/7 상시 구동 — 세션 경계와 무관하게 메모리 갱신
4. 멀티모달 입력 지원 — 파일 drop만으로 자동 수집

---

분석 소스:
1. 유출 TypeScript 소스 v2.1.88 (`src/services/autoDream/`)
2. GoogleCloudPlatform/generative-ai `gemini/agents/always-on-memory-agent/agent.py` (2026-04-02)
