# Claude Code 바이너리에서 JavaScript 코드 추출 방법론

## 개요

Claude Code는 두 가지 설치 방법을 제공합니다:
- **npm 버전**: Node.js 스크립트 기반 (JavaScript 소스 직접 접근 가능)
- **Native installer 버전**: 컴파일된 Mach-O 바이너리 (ARM64)

Native 바이너리에서 JavaScript 코드를 추출하면 다음이 가능합니다:
- 내부 구현 분석
- 버전별 차이 비교
- 시스템 프롬프트 및 도구 정의 추출

## 환경

- **OS**: macOS (Darwin 25.2.0)
- **아키텍처**: ARM64 (Apple Silicon)
- **대상 바이너리**: Claude Code v2.1.29 Native installer
- **바이너리 경로**: `~/.local/share/claude/versions/2.1.29`
- **바이너리 크기**: 171MB

## 추출 방법

### 1단계: 바이너리 문자열 추출

`strings` 명령어를 사용하여 바이너리에 포함된 모든 텍스트를 추출합니다.

```bash
strings /Users/jaesolshin/.local/share/claude/versions/2.1.29 > native_v2.1.29_strings.txt
```

**결과:**
- 출력 파일: `native_v2.1.29_strings.txt`
- 크기: 29MB
- 라인 수: ~300,000줄

### 2단계: 버전 마커 찾기

JavaScript 코드는 보통 버전 주석으로 시작합니다.

```bash
grep -n "// Version: 2.1.29" native_v2.1.29_strings.txt
```

**발견된 라인:**
```
114470:// Version: 2.1.29
266753:// Version: 2.1.29
271839:// Version: 2.1.29
271849:// Version: 2.1.29
...
```

첫 번째 발견(114470)이 메인 코드 블록의 시작점입니다.

### 3단계: JavaScript 코드 블록 추출

버전 마커 사이의 코드를 추출합니다.

```bash
sed -n '114470,266752p' native_v2.1.29_strings.txt > native_v2.1.29_extracted.js
```

**추출 범위:**
- 시작: 114470 (첫 번째 버전 마커)
- 종료: 266752 (두 번째 버전 마커 직전)

**결과:**
- 출력 파일: `native_v2.1.29_extracted.js`
- 크기: 13MB
- 라인 수: 152,283줄
- 상태: Minified (압축된 코드)

### 4단계: 코드 구조 확인

추출된 코드의 시작 부분을 확인합니다.

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

## 추출된 코드 특징

### 번들러
**Bun**을 사용하여 번들링됨 (Bun의 번들링 패턴 확인)

### Native 모듈
바이너리에 포함된 네이티브 모듈들:

```javascript
require("/$bunfs/root/image-processor.node")  // 이미지 처리
require("/$bunfs/root/color-diff.node")       // 색상 비교
require("/$bunfs/root/file-index.node")       // 파일 인덱싱
require("/$bunfs/root/ripgrep.node")          // 코드 검색
```

### 코드 형식
- **Minified**: 변수명이 난독화됨 (예: `RH0`, `AH0`, `Ee`)
- **ES 모듈**: 현대적인 JavaScript 모듈 시스템 사용
- **CommonJS 호환**: `require()` 및 `exports` 지원

## 버전 비교

| 항목 | Native v2.1.29 | npm v2.1.33 |
|------|----------------|-------------|
| **파일 형식** | Mach-O 바이너리 | JavaScript |
| **전체 크기** | 171MB | 11.3MB (cli.js) |
| **추출 코드 크기** | 13MB | 11.3MB |
| **라인 수** | 152,283 | 7,587 |
| **번들러** | Bun | (번들러 정보 확인 필요) |
| **접근성** | 추출 필요 | 직접 읽기 가능 |

**주요 차이점:**
1. Native 버전이 더 많은 코드를 포함 (152k vs 7.5k 라인)
2. Native 버전에는 Bun 런타임 코드가 포함되어 있을 가능성
3. npm 버전은 외부 의존성을 `node_modules`에 분리 저장

## 추출 결과 활용

### 1. 시스템 프롬프트 추출
```bash
grep -A 100 "You are Claude Code" native_v2.1.29_extracted.js
```

### 2. 도구(Tool) 정의 찾기
```bash
grep -E "(Bash|Read|Write|Edit|Grep|Glob)" native_v2.1.29_extracted.js | head -50
```

### 3. 버전 간 차이 비교
```bash
diff native_v2.1.29_extracted.js npm/cli.js
```

### 4. 특정 기능 분석
```bash
grep -A 20 "WebFetch" native_v2.1.29_extracted.js
```

## 제한사항

### Minification
- 변수명이 난독화되어 읽기 어려움
- 원본 주석이 일부 제거됨
- 디버깅 정보 없음

### 완전성
- strings 명령어는 NULL 바이트로 구분된 문자열만 추출
- 일부 바이너리 데이터나 암호화된 섹션은 추출되지 않을 수 있음

### 법적 고려사항
- 추출된 코드는 분석 및 학습 목적으로만 사용
- 재배포나 상업적 이용 금지
- Anthropic의 라이선스 조항 준수

## 재현 단계 요약

```bash
# 1. 바이너리에서 문자열 추출
strings ~/.local/share/claude/versions/2.1.29 > native_v2.1.29_strings.txt

# 2. 버전 마커 위치 찾기
grep -n "// Version: 2.1.29" native_v2.1.29_strings.txt

# 3. JavaScript 코드 추출 (라인 범위는 2단계 결과에 따라 조정)
sed -n '114470,266752p' native_v2.1.29_strings.txt > native_v2.1.29_extracted.js

# 4. 추출 결과 확인
ls -lh native_v2.1.29_extracted.js
wc -l native_v2.1.29_extracted.js
head -50 native_v2.1.29_extracted.js
```

## 결론

Native 바이너리에서 JavaScript 코드를 성공적으로 추출할 수 있었습니다. 이를 통해:

[SUCCESS] 달성 사항:
- v2.1.29의 전체 코드 접근
- 내부 구조 및 아키텍처 분석 가능
- npm 버전과 비교 분석 가능

[WARN] 주의사항:
- Minified 코드로 가독성 낮음
- 완전한 역공학은 아님 (바이너리 데이터 제외)
- 분석 목적으로만 사용

## 다음 단계

1. **코드 포맷팅**: Prettier 등으로 가독성 개선
2. **시스템 프롬프트 추출**: 핵심 지시사항 찾기
3. **도구 정의 분석**: 사용 가능한 도구 목록 작성
4. **버전 비교**: v2.1.29 vs v2.1.33 차이점 문서화
5. **기능 분석**: 특정 도구(WebFetch, Task 등) 구현 방식 연구

---

**작성일**: 2026-02-06
**대상 버전**: Claude Code v2.1.29 Native installer
**추출 환경**: macOS ARM64
