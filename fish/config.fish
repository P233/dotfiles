fish_add_path --path ~/.local/bin ~/.cargo/bin /opt/homebrew/opt/node@24/bin

if status is-interactive
    set fish_greeting
end

# LM Studio binaries are fallbacks; repeated sourcing must not grow PATH.
fish_add_path --path --append ~/.lmstudio/bin

set -gx PNPM_HOME "$HOME/Library/pnpm"
fish_add_path --path "$PNPM_HOME"
