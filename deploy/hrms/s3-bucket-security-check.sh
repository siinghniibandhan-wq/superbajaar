#!/usr/bin/env bash
set -Eeuo pipefail
: "${SB_PRIVATE_DOCUMENT_BUCKET:?Set SB_PRIVATE_DOCUMENT_BUCKET}"
: "${SB_S3_REGION:?Set SB_S3_REGION}"
command -v aws >/dev/null || { echo "AWS CLI is required" >&2; exit 1; }
public="$(aws s3api get-public-access-block --bucket "$SB_PRIVATE_DOCUMENT_BUCKET" --region "$SB_S3_REGION" --query 'PublicAccessBlockConfiguration.[BlockPublicAcls,IgnorePublicAcls,BlockPublicPolicy,RestrictPublicBuckets]' --output text)"
[[ "$public" != *False* && "$public" != *None* ]] || { echo "S3 public-access block is incomplete: $public" >&2; exit 1; }
encryption="$(aws s3api get-bucket-encryption --bucket "$SB_PRIVATE_DOCUMENT_BUCKET" --region "$SB_S3_REGION" --query 'ServerSideEncryptionConfiguration.Rules[0].ApplyServerSideEncryptionByDefault.SSEAlgorithm' --output text)"
[[ "$encryption" == "AES256" ]] || { echo "HR document bucket must use AES256 default encryption; got $encryption" >&2; exit 1; }
versioning="$(aws s3api get-bucket-versioning --bucket "$SB_PRIVATE_DOCUMENT_BUCKET" --region "$SB_S3_REGION" --query 'Status' --output text)"
[[ "$versioning" == "Enabled" ]] || { echo "Enable S3 bucket versioning before HR document retention is activated" >&2; exit 1; }
public_policy="$(aws s3api get-bucket-policy-status --bucket "$SB_PRIVATE_DOCUMENT_BUCKET" --region "$SB_S3_REGION" --query 'PolicyStatus.IsPublic' --output text)"
[[ "$public_policy" == "False" ]] || { echo "HR document bucket policy is public or missing: $public_policy" >&2; exit 1; }
echo "Private HR document bucket security checks passed."
