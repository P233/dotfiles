VSCODE_SRC  := $(CURDIR)/vscode
VSCODE_DEST := $(HOME)/Library/Application Support/Code/User

.PHONY: install install-scripts install-vscode install-macos clean

install: install-scripts install-vscode install-macos

install-scripts:
	mkdir -p ~/.local/bin
	swiftc -O -o ~/.local/bin/toggle-app scripts/toggle-app.swift
	install -m 755 scripts/git-dirty-check.sh ~/.local/bin/git-dirty-check

install-vscode:
	@if [ ! -d "$(VSCODE_DEST)" ]; then \
		echo "Error: VSCode not installed. Install VSCode first."; \
		exit 1; \
	fi
	ln -sf "$(VSCODE_SRC)/settings.json"    "$(VSCODE_DEST)/settings.json"
	ln -sf "$(VSCODE_SRC)/keybindings.json" "$(VSCODE_DEST)/keybindings.json"
	cd "$(VSCODE_SRC)/open-in-emacs" && npx --yes @vscode/vsce package --allow-missing-repository -o open-in-emacs.vsix
	code --install-extension "$(VSCODE_SRC)/open-in-emacs/open-in-emacs.vsix"

install-macos:
	bash macos/defaults.sh

clean:
	rm -f ~/.local/bin/toggle-app
	rm -f ~/.local/bin/git-dirty-check
