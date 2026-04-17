# Mastering The Craft: Minecraft 1.16.1 Speedrun Tutor

An Ollama-powered tutor that analyzes Minecraft speedrun data and gives actionable coaching feedback instantaniously. Built for 1.16 filtered seeds (MCSR).

- [Mastering The Craft: Minecraft 1.16.1 Speedrun Tutor](#mastering-the-craft-minecraft-1161-speedrun-tutor)
  - [TLDR Setup](#tldr-setup)
  - [What You Get](#what-you-get)
  - [System Requirements](#system-requirements)
    - [Required Software](#required-software)
    - [Minecraft/Mod Requirements](#minecraftmod-requirements)
  - [Install](#install)
  - [Quick Start (CLI)](#quick-start-cli)
    - [1) Analyze Minecraft-generated data (default flow)](#1-analyze-minecraft-generated-data-default-flow)
    - [2) Analyze a direct JSON file](#2-analyze-a-direct-json-file)
    - [3) Live watch mode (auto-analyze each new run)](#3-live-watch-mode-auto-analyze-each-new-run)
    - [4) Useful optional flags](#4-useful-optional-flags)
  - [Quick Start (GUI)](#quick-start-gui)
  - [Copy/Paste Command Reference](#copypaste-command-reference)
  - [How Detection Works](#how-detection-works)
  - [Troubleshooting](#troubleshooting)
    - [Ollama connection errors](#ollama-connection-errors)
    - [Files not found](#files-not-found)
  - [Notes](#notes)

## TLDR Setup

If you already have Minecraft + SpeedRunIGT set up, run this from the project folder:

```bash
ollama pull llama3.3
python main.py --source minecraft
```

For continuous auto-analysis after each run:

```bash
python main.py --source minecraft --watch
```

## What You Get

- CLI mode for one-shot analysis or live watch mode.
- GUI mode (Tkinter) for setup + auto-detecting new runs.
- Feedback grounded in run stats, advancements, and SpeedRunIGT JSON.
- Optional token-saving mode by limiting initial event count.

## System Requirements

### Required Software

- Python 3.10+
- Ollama installed and available in your shell PATH
- Minecraft Java 1.16.1 setup that exports run data

### Minecraft/Mod Requirements

- Fabric 1.16.1 instance (or equivalent 1.16.1 setup)
- SpeedRunIGT mod configured to write JSON run records
- Access to your instance `.minecraft` directory containing:
  - `stats/<uuid>.json`
  - `advancements/<uuid>.json`
  - SpeedRunIGT JSON output

## Install

Run these commands from the project folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Install and start Ollama (if not already running):

```bash
ollama serve
```

Pull the default model used by this app:

```bash
ollama pull llama3.3
```

Notes:

- The app also attempts to start Ollama automatically if needed.
- If a selected model is missing, the app can auto-pull it.

## Quick Start (CLI)

### 1) Analyze Minecraft-generated data (default flow)

```bash
python main.py --source minecraft
```

Use this after ending a run (return to title/close world) so data is flushed to disk.

### 2) Analyze a direct JSON file

```bash
python main.py --source json --file sample_run_data.json
```

### 3) Live watch mode (auto-analyze each new run)

```bash
python main.py --source minecraft --watch
```

Custom poll interval:

```bash
python main.py --source minecraft --watch --poll-seconds 2
```

### 4) Useful optional flags

Set a different Ollama model:

```bash
python main.py --source minecraft --model llama3.3
```

Limit events in initial prompt (token-saving):

```bash
python main.py --source minecraft --max-events 80
```

Run setup diagnostics only:

```bash
python main.py --source minecraft --check
```

Save assembled analysis payload for inspection:

```bash
python main.py --source minecraft --save-data
```

Specify explicit paths when auto-detection fails:

```bash
python main.py --source minecraft \
  --minecraft-dir "$HOME/Library/Application Support/minecraft" \
  --uuid <player_uuid> \
  --igt-file "/path/to/speedrunigt_record.json"
```

## Quick Start (GUI)

Launch:

```bash
python gui_app.py
```

Inside the app:

1. Set your `.minecraft` directory and optional UUID/IGT file.
2. Click **Save Settings**.
3. Click **Validate Paths**.
4. Click **Generate Feedback** for one-shot analysis.
5. Click **Start Watch** for continuous auto-analysis.

## Copy/Paste Command Reference

```bash
# Activate virtual environment
source .venv/bin/activate

# CLI: analyze latest Minecraft run
python main.py --source minecraft

# CLI: watch continuously
python main.py --source minecraft --watch

# CLI: analyze a file directly
python main.py --source json --file sample_run_data.json

# GUI mode
python gui_app.py
```

## How Detection Works

The parser reads:

- `stats/<uuid>.json`
- `advancements/<uuid>.json`
- Latest SpeedRunIGT JSON record (from known folders)

## Troubleshooting

### Ollama connection errors

```bash
ollama serve
ollama pull llama3.3
```

Then rerun the app command.

### Files not found

- Confirm you are using the correct `.minecraft` folder for your instance.
- Confirm SpeedRunIGT actually exported JSON for that run.
- Retry with explicit `--uuid` and `--igt-file` paths.

## Notes

- Current coaching emphasis is strongest from Overworld through Nether progression.
- Works with both raw JSON input and Minecraft-generated files.
