# Native Binary Installer 분석

## 개요

Claude Code는 npm 패키지 외에도 **Native Installer**를 제공한다. 이는 Bun 런타임과 JavaScript 코드를 하나의 실행 파일로 번들링한 것으로, Node.js 설치 없이 독립적으로 실행 가능하다.

### 분석 환경

- **OS**: macOS (Darwin 25.2.0)
- **아키텍처**: ARM64 (Apple Silicon)
- **대상 바이너리**: Claude Code v2.1.29 Native installer
- **바이너리 경로**: `~/.local/share/claude/versions/2.1.29`
- **바이너리 크기**: 171MB
- **파일 형식**: Mach-O 64-bit executable arm64

---

## 1. Native vs npm 비교

### 1.1 설치 위치

**Native Installer:**
```bash
~/.local/share/claude/versions/
├── 2.1.20  (173MB)
├── 2.1.29  (171MB)
├── 2.1.32  (172MB)
└── 2.1.33  (173MB)

# 심볼릭 링크
~/.local/bin/claude -> ~/.local/share/claude/versions/2.1.33
```

**npm 패키지:**
```bash
~/.nvm/versions/node/v20.18.1/lib/node_modules/@anthropic-ai/claude-code/
├── cli.js (11.3MB)
├── package.json
├── node_modules/
└── vendor/
```

### 1.2 파일 형식 비교

| 항목 | Native v2.1.29 | npm v2.1.33 |
|------|----------------|-------------|
| **파일 형식** | Mach-O 64-bit ARM64 바이너리 | JavaScript |
| **전체 크기** | 171MB | 11.3MB (cli.js) + node_modules |
| **추출 코드 크기** | 13MB | 11.3MB |
| **라인 수** | 152,283 | 7,587 |
| **번들러** | Bun | (확인 필요) |
| **접근성** | strings 추출 필요 | 직접 읽기 가능 |
| **실행 속도** | 빠름 (Bun) | 보통 (Node.js) |

**주요 차이점:**
- Native 버전이 더 많은 코드 포함 (152k vs 7.5k 라인)
- Native에는 Bun 런타임 코드가 포함
- npm 버전은 외부 의존성을 node_modules에 분리

### 1.3 바이너리 구조

```
claude (171MB 실행 파일)
├─ Bun 런타임 (~100MB)
│  └─ 컴파일된 JavaScript 엔진 (C++/Zig)
│
├─ JavaScript 코드 (~13MB)
│  └─ Claude Code CLI 로직 (평문 문자열)
│
└─ 네이티브 모듈 (~58MB)
   ├─ image-processor.node
   ├─ color-diff.node
   ├─ file-index.node
   └─ ripgrep.node
```

---

## 2. 바이너리에서 코드 추출 방법

### 2.1 왜 추출이 가능한가?

**핵심 원리:**
- JavaScript는 컴파일 언어가 아님 (인터프리터 언어)
- Bun은 런타임 + JavaScript를 번들링 (기계어 변환 안 함)
- JavaScript 코드는 바이너리 내에 **평문 문자열**로 저장
- `strings` 명령어로 추출 가능

**실행 과정:**
```
1. 바이너리 실행
   ↓
2. Bun 런타임 시작 (컴파일된 C++ 코드)
   ↓
3. 내장된 JavaScript 문자열 읽기
   ↓
4. JavaScript 코드 파싱 및 실행
```

### 2.2 추출 단계

#### 1단계: 바이너리 문자열 추출

```bash
strings /Users/jaesolshin/.local/share/claude/versions/2.1.29 > native_v2.1.29_strings.txt
```

**결과:**
- 출력 파일: 29MB
- 라인 수: ~300,000줄

#### 2단계: 버전 마커 찾기

```bash
grep -n "// Version: 2.1.29" native_v2.1.29_strings.txt
```

**발견된 라인:**
```
114470:// Version: 2.1.29
266753:// Version: 2.1.29
271839:// Version: 2.1.29
...
```

첫 번째 발견(114470)이 메인 코드 블록의 시작점.

#### 3단계: JavaScript 코드 블록 추출

```bash
sed -n '114470,266752p' native_v2.1.29_strings.txt > native_v2.1.29_extracted.js
```

**결과:**
- 출력 파일: 13MB
- 라인 수: 152,283줄
- 상태: Minified (압축된 코드)

#### 4단계: 코드 구조 확인

```bash
head -50 native_v2.1.29_extracted.js
```

**발견 사항:**
```javascript
// Version: 2.1.29
var RH0=Object.create;
var{getPrototypeOf:AH0,defineProperty:Ee,getOwnPropertyNames:AdT,...}=Object
...
```

### 2.3 추출된 코드 특징

**번들러:** Bun 사용 확인
```javascript
require("/$bunfs/root/image-processor.node")  // 이미지 처리
require("/$bunfs/root/color-diff.node")       // 색상 비교
require("/$bunfs/root/file-index.node")       // 파일 인덱싱
require("/$bunfs/root/ripgrep.node")          // 코드 검색
```

**코드 형식:**
- Minified: 변수명 난독화 (예: `RH0`, `AH0`, `Ee`)
- ES 모듈: 현대적인 JavaScript 모듈 시스템
- CommonJS 호환: `require()` 및 `exports` 지원

---

## 3. strings 명령어 작동 원리

### 3.1 알고리즘

```
1. 바이너리 파일을 바이트 단위로 읽기
2. 연속된 출력 가능한 문자 찾기 (ASCII 32-126)
3. 4글자 이상이면 문자열로 간주
4. NULL(0x00)나 비출력 문자를 만나면 종료
5. 발견된 문자열 출력
```

### 3.2 실제 예시

바이너리 hexdump 예시:
```
000004c0  ... 48 65 6c 6c  6f 2c 20 74 68 69 73 20  |....Hello, this |
000004d0  69 73 20 65 6d 62 65 64  64 65 64 20 74 65 78 74  |is embedded text|
000004e0  21 00 66 75 6e 63 74 69  6f 6e 20 67 72 65 65 74  |!.function greet|
```

strings 결과:
```
Hello, this is embedded text!
function greet
```

### 3.3 strings 옵션

| 옵션 | 설명 |
|------|------|
| `-n N` | 최소 N글자 이상만 추출 (기본 4) |
| `-a` | 전체 파일 스캔 (코드 섹션 포함) |
| `-t x` | 오프셋을 16진수로 표시 |
| `-o` | 10진수 오프셋 표시 |

---

## 4. 컴파일 vs 번들링

### 4.1 진짜 컴파일 (C/C++/Rust)

```
소스 코드 (.c, .cpp, .rs)
    ↓ [컴파일러]
기계어 (0101...)
    ↓
실행 파일 (추출 불가능)
```

**예시:**
```c
int add(int a, int b) {
    return a + b;
}
```

컴파일 후:
```
55 48 89 e5 89 7d fc 89 75 f8 8b 55 fc 8b 45 f8 01 d0 5d c3
```

strings 실행: **(아무것도 없음)**

### 4.2 번들링 (Node.js/Bun/Deno)

```
JavaScript 코드 (.js)
    ↓ [번들러]
런타임 + JS 문자열 + 네이티브 모듈
    ↓
실행 파일 (JS는 추출 가능!)
```

**예시:**
```javascript
function add(a, b) {
    return a + b;
}
```

번들링 후 (바이너리 안):
```
[런타임 실행 코드 - 기계어]
...
[JavaScript 코드 - 문자열]
66 75 6e 63 74 69 6f 6e 20 61 64 64  // "function add"
28 61 2c 20 62 29 20 7b              // "(a, b) {"
...
```

strings 실행:
```javascript
function add(a, b) {
    return a + b;
}
```

### 4.3 왜 이런 차이가?

| | 컴파일 언어 | 인터프리터 언어 |
|---|-------------|-----------------|
| **실행 방식** | CPU가 직접 실행 | 런타임이 해석 후 실행 |
| **변환** | 소스 → 기계어 | 소스 → 그대로 유지 |
| **런타임** | 불필요 | 필수 (V8, Bun 등) |
| **속도** | 매우 빠름 | 상대적으로 느림 |
| **코드 복구** | 불가능 | strings로 가능 |

---

## 5. Native Installer 장단점

### 5.1 장점

**1. Node.js 설치 불필요**
```
[X] 기업 보안 정책으로 Node.js 설치 금지
[X] sudo 권한 없음
[X] 패키지 관리자 사용 불가
[O] 단일 바이너리만 복사하면 OK!
```

**2. 버전 충돌 회피**
```
프로젝트 A: Node.js v16 필요
프로젝트 B: Node.js v20 필요
Claude Code: Node.js 버전 무관!
```

**3. CI/CD 환경**
```bash
# Docker 컨테이너에서
# Node.js 설치 없이 Claude Code만 추가
COPY claude /usr/local/bin/
RUN chmod +x /usr/local/bin/claude
```

**4. 빠른 배포**
```bash
# npm 방식 (느림)
npm install -g @anthropic-ai/claude-code

# Native 방식 (빠름)
curl -fsSL https://... -o claude
chmod +x claude
```

**5. 실행 속도**
- Bun이 Node.js보다 빠름
- 콜드 스타트 시간 단축

### 5.2 단점

**1. 파일 크기**
```
Native: 171MB (각 버전마다)
npm: 11.3MB (cli.js) + node_modules
```

**2. 디스크 공간**
```
여러 버전 보관 시:
2.1.20: 173MB
2.1.29: 171MB
2.1.32: 172MB
2.1.33: 173MB
총: 689MB

npm: 단일 버전만 유지
```

**3. 코드 분석 어려움**
- strings 추출 과정 필요
- Minified 코드로 가독성 낮음

**4. 업데이트**
- 전체 파일 다시 다운로드
- npm처럼 증분 업데이트 불가

### 5.3 선택 가이드

**Native Installer를 선택해야 하는 경우:**
- Node.js 설치가 어렵거나 금지된 환경
- 여러 프로젝트에서 Node.js 버전이 다른 경우
- 기업 보안 정책으로 npm registry 접근 제한
- CI/CD 환경에서 빠른 배포
- 더 빠른 실행 속도 필요

**npm 패키지를 선택해야 하는 경우:**
- 개발자 로컬 환경 (Node.js 이미 설치됨)
- 코드 분석 및 연구 목적
- 기존 npm 워크플로우와 통합
- 디스크 공간 효율성 중요

---

## 6. 실제 활용 예시

### 6.1 시스템 프롬프트 추출

```bash
grep -A 100 "You are Claude Code" native_v2.1.29_extracted.js
```

### 6.2 도구 정의 찾기

```bash
grep -E "(Bash|Read|Write|Edit|Grep|Glob)" native_v2.1.29_extracted.js | head -50
```

### 6.3 버전 간 차이 비교

```bash
diff native_v2.1.29_extracted.js npm/cli.js
```

### 6.4 특정 기능 분석

```bash
grep -A 20 "WebFetch" native_v2.1.29_extracted.js
```

---

## 7. 제한사항 및 주의사항

### 7.1 Minification

- 변수명이 난독화되어 읽기 어려움
- 원본 주석이 일부 제거됨
- 디버깅 정보 없음

### 7.2 완전성

- strings 명령어는 NULL 바이트로 구분된 문자열만 추출
- 일부 바이너리 데이터나 암호화된 섹션은 추출되지 않을 수 있음

### 7.3 법적 고려사항

- 추출된 코드는 분석 및 학습 목적으로만 사용
- 재배포나 상업적 이용 금지
- Anthropic의 라이선스 조항 준수

---

## 8. 재현 단계 요약

```bash
# 1. 바이너리에서 문자열 추출
strings ~/.local/share/claude/versions/2.1.29 > native_v2.1.29_strings.txt

# 2. 버전 마커 위치 찾기
grep -n "// Version: 2.1.29" native_v2.1.29_strings.txt

# 3. JavaScript 코드 추출
sed -n '114470,266752p' native_v2.1.29_strings.txt > native_v2.1.29_extracted.js

# 4. 추출 결과 확인
ls -lh native_v2.1.29_extracted.js
wc -l native_v2.1.29_extracted.js
head -50 native_v2.1.29_extracted.js
```

---

## 결론

Native 바이너리에서 JavaScript 코드를 성공적으로 추출할 수 있었다:

**[SUCCESS] 달성 사항:**
- v2.1.29의 전체 코드 접근
- 내부 구조 및 아키텍처 분석 가능
- npm 버전과 비교 분석 가능

**[WARN] 주의사항:**
- Minified 코드로 가독성 낮음
- 완전한 역공학은 아님 (바이너리 데이터 제외)
- 분석 목적으로만 사용

**다음 단계:**
1. 코드 포맷팅: Prettier 등으로 가독성 개선
2. 시스템 프롬프트 추출: 핵심 지시사항 찾기
3. 도구 정의 분석: 사용 가능한 도구 목록 작성
4. 버전 비교: v2.1.29 vs v2.1.33 차이점 문서화
5. 기능 분석: 특정 도구(WebFetch, Task 등) 구현 방식 연구

---

**작성일**: 2026-02-06
**대상 버전**: Claude Code v2.1.29 Native installer
**추출 환경**: macOS ARM64
