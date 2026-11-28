#!/usr/bin/env bash
set -Eeuo pipefail
: "${SB_HR_API_BASE_URL:?Set SB_HR_API_BASE_URL}"
: "${SB_HR_SCHEDULER_TOKEN:?Set a dedicated manager-scoped bearer token}"
api="${SB_HR_API_BASE_URL%/}"
auth=(-H "Authorization: Bearer ${SB_HR_SCHEDULER_TOKEN}" -H "Content-Type: application/json")
post(){
  local route="$1"
  curl --fail --silent --show-error --max-time 60 -X POST "${api}${route}" "${auth[@]}" -d '{}'
  printf '\n'
}
post /hr/enterprise/notifications/refresh
post /hr/enterprise/documents/retention/execute
post /hr/enterprise/analytics/scheduled/run
