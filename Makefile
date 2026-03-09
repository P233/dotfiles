.PHONY: install clean

install:
	mkdir -p ~/.local/bin
	swiftc -O -o ~/.local/bin/toggle-app scripts/toggle-app.swift

clean:
	rm -f ~/.local/bin/toggle-app
