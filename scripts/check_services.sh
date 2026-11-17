#!/usr/bin/env bash
# Phase 0 check: are Ollama and VoiceStudio reachable on this machine?
set -u
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
VS_URL="${VOICESTUDIO_URL:-http://127.0.0.1:3900}"

ok()   { printf '  \e[32m✔\e[0m %s\n' "$*"; }
bad()  { printf '  \e[31m✘\e[0m %s\n' "$*"; }

echo "Ollama ($OLLAMA_URL)"
if v=$(curl -sf -m 3 "$OLLAMA_URL/api/version"); then
  ok "running: $v"
  curl -sf -m 5 "$OLLAMA_URL/api/tags" | python3 -c 'import json,sys; [print("    -", m["name"]) for m in json.load(sys.stdin)["models"]]'
else
  bad "not reachable. Start it: systemctl start ollama   (or: ollama serve)"
fi

echo "VoiceStudio ($VS_URL)"
if d=$(curl -sf -m 3 "$VS_URL/.well-known/voicestudio-speech"); then
  ok "discovery: $(echo "$d" | head -c 200)"
  echo "  voices:"; curl -sf -m 5 "$VS_URL/v1/audio/voices" | head -c 600; echo
  echo "  models:"; curl -sf -m 5 "$VS_URL/v1/models" | head -c 600; echo
else
  bad "not reachable. Install: yay -S voicestudio-bin  (then launch it and download one STT + one TTS model)"
fi
