# 트랜잭션 흐름

도메인별 처리 순서와 Postgres 트랜잭션 경계를 그립니다. 규칙과 근거는 ADR-013 "트랜잭션 규칙"과 ADR-005·008에 있습니다.

- 파란 상자 하나가 `transaction.atomic()` 하나입니다. 상자 밖의 Postgres 쿼리는 각각 autocommit입니다.
- S3 호출은 언제나 상자 밖에 있습니다. Mongo 호출은 릴레이에서만 상자 안에 있습니다(규칙 2번의 예외).
- 상태 전환은 조건부 `UPDATE`로 합니다. 반환값이 1일 때만 같은 상자 안에서 `event_outbox`를 기록합니다.

## 개요

```mermaid
flowchart LR
    subgraph REQ[요청 경로]
        U[업로드 확정·거절]
        D[다운로드]
        SD[소프트 삭제]
    end
    subgraph BATCH[배치·운영]
        M[attachment_maintenance]
        OP[purge_attachment]
    end
    PG[(Postgres<br/>상태 + event_outbox)]
    S3[(S3)]
    MG[(MongoDB<br/>attachment_events)]
    R[relay_events --loop]

    U --> PG
    D --> PG
    SD --> PG
    M --> PG
    OP --> PG
    U -.트랜잭션 밖.-> S3
    D -.트랜잭션 밖.-> S3
    M -.트랜잭션 밖.-> S3
    OP -.트랜잭션 밖.-> S3
    PG --> R --> MG
```

요청 경로는 MongoDB를 직접 부르지 않습니다. 이벤트는 Postgres `event_outbox`를 거쳐 릴레이만 MongoDB로 옮깁니다.

---

## 1. 업로드

### 1-1. presign 발급

```mermaid
sequenceDiagram
    participant C as 브라우저
    participant V as PresignView
    participant S as presign_uploads
    participant PG as Postgres
    participant S3

    C->>V: POST /api/attachments/presign
    V->>S: presign_uploads(user, files)
    S->>S: 개수·타입·크기 검사 (하나라도 실패하면 전부 거절)
    loop 파일마다
        S->>PG: INSERT attachment (PENDING) autocommit
        S->>S: presigned POST 서명 (로컬 계산, 네트워크 없음)
    end
    S-->>V: public_id, url, fields
    V-->>C: 201
    C->>S3: POST 업로드 (브라우저가 직접)
```

이벤트는 기록하지 않습니다. 업로드 결과는 `/complete`에서 정해집니다.

### 1-2. `/complete` 확정·거절

```mermaid
sequenceDiagram
    participant V as CompleteView
    participant S as completion
    participant PG as Postgres
    participant S3

    V->>S: complete_upload(user, public_id, ip, user_agent)
    S->>PG: SELECT attachment autocommit
    alt 없음 또는 삭제됨
        S-->>V: AttachmentNotFound → 404
    else 다른 사용자
        S-->>V: NotOwner → 403
    else 이미 COMPLETED
        S-->>V: 200 (멱등)
    else 이미 REJECTED
        S-->>V: UploadRejected → 400
    else PENDING
        S->>S3: head (선언 타입)
        alt 객체 없음
            S-->>V: UploadNotReceived → 409, PENDING 유지
        else 객체 있음
            S->>S3: read_prefix (앞 8바이트)
            alt 시그니처 일치
                rect rgba(80, 140, 255, 0.15)
                    S->>PG: UPDATE status=COMPLETED, uploaded_at WHERE status=PENDING
                    opt 반환값 == 1
                        S->>PG: INSERT event_outbox (UPLOAD_COMPLETED)
                    end
                end
                S->>PG: refresh_from_db
                S-->>V: 200
            else 불일치
                rect rgba(80, 140, 255, 0.15)
                    S->>PG: UPDATE status=REJECTED WHERE status=PENDING
                    opt 반환값 == 1
                        S->>PG: INSERT event_outbox (UPLOAD_REJECTED)
                    end
                end
                S->>PG: refresh_from_db
                S->>S3: delete (실패해도 REJECTED 유지, 로그만)
                S-->>V: UploadRejected → 400 (예외는 상자 밖에서)
            end
        end
    end
```

### 1-3. 동시 `/complete` (경쟁)

```mermaid
sequenceDiagram
    participant A as 요청 A
    participant B as 요청 B
    participant PG as Postgres

    A->>PG: SELECT (PENDING)
    B->>PG: SELECT (PENDING)
    Note over A,B: 둘 다 S3 검사 통과
    rect rgba(80, 140, 255, 0.15)
        A->>PG: UPDATE … WHERE status=PENDING → 1
        A->>PG: INSERT event_outbox
    end
    rect rgba(80, 140, 255, 0.15)
        B->>PG: UPDATE … WHERE status=PENDING → 0
        Note right of B: 이벤트 없음
    end
    B->>PG: refresh_from_db → COMPLETED
    Note over A,B: 둘 다 200, 이벤트는 1개
```

### 1-4. 배치 확정 (24시간 지난 PENDING)

`attachment_maintenance`가 1-2의 PENDING 분기와 같은 `finalize_pending`을 호출합니다. 다음이 다릅니다.

- `ip`·`user_agent`는 null입니다.
- `uploaded_at`과 이벤트 시각은 배치를 시작할 때 구한 시각입니다.
- 객체가 없으면 하드 삭제(3-2)로 넘어갑니다. 거절된 행은 같은 실행의 REJECTED 정리 단계에서 하드 삭제됩니다.

---

## 2. 다운로드

```mermaid
sequenceDiagram
    participant C as 브라우저
    participant V as DownloadView
    participant S as open_download
    participant PG as Postgres
    participant S3

    C->>V: GET /api/attachments/{id}/download
    V->>S: open_download(user, public_id, ip, user_agent)
    S->>PG: SELECT attachment (COMPLETED, 삭제 안 됨) autocommit
    alt 없음
        S-->>V: 404 (이벤트 없음)
    else 다른 사용자
        S-->>V: 403 (이벤트 없음)
    else 본인
        S->>S3: open (스트림)
        alt 객체 없음
            S-->>V: 404 (이벤트 없음)
        else 열림
            S->>PG: INSERT event_outbox (DOWNLOADED) 단독 autocommit
            S-->>V: Download
            V-->>C: FileResponse 스트리밍 (attachment, nosniff, no-store)
        end
    end
```

`DOWNLOADED`는 "응답을 시작했다"는 뜻입니다. 전송 완료까지 보장하지는 않습니다.

---

## 3. 삭제

### 3-1. 소프트 삭제

```mermaid
sequenceDiagram
    participant V as AttachmentDetailView
    participant S as soft_delete
    participant PG as Postgres

    V->>S: soft_delete(user, public_id, ip, user_agent)
    S->>PG: SELECT attachment (COMPLETED) autocommit
    alt 없음
        S-->>V: 404
    else 다른 사용자
        S-->>V: 403
    else 본인
        rect rgba(80, 140, 255, 0.15)
            S->>PG: UPDATE deleted_at WHERE deleted_at IS NULL
            opt 반환값 == 1
                S->>PG: INSERT event_outbox (SOFT_DELETED)
            end
        end
        S-->>V: 204 (재호출도 204, 이벤트는 처음 한 번)
    end
```

S3는 건드리지 않습니다. 30일 뒤 배치가 하드 삭제합니다.

### 3-2. 하드 삭제 (`purge`, 배치·운영 공통)

```mermaid
sequenceDiagram
    participant CALLER as 배치 또는 purge_attachment
    participant P as purge
    participant PG as Postgres
    participant S3

    CALLER->>P: purge(attachment_id, requested_by, now)
    Note over P: 바깥 트랜잭션 안이면 RuntimeError
    rect rgba(80, 140, 255, 0.15)
        P->>PG: SELECT … FOR UPDATE SKIP LOCKED
        alt 잠겨 있음
            P-->>CALLER: SKIPPED_LOCKED
        else 행 없음
            P-->>CALLER: ALREADY_GONE
        else status != DELETING
            P->>PG: UPDATE status=DELETING
            P->>PG: INSERT AttachmentPurgeLog
            P->>PG: INSERT event_outbox (PURGED, requested_by)
        else 이미 DELETING (재시도)
            Note right of P: 로그·이벤트를 다시 쓰지 않음
        end
    end
    P->>S3: delete
    alt S3 실패
        P-->>CALLER: StorageError (DELETING으로 남음, 다음 실행이 재시도)
    else 성공
        P->>PG: DELETE attachment autocommit
        P-->>CALLER: PURGED (이미 지워졌으면 ALREADY_GONE)
    end
```

- **운영 삭제 (`purge_attachment --public-id --operator`):** `purge_by_operator`가 운영자(활성 사용자)와 첨부를 조회한 뒤 `purge(requested_by=운영자)`를 호출합니다. `requested_by`는 감사 로그와 `PURGED` 이벤트에 운영자 id로 들어갑니다.
- **배치 삭제:** `requested_by`는 null이고, `now`는 배치를 시작할 때 구한 시각입니다.

---

## 4. 이벤트 발행

### 4-1. 릴레이 (`relay_events`)

```mermaid
sequenceDiagram
    participant L as run_loop / relay_events
    participant R as relay_once
    participant PG as Postgres
    participant MG as MongoDB

    L->>R: relay_once(db)
    rect rgba(80, 140, 255, 0.15)
        R->>PG: SELECT … WHERE published_at IS NULL ORDER BY id LIMIT 100 FOR UPDATE SKIP LOCKED
        alt 0건
            R-->>L: 0
        else 1건 이상
            R->>MG: insert_many(ordered=False) 잠금을 쥔 채, 상한 5초
            alt 성공 또는 오류가 전부 11000
                R->>PG: UPDATE published_at = now
                Note over R,PG: 커밋
                R-->>L: 발행 건수
            else 11000이 아닌 쓰기 오류 또는 연결 오류
                Note over R,PG: 롤백, 행은 미발행으로 남음
                R-->>L: raise
            end
        end
    end
```

```mermaid
flowchart LR
    A[relay_once] -->|0건| I[1초 대기] --> A
    A -->|1건 이상| A
    A -->|PyMongoError| B[backoff 대기<br/>1 → 2 → 4 … 최대 30초] --> A
    B -.다음 성공 시 1초로 초기화.-> A
```

- **`--loop` 없음:** 한 번 실행하고 `published=N`을 출력합니다. Mongo가 실패하면 `CommandError`(exit 1)로 끝납니다.
- **동시 실행:** 릴레이를 여러 개 띄워도 `SKIP LOCKED` 때문에 같은 행을 잡지 않습니다.
- **at-least-once:** 커밋 직전에 죽으면 같은 이벤트가 다시 전송되고, Mongo `event_id` unique 인덱스가 중복을 흡수합니다.

### 4-2. 아웃박스 정리

```mermaid
sequenceDiagram
    participant M as attachment_maintenance (6단계)
    participant PG as Postgres

    M->>PG: DELETE FROM event_outbox WHERE published_at <= now - 7일 (autocommit, 쿼리 1개)
    Note right of PG: 미발행 행(published_at IS NULL)은 조건에 걸리지 않음
```

---

## 부록: `attachment_maintenance` 실행 순서

```mermaid
flowchart TD
    N[now를 한 번 구함] --> S1[1. 남은 DELETING 재시도 → purge]
    S1 --> S2[2. 24시간 지난 PENDING → finalize_pending]
    S2 -->|객체 없음| P2[purge]
    S2 -->|형식 불일치| RJ[REJECTED]
    S2 --> S3[3. REJECTED → purge]
    S3 --> S4[4. 소프트 삭제 30일 경과 → purge]
    S4 --> S5[5. 업로드 1년 경과 → purge]
    S5 --> S6[6. 발행 후 7일 지난 event_outbox 삭제]
    S6 --> OUT[MaintenanceResult 반환]
```

각 단계는 잠금 없이 대상 id만 고르고, 잠금은 `purge()`가 겁니다. 한 실행에서 실패해 DELETING으로 남은 행은 다음 실행의 1단계가 처리합니다.
