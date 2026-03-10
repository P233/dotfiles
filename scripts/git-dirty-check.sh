#!/bin/bash
#
# Git Dirty Check — Alfred Script Filter
# Scans ~/Projects/ and ~/.config for git repos with uncommitted changes or unpushed commits.
# Outputs Alfred Script Filter JSON.

SCAN_DIRS=("$HOME/Projects" "$HOME/.config")
items=()

check_repo() {
    local repo="$1"
    local name="$2"

    cd "$repo" || return

    local problems=()

    # Uncommitted changes (staged + unstaged + untracked)
    local status=$(git status --porcelain 2>/dev/null)
    if [[ -n "$status" ]]; then
        local staged=$(echo "$status" | grep -c '^[MADRC]')
        local unstaged=$(echo "$status" | grep -c '^.[MDRC]')
        local untracked=$(echo "$status" | grep -c '^??')
        local parts=()
        [[ $staged -gt 0 ]] && parts+=("${staged} staged")
        [[ $unstaged -gt 0 ]] && parts+=("${unstaged} modified")
        [[ $untracked -gt 0 ]] && parts+=("${untracked} untracked")
        problems+=("$(printf '%s, ' "${parts[@]}" | sed 's/, $//')")
    fi

    # Unpushed commits
    local ahead=$(git rev-list --count @{upstream}..HEAD 2>/dev/null)
    if [[ -n "$ahead" && "$ahead" -gt 0 ]]; then
        problems+=("${ahead} unpushed commit$([ "$ahead" -gt 1 ] && echo s)")
    fi

    # Skip clean repos
    [[ ${#problems[@]} -eq 0 ]] && return

    local subtitle=$(printf '%s · ' "${problems[@]}" | sed 's/ · $//')

    # Escape strings for JSON
    local name_json=$(echo "$name" | sed 's/\\/\\\\/g; s/"/\\"/g')
    local subtitle_json=$(echo "$subtitle" | sed 's/\\/\\\\/g; s/"/\\"/g')
    local repo_json=$(echo "$repo" | sed 's/\\/\\\\/g; s/"/\\"/g')

    items+=("{\"title\":\"$name_json\",\"subtitle\":\"$subtitle_json\",\"arg\":\"$repo_json\",\"icon\":{\"path\":\"icon.png\"}}")
}

for dir in "${SCAN_DIRS[@]}"; do
    # Check if the directory itself is a git repo
    if [[ -d "$dir/.git" ]]; then
        check_repo "$dir" "~${dir#$HOME}"
    fi

    # Check subdirectories
    while IFS= read -r gitdir; do
        repo="${gitdir%/.git}"
        name="~${repo#$HOME}"
        check_repo "$repo" "$name"
    done < <(find "$dir" -maxdepth 3 -mindepth 2 -name ".git" -type d 2>/dev/null | sort)
done

if [[ ${#items[@]} -eq 0 ]]; then
    echo '{"items":[{"title":"All clean ✓","subtitle":"No dirty repos found","valid":false}]}'
else
    joined=$(printf '%s,' "${items[@]}" | sed 's/,$//')
    echo "{\"items\":[$joined]}"
fi
