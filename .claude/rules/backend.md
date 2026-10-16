---
paths: backend/**
---

# 백엔드 규칙

## 계층 (ADR-015)

의존 방향: views → services → selectors → storage·events → models. 역방향 import는 금지이며 `uv run lint-imports`로 검사합니다. `exceptions.py`(도메인 예외)는 모든 계층이 import할 수 있습니다.

- **views**: 인증 확인, serializer로 입력 검증, service·selector 호출, 응답 생성(`FileResponse` 헤더 포함)만 합니다.
  - ORM을 직접 호출하지 않습니다(읽기는 selectors, 쓰기는 services).
  - `transaction.atomic`을 쓰지 않습니다.
  - 인가를 직접 판정하지 않습니다. `request.user`를 service·selector에 넘깁니다.
- **serializers**: 입력 형태 검증과 출력 형태 정의만 합니다. `create()`·`update()`·`save()`에 비즈니스 로직을 넣지 않습니다. 출력 필드에 `public_id` 외의 저장소 식별자가 들어가지 않는지 확인합니다.
- **services** (쓰기): 비즈니스 규칙, 소유자 비교(`created_by`), 트랜잭션 경계(`transaction.atomic`), 같은 트랜잭션 안의 `event_outbox` 기록을 담당합니다.
  - 인자는 user와 원시값, 반환은 모델 또는 dataclass입니다.
  - `request`, `rest_framework`, `django.http`를 import하지 않습니다.
  - `StorageGateway`와 시각은 인자(또는 기본값 있는 키워드 인자)로 주입받습니다. 테스트에서 fake로 바꿀 수 있어야 합니다.
  - 실패는 `exceptions.py`의 도메인 예외로 던집니다.
- **selectors** (읽기): 조회·목록 쿼리를 담당하며 소유자 조건을 쿼리에 포함합니다. 부작용이 없습니다.
- **storage**: `StorageGateway` 프로토콜, boto3 어댑터, in-memory fake. boto3 예외를 도메인 예외로 매핑합니다. boto3는 이 패키지 밖에서 import하지 않습니다.
- **events**: outbox 기록 헬퍼와 relay. MongoDB 클라이언트(pymongo)는 이 패키지 밖에서 import하지 않습니다.
- **models**: 필드, DB 제약, 단순 파생 속성만 둡니다. 외부 I/O를 하지 않습니다.
- **management/commands**: 인자 파싱과 출력만 하고, 로직은 services를 호출합니다. 예외: MongoDB를 다루는 명령(`ensure_mongo_indexes`, `relay_events`)은 events를 직접 호출합니다. services는 import 계약상 pymongo에 닿을 수 없기 때문입니다(2026-10-16 결정).
- **signals는 쓰지 않습니다.** 부수효과는 service에서 명시적으로 호출합니다.
- **도메인 예외 → HTTP 상태 매핑**은 DRF 커스텀 `EXCEPTION_HANDLER` 한 곳에서만 합니다. 다른 사용자의 리소스에 어떤 상태 코드를 줄지는 ADR을 따릅니다.

## 테스트 인프라

- 서비스 테스트는 in-memory fake gateway를, boto3 어댑터 테스트는 moto를 씁니다. fake와 어댑터는 같은 계약 테스트를 통과해야 합니다.
- `StorageGateway`에 메서드를 추가·변경할 때는 **계약 테스트 → fake → 어댑터** 순서로 진행하고, 셋 중 일부만 바꾼 채로 사이클을 끝내지 않습니다.
- 시간 규칙(24h, 30일, 1년)은 `time-machine`으로 고정합니다.
- 테스트 DB는 **Postgres**입니다(SQLite 금지). 이벤트 테스트는 **실제 MongoDB**입니다(mongomock 금지).
- 실제 S3를 쓰는 테스트는 `@pytest.mark.s3`를 붙이며, 기본 실행에서 제외됩니다.
- views 테스트는 DRF `APIClient`로 HTTP 계약(상태 코드, 헤더, 응답 필드)만 검증합니다. 비즈니스 분기는 service 테스트에서 검증합니다.

## 마이그레이션

- 모델을 바꾸면 `makemigrations`로 생성하고, 생성된 파일 이름과 내용을 사용자에게 보고합니다.
- 이미 커밋된 마이그레이션은 수정·삭제하지 않습니다. 고칠 일이 있으면 새 마이그레이션을 만듭니다.
- 데이터 마이그레이션(`RunPython`)은 작성 전에 사용자에게 묻습니다.
