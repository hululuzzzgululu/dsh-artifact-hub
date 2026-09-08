#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
HUB_DIR="${ROOT_DIR}/hub"
PLUGIN_DIR="${ROOT_DIR}/plugins/dsh-artifact-hub"
SHARE_WEB_DIR="${ROOT_DIR}/apps/share-web"

ENV_FILE="${DSH_ARTIFACT_HUB_ENV_FILE:-${SCRIPT_DIR}/dev.env}"
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

: "${HUB_HOST:=127.0.0.1}"
: "${HUB_PORT:=8000}"
: "${HUB_URL:=http://127.0.0.1:${HUB_PORT}}"
: "${HUB_STORAGE_MODE:=sqlite}"
: "${HUB_ARTIFACT_ROOT:=${HUB_DIR}/data/artifacts}"
: "${HUB_DATABASE_PATH:=${HUB_DIR}/data/hub.sqlite3}"

: "${SHARE_WEB_HOST:=127.0.0.1}"
: "${SHARE_WEB_PORT:=5173}"
: "${SHARE_WEB_URL:=http://127.0.0.1:${SHARE_WEB_PORT}}"
: "${HUB_BASE_URL:=${SHARE_WEB_URL}}"

: "${DSH_PROFILE:=web}"
: "${DSH_WEB_HOST:=127.0.0.1}"
: "${DSH_WEB_PORT:=3080}"
: "${DSH_WEB_URL:=http://127.0.0.1:${DSH_WEB_PORT}}"
: "${DSH_ARTIFACT_HUB_CREATED_BY:=dsh-local-user}"
: "${DSH_ARTIFACT_HUB_MODE:=local}"
: "${DSH_ARTIFACT_HUB_ARTIFACT_ROOT:=${HUB_ARTIFACT_ROOT}}"

: "${STARTUP_TIMEOUT_SECONDS:=60}"
: "${DSH_ARTIFACT_HUB_TMP_DIR:=${TMPDIR:-/tmp}}"
: "${DSH_ARTIFACT_HUB_RUN_DIR:=${DSH_ARTIFACT_HUB_TMP_DIR%/}/dsh-artifact-hub-dev-${UID:-user}}"

HUB_PID=""
SHARE_WEB_PID=""
DSH_WEB_PID=""

log() {
  printf '[artifact-hub-dev] %s\n' "$*"
}

die() {
  printf '[artifact-hub-dev] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "缺少命令：$1"
}

check_prerequisites() {
  require_command uv
  require_command node
  require_command pnpm
  require_command dsh
  require_command curl
  require_command lsof
}

assert_port_free() {
  local name="$1"
  local port="$2"
  local listeners
  listeners="$(lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null || true)"
  if [[ -n "${listeners}" ]]; then
    die "${name} 端口 ${port} 已被 PID ${listeners//$'\n'/,} 占用；请先停止该进程或在 scripts/dev.env 中换端口"
  fi
}

plugin_is_installed() {
  dsh plugin --profile "${DSH_PROFILE}" list --depth 0 2>/dev/null \
    | grep -F 'dsh-artifact-hub' >/dev/null 2>&1
}

setup_all() {
  check_prerequisites

  log '同步 Python 依赖'
  (cd "${HUB_DIR}" && uv sync --frozen)

  log '安装并构建 DSH 插件'
  (cd "${PLUGIN_DIR}" && pnpm install --frozen-lockfile && pnpm run build)

  log '安装 share-web 依赖'
  (cd "${SHARE_WEB_DIR}" && pnpm install --frozen-lockfile)

  log "把本地插件安装到 DSH profile：${DSH_PROFILE}"
  dsh plugin --profile "${DSH_PROFILE}" add "${PLUGIN_DIR}"

  plugin_is_installed || die "插件安装后仍未出现在 DSH profile ${DSH_PROFILE} 中"
  log 'setup 完成'
}

test_all() {
  check_prerequisites

  log '测试 Python Hub'
  (
    cd "${HUB_DIR}"
    uv run python -m unittest discover -s tests -v
    uv run python -m compileall -q src tests
  )

  log '测试并构建 DSH 插件'
  (
    cd "${PLUGIN_DIR}"
    pnpm test
    pnpm run typecheck
    pnpm run build
  )

  log '测试并构建 share-web'
  (
    cd "${SHARE_WEB_DIR}"
    pnpm test
    pnpm run typecheck
    pnpm run build
  )

  log '全部测试通过'
}

wait_for_http() {
  local name="$1"
  local url="$2"
  local elapsed=0

  while (( elapsed < STARTUP_TIMEOUT_SECONDS )); do
    if curl --silent --show-error --fail --location --max-time 2 "${url}" >/dev/null 2>&1; then
      log "${name} 已就绪：${url}"
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done

  return 1
}

show_logs() {
  local log_file
  for log_file in "${DSH_ARTIFACT_HUB_RUN_DIR}/hub.log" \
    "${DSH_ARTIFACT_HUB_RUN_DIR}/share-web.log" \
    "${DSH_ARTIFACT_HUB_RUN_DIR}/dsh-web.log"; do
    if [[ -f "${log_file}" ]]; then
      printf '\n===== %s =====\n' "${log_file}"
      tail -n 80 "${log_file}" || true
    fi
  done
}

smoke_all() {
  check_prerequisites

  curl --silent --show-error --fail "${HUB_URL}/healthz" >/dev/null
  curl --silent --show-error --fail --location "${SHARE_WEB_URL}/" >/dev/null
  curl --silent --show-error --fail --location "${DSH_WEB_URL}/" >/dev/null

  local rpc_status
  rpc_status="$(curl --silent --show-error \
    --output "${DSH_ARTIFACT_HUB_RUN_DIR}/plugin-route-smoke.json" \
    --write-out '%{http_code}' \
    --request POST \
    --header 'content-type: application/json' \
    --data '{"type":"client-request","rpcId":"00000000-0000-4000-8000-000000000001","method":"shares","payload":{}}' \
    "${DSH_WEB_URL}/artifact-hub/shares")"
  if [[ "${rpc_status}" != '200' ]] \
    || ! grep -F '"type":"server-response"' "${DSH_ARTIFACT_HUB_RUN_DIR}/plugin-route-smoke.json" >/dev/null \
    || ! grep -F '"ok":false' "${DSH_ARTIFACT_HUB_RUN_DIR}/plugin-route-smoke.json" >/dev/null; then
    die "DSH 插件 RPC 检查失败：HTTP ${rpc_status}，响应见 ${DSH_ARTIFACT_HUB_RUN_DIR}/plugin-route-smoke.json"
  fi

  curl --silent --show-error --fail "${HUB_URL}/openapi.json" \
    | grep -F 'workspace_root' >/dev/null \
    || die 'Hub OpenAPI 未包含 workspace_root，请确认没有启动旧进程'

  log '三个服务的启动 smoke test 通过'
}

terminate_pid() {
  local pid="$1"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
    kill "${pid}" 2>/dev/null || true
    wait "${pid}" 2>/dev/null || true
  fi
}

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM
  if [[ -n "${HUB_PID}${SHARE_WEB_PID}${DSH_WEB_PID}" ]]; then
    log '正在停止本次启动的服务'
  fi
  terminate_pid "${DSH_WEB_PID}"
  terminate_pid "${SHARE_WEB_PID}"
  terminate_pid "${HUB_PID}"
  exit "${exit_code}"
}

handle_signal() {
  exit 130
}

start_all() {
  check_prerequisites
  plugin_is_installed || die "DSH 插件尚未安装，请先运行：$0 setup"

  assert_port_free 'Hub' "${HUB_PORT}"
  assert_port_free 'share-web' "${SHARE_WEB_PORT}"
  assert_port_free 'DSH Web' "${DSH_WEB_PORT}"

  mkdir -p "${DSH_ARTIFACT_HUB_RUN_DIR}"
  trap cleanup EXIT
  trap handle_signal INT TERM

  log '构建最新 DSH 插件'
  (cd "${PLUGIN_DIR}" && pnpm run build)

  log "启动 Hub：${HUB_URL}"
  (
    cd "${HUB_DIR}"
    exec env \
      HUB_HOST="${HUB_HOST}" \
      HUB_PORT="${HUB_PORT}" \
      HUB_BASE_URL="${HUB_BASE_URL}" \
      HUB_STORAGE_MODE="${HUB_STORAGE_MODE}" \
      HUB_ARTIFACT_ROOT="${HUB_ARTIFACT_ROOT}" \
      HUB_DATABASE_PATH="${HUB_DATABASE_PATH}" \
      uv run python -m api.main
  ) >"${DSH_ARTIFACT_HUB_RUN_DIR}/hub.log" 2>&1 &
  HUB_PID=$!

  log "启动 share-web：${SHARE_WEB_URL}"
  (
    cd "${SHARE_WEB_DIR}"
    exec env VITE_HUB_PROXY_TARGET="${HUB_URL}" \
      pnpm exec vite --host "${SHARE_WEB_HOST}" --port "${SHARE_WEB_PORT}"
  ) >"${DSH_ARTIFACT_HUB_RUN_DIR}/share-web.log" 2>&1 &
  SHARE_WEB_PID=$!

  log "启动 DSH Web：${DSH_WEB_URL}"
  (
    cd "${ROOT_DIR}"
    exec env \
      DSH_ARTIFACT_HUB_URL="${HUB_URL}" \
      DSH_ARTIFACT_HUB_CREATED_BY="${DSH_ARTIFACT_HUB_CREATED_BY}" \
      DSH_ARTIFACT_HUB_MODE="${DSH_ARTIFACT_HUB_MODE}" \
      DSH_ARTIFACT_HUB_ARTIFACT_ROOT="${DSH_ARTIFACT_HUB_ARTIFACT_ROOT}" \
      dsh --profile "${DSH_PROFILE}" --host "${DSH_WEB_HOST}" --port "${DSH_WEB_PORT}" --no-open
  ) >"${DSH_ARTIFACT_HUB_RUN_DIR}/dsh-web.log" 2>&1 &
  DSH_WEB_PID=$!

  if ! wait_for_http 'Hub' "${HUB_URL}/healthz" \
    || ! wait_for_http 'share-web' "${SHARE_WEB_URL}/" \
    || ! wait_for_http 'DSH Web' "${DSH_WEB_URL}/"; then
    show_logs
    die "服务未能在 ${STARTUP_TIMEOUT_SECONDS} 秒内全部就绪"
  fi

  smoke_all
  log "日志目录：${DSH_ARTIFACT_HUB_RUN_DIR}"
  log '服务正在运行；按 Ctrl-C 一并停止'

  while kill -0 "${HUB_PID}" 2>/dev/null \
    && kill -0 "${SHARE_WEB_PID}" 2>/dev/null \
    && kill -0 "${DSH_WEB_PID}" 2>/dev/null; do
    sleep 1
  done

  show_logs
  die '至少一个服务意外退出'
}

usage() {
  cat <<EOF
用法：$(basename "$0") <command>

命令：
  setup   同步依赖、构建插件，并安装到 DSH profile
  test    运行 Hub、插件和 share-web 的完整测试与构建
  start   前台启动三个服务，自动 smoke test，Ctrl-C 时全部停止
  check   检查已经运行的三个服务和 DSH 插件 RPC
  all     依次执行 setup、test、start
  help    显示本帮助

配置：
  默认读取 ${SCRIPT_DIR}/dev.env；可复制 dev.env.example 后修改。
EOF
}

main() {
  local command="${1:-help}"
  case "${command}" in
    setup) setup_all ;;
    test) test_all ;;
    start) start_all ;;
    check) mkdir -p "${DSH_ARTIFACT_HUB_RUN_DIR}"; smoke_all ;;
    all) setup_all; test_all; start_all ;;
    help|-h|--help) usage ;;
    *) usage >&2; die "未知命令：${command}" ;;
  esac
}

main "$@"
