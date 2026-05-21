#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="${SOURCE_SKILLS_DIR:-$HOME/.claude/skills}"
target_dir="$repo_root/skills"

if [[ ! -d "$source_dir" ]]; then
  echo "Error: source skills directory not found: $source_dir" >&2
  exit 1
fi

skills=()
while IFS= read -r skill_file; do
  skills+=("$(basename "$(dirname "$skill_file")")")
done < <(find "$source_dir" -mindepth 2 -maxdepth 2 -name SKILL.md -print | sort)

if [[ ${#skills[@]} -eq 0 ]]; then
  echo "Error: no skills found in $source_dir" >&2
  exit 1
fi

mkdir -p "$target_dir"

for skill in "${skills[@]}"; do
  mkdir -p "$target_dir/$skill"
  rsync -a --delete --exclude '.DS_Store' --exclude '.ace-tool' --exclude '.serena' "$source_dir/$skill/" "$target_dir/$skill/"
  echo "Synced $skill -> $target_dir/$skill"
done

echo "Synced ${#skills[@]} skills from $source_dir"
