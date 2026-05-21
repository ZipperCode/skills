#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="${SOURCE_SKILLS_DIR:-$HOME/.claude/skills}"
target_dir="$repo_root/skills"

skills=(
  grill-me
  herosms-api
  sub2api-account-manager
  temp-mail
  temp-mail-orchestration
)

if [[ ! -d "$source_dir" ]]; then
  echo "Error: source skills directory not found: $source_dir" >&2
  exit 1
fi

mkdir -p "$target_dir"

for skill in "${skills[@]}"; do
  if [[ ! -f "$source_dir/$skill/SKILL.md" ]]; then
    echo "Error: missing $source_dir/$skill/SKILL.md" >&2
    exit 1
  fi

  mkdir -p "$target_dir/$skill"
  rsync -a --delete --exclude '.DS_Store' "$source_dir/$skill/" "$target_dir/$skill/"
  echo "Synced $skill -> $target_dir/$skill"
done

echo "Synced ${#skills[@]} skills from $source_dir"
