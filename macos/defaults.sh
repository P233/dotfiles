#!/bin/bash
# macOS defaults — only settings that differ from stock macOS.
# Run via: make install-macos
set -eu

# Windows: disable automatic window animations in apps that honor this global preference.
# This does not disable Dock minimization or Spaces transitions.
defaults write -g NSAutomaticWindowAnimationsEnabled -bool false

# Dock: auto-hide without a reveal delay or hide/show animation.
defaults write com.apple.dock autohide -bool true
defaults write com.apple.dock autohide-delay -float 0
defaults write com.apple.dock autohide-time-modifier -float 0

# Dock: disable icon bouncing when launching apps.
defaults write com.apple.dock launchanim -bool false

# Dock: preserve the existing scale minimize effect; this is still animated.
defaults write com.apple.dock mineffect -string scale

killall Dock
