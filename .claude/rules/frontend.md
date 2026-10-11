---
paths: frontend/**
---

# 프론트엔드 규칙

## 구조

- **`src/upload/`**: 업로드 도메인 로직(reducer, 동시성 풀, 사전 검증, 재시도·에러 분류). React와 axios에 의존하지 않는 순수 TS로 두고 Vitest로 단위 테스트합니다(TDD 대상).
- **`src/api/`**: HTTP 호출만 둡니다. 컴포넌트에서 axios를 직접 호출하지 않습니다.
- **컴포넌트**: 상태는 hooks로 받아 렌더링만 합니다. 비즈니스 분기를 컴포넌트에 두지 않습니다.

## 라이브러리 사용

- 업로드 HTTP는 axios(`onUploadProgress`)를 씁니다.
- 동시성 풀은 직접 구현합니다(p-limit 등 추가 금지).
- 서버 상태는 TanStack Query, 업로드 큐는 `useReducer`로 관리합니다. 서버 상태를 `useState`·reducer에 복제하지 않습니다.

## 테스트

- 도메인 로직은 Vitest 단위 테스트, 컴포넌트는 RTL + MSW로 테스트합니다.
- MSW 핸들러 응답은 백엔드 API 계약과 같은 형태로 유지합니다. 응답에 `s3_key`·버킷 이름 같은 필드를 넣지 않습니다.
- S3 업로드(presigned POST)는 MSW로 대체하며, 테스트에서 실제 S3를 호출하지 않습니다.
