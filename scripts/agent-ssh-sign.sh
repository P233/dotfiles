#!/bin/sh
# Use the existing local signing agent rather than an interactive GUI signer.
export SSH_AUTH_SOCK="$HOME/.local/state/agent-signing/agent.sock"
exec /usr/bin/ssh-keygen "$@"
