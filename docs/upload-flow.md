``` mermaid
sequenceDiagram
    participant U as 사용자
    participant FE as 프론트 src/upload
    participant API as DRF views-services
    participant DB as Postgres
    participant S3 as S3
    participant BG as 배치-릴레이

    U->>FE: 파일 5개 선택
    FE->>FE: 파일마다 사전 검증 (PNG·JPEG, 2.5MiB 이하, 이름 255자 이하)
    Note over FE: 통과한 파일에 clientRef f1..f5 부여. 거절된 파일은 화면에만 표시

    Note over FE,S3: presign. 최대 10개를 요청 1회로
    FE->>API: POST /attachments/presign files f1..f5
    API->>API: serializer 형태 검증, 서비스가 개수·타입·크기 전체 검사. 하나라도 틀리면 400, 행 생성 없음
    loop 파일마다
        API->>DB: INSERT Attachment PENDING, s3_key는 서버가 결정
        API->>S3: generate_presigned_post. Content-Type 일치, 1~2.5MiB, 300초
    end
    API-->>FE: 201 uploads client_ref, public_id, url, fields
    Note over API,FE: S3 정보가 응답에 담기는 유일한 예외

    Note over FE,DB: 업로드·확정. 파일 단위, 동시 3개
    par 풀 워커 3개가 f1..f5를 나눠 처리
        FE->>S3: POST FormData, fields 뒤에 file. onUploadProgress로 진행률
        S3-->>FE: 204
        FE->>API: POST /attachments/public_id/complete
        API->>DB: SELECT deleted 아님, DELETING 아님. 소유자 비교
        API->>S3: HEAD. 없으면 409 UploadNotReceived
        API->>S3: GET Range 0-7. magic bytes 판정
        alt 형식 일치
            API->>DB: UPDATE PENDING to COMPLETED, uploaded_at=now. 같은 트랜잭션에 EventOutbox UPLOAD_COMPLETED
            API-->>FE: 200 public_id, status
            FE->>FE: onCompleted. 목록 쿼리 무효화
        else 형식 불일치
            API->>DB: UPDATE to REJECTED. EventOutbox UPLOAD_REJECTED
            API->>S3: DELETE object
            API-->>FE: 400 invalid_format. 그 파일만 최종 실패
        end
    end

    Note over DB,BG: 요청 경로 밖. 상시 프로세스 없음
    BG->>DB: relay_events --loop. 미발행 outbox를 MongoDB 활동 로그로
    BG->>DB: attachment_maintenance 수동 실행. 24h 넘은 PENDING을 같은 검증으로 COMPLETED 또는 삭제
```