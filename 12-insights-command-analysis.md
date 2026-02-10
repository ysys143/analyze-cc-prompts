# /insights 커맨드 동작 분석 (v2.1.38)

Claude Code의 `/insights` 커맨드는 사용자의 전체 세션 히스토리를 분석하여 **사용 패턴, 강점, 마찰점, 개선 제안**을 포함한 종합 리포트를 생성하는 기능이다.

---

## 1. 전체 아키텍처

```
사용자: /insights
     |
     v
+----------------------------------------------------------+
|  Phase 1: 세션 데이터 수집                                 |
|  +----------+    +-------------+    +--------------+     |
|  | 세션 디렉토리|---->| JSONL 로그   |---->| 메타데이터 추출|     |
|  | 스캔       |    | 파싱 (HT6)  |    | (FBA/m5z)   |     |
|  +----------+    +-------------+    +--------------+     |
|                                            |             |
|                                   캐시 확인/저장           |
|                                (~/.claude/usage-data/     |
|                                 session-meta/)            |
+----------------------------------------------------------+
     |
     v
+----------------------------------------------------------+
|  Phase 2: AI 기반 세션별 분석 (Facet Extraction)            |
|                                                          |
|  각 세션 -> Claude API 호출 -> 구조화된 JSON 추출            |
|  (목표, 만족도, 마찰점, 결과, 세션 유형 등)                   |
|                                                          |
|  캐시: ~/.claude/usage-data/facets/                       |
|  최대 50개 신규 세션 분석, 배치 크기 50                      |
+----------------------------------------------------------+
     |
     v
+----------------------------------------------------------+
|  Phase 3: 집계 (Aggregation)                              |
|                                                          |
|  모든 세션 메타 + 패싯 -> 통합 통계 객체 생성                 |
|  (도구 사용량, 언어, 목표 분류, 만족도, 마찰 등)               |
+----------------------------------------------------------+
     |
     v
+----------------------------------------------------------+
|  Phase 4: 7개 병렬 AI 분석 + 1개 최종 요약                  |
|                                                          |
|  +--------------+ +--------------+ +--------------+      |
|  |project_areas | |interaction   | |what_works    |      |
|  |(작업 영역)    | |_style        | |(성공 사례)    |      |
|  |              | |(상호작용 패턴) | |              |      |
|  +--------------+ +--------------+ +--------------+      |
|  +--------------+ +--------------+ +--------------+      |
|  |friction      | |suggestions   | |on_the_horizon|      |
|  |_analysis     | |(개선 제안)    | |(미래 기회)    |      |
|  |(마찰 분석)    | |              | |              |      |
|  +--------------+ +--------------+ +--------------+      |
|  +--------------+                                        |
|  |fun_ending    |  ->  +--------------+                   |
|  |(기억에 남는   |     |at_a_glance   |                   |
|  | 순간)        |     |(최종 요약)    |                   |
|  +--------------+     +--------------+                   |
+----------------------------------------------------------+
     |
     v
+----------------------------------------------------------+
|  Phase 5: 출력 생성                                       |
|                                                          |
|  +------------------+   +------------------+             |
|  | HTML 리포트 생성   |   | 터미널 마크다운    |             |
|  | (report.html)     |   | 요약 출력         |             |
|  | -> 브라우저에서 열기|   | -> CLI에 표시     |             |
|  +------------------+   +------------------+             |
+----------------------------------------------------------+
```

---

## 2. Phase 1: 세션 데이터 수집

### 2.1 세션 디렉토리 스캔 (`z9z`)

```javascript
// 모든 프로젝트 디렉토리를 순회하며 세션 JSONL 파일 발견
let q = oI(),        // ~/.claude/projects/ (세션 저장 경로)
    K = A.readdirSync(q);  // 프로젝트별 하위 디렉토리

// 각 디렉토리에서 세션 파일 목록 수집
// Rd1()로 세션 ID, 경로, mtime, size 추출
// mtime 기준 최신순 정렬
```

### 2.2 세션 메타데이터 추출 (`m5z` / `FBA`)

각 세션 JSONL 로그에서 다음 정보를 추출:

| 추출 항목 | 설명 |
|-----------|------|
| `toolCounts` | 도구별 사용 횟수 (Read, Edit, Bash 등) |
| `languages` | 파일 확장자 기반 언어 분포 (.ts->TypeScript 등) |
| `gitCommits` | `git commit` 명령 실행 횟수 |
| `gitPushes` | `git push` 명령 실행 횟수 |
| `inputTokens` / `outputTokens` | 총 토큰 사용량 |
| `userInterruptions` | 사용자가 요청을 중단한 횟수 |
| `userResponseTimes` | 사용자 응답 시간 (초) |
| `toolErrors` / `toolErrorCategories` | 도구 에러 횟수 및 분류 |
| `linesAdded` / `linesRemoved` | 추가/삭제된 코드 라인 수 |
| `filesModified` | 수정된 파일 수 |
| `messageHours` | 메시지 발송 시간대 (0-23시) |
| `usesTaskAgent` | Task 에이전트 사용 여부 |
| `usesMcp` | MCP 서버 사용 여부 |
| `usesWebSearch` / `usesWebFetch` | 웹 검색/가져오기 사용 여부 |

**코드 변경량 계산 방식:**
```javascript
// Edit 도구: diff 라이브러리(lo)로 old_string <-> new_string 비교
for (let l of lo(old_string, new_string)) {
    if (l.added) linesAdded += l.count;
    if (l.removed) linesRemoved += l.count;
}

// Write 도구: 전체 content의 줄 수를 추가로 카운트
linesAdded += content.split('\n').length;
```

**도구 에러 분류:**
```javascript
"Command Failed"    // exit code 에러
"User Rejected"     // 사용자가 거부
"Edit Failed"       // 문자열 교체 실패
"File Changed"      // 파일이 읽기 후 변경됨
"File Too Large"    // 파일 크기 초과
"File Not Found"    // 파일 없음
"Other"             // 기타
```

### 2.3 캐싱 시스템

```
~/.claude/usage-data/
├── session-meta/          # 세션 메타데이터 캐시
│   ├── {session_id}.json
│   └── ...
├── facets/                # AI 분석 결과 캐시
│   ├── {session_id}.json
│   └── ...
└── report.html            # 최종 HTML 리포트
```

- 이미 분석된 세션은 캐시에서 로드 -> **재분석 방지**
- 새 세션만 API 호출로 분석 -> **비용 절감**

---

## 3. Phase 2: AI 기반 패싯 추출 (Facet Extraction)

### 3.1 세션 필터링

```javascript
// 분석 대상 제외 조건
function isInsightsQuery(session) {
    // 세션의 처음 5개 메시지에 insights 관련 프롬프트가 있으면 제외
    // (자기 자신의 분석 세션을 분석하지 않도록)
}

// 유효 세션 조건
function isValidSession(meta) {
    return meta.user_message_count >= 2    // 최소 2개 사용자 메시지
        && meta.duration_minutes >= 1;     // 최소 1분 이상
}
```

### 3.2 긴 세션 요약 (`p5z` / `U5z`)

세션 트랜스크립트가 30,000자를 초과하면:
1. 25,000자씩 분할
2. 각 청크를 AI로 요약 (별도 API 호출)
3. 요약들을 합쳐서 패싯 추출에 사용

**요약 프롬프트:**
```
Summarize this portion of a Claude Code session transcript. Focus on:
1. What the user asked for
2. What Claude did (tools used, files modified)
3. Any friction or issues
4. The outcome

Keep it concise - 3-5 sentences. Preserve specific details like file names,
error messages, and user feedback.
```

### 3.3 패싯 추출 프롬프트 (핵심)

```
Analyze this Claude Code session and extract structured facets.

CRITICAL GUIDELINES:

1. **goal_categories**: Count ONLY what the USER explicitly asked for.
   - DO NOT count Claude's autonomous codebase exploration
   - DO NOT count work Claude decided to do on its own
   - ONLY count when user says "can you...", "please...", "I need...", "let's..."

2. **user_satisfaction_counts**: Base ONLY on explicit user signals.
   - "Yay!", "great!", "perfect!" -> happy
   - "thanks", "looks good", "that works" -> satisfied
   - "ok, now let's..." (continuing without complaint) -> likely_satisfied
   - "that's not right", "try again" -> dissatisfied
   - "this is broken", "I give up" -> frustrated

3. **friction_counts**: Be specific about what went wrong.
   - misunderstood_request: Claude interpreted incorrectly
   - wrong_approach: Right goal, wrong solution method
   - buggy_code: Code didn't work correctly
   - user_rejected_action: User said no/stop to a tool call
   - excessive_changes: Over-engineered or changed too much

4. If very short or just warmup, use warmup_minimal for goal_category
```

**추출되는 JSON 스키마:**
```json
{
  "underlying_goal": "사용자가 근본적으로 달성하고자 한 것",
  "goal_categories": {"category_name": "count"},
  "outcome": "fully_achieved|mostly_achieved|partially_achieved|not_achieved|unclear_from_transcript",
  "user_satisfaction_counts": {"level": "count"},
  "claude_helpfulness": "unhelpful|slightly_helpful|moderately_helpful|very_helpful|essential",
  "session_type": "single_task|multi_task|iterative_refinement|exploration|quick_question",
  "friction_counts": {"friction_type": "count"},
  "friction_detail": "마찰 설명 한 문장",
  "primary_success": "none|fast_accurate_search|correct_code_edits|good_explanations|proactive_help|multi_file_changes|good_debugging",
  "brief_summary": "한 문장 요약: 사용자가 원한 것과 결과"
}
```

### 3.4 "warmup" 세션 필터링

패싯 추출 후, `warmup_minimal` 카테고리만 있는 세션은 최종 통계에서 제외:

```javascript
// 단일 goal_category가 "warmup_minimal"인 세션 제거
const isWarmup = (sessionId) => {
    let facets = P.get(sessionId);
    let goals = facets.goal_categories;
    let nonZero = Object.keys(goals).filter(k => goals[k] > 0);
    return nonZero.length === 1 && nonZero[0] === "warmup_minimal";
};
```

---

## 4. Phase 3: 데이터 집계

`o5z` 함수에서 모든 세션 메타 + 패싯을 합산:

```javascript
// 집계 결과 구조
{
  total_sessions,                // 총 세션 수
  sessions_with_facets,          // AI 분석 완료된 세션 수
  date_range: { start, end },    // 기간
  total_messages,                // 총 메시지 수
  total_duration_hours,          // 총 사용 시간
  total_input_tokens,            // 총 입력 토큰
  total_output_tokens,           // 총 출력 토큰
  tool_counts: {},               // 도구별 사용 횟수
  languages: {},                 // 언어별 사용 횟수
  git_commits,                   // 총 커밋 수
  git_pushes,                    // 총 푸시 수
  projects: {},                  // 프로젝트별 세션 수
  goal_categories: {},           // 목표 분류
  outcomes: {},                  // 결과 분포
  satisfaction: {},              // 만족도 분포
  helpfulness: {},               // 도움 정도 분포
  session_types: {},             // 세션 유형 분포
  friction: {},                  // 마찰 유형 분포
  success: {},                   // 성공 요인 분포
  session_summaries: [],         // 최대 50개 세션 요약
  total_interruptions,           // 총 중단 횟수
  total_tool_errors,             // 총 도구 에러
  tool_error_categories: {},     // 에러 유형 분포
  user_response_times: [],       // 응답 시간 배열
  median_response_time,          // 중간값
  avg_response_time,             // 평균값
  sessions_using_task_agent,     // Task 에이전트 사용 세션 수
  sessions_using_mcp,            // MCP 사용 세션 수
  sessions_using_web_search,     // 웹 검색 사용 세션 수
  sessions_using_web_fetch,      // 웹 가져오기 사용 세션 수
  total_lines_added,             // 총 추가 라인
  total_lines_removed,           // 총 삭제 라인
  total_files_modified,          // 총 수정 파일
  days_active,                   // 활성 일수
  messages_per_day,              // 일평균 메시지
  message_hours: [],             // 시간대별 메시지
  multi_clauding: {}             // 병렬 세션 사용 분석
}
```

### 4.1 Multi-Clauding 감지 (`r5z`)

사용자가 여러 Claude Code 세션을 **동시에** 사용하는 패턴을 감지:

```javascript
// 알고리즘:
// 1. 모든 세션의 사용자 메시지 타임스탬프를 시간순 정렬
// 2. 30분(1800000ms) 슬라이딩 윈도우 적용
// 3. 윈도우 내에서 다른 세션의 메시지가 있으면 overlap_event
//
// 결과:
// - overlap_events: 겹침 이벤트 수
// - sessions_involved: 관련 세션 수
// - user_messages_during: 겹침 중 발송된 메시지 수
```

---

## 5. Phase 4: 7개 병렬 AI 분석 프롬프트

집계된 데이터를 기반으로 7개의 분석 프롬프트가 **동시에** 실행된다.

### 5.1 project_areas (작업 영역)

```
Analyze this Claude Code usage data and identify project areas.

RESPOND WITH ONLY A VALID JSON OBJECT:
{
  "areas": [
    {"name": "Area name", "session_count": N,
     "description": "2-3 sentences about what was worked on..."}
  ]
}

Include 4-5 areas. Skip internal CC operations.
```
-> maxTokens: 8192

### 5.2 interaction_style (상호작용 패턴)

```
Analyze this Claude Code usage data and describe the user's interaction style.

RESPOND WITH ONLY A VALID JSON OBJECT:
{
  "narrative": "2-3 paragraphs analyzing HOW the user interacts with Claude Code.
                Use second person 'you'. Describe patterns: iterate quickly vs
                detailed upfront specs? Interrupt often or let Claude run?
                Include specific examples. Use **bold** for key insights.",
  "key_pattern": "One sentence summary of most distinctive interaction style"
}
```
-> maxTokens: 8192

### 5.3 what_works (성공 사례)

```
Analyze this Claude Code usage data and identify what's working well
for this user. Use second person ("you").

RESPOND WITH ONLY A VALID JSON OBJECT:
{
  "intro": "1 sentence of context",
  "impressive_workflows": [
    {"title": "Short title (3-6 words)",
     "description": "2-3 sentences describing the impressive workflow.
                     Use 'you' not 'the user'."}
  ]
}

Include 3 impressive workflows.
```
-> maxTokens: 8192

### 5.4 friction_analysis (마찰 분석)

```
Analyze this Claude Code usage data and identify friction points
for this user. Use second person ("you").

RESPOND WITH ONLY A VALID JSON OBJECT:
{
  "intro": "1 sentence summarizing friction patterns",
  "categories": [
    {"category": "Concrete category name",
     "description": "1-2 sentences explaining this category...",
     "examples": ["Specific example with consequence",
                  "Another example"]}
  ]
}

Include 3 friction categories with 2 examples each.
```
-> maxTokens: 8192

### 5.5 suggestions (개선 제안)

이 프롬프트는 Claude Code의 기능 레퍼런스를 포함하고 있어 가장 길다:

```
Analyze this Claude Code usage data and suggest improvements.

## CC FEATURES REFERENCE (pick from these for features_to_try):
1. **MCP Servers**: Connect Claude to external tools, databases, and APIs
   via Model Context Protocol.
   - How to use: Run `claude mcp add <server-name> -- <command>`
   - Good for: database queries, Slack integration, GitHub issue lookup

2. **Custom Skills**: Reusable prompts you define as markdown files
   that run with a single /command.
   - How to use: Create `.claude/skills/commit/SKILL.md` with instructions.
   - Good for: repetitive workflows - /commit, /review, /test, /deploy

3. **Hooks**: Shell commands that auto-run at specific lifecycle events.
   - How to use: Add to `.claude/settings.json` under "hooks" key.
   - Good for: auto-formatting code, running type checks

4. **Headless Mode**: Run Claude non-interactively from scripts and CI/CD.
   - How to use: `claude -p "fix lint errors" --allowedTools "Edit,Read,Bash"`
   - Good for: CI/CD integration, batch code fixes

5. **Task Agents**: Claude spawns focused sub-agents for complex exploration.
   - How to use: Claude auto-invokes when helpful, or ask
     "use an agent to explore X"

RESPOND WITH ONLY A VALID JSON OBJECT:
{
  "claude_md_additions": [
    {"addition": "CLAUDE.md에 추가할 구체적 내용",
     "why": "왜 도움이 되는지 1문장",
     "prompt_scaffold": "CLAUDE.md 어디에 추가할지 안내"}
  ],
  "features_to_try": [
    {"feature": "기능명",
     "one_liner": "한 줄 설명",
     "why_for_you": "이 사용자에게 도움이 되는 이유",
     "example_code": "복사 가능한 명령/설정"}
  ],
  "usage_patterns": [
    {"title": "짧은 제목",
     "suggestion": "1-2문장 요약",
     "detail": "3-4문장 상세 설명",
     "copyable_prompt": "복사해서 시도할 수 있는 프롬프트"}
  ]
}

IMPORTANT for claude_md_additions: PRIORITIZE instructions that appear
MULTIPLE TIMES in the user data. If user told Claude the same thing in
2+ sessions, that's a PRIME candidate - they shouldn't have to repeat
themselves.
```
-> maxTokens: 8192

### 5.6 on_the_horizon (미래 기회)

```
Analyze this Claude Code usage data and identify future opportunities.

RESPOND WITH ONLY A VALID JSON OBJECT:
{
  "intro": "1 sentence about evolving AI-assisted development",
  "opportunities": [
    {"title": "Short title (4-8 words)",
     "whats_possible": "2-3 ambitious sentences about autonomous workflows",
     "how_to_try": "1-2 sentences mentioning relevant tooling",
     "copyable_prompt": "Detailed prompt to try"}
  ]
}

Include 3 opportunities. Think BIG - autonomous workflows,
parallel agents, iterating against tests.
```
-> maxTokens: 8192

### 5.7 fun_ending (기억에 남는 순간)

```
Analyze this Claude Code usage data and find a memorable moment.

RESPOND WITH ONLY A VALID JSON OBJECT:
{
  "headline": "A memorable QUALITATIVE moment from the transcripts -
               not a statistic. Something human, funny, or surprising.",
  "detail": "Brief context about when/where this happened"
}

Find something genuinely interesting or amusing from the session summaries.
```
-> maxTokens: 8192

### 5.8 at_a_glance (최종 요약) - Phase 4 결과 합성

7개 분석이 완료된 후, 그 결과들을 종합하여 최종 요약을 생성:

```
You're writing an "At a Glance" summary for a Claude Code usage insights
report. The goal is to help users understand their usage and improve how
they can use Claude better, especially as models improve.

Use this 4-part structure:

1. **What's working** - What is the user's unique style of interacting
   with Claude and what are some impactful things they've done?
   Don't be fluffy or overly complimentary.

2. **What's hindering you** - Split into (a) Claude's fault
   (misunderstandings, wrong approaches, bugs) and (b) user-side friction.
   Be honest but constructive.

3. **Quick wins to try** - Specific Claude Code features they could try.

4. **Ambitious workflows for better models** - As we move to much more
   capable models over the next 3-6 months, what should they prepare for?

Keep each section to 2-3 not-too-long sentences. Don't mention specific
numerical stats. Use a coaching tone.

RESPOND WITH ONLY A VALID JSON OBJECT:
{
  "whats_working": "...",
  "whats_hindering": "...",
  "quick_wins": "...",
  "ambitious_workflows": "..."
}

SESSION DATA:
[집계 통계]

## Project Areas (what user works on)
[project_areas 결과]

## Big Wins (impressive accomplishments)
[what_works 결과]

## Friction Categories (where things go wrong)
[friction_analysis 결과]

## Features to Try
[suggestions.features_to_try 결과]

## Usage Patterns to Adopt
[suggestions.usage_patterns 결과]

## On the Horizon
[on_the_horizon 결과]
```

---

## 6. Phase 5: 출력 생성

### 6.1 HTML 리포트 (`Y9z`)

`~/.claude/usage-data/report.html`에 저장되는 독립형 HTML 파일:

**리포트 구조:**
```
+-------------------------------------+
|  Claude Code Insights                |
|  [Messages] [Lines] [Files] [Days]   |
|                                      |
|  +- At a Glance (금색 배경) -------+  |
|  |  What's working                 |  |
|  |  What's hindering               |  |
|  |  Quick wins                     |  |
|  |  Ambitious workflows            |  |
|  +---------------------------------+  |
|                                      |
|  +- Charts (2x2 그리드) ----------+  |
|  |  What You Wanted | Top Tools    |  |
|  |  Languages       | Types        |  |
|  +---------------------------------+  |
|                                      |
|  [Response Time Distribution]         |
|  [Multi-Clauding Detection]           |
|  [Time of Day + Tool Errors]          |
|                                      |
|  [*] What You Work On (프로젝트 영역) |
|  [*] How You Use CC (상호작용 패턴)   |
|  [*] Impressive Things (성공 사례)    |
|  [*] Where Things Go Wrong (마찰점)  |
|  [*] Outcomes + Satisfaction          |
|                                      |
|  [>] CLAUDE.md Suggestions            |
|      (체크박스 + 복사 버튼 포함)       |
|  [>] Features to Try                  |
|  [>] New Usage Patterns               |
|  [>] On the Horizon (보라색 카드)      |
|                                      |
|  [~] Fun Ending (금색 배경)            |
|  [v] Session List (접이식)             |
+--------------------------------------+
```

**주요 인터랙티브 기능:**
- 시간대 선택기 (PT/ET/London/CET/Tokyo/Custom)
- CLAUDE.md 제안사항 체크박스 + "Copy selected" 버튼
- 코드/프롬프트 복사 버튼
- 세션 목록 접이식(collapsible) 토글

### 6.2 터미널 출력

사용자가 CLI에서 보는 마크다운 요약:

```markdown
# Claude Code Insights

[N] sessions - [N] messages - [N]h - [N] commits
YYYY-MM-DD to YYYY-MM-DD

## At a Glance

**What's working:** [요약]
**What's hindering you:** [요약]
**Quick wins to try:** [요약]
**Ambitious workflows:** [요약]

Your full shareable insights report is ready: file:///path/report.html
```

### 6.3 모델에 전달되는 최종 프롬프트

`/insights` 실행 후 Claude에게 전달되는 프롬프트:

```
The user just ran /insights to generate a usage report analyzing
their Claude Code sessions.

Here is the full insights data:
[전체 insights JSON]

Report URL: file:///path/report.html
HTML file: /path/report.html
Facets directory: ~/.claude/usage-data/facets/

Here is what the user sees:
[터미널 마크다운 요약]

Now output the following message exactly:

<message>
Your shareable insights report is ready:
file:///path/report.html

Want to dig into any section or try one of the suggestions?
</message>
```

---

## 7. API 호출 모델 선택

```javascript
// 패싯 추출 (세션별 분석): fOq() 사용
// -> _u() -> 현재 사용 중인 모델과 동일

// 7개 병렬 분석: I5z() 사용
// -> _u() -> 현재 사용 중인 모델과 동일

// 공통 옵션:
{
    querySource: "insights",          // 쿼리 출처 태그
    agents: [],                       // 에이전트 없음
    isNonInteractiveSession: true,    // 비대화형
    hasAppendSystemPrompt: false,     // 시스템 프롬프트 추가 없음
    mcpTools: [],                     // MCP 도구 없음
    maxOutputTokensOverride: 500~8192 // 프롬프트별 다름
}
```

---

## 8. 카테고리 라벨 매핑 (`b5z`)

코드 내부에서 사용되는 카테고리 키와 사용자에게 표시되는 라벨 매핑:

### 목표 카테고리 (goal_categories)

| 내부 키 | 표시 라벨 |
|---------|----------|
| `debug_investigate` | Debug/Investigate |
| `implement_feature` | Implement Feature |
| `fix_bug` | Fix Bug |
| `write_script_tool` | Write Script/Tool |
| `refactor_code` | Refactor Code |
| `configure_system` | Configure System |
| `create_pr_commit` | Create PR/Commit |
| `analyze_data` | Analyze Data |
| `understand_codebase` | Understand Codebase |
| `write_tests` | Write Tests |
| `write_docs` | Write Docs |
| `deploy_infra` | Deploy/Infra |
| `warmup_minimal` | Cache Warmup |

### 만족도 수준 (satisfaction)

| 내부 키 | 표시 라벨 |
|---------|----------|
| `frustrated` | Frustrated |
| `dissatisfied` | Dissatisfied |
| `likely_satisfied` | Likely Satisfied |
| `satisfied` | Satisfied |
| `happy` | Happy |
| `unsure` | Unsure |
| `neutral` | Neutral |
| `delighted` | Delighted |

### 결과 (outcomes)

| 내부 키 | 표시 라벨 |
|---------|----------|
| `fully_achieved` | Fully Achieved |
| `mostly_achieved` | Mostly Achieved |
| `partially_achieved` | Partially Achieved |
| `not_achieved` | Not Achieved |
| `unclear_from_transcript` | Unclear |

### 마찰 유형 (friction)

| 내부 키 | 표시 라벨 |
|---------|----------|
| `misunderstood_request` | Misunderstood Request |
| `wrong_approach` | Wrong Approach |
| `buggy_code` | Buggy Code |
| `user_rejected_action` | User Rejected Action |
| `claude_got_blocked` | Claude Got Blocked |
| `user_stopped_early` | User Stopped Early |
| `wrong_file_or_location` | Wrong File/Location |
| `excessive_changes` | Excessive Changes |
| `slow_or_verbose` | Slow/Verbose |
| `tool_failed` | Tool Failed |
| `user_unclear` | User Unclear |
| `external_issue` | External Issue |

### 성공 요인 (success)

| 내부 키 | 표시 라벨 |
|---------|----------|
| `fast_accurate_search` | Fast/Accurate Search |
| `correct_code_edits` | Correct Code Edits |
| `good_explanations` | Good Explanations |
| `proactive_help` | Proactive Help |
| `multi_file_changes` | Multi-file Changes |
| `good_debugging` | Good Debugging |

---

## 9. 파일 확장자 -> 언어 매핑

```javascript
{
  ".ts": "TypeScript",  ".tsx": "TypeScript",
  ".js": "JavaScript",  ".jsx": "JavaScript",
  ".py": "Python",      ".rb": "Ruby",
  ".go": "Go",          ".rs": "Rust",
  ".java": "Java",      ".md": "Markdown",
  ".json": "JSON",      ".yaml": "YAML",
  ".yml": "YAML",       ".sh": "Shell",
  ".css": "CSS",        ".html": "HTML"
}
```

---

## 10. /stats 커맨드 (관련 기능)

`/insights`와 별도로 `/stats` 커맨드도 존재한다. `/stats`는 **TUI(Terminal UI)** 기반의 실시간 사용 통계 뷰어:

| 항목 | /stats | /insights |
|------|--------|-----------|
| **출력 형식** | TUI (Ink/React) | HTML 리포트 + 마크다운 |
| **AI 분석** | 없음 (순수 통계) | 9회 이상 API 호출 |
| **포함 데이터** | 사용량, 모델, 스트릭 | + 목표, 만족도, 마찰, 제안 |
| **인터랙션** | 키보드 네비게이션 | 브라우저에서 열기 |
| **기간 선택** | 7일/30일/전체 | 전체 |
| **비용** | 무료 (로컬 계산) | 토큰 비용 발생 |

### /stats의 재미 요소

토큰 사용량을 유명 서적과 비교:
```javascript
[
  {name: "The Little Prince", tokens: 22000},
  {name: "The Great Gatsby", tokens: 62000},
  {name: "1984", tokens: 123000},
  {name: "Dune", tokens: 244000},
  {name: "War and Peace", tokens: 730000}
  // ... 총 24권
]
```

세션 길이를 활동과 비교:
```javascript
[
  {name: "a TED talk", minutes: 18},
  {name: "an episode of The Office", minutes: 22},
  {name: "a yoga class", minutes: 60},
  {name: "the movie Inception", minutes: 148},
  {name: "a full night of sleep", minutes: 480}
  // ... 총 10개
]
```

---

## 11. 핵심 설계 특징 요약

1. **다단계 AI 파이프라인**: 세션별 패싯 추출 -> 집계 -> 7개 병렬 분석 -> 최종 요약 = 최소 9+N회의 API 호출
2. **적극적 캐싱**: 세션 메타데이터와 패싯을 디스크에 캐시하여 반복 실행 시 비용 절감
3. **warmup 세션 필터링**: 의미 없는 짧은 세션을 자동 제외
4. **Multi-Clauding 감지**: 30분 슬라이딩 윈도우로 병렬 세션 사용 패턴 분석
5. **CLAUDE.md 자동 제안**: 반복되는 사용자 지시사항을 감지하여 CLAUDE.md에 추가할 내용 제안
6. **공유 가능한 HTML 리포트**: 독립형 HTML 파일로 생성되어 브라우저에서 열거나 공유 가능
7. **코칭 톤**: "Don't be fluffy or overly complimentary", "Be honest but constructive" 등의 지침으로 실질적 피드백 지향

---

## 12. 데이터 흐름 요약

```
[Session JSONL Logs]
        |
        v  m5z() - 로컬 파싱
[Session Metadata]  <->  [Cache: session-meta/]
        |
        v  n5z() - AI 호출 (세션당 1회)
[Session Facets]    <->  [Cache: facets/]
        |
        v  o5z() - 로컬 집계
[Aggregate Stats]
        |
        v  s5z() - 7개 병렬 AI 호출
[7 Analysis Results]
        |
        v  at_a_glance - 1개 최종 AI 호출
[Final Summary]
        |
        |---> Y9z() - HTML 리포트 생성 -> report.html
        |
        +---> getPromptForCommand() - 터미널 출력
                -> Claude가 사용자에게 결과 전달
```

---

## 13. v2.1.29와의 차이점

v2.1.29에는 `/insights` 커맨드가 **존재하지 않았다**. 이는 v2.1.38에서 새로 추가된 기능이다. v2.1.29에서 확인되는 관련 기능은 `/stats` (TUI 기반 통계 뷰어)뿐이었으며, AI 기반 사용 패턴 분석은 없었다.
