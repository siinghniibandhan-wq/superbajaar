#!/usr/bin/env bash
set -Eeuo pipefail
: "${SB_PRIVATE_DOCUMENT_BUCKET:?Set SB_PRIVATE_DOCUMENT_BUCKET}"
: "${SB_S3_REGION:?Set SB_S3_REGION}"
command -v aws >/dev/null || { echo "AWS CLI is required" >&2; exit 1; }
aws s3api get-public-access-block --bucket "$SB_PRIVATE_DOCUMENT_BUCKET" --region "$SB_S3_REGION"
aws s3api get-bucket-encryption --bucket "$SB_PRIVATE_DOCUMENT_BUCKET" --region "$SB_S3_REGION"
aws s3api get-bucket-versioning --bucket "$SB_PRIVATE_DOCUMENT_BUCKET" --region "$SB_S3_REGION"
aws s3api get-bucket-policy-status --bucket "$SB_PRIVATE_DOCUMENT_BUCKET" --region "$SB_S3_REGION"
echo "Review the returned configuration: all public access blocks must be true, default encryption must be enabled, and versioning should be Enabled."
