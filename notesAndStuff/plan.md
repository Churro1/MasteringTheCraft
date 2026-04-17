# Minecraft 1.16.1 Speedrun Tutor: Condensed Plan + Status

## Project Goal

Use local Minecraft run artifacts plus Ollama to provide actionable speedrun coaching in CLI and GUI flows.

## Implemented

- [x] Core architecture in place:
  - `main.py` (CLI app + watch mode)
  - `ollama_client.py` (chat client)
  - `speedrun_data_parser.py` (data loading + feature extraction)
  - `gui_app.py` (desktop GUI with validation and watch)
- [x] Two input modes are implemented:
  - `--source json`
  - `--source minecraft`
- [x] Ollama startup automation:
  - Auto-check API
  - Auto-run `ollama serve` if needed
  - Auto-pull missing model
- [x] Live workflows implemented:
  - CLI one-shot analysis + follow-up chat
  - CLI `--watch` mode
  - GUI one-shot feedback and GUI watch mode
- [x] Diagnostics and tooling:
  - `--check` for setup diagnostics
  - `--save-data` for prompt payload capture

## Still Needs Implementation

- [ ] Automatic launcher path discovery for common macOS launchers (instead of relying on manual `--minecraft-dir` overrides).
- [ ] Stronger SpeedRunIGT schema handling and validation against additional real-world record variants.
- [ ] Persistent run history and trend comparison across attempts.
- [ ] Split-specific drill generation driven by multi-run trends.
- [ ] Expert model. Give LLM context from world record level runs for it to base its feedback on.
