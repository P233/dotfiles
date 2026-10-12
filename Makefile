PNPM_VERSION := 12.11.2
FONTTOOLS_VERSION := 4.66.1

.PHONY: install install-scripts install-pnpm install-ghostty install-tmux install-macos check clean

install: install-scripts install-pnpm install-ghostty install-tmux install-macos

install-scripts:
	mkdir -p "$(HOME)/.local/bin"
	install -m 755 scripts/git-dirty-check.py "$(HOME)/.local/bin/git-dirty-check"
	install -m 755 scripts/agent-ssh-sign.sh "$(HOME)/.local/bin/agent-ssh-sign"

install-pnpm:
	npm install --global --no-audit --no-fund pnpm@$(PNPM_VERSION)

install-ghostty:
	uv run --python '>=3.11' --with fonttools==$(FONTTOOLS_VERSION) python ghostty/install-triangle-font.py

install-tmux:
	sh tmux/install.sh

install-macos:
	bash macos/defaults.sh

# The scripts run under the system interpreter, so their tests do too.
check:
	/usr/bin/python3 -B -m unittest discover -s scripts/tests -v
	/usr/bin/python3 -B -m unittest discover -s tmux/tests -v
	uv run --python '>=3.11' --with fonttools==$(FONTTOOLS_VERSION) python -B -m unittest discover -s ghostty/tests -v
	shellcheck macos/defaults.sh scripts/agent-ssh-sign.sh tmux/install.sh tmux/scripts/*.sh
	fish --no-config --no-execute fish/config.fish

clean:
	rm -f "$(HOME)/.local/bin/git-dirty-check"
