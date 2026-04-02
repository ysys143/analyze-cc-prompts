# Buddy(Companion) 토큰 무소비 설계 분석

분석 대상: 유출 TypeScript 소스 (v2.1.88, 유출일 2026-03-31)
분석 파일:
1. `src/buddy/companion.ts`
2. `src/buddy/CompanionSprite.tsx`
3. `src/buddy/prompt.ts`
4. `src/buddy/types.ts`
5. `src/buddy/useBuddyNotification.tsx`

---

## 1. 개요

Buddy(공식명 Companion)는 터미널 입력창 옆에 상주하는 동물 캐릭터 스프라이트다.
애니메이션, 말풍선 반응, 이름 호명 대답 등 풍부한 상호작용이 있음에도
**지속 구동 중 추가 LLM API 호출이 0건**이다.

이 문서는 소스코드 수준에서 그 설계 근거를 분석한다.

---

## 2. 아키텍처 개관

Buddy 시스템은 세 레이어로 분리된다:

```
+---------------------+---------------------+---------------------+
|   BONES 레이어       |   SOUL 레이어         |   UI 레이어           |
|  (결정론적 생성)      |  (1회 LLM 생성 후    |  (순수 React         |
|                     |   config 저장)        |   상태 머신)          |
+---------------------+---------------------+---------------------+
| hash(userId+SALT)   | name, personality   | setInterval(500ms)  |
| -> 종, 눈, 모자, 희귀도 | -> globalConfig에 저장| -> 스프라이트 틱 구동   |
| mulberry32 PRNG     | 해치 시 1회만 생성      | AppState 구독        |
+---------------------+---------------------+---------------------+
         |                    |                       |
         v                    v                       v
  API 호출 없음          해치 시 1회만 비용         API 호출 없음
```

---

## 3. BONES 레이어: 결정론적 캐릭터 생성

### 3.1 PRNG 기반 생성

`companion.ts`는 userId를 시드로 하는 Mulberry32 PRNG로 캐릭터를 생성한다:

```typescript
// Mulberry32 — tiny seeded PRNG, good enough for picking ducks
function mulberry32(seed: number): () => number { ... }

const SALT = 'friend-2026-401'

export function roll(userId: string): Roll {
  const key = userId + SALT
  if (rollCache?.key === key) return rollCache.value          // 캐시 히트
  const value = rollFrom(mulberry32(hashString(key)))        // 해시 -> PRNG
  rollCache = { key, value }
  return value
}
```

동일 userId에 대해 항상 동일한 종(species), 눈(eye), 모자(hat), 희귀도(rarity)가 나온다.
API 호출 없이 순수 수학 연산으로 처리된다.

### 3.2 결정론의 보안적 의의

bones는 config에 저장되지 않는다:

```typescript
// What actually persists in config. Bones are regenerated from hash(userId)
// on every read so species renames don't break stored companions and
// users can't edit their way to a legendary.
export type StoredCompanion = CompanionSoul & { hatchedAt: number }
```

매 읽기마다 userId로 재생성하므로:
1. 사용자가 config를 수동 편집해 legendary를 위조할 수 없다.
2. SPECIES 배열이 업데이트되어도 기존 저장 데이터가 깨지지 않는다.

---

## 4. SOUL 레이어: 1회 생성 후 영속

캐릭터의 이름(name)과 성격(personality)은 해치(hatch) 시 Claude가 1회 생성하고
`globalConfig.companion`에 저장한다. 이후에는 config에서 읽을 뿐 재생성하지 않는다.

즉 **토큰 비용은 해치 시 단 1회**이며, 이후 세션에서는 0이다.

---

## 5. UI 레이어: 순수 React 상태 머신

### 5.1 스프라이트 애니메이션

`CompanionSprite.tsx`는 `setInterval`로 500ms마다 틱을 증가시키며
틱 인덱스를 IDLE_SEQUENCE 배열에 대입해 프레임을 결정한다:

```typescript
const TICK_MS = 500
const IDLE_SEQUENCE = [0, 0, 0, 0, 1, 0, 0, 0, -1, 0, 0, 2, 0, 0, 0]
//                                                  ^ -1 = 눈 깜빡임

useEffect(() => {
  const timer = setInterval(setT => setT((t: number) => t + 1), TICK_MS, setTick)
  return () => clearInterval(timer)
}, [])
```

LLM 호출 없이 로컬 타이머만으로 idle, fidget, 눈 깜빡임 애니메이션을 구현한다.

### 5.2 말풍선 반응

말풍선 텍스트는 `AppState.companionReaction`에서 읽는다.
이 값은 Claude의 기존 API 응답에서 설정된다 — 별도 API 호출이 아니다.

`prompt.ts`의 companion_intro 지시문이 그 메커니즘을 설명한다:

```typescript
export function companionIntroText(name: string, species: string): string {
  return `# Companion

A small ${species} named ${name} sits beside the user's input box and
occasionally comments in a speech bubble. You're not ${name} — it's a
separate watcher.

When the user addresses ${name} directly (by name), its bubble will answer.
Your job in that moment is to stay out of the way: respond in ONE line or
less, or just answer any part of the message meant for you.`
}
```

사용자가 buddy 이름을 직접 부르면, Claude가 기존 응답 안에서 1줄로 buddy 반응을 포함시킨다.
별도 API 호출이 아니라 동일 API 호출 내에서 처리된다.

---

## 6. companion_intro 토큰 비용

`prompt.ts`의 `getCompanionIntroAttachment()`는 세션 시작 시 companion 소개 텍스트를
attachment로 주입한다. 이 과정에서 중복 주입 방지 로직이 있다:

```typescript
// Skip if already announced for this companion.
for (const msg of messages ?? []) {
  if (msg.type !== 'attachment') continue
  if (msg.attachment.type !== 'companion_intro') continue
  if (msg.attachment.name === companion.name) return []   // 이미 소개됨
}
```

즉 companion_intro는 **동일 세션 내에서 1회만** 시스템 컨텍스트에 추가된다.
추가되는 텍스트는 약 5~6줄의 짧은 지시문이며, 이것이 buddy의 전체 토큰 비용이다.

---

## 7. feature flag에 의한 빌드타임 제거

BUDDY 기능 전체는 `bun:bundle`의 feature flag로 제어된다:

```typescript
import { feature } from 'bun:bundle'

if (!feature('BUDDY')) return []       // prompt.ts
if (!feature('BUDDY')) return null     // CompanionSprite.tsx
if (!feature('BUDDY')) return 0        // companionReservedColumns
```

외부 배포(external) 빌드에서 `BUDDY` flag가 비활성화되면 Bun 번들러가 dead code로
판단하고 빌드 결과물에서 완전히 제거한다. 현재 npm 배포본(v2.1.88 기준)에서
companion 관련 코드가 존재한다면, 해당 flag가 활성화된 빌드임을 의미한다.

---

## 8. 토큰 비용 요약

| 이벤트 | 토큰 비용 | 발생 빈도 |
|--------|----------|---------|
| 해치(hatch) | 이름+성격 생성 비용 | 계정 생애 1회 |
| 세션 시작 | companion_intro 약 50토큰 | 세션당 1회 |
| 스프라이트 애니메이션 | 0 | 500ms마다 (로컬) |
| 말풍선 반응 | 0 (기존 응답 재활용) | 이름 호명 시 |
| 캐릭터 재계산 | 0 (PRNG) | 매 접근 시 |

---

## 9. 설계 원칙 정리

1. 결정론적 생성: 시각적 속성(bones)은 hash+PRNG로 생성해 API 비용을 완전히 제거.
2. 1회 생성 영속: 고유 속성(soul)은 최초 1회만 LLM으로 생성하고 config에 저장.
3. 로컬 상태 머신: 애니메이션은 setInterval 기반 React 상태 머신으로 API와 무관.
4. 응답 내 처리: 말풍선 반응은 별도 API 호출 없이 기존 응답의 일부로 처리.
5. 세션 dedupe: companion_intro는 세션당 1회만 주입해 반복 비용 방지.

---

분석 소스: 유출 TypeScript 소스 v2.1.88 (`src/buddy/` 디렉토리 전체)
