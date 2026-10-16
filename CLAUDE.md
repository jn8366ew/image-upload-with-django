# CLAUDE.md

로그인 사용자가 PNG·JPEG 이미지를 S3에 직접 올리고(presigned POST), Django를 거쳐서만 내려받으며, 1년 뒤 자동 삭제되는 MVP입니다.

- **설계 근거:** [`image-upload-adr.md`](./image-upload-adr.md) (ADR-001~015)
- **작업 순서·테스트 목록:** [`image-upload-roadmap.md`](./image-upload-roadmap.md) — 무엇을 구현할지는 이 문서의 체크박스가 단일 원천입니다.
- **현재 단계:** 로드맵에서 미체크 항목이 남아 있는 첫 Phase입니다. 작업 시작 전 그 Phase 섹션만 읽습니다.
- **영역별 규칙:** 백엔드 `.claude/rules/backend.md`, 프론트 `.claude/rules/frontend.md`. 해당 경로의 파일을 열 때 자동 로드되며, 파일을 열기 전에 계획을 세우는 경우에는 먼저 직접 읽습니다.

## 환경

- **Windows 네이티브**에서 개발합니다. ADR-011의 "호스트(WSL2)" 표기는 Windows 호스트로 읽습니다.
- Python은 uv로 관리합니다(`uv run ...`). pip·venv를 직접 쓰지 않습니다.
- Docker Desktop의 `docker compose`로는 **Postgres와 MongoDB만** 띄웁니다. Django `runserver`, Vite, `relay_events`는 호스트에서 실행합니다.
- 비밀값은 `.env`(gitignore), AWS 자격 증명은 `~/.aws` 프로파일 + `AWS_PROFILE`입니다.
  - Claude는 `.env`와 `~/.aws`의 내용을 읽거나 출력하지 않습니다(어떤 명령으로도). 필요한 키 이름은 `.env.example`로 관리합니다.
  - 액세스 키를 리포·`.env`·코드에 넣지 않습니다.
- 위 금지 중 일부는 `.claude/settings.json` 권한으로도 강제됩니다. 권한 거부·확인 요청이 뜨면 우회하지 말고 사용자에게 알립니다.
- 모르는 부분이나 근거 없는 부분은 사용자에게 미리 보고 할것. 

## 리포 구조 (예정)

```
backend/            # uv, Django 5.2 LTS + DRF, pytest-django
frontend/           # Vite + React + TS, Vitest, RTL, MSW
infra/              # Terraform (S3·IAM·Budgets만, state는 로컬·gitignore)
spikes/             # 동작 확인용 실험 코드. 머지하지 않음
.claude/            # settings.json(권한), rules/(영역별 규칙)
docker-compose.yml  # Postgres, MongoDB
```

## 명령어

```bash
docker compose up -d                                   # Postgres, MongoDB

# backend/
uv run pytest                                          # 백엔드 테스트 (s3 마커 제외)
uv run pytest -m s3                                    # 실제 dev 버킷 계약 테스트 — 사용자가 요청할 때만
uv run ruff check . && uv run ruff format --check .    # 린트·포맷
uv run lint-imports                                    # 계층 의존 계약 (ADR-015)
uv run python manage.py makemigrations
uv run python manage.py migrate
uv run python manage.py runserver
uv run python manage.py relay_events --loop            # 별도 터미널
uv run python manage.py attachment_maintenance         # 수동 배치

# frontend/
npm run dev                                            # /api proxy
npm run test                                           # Vitest
npm run lint
npx tsc -b                                             # 타입 체크

# infra/
terraform fmt -check && terraform validate && terraform test
```

## TDD 작업 규칙 (ADR-010, 예외 없음)

비즈니스 로직은 Red → Green → Refactor 사이클로만 추가합니다. 테스트 없는 비즈니스 로직은 쓰지 않습니다.

1. **로드맵 체크박스 하나 = 사이클 하나.** 체크리스트에 없는 동작이 필요하면, 먼저 로드맵에 테스트 항목을 추가하고 사용자에게 알립니다.
2. **Red:** 테스트를 **하나만** 작성하고 실행합니다. **기대한 이유로** 실패하는지 출력으로 확인합니다. import 에러·오타로 인한 실패는 Red가 아닙니다.
3. **Green:** 그 테스트를 통과시키는 최소한의 코드만 씁니다. 전체 테스트가 green이어야 합니다.
4. **Refactor:** green 상태에서만, 동작을 바꾸지 않고 정리합니다.
5. **버그 수정**도 재현 테스트(Red)부터 시작합니다.
6. **사이클 완료 조건:** 변경한 영역의 전체 테스트 + 린트 + 타입 체크가 통과하고, 백엔드라면 `lint-imports`도 통과한 출력을 보여줍니다.
7. 완료 후 로드맵 체크박스를 체크하고 **커밋 메시지를 제안만** 합니다. `git commit`은 사용자가 직접 합니다.
   - `test+feat: <test_name>` 또는 `test+fix: <test_name>` (Red+Green)
   - `refactor: <내용>` (별도)

**테스트로 통과시키기 금지:** 실패하는 테스트를 삭제·skip하거나 단언을 완화해 통과시키지 않습니다. 테스트 자체가 틀렸다고 판단되면 이유를 설명하고 사용자 승인 후 고칩니다.

**비즈니스 로직 범위:** `services/`, `selectors/`, DRF 커스텀 exception handler(도메인 예외 → 상태 코드 매핑), `management/commands/`, `storage/`(예외 매핑), `events/`, 프론트 `src/upload/`(reducer, 동시성 풀, 사전 검증, 재시도·에러 분류). 설정·마이그레이션·UI 레이아웃·Terraform 리소스 정의는 제외합니다(단, Terraform 보안 설정은 `terraform test`로 단언).

CI 게이트는 변경된 비즈니스 로직 라인 커버리지 100%입니다(`diff-cover`, Vitest coverage).

## spikes/

- TDD 대상이 아니며, `backend/`·`frontend/`에서 import하거나 코드를 복사해 오지 않습니다.
- Spike로 확인한 사실은 ADR이나 로드맵에 반영하고 사용자에게 알립니다. 본 코드에서는 테스트부터 다시 작성합니다.

## 의존성

- 다음은 도입하지 않습니다: Pillow 등 이미지 처리, `django-storages`, Celery, S3 이벤트·SQS, JWT, Uppy, Redis.
- 그 밖의 새 런타임·개발 의존성(`uv add`, `npm install <pkg>`)은 이유를 설명하고 사용자 승인 후 추가합니다.

## 절대 규칙 (보안·데이터)

- API 응답에 `s3_key`, 버킷 이름, S3 도메인, presigned GET URL을 **절대** 넣지 않습니다. 식별자는 `public_id`만 씁니다. 예외는 presign 응답의 업로드 폼 하나뿐입니다(ADR-012).
- 다운로드는 Django가 `get_object` 스트림을 `FileResponse`로 내려줍니다(`attachment`, `nosniff`, `private, no-store`). 리다이렉트하지 않습니다.
- 인가는 항상 DB의 `created_by`와 로그인 사용자를 비교합니다. 클라이언트 값·S3 메타데이터로 판정하지 않습니다.
- boto3 S3 클라이언트는 `region_name`, `signature_version="s3v4"`, `s3={"addressing_style": "virtual"}`을 반드시 명시합니다. 하나라도 빠지면 presigned POST URL이 전역 엔드포인트로 나와 307 → CORS 업로드가 실패합니다(0-3 spike).
- 시간은 UTC(`TIME_ZONE="UTC"`, `USE_TZ=True`)이고, 모든 시각은 서버가 찍습니다.
- 확장자는 신뢰하지 않습니다. 포맷은 앞 8바이트 magic bytes로 판정하고, S3 key 확장자는 서버가 정합니다.
- 이벤트는 비즈니스 상태 변경과 같은 Postgres 트랜잭션에서 `event_outbox`에 기록합니다. 요청 처리 경로에서 MongoDB를 직접 호출하지 않습니다.
- 사용자 API로 IP·user agent를 노출하지 않습니다.

## 비용 가드 (ADR-014)

- Terraform에는 S3·IAM·Budgets만 둡니다. 다음을 추가하지 않습니다: ALB, NAT Gateway, RDS, ECS/Fargate, CloudFront, EventBridge Scheduler, KMS 고객 관리형 키, Secrets Manager, Route 53.
- `terraform apply`·`destroy`·`import`·`state` 등 실제 AWS나 state를 바꾸는 명령, 그리고 `aws` CLI는 사용자가 명시적으로 요청할 때만 실행합니다.

## 미결 사항

ADR 하단 "미결 사항"에 걸리는 값(presign 한도, 시간 표시 방식 등)은 임의로 정하지 말고 사용자에게 묻습니다. 정해지면 ADR에 반영합니다.

## Lessons

사용자에게 교정받으면 재발 방지 규칙을 아래에 한 줄로 추가합니다(무엇을 하지 말지 + 이유). 같은 계열이 3개를 넘으면 위 섹션의 규칙으로 합치고 여기서 지웁니다.

- 비용·수치·외부 서비스 동작을 말할 때 출처(ADR 줄 번호, 공식 문서 URL)를 붙이고, 검증 안 한 값은 "추정"이라고 밝힌다. (ADR 예상치 "월 몇 센트"를 검증된 사실처럼 보고했음)
- 처음부터 통과해 Red가 나올 수 없는 테스트(프레임워크 기본 동작 고정, 변이 검증으로 대신한 테스트)는 만들지 않는다. 커버리지 수치보다 "기능이 되는지/안 되는지"를 검증하는 테스트에 집중한다. (1-3의 끝 슬래시·CSRF 교체·로그아웃 GET 테스트를 사용자가 불필요하다고 함) 예외: 인증·인가 같은 보안 가드는 가드를 잠시 풀어 Red를 확인하고 남긴다(ADR-010).
- 필수가 아닌 주석(필드 설명, ADR 번호 표기, 모듈 docstring)을 달지 않는다. 남기는 건 코드만 봐서는 알 수 없는 함정(예: S3 file 필드 순서)뿐이다. (사용자가 주석을 직접 걷어냄)
