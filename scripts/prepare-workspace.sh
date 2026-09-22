#!/usr/bin/env bash
# Prepare local context only. Existing repository work is never switched or reset.
set -euo pipefail
export GIT_OPTIONAL_LOCKS=0

agent=all
check=false
strict=false
usage() {
  printf '%s\n' 'Usage: bash scripts/prepare-workspace.sh [--agent codex|claude|all|generic] [--check] [--strict]'
}
fail() { printf 'error: %s\n' "$*" >&2; exit 1; }
warn() { printf 'warning: %s\n' "$*" >&2; }
while (($#)); do
  case "$1" in
    --agent)
      (($# >= 2)) || fail '--agent requires a value'
      agent=$2; shift 2 ;;
    --check) check=true; shift ;;
    --strict) strict=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; fail 'unknown argument' ;;
  esac
done
case "$agent" in codex|claude|all|generic) ;; *) fail 'unsupported agent' ;; esac
command -v git >/dev/null 2>&1 || fail 'Git is required'
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
git_root=$(git -C "$root" rev-parse --show-toplevel 2>/dev/null) || fail 'workspace is not a Git repository'
[[ $(cd -- "$git_root" && pwd -P) == "$root" ]] || fail 'script must belong to the workspace Git root'
[[ -f "$root/.gitmodules" && ! -L "$root/.gitmodules" ]] || fail 'workspace .gitmodules is missing or is a symlink'

modules=(yourown-platform yourown-rag)
pins=()
missing=()
# Preflight both repositories before initializing anything.
for module in "${modules[@]}"; do
  entry=$(git -C "$root" ls-files --stage -- "$module")
  [[ -n "$entry" && "$entry" != *$'\n'* ]] || fail "$module must have exactly one staged gitlink"
  read -r mode pin stage indexed_path <<< "$entry"
  [[ "$mode" == 160000 && "$stage" == 0 && "$indexed_path" == "$module" ]] || fail "$module is not an unconflicted staged gitlink"
  pins+=("$pin")
  declared_path=$(git -C "$root" config -f .gitmodules --get "submodule.$module.path") || fail "$module is absent from .gitmodules"
  [[ "$declared_path" == "$module" ]] || fail "$module has an unexpected submodule path"
  git -C "$root" config -f .gitmodules --get "submodule.$module.url" >/dev/null || fail "$module has no submodule URL"
  path="$root/$module"
  [[ ! -L "$path" ]] || fail "$module is a symlink; preserving it"
  if [[ ! -e "$path" ]]; then
    missing+=("$module")
    continue
  fi
  [[ -d "$path" ]] || fail "$module is not a directory; preserving it"
  own_root=$(git -C "$path" rev-parse --show-toplevel 2>/dev/null || true)
  if [[ -z "$own_root" || $(cd -- "$own_root" && pwd -P) != "$path" ]]; then
    shopt -s nullglob dotglob
    contents=("$path"/*)
    shopt -u nullglob dotglob
    ((${#contents[@]} == 0)) || fail "$module contains files but is not its own Git checkout; preserving it"
    missing+=("$module")
    continue
  fi
  head=$(git -C "$path" rev-parse --verify HEAD) || fail "$module has no valid HEAD"
  state=clean
  changes=$(git -C "$path" status --porcelain=v1 --untracked-files=normal --ignore-submodules=none) || fail "$module status could not be read"
  if [[ -n "$changes" ]]; then
    state=dirty
    if "$strict"; then fail "$module has local changes (--strict)"; fi
    warn "$module has local changes; preserving them"
  fi
  if [[ "$head" != "$pin" ]]; then
    if "$strict"; then fail "$module differs from the workspace pin (--strict)"; fi
    warn "$module differs from the workspace pin; keeping current HEAD"
  fi
  printf '%s: %s, HEAD %.12s, pin %.12s\n' "$module" "$state" "$head" "$pin"
done

for module in ${missing[@]+"${missing[@]}"}; do
  if "$check"; then fail "$module is not initialized; run prepare without --check"; fi
  # Only missing/empty checkouts reach this command. No --remote, --force or reset.
  printf 'Initializing %s at the workspace pin\n' "$module"
  git -C "$root" submodule update --init --checkout -- "$module"
done
# Verify initializations independently of command success and local Git settings.
for i in "${!modules[@]}"; do
  module=${modules[$i]}
  for initialized in ${missing[@]+"${missing[@]}"}; do
    [[ "$module" == "$initialized" ]] || continue
    own_root=$(git -C "$root/$module" rev-parse --show-toplevel)
    [[ $(cd -- "$own_root" && pwd -P) == "$root/$module" ]] || fail "$module was not initialized at its expected root"
    [[ $(git -C "$root/$module" rev-parse HEAD) == "${pins[$i]}" ]] || fail "$module initialization did not use the workspace pin"
    printf '%s: initialized at %.12s\n' "$module" "${pins[$i]}"
  done
done

rag="$root/yourown-rag"
for dir in rules knowledge skills; do
  [[ -d "$rag/$dir" && ! -L "$rag/$dir" ]] || fail "yourown-rag/$dir must be a local directory"
done
for file in rules/core.md rules/terraform.md knowledge/platform.md skills/yourown-terraform/SKILL.md; do
  [[ -f "$rag/$file" && ! -L "$rag/$file" ]] || fail "required context is missing or a symlink: yourown-rag/$file"
done
skills=()
for file in "$rag"/skills/*/SKILL.md; do
  [[ -f "$file" ]] || continue
  dir=${file%/SKILL.md}
  [[ ! -L "$dir" && ! -L "$file" ]] || fail 'skill sources must be local directories and files'
  skills+=("${dir##*/}")
done
((${#skills[@]} > 0)) || fail 'no skills found'
clients=()
case "$agent" in
  codex) clients=(.agents) ;;
  claude) clients=(.claude) ;;
  all) clients=(.agents .claude) ;;
esac
# Validate every destination before creating any links.
for client in ${clients[@]+"${clients[@]}"}; do
  for dir in "$root/$client" "$root/$client/skills"; do
    [[ ! -L "$dir" ]] || fail "$client skills parent is a symlink; preserving it"
    [[ ! -e "$dir" || -d "$dir" ]] || fail "$client skills parent is not a directory; preserving it"
  done
  for skill in "${skills[@]}"; do
    destination="$root/$client/skills/$skill"
    target="../../yourown-rag/skills/$skill"
    if [[ -L "$destination" ]]; then
      [[ $(readlink "$destination") == "$target" ]] || fail "$client/skills/$skill has a conflicting link; preserving it"
    elif [[ -e "$destination" ]]; then
      fail "$client/skills/$skill already exists; preserving it"
    elif "$check"; then
      fail "$client/skills/$skill is missing; run prepare without --check"
    fi
  done
done
if ! "$check"; then
  for client in ${clients[@]+"${clients[@]}"}; do
    mkdir -p -- "$root/$client/skills"
    for skill in "${skills[@]}"; do
      destination="$root/$client/skills/$skill"
      [[ -L "$destination" ]] || ln -s -- "../../yourown-rag/skills/$skill" "$destination"
    done
  done
fi
printf 'Workspace ready: agent=%s, strict=%s\n' "$agent" "$strict"
