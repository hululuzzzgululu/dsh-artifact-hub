#!/usr/bin/env bash

set -euo pipefail

invocation_dir="$(pwd)"

usage() {
  echo "Usage: $0 [output_zip_path]" >&2
  echo "       $0 --commit <commit> [output_zip_path]" >&2
}

mode="uncommitted"
commit_ref=""
output_zip_path=""

if [[ $# -gt 0 && "$1" == "--commit" ]]; then
  mode="commit"
  if [[ $# -lt 2 || $# -gt 3 ]]; then
    usage
    exit 1
  fi
  commit_ref="$2"
  if [[ $# -eq 3 ]]; then
    output_zip_path="$3"
  fi
elif [[ $# -gt 1 ]]; then
  usage
  exit 1
elif [[ $# -eq 1 ]]; then
  output_zip_path="$1"
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git is required" >&2
  exit 1
fi

if ! command -v zip >/dev/null 2>&1; then
  echo "zip is required" >&2
  exit 1
fi

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "Current directory is not inside a git repository" >&2
  exit 1
}

cd "$repo_root"

tmp_dir="$(mktemp -d)"
status_file="$tmp_dir/git-status.bin"
deleted_manifest="$tmp_dir/deleted_files.txt"
cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

declare -a existing_files=()
declare -a deleted_files=()
declare -a zip_existing_files=()

has_path() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    if [[ "$item" == "$needle" ]]; then
      return 0
    fi
  done
  return 1
}

to_zip_arg() {
  local path="$1"
  if [[ "$path" == -* ]]; then
    printf './%s' "$path"
    return 0
  fi
  printf '%s' "$path"
}

append_zip_path() {
  local path="$1"
  if ! has_path "$path" "${zip_existing_files[@]-}"; then
    zip_existing_files+=("$path")
  fi
}

if [[ "$mode" == "uncommitted" ]]; then
  git status --porcelain -z >"$status_file"

  if [[ ! -s "$status_file" ]]; then
    echo "No uncommitted files found" >&2
    exit 1
  fi

  while IFS= read -r -d '' entry; do
    status="${entry:0:2}"
    path="${entry:3}"
    x="${status:0:1}"
    y="${status:1:1}"

    if [[ "$x" == "R" || "$x" == "C" || "$y" == "R" || "$y" == "C" ]]; then
      IFS= read -r -d '' _original_path || true
    fi

    if [[ "$x" == "D" || "$y" == "D" ]]; then
      if ! has_path "$path" "${deleted_files[@]-}"; then
        deleted_files+=("$path")
      fi
      continue
    fi

    if [[ -e "$path" ]] && ! has_path "$path" "${existing_files[@]-}"; then
      existing_files+=("$path")
    fi
  done <"$status_file"

  if [[ ${#existing_files[@]} -eq 0 && ${#deleted_files[@]} -eq 0 ]]; then
    echo "No uncommitted files found" >&2
    exit 1
  fi

  if [[ ${#existing_files[@]} -gt 0 ]]; then
    for path in "${existing_files[@]}"; do
      if [[ -d "$path" ]]; then
        while IFS= read -r nested_path; do
          [[ -n "$nested_path" ]] || continue
          append_zip_path "$(to_zip_arg "$nested_path")"
        done < <(git ls-files --others --exclude-standard -- "$path")
        continue
      fi

      append_zip_path "$(to_zip_arg "$path")"
    done
  fi

  timestamp="$(date +%Y%m%d-%H%M%S)"
  archive_path="$repo_root/uncommitted-$timestamp.zip"
else
  commit_id="$(git rev-parse --verify "${commit_ref}^{commit}" 2>/dev/null)" || {
    echo "Commit not found: $commit_ref" >&2
    exit 1
  }
  parent_id="$(git rev-parse --verify "${commit_id}^" 2>/dev/null)" || {
    echo "Commit has no parent: $commit_ref" >&2
    exit 1
  }

  git diff --name-status -z "$parent_id" "$commit_id" >"$status_file"

  if [[ ! -s "$status_file" ]]; then
    echo "No changed files found for commit: $commit_ref" >&2
    exit 1
  fi

  while IFS= read -r -d '' status; do
    if [[ "$status" == R* || "$status" == C* ]]; then
      IFS= read -r -d '' _original_path || true
      IFS= read -r -d '' path || true
    else
      IFS= read -r -d '' path || true
    fi

    if [[ "$status" == D* ]]; then
      if ! has_path "$path" "${deleted_files[@]-}"; then
        deleted_files+=("$path")
      fi
      continue
    fi

    if ! has_path "$path" "${existing_files[@]-}"; then
      existing_files+=("$path")
    fi
  done <"$status_file"

  short_commit="$(git rev-parse --short "$commit_id")"
  timestamp="$(date +%Y%m%d-%H%M%S)"
  archive_path="$repo_root/commit-$short_commit-$timestamp.zip"
fi

: >"$deleted_manifest"
if [[ ${#deleted_files[@]} -gt 0 ]]; then
  printf "%s\n" "${deleted_files[@]}" >"$deleted_manifest"
fi

if [[ -n "$output_zip_path" ]]; then
  if [[ "$output_zip_path" = /* ]]; then
    archive_path="$output_zip_path"
  else
    archive_path="$invocation_dir/$output_zip_path"
  fi
fi

mkdir -p "$(dirname "$archive_path")"

if [[ "$mode" == "commit" && ${#existing_files[@]} -gt 0 ]]; then
  git archive --format=zip --output="$archive_path" "$commit_id" -- "${existing_files[@]}"
elif [[ ${#zip_existing_files[@]} -gt 0 ]]; then
  first_path="${zip_existing_files[0]}"
  zip -qr "$archive_path" "$first_path"
  if [[ ${#zip_existing_files[@]} -gt 1 ]]; then
    for path in "${zip_existing_files[@]:1}"; do
      zip -qr "$archive_path" "$path"
    done
  fi
fi

zip -q -j "$archive_path" "$deleted_manifest"
echo "$archive_path"
