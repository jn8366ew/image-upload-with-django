#!/usr/bin/env bash
# 비용 가드 (ADR-014): infra/*.tf에 허용 목록 밖의 리소스 타입이 없는지 정적으로 검사합니다.
# - 시간 과금 리소스(ALB, NAT, RDS, ECS, CloudFront, Scheduler 등)를 막습니다.
# - aws_s3_bucket_versioning도 막습니다. 한 번 켜면 되돌릴 수 없습니다 (ADR-005).
# 사용: bash infra/scripts/check_resource_types.sh
set -euo pipefail

cd "$(dirname "$0")/.."

allowed=(
  aws_s3_bucket
  aws_s3_bucket_public_access_block
  aws_s3_bucket_ownership_controls
  aws_s3_bucket_server_side_encryption_configuration
  aws_s3_bucket_policy
  aws_s3_bucket_lifecycle_configuration
  aws_s3_bucket_cors_configuration
  aws_iam_user
  aws_iam_user_policy
  aws_budgets_budget
)

if grep -qE '^[[:space:]]*module[[:space:]]+"' ./*.tf; then
  echo "module 블록은 허용하지 않습니다 (리소스 타입을 정적으로 검사할 수 없음)." >&2
  exit 1
fi

found=$(grep -ohE '^[[:space:]]*resource[[:space:]]+"[a-z0-9_]+"' ./*.tf \
  | sed -E 's/.*"([a-z0-9_]+)"/\1/' | sort -u)

status=0
for type in $found; do
  ok=false
  for a in "${allowed[@]}"; do
    [[ "$type" == "$a" ]] && ok=true && break
  done
  if [[ "$ok" == false ]]; then
    echo "허용되지 않은 리소스 타입: $type (ADR-014 비용 가드)" >&2
    status=1
  fi
done

if [[ $status -eq 0 ]]; then
  echo "리소스 타입 검사 통과: $(echo "$found" | wc -l | tr -d ' ')종"
fi
exit $status
