.PHONY: install install-scripts install-macos clean

install: install-scripts install-macos

install-scripts:
	mkdir -p ~/.local/bin
	swiftc -O -o ~/.local/bin/toggle-app scripts/toggle-app.swift
	install -m 755 scripts/git-dirty-check.sh ~/.local/bin/git-dirty-check

install-macos:
	bash macos/defaults.sh

clean:
	rm -f ~/.local/bin/toggle-app
	rm -f ~/.local/bin/git-dirty-check
