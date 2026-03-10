#!/bin/bash
# macOS defaults — only settings that differ from stock macOS.
# Run via: make install-macos

# Dock: auto-hide, no delay, no animation
defaults write com.apple.dock autohide -bool true
defaults write com.apple.dock autohide-delay -float 0
defaults write com.apple.dock autohide-time-modifier -float 0

killall Dock
