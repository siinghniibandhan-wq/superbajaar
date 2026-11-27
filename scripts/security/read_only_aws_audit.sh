#!/usr/bin/env bash
# Read-only production security audit. Does not print secret values or modify resources.
set +e
export AWS_PAGER=""
ROOT="/opt/superbajaar/source"
ENV_FILE="$ROOT/backend/.env"

section() { printf '\n===== %s =====\n' "$1"; }
run() { printf '\n$ %s\n' "$*"; "$@" 2>&1; }

section "Host and operating system"
run uname -a
run df -h /
run free -h
run systemctl is-active superbajaar-backend.service
run systemctl is-enabled superbajaar-backend.service
run systemctl show superbajaar-backend.service -p User -p Group -p WorkingDirectory -p ExecStart -p NoNewPrivileges -p PrivateTmp -p ProtectSystem -p ProtectHome

section "Network listeners"
if command -v ss >/dev/null 2>&1; then ss -lntup 2>&1 | sed -E 's/users:\(\(.*\)\)/users:(redacted)/'; fi
if command -v nginx >/dev/null 2>&1; then
  nginx -t 2>&1
  nginx -T 2>&1 | grep -Ei 'listen |server_name|ssl_protocols|ssl_ciphers|add_header|client_max_body_size|proxy_pass|limit_req|limit_conn' | sed -E 's/(ssl_certificate_key|proxy_set_header Authorization)[^;]*/\1 [redacted]/I'
fi

section "PostgreSQL role and access posture (no password/hash data)"
if command -v sudo >/dev/null 2>&1 && command -v psql >/dev/null 2>&1; then
  sudo -u postgres psql -X -d superbajaar -Atc "SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname IN ('postgres','superbajaar_app','superbajaar_user');"
  sudo -u postgres psql -X -d superbajaar -Atc "SELECT grantee, privilege_type FROM information_schema.role_table_grants WHERE table_schema='public' AND grantee IN ('PUBLIC','superbajaar_app','superbajaar_user') GROUP BY grantee, privilege_type ORDER BY grantee, privilege_type;"
  sudo -u postgres psql -X -d superbajaar -Atc "SELECT datname, pg_catalog.pg_get_userbyid(datdba) FROM pg_database WHERE datname='superbajaar';"
else
  echo "SKIP: postgres local inspection tools unavailable"
fi

section "Instance metadata and attached IAM role"
TOKEN=$(curl -fsS -X PUT -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' http://169.254.169.254/latest/api/token 2>/dev/null)
if [ -n "$TOKEN" ]; then
  echo "IMDSv2 token request: PASS"
  ROLE=$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/iam/security-credentials/ 2>/dev/null | head -1)
  INSTANCE_ID=$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null)
  REGION=$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region 2>/dev/null)
  echo "Instance ID: ${INSTANCE_ID:-unavailable}"
  echo "Region: ${REGION:-unavailable}"
  echo "Instance role name: ${ROLE:-none}"
else
  echo "IMDSv2 token request: FAIL or metadata endpoint unavailable"
fi
if command -v aws >/dev/null 2>&1 && [ -n "$ROLE" ]; then
  ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
  run aws iam list-attached-role-policies --role-name "$ROLE" --query 'AttachedPolicies[].{Name:PolicyName,Arn:PolicyArn}' --output table
  for POLICY_ARN in $(aws iam list-attached-role-policies --role-name "$ROLE" --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null); do
    VERSION=$(aws iam get-policy --policy-arn "$POLICY_ARN" --query 'Policy.DefaultVersionId' --output text 2>/dev/null)
    if [ -n "$VERSION" ] && [ "$VERSION" != "None" ]; then
      run aws iam get-policy-version --policy-arn "$POLICY_ARN" --version-id "$VERSION" --query 'PolicyVersion.Document' --output json
    fi
  done
  INLINE_NAMES=$(aws iam list-role-policies --role-name "$ROLE" --query 'PolicyNames[]' --output text 2>/dev/null)
  echo "Inline IAM policies: ${INLINE_NAMES:-none}"
  for POLICY_NAME in $INLINE_NAMES; do
    run aws iam get-role-policy --role-name "$ROLE" --policy-name "$POLICY_NAME" --query 'PolicyDocument' --output json
  done
  if [ -n "$ACCOUNT_ID" ]; then
    run aws s3control get-public-access-block --account-id "$ACCOUNT_ID"
  fi
  if [ -n "$INSTANCE_ID" ]; then
    SG_IDS=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --region "$REGION" --query 'Reservations[].Instances[].SecurityGroups[].GroupId' --output text 2>/dev/null)
    run aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --region "$REGION" --query 'Reservations[].Instances[].{State:State.Name,MetadataOptions:MetadataOptions,SecurityGroups:SecurityGroups[].GroupId}' --output json
    if [ -n "$SG_IDS" ]; then
      run aws ec2 describe-security-groups --group-ids $SG_IDS --region "$REGION" --query 'SecurityGroups[].{GroupId:GroupId,GroupName:GroupName,Ingress:IpPermissions,Egress:IpPermissionsEgress}' --output json
    fi
  fi
else
  echo "SKIP: AWS CLI or attached instance role unavailable"
fi

section "S3 media bucket controls"
BUCKET=""
if [ -r "$ENV_FILE" ]; then
  BUCKET=$(grep -E '^MEDIA_BUCKET=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"\047\r')
fi
if command -v aws >/dev/null 2>&1 && [ -n "$BUCKET" ]; then
  echo "Media bucket name: $BUCKET"
  run aws s3api get-public-access-block --bucket "$BUCKET" --region "${REGION:-ap-south-1}"
  run aws s3api get-bucket-policy-status --bucket "$BUCKET" --region "${REGION:-ap-south-1}"
  run aws s3api get-bucket-policy --bucket "$BUCKET" --region "${REGION:-ap-south-1}"
  run aws s3api get-bucket-ownership-controls --bucket "$BUCKET" --region "${REGION:-ap-south-1}"
  run aws s3api get-bucket-encryption --bucket "$BUCKET" --region "${REGION:-ap-south-1}"
  run aws s3api get-bucket-versioning --bucket "$BUCKET" --region "${REGION:-ap-south-1}"
  run aws s3api get-bucket-lifecycle-configuration --bucket "$BUCKET" --region "${REGION:-ap-south-1}"
else
  echo "SKIP: MEDIA_BUCKET not configured or AWS CLI unavailable"
fi

section "Runtime secret hygiene (names/status only)"
if [ -r "$ENV_FILE" ]; then
  for key in DATABASE_URL JWT_SECRET_KEY SB_SECRET_KEY RAZORPAY_KEY_ID RAZORPAY_KEY_SECRET RAZORPAY_WEBHOOK_SECRET AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY; do
    if grep -qE "^${key}=" "$ENV_FILE"; then echo "$key: present (value redacted)"; else echo "$key: absent"; fi
  done
  stat -c 'backend .env permissions: %a owner: %U:%G' "$ENV_FILE"
else
  echo "backend .env: not readable by audit user"
fi

section "Completion"
echo "Read-only audit finished. Review every FAIL/SKIP and retain this output securely."
