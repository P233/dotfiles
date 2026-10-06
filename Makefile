PNPM_VERSION := 12.9.1

.PHONY: install install-scripts install-pnpm install-macos check clean

install: install-scripts install-pnpm install-macos

install-scripts:
	mkdir -p ~/.local/bin
	swiftc -O -o ~/.local/bin/toggle-app scripts/toggle-app.swift
	install -m 755 scripts/git-dirty-check.sh ~/.local/bin/git-dirty-check

# Independent of Homebrew's versioned Node Cellar and its optional Corepack.
install-pnpm:
	npm install --prefix "$(HOME)/.local/share/pnpm-cli" --ignore-scripts --no-audit --no-fund --save-exact pnpm@$(PNPM_VERSION)
	mkdir -p "$(HOME)/.local/bin"
	ln -sf "$(HOME)/.local/share/pnpm-cli/node_modules/.bin/pnpm" "$(HOME)/.local/bin/pnpm"
	ln -sf "$(HOME)/.local/share/pnpm-cli/node_modules/.bin/pnpx" "$(HOME)/.local/bin/pnpx"
	test -x "$(HOME)/.local/bin/pnpm"
	test -x "$(HOME)/.local/bin/pnpx"

install-macos:
	bash macos/defaults.sh

# The scripts run under the system interpreter, so their tests do too.
check:
	shellcheck macos/defaults.sh
	fish --no-config --no-execute fish/config.fish

clean:
	rm -f ~/.local/bin/toggle-app
	rm -f ~/.local/bin/git-dirty-check
