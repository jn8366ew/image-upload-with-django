# image-upload-with-django

## 소개

로그인한 사용자가 PNG·JPEG 이미지를 여러 장 S3에 올리고, 업로드 1년 후 자동 삭제되는 이미지 업로드 시스템 MVP입니다.

- 이미지는 브라우저에서 S3로 직접 업로드합니다(presigned POST).
- 다운로드는 Django를 거쳐서만 제공하며, S3 key나 URL을 노출하지 않습니다.

## 목적

- 과거에 미비했던 아키텍처를 재구성합니다.
- 서버 부하 없이 대용량 업로드를 처리하면서도 파일 접근은 서버가 통제하는 구조를 직접 설계·구현합니다.
- 모든 비즈니스 로직을 TDD(Red → Green → Refactor)로 작성하는 개발 방식을 연습합니다.
- React + TypeScript와 MongoDB를 실제 기능에 적용해 익힙니다.

## 스택

| 영역 | 기술 |
| --- | --- |
| Backend | Django 5.2 LTS, Django REST Framework, uv |
| Database | PostgreSQL, MongoDB(활동 로그) |
| Frontend | React, TypeScript, Vite, TanStack Query, axios |
| Storage | AWS S3 (boto3) |
| Infra | Terraform, Docker Compose(로컬 DB) |
| Test | pytest, moto, time-machine, Vitest, React Testing Library, MSW |
