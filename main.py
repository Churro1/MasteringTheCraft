import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from ollama_client import OllamaTutorClient
from speedrun_data_parser import SpeedrunDataParser


SYSTEM_PROMPT = """
You are an expert Minecraft 1.16.1 speedrun tutor focused on coaching beginners.
You analyze run event data and provide practical, specific, non-judgmental advice. No need to be kind. No need to lie. Just give honest feedback based on the data. Your goal is to help the runner improve as quickly as possible.

Critical output rule:
- Do NOT describe the dataset format or list JSON keys/sections.
- Do NOT explain "what the data is".
- Do NOT start with phrases like "This is JSON...", "The data contains...", or "It appears to be...".
- Always convert data into performance insights and coaching actions.
- Only give coaching feedback that is directly supported by the data.
- Do not give a list of the acheivements. 

Start with a concise run-performance summary sentence that states what happened in the run.

Hard constraints:

- The user needs you to use the information in the provided JSON data to give feedback. Do not make assumptions beyond the data.
- You will have to determine what splits the user was practicing based on the events and their timing. Do not assume splits that are not supported by the data.
- The user may use tools to start their practice later in the run. Only give feedback on the portion of the run that is supported by the data you have. If you don't have data for a split, say you don't have enough information to analyze it.
- Use these baseline heuristics when relevant:
    - Overworld split:
        - Iron target: about 3 for bucket, 3 for iron pickaxe, and one for flint and steel (but sometimes a wood light portal is better).
        - Hay bales around 8 is often enough; over-farming is a common loss.
        - Sub-3-minute portal entry is excellent, 3-5 is decent, >5 usually has route or execution leaks.
    - Nether split:
        - Finding bastion within 30ish second is great. Much over 1 minute is a sign of a route or execution mistake.
        - From the bastion you need to have 20 obsidian, at least 14 ender pearls, and string for at least 6 beds. This is the ideal.
        - Finding the fortress is the next critical step. Use f3 to pieray where the spawner is.
        - get 7 blaze rods.
    - Finding Stronghold
        - Use a calcualtor to minimize the number of eyes you need to throw. Each eye has about 8-12 seconds throw+travel time, so saving even a few can be a big time save.
        - Travel in the nether to get to the location and build a second portal there.
    - Found Stronghold: 
        - You need to craft all beds, eyes of ender, and have food (or hunger reset by setting your spawn and dying.)
    - End fight: 
        - Use beds to kill the ender dragon in a one cycle. 
- Distinguish between:
  1) Inventory/resource mistakes
  2) Routing/pathing mistakes
  3) Mechanical execution mistakes

Response style:
- Be concise and actionable.
- When giving critique, include concrete alternatives.
- If information is missing from the JSON, state assumptions clearly.
- Every claim should reference a concrete metric/timestamp/count from the run data.
- If run data is too sparse for coaching, say that clearly in one sentence and then provide exactly 3 data-collection steps for the next attempt.
""".strip()


STRICT_RESPONSE_TEMPLATE = (
    "Use this exact output format and headings with no extra sections or preamble:\n"
    "RUN SUMMARY:\n"
    "<2-4 sentences about what happened in the run. Do not describe JSON/schema.>\n\n"
    "TOP TIME LOSSES:\n"
    "1) <loss #1 with evidence>\n"
    "2) <loss #2 with evidence>\n"
    "3) <loss #3 with evidence>\n\n"
    "TOP FIXES FOR NEXT RUN:\n"
    "1) <specific fix #1 linked to loss #1>\n"
    "2) <specific fix #2 linked to loss #2>\n"
    "3) <specific fix #3 linked to loss #3>\n\n"
    "PRACTICE DRILL:\n"
    "<one short drill for the next attempt>\n"
)


STRICT_HEADINGS = (
    "RUN SUMMARY:",
    "TOP TIME LOSSES:",
    "TOP FIXES FOR NEXT RUN:",
    "PRACTICE DRILL:",
)


SCHEMA_PHRASES = (
    "this is a json",
    "the data contains",
    "it appears to be",
    "the json",
    "collection of",
    "the data is organized",
)


def _matches_strict_format(text: str) -> bool:
    lowered = text.lower()
    if any(marker in lowered for marker in SCHEMA_PHRASES):
        return False

    return all(heading in text for heading in STRICT_HEADINGS)


def generate_strict_initial_feedback(client: OllamaTutorClient, prompt: str) -> str:
    """Generate first-pass feedback and force one rewrite if format drifts."""
    first_reply = client.send(prompt, system_instruction=SYSTEM_PROMPT)
    if _matches_strict_format(first_reply):
        return first_reply

    rewrite_prompt = (
        "Rewrite your previous response now."
        " Keep all factual claims grounded in the same run data,"
        " but strictly follow this exact template with these exact headings.\n\n"
        f"{STRICT_RESPONSE_TEMPLATE}\n"
        "Hard rules:\n"
        "- No schema/data-format description.\n"
        "- No extra sections.\n"
        "- Keep it concise and actionable."
    )
    return client.send(rewrite_prompt, system_instruction=SYSTEM_PROMPT)


def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description="Analyze Minecraft speedrun JSON and chat with an Ollama tutoring agent."
    )
    parser.add_argument(
        "--source",
        choices=["json", "minecraft"],
        default="minecraft",
        help="Input source type: direct JSON file or Minecraft-generated files.",
    )
    parser.add_argument(
        "--file",
        type=str,
        default="",
        help="Path to JSON run data file.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="llama3.3",
        help="Ollama model name.",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=120,
        help="Max number of events to include in initial analysis prompt.",
    )
    parser.add_argument(
        "--minecraft-dir",
        type=str,
        default="/Applications/MultiMC.app/Data/instances/Minecraft Tutor/.minecraft",
        help="Path to .minecraft directory for stats/advancements/SpeedRunIGT data.",
    )
    parser.add_argument(
        "--uuid",
        type=str,
        default="",
        help="Minecraft UUID for stats and advancements JSON. If omitted, newest stats file is used.",
    )
    parser.add_argument(
        "--igt-file",
        type=str,
        default="",
        help="Path to SpeedRunIGT record JSON file. If omitted, newest record in known folders is used.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep running and automatically analyze new Minecraft run data updates.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=3,
        help="Polling interval in seconds for watch mode.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run diagnostic checks on Minecraft directory setup and exit.",
    )
    parser.add_argument(
        "--save-data",
        action="store_true",
        help="Save analysis data to a file so you can inspect what Ollama receives.",
    )
    return parser.parse_args()


def read_json_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if path.suffix.lower() != ".json":
        raise ValueError("Please provide a .json file.")

    with path.open("r", encoding="utf-8") as f:
        try:
            payload = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Top-level JSON must be an object with run metadata and events.")
    return payload


def compact_run_data(data: Dict[str, Any], max_events: int) -> Dict[str, Any]:
    compact: Dict[str, Any] = {k: v for k, v in data.items() if k != "events"}
    events = data.get("events", [])

    if not isinstance(events, list):
        compact["events"] = events
        return compact

    max_events = max(1, max_events)
    if len(events) <= max_events:
        compact["events"] = events
        compact["event_count_original"] = len(events)
        return compact

    head_count = max_events // 2
    tail_count = max_events - head_count
    compact["events"] = events[:head_count] + events[-tail_count:]
    compact["event_count_original"] = len(events)
    compact["event_count_sent"] = len(compact["events"])
    compact["event_truncated"] = True
    compact["event_truncation_note"] = (
        "Only the first and last events were included for the initial analysis "
        "to reduce token usage."
    )
    return compact


def build_initial_prompt(data: Dict[str, Any], source_path: Path) -> str:
    serialized = json.dumps(data, separators=(",", ":"), ensure_ascii=True)
    return (
        "Analyze this Minecraft speedrun run data and give me coaching feedback.\\n\\n"
        f"{STRICT_RESPONSE_TEMPLATE}\\n"
        f"Source file: {source_path}\\n"
        f"Run data JSON:\\n{serialized}"
    )


def _serialize_for_prompt(payload: Optional[Dict[str, Any]], max_chars: int = 30000) -> str:
    if not isinstance(payload, dict):
        return "{}"

    serialized = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    if len(serialized) <= max_chars:
        return serialized

    return (
        serialized[:max_chars]
        + "\\n... [TRUNCATED FOR PROMPT SIZE] ..."
        + f"\\n(original_length={len(serialized)} chars, sent_length={max_chars} chars)"
    )


def build_minecraft_context_prompt(
    context_text: str,
    minecraft_dir: Path,
    stats_data: Optional[Dict[str, Any]],
    advancements_data: Optional[Dict[str, Any]],
    igt_data: Optional[Dict[str, Any]],
    stats_path: Optional[Path],
    advancements_path: Optional[Path],
    igt_path: Optional[Path],
) -> str:
    stats_json = _serialize_for_prompt(stats_data)
    advancements_json = _serialize_for_prompt(advancements_data)
    igt_json = _serialize_for_prompt(igt_data)

    return (
        "Analyze this Minecraft speedrun run summary and give me coaching feedback.\\n\\n"
        "Use BOTH the parsed summary and the raw JSON sections."
        " If they disagree, trust the raw JSON and explain the mismatch.\\n\\n"
        "Important: Do NOT describe JSON structure, key names, or file contents at a schema level."
        " Convert data into run insights, mistakes, and next actions only.\\n\\n"
        f"{STRICT_RESPONSE_TEMPLATE}\\n"
        f"Minecraft directory: {minecraft_dir}\\n"
        f"Stats file: {stats_path}\\n"
        f"Advancements file: {advancements_path}\\n"
        f"SpeedRunIGT file: {igt_path}\\n\\n"
        "Parsed context:\\n"
        f"{context_text}\\n\\n"
        "RAW SPEEDRUNIGT JSON:\\n"
        f"{igt_json}\\n\\n"
        "RAW MINECRAFT STATS JSON:\\n"
        f"{stats_json}\\n\\n"
        "RAW MINECRAFT ADVANCEMENTS JSON:\\n"
        f"{advancements_json}"
    )


def prompt_for_json_path(initial_value: str) -> Path:
    if initial_value.strip():
        return Path(initial_value.strip()).expanduser().resolve()

    user_input = input("Enter path to your run JSON file: ").strip()
    return Path(user_input).expanduser().resolve()


def _ollama_api_ready() -> bool:
    endpoint = "http://127.0.0.1:11434/api/tags"
    try:
        request = urllib.request.Request(endpoint, method="GET")
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


def start_ollama_service() -> None:
    if _ollama_api_ready():
        return

    start_result = subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if start_result.poll() is not None:
        raise SystemExit(
            "Failed to start terminal Ollama server with `ollama serve`. "
            "Ensure Ollama CLI is installed and available in PATH."
        )


def wait_for_ollama_api(timeout_seconds: int = 45) -> None:
    endpoint = "http://127.0.0.1:11434/api/tags"
    deadline = time.time() + timeout_seconds
    last_error = ""

    while time.time() < deadline:
        try:
            request = urllib.request.Request(endpoint, method="GET")
            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status == 200:
                    return
        except urllib.error.URLError as exc:
            last_error = str(exc)
        except Exception as exc:
            last_error = str(exc)
        time.sleep(1)

    raise SystemExit(
        "Ollama did not become ready on http://127.0.0.1:11434 in time. "
        f"Last error: {last_error or 'No response from local Ollama API.'}"
    )


def ensure_ollama_model(model: str) -> None:
    list_result = subprocess.run(
        ["ollama", "list"],
        capture_output=True,
        text=True,
        check=False,
    )
    if list_result.returncode != 0:
        detail = (list_result.stderr or list_result.stdout).strip() or "Unknown ollama error."
        raise SystemExit(f"Failed to list Ollama models. Details: {detail}")

    if model in list_result.stdout:
        return

    print(f"Model '{model}' not found locally. Pulling it now...\n")
    pull_result = subprocess.run(
        ["ollama", "pull", model],
        capture_output=False,
        text=True,
        check=False,
    )
    if pull_result.returncode != 0:
        raise SystemExit(
            f"Failed to pull Ollama model '{model}'. Run `ollama pull {model}` manually and retry."
        )


def build_minecraft_prompt_and_signature(args: argparse.Namespace) -> Tuple[str, str]:
    minecraft_dir = Path(args.minecraft_dir).expanduser().resolve()
    parser = SpeedrunDataParser(
        minecraft_dir=minecraft_dir,
        uuid=args.uuid.strip() or None,
        igt_file=Path(args.igt_file).expanduser().resolve() if args.igt_file.strip() else None,
    )
    parsed_context = parser.generate_llm_context()
    prompt = build_minecraft_context_prompt(
        context_text=parsed_context,
        minecraft_dir=minecraft_dir,
        stats_data=parser.stats_data,
        advancements_data=parser.advancements_data,
        igt_data=parser.igt_data,
        stats_path=parser.stats_path,
        advancements_path=parser.advancements_path,
        igt_path=parser.resolved_igt_path,
    )

    signature = build_file_signature(
        [parser.stats_path, parser.advancements_path, parser.resolved_igt_path]
    )
    return prompt, signature


def build_file_signature(paths: Iterable[Optional[Path]]) -> str:
    parts = []
    for path in paths:
        if path is None:
            continue
        if not path.exists():
            parts.append(f"{path}:missing")
            continue
        stat = path.stat()
        parts.append(f"{path}:{stat.st_mtime_ns}:{stat.st_size}")
    return "|".join(parts)


def save_analysis_data(prompt: str, save_path: Optional[Path] = None) -> None:
    """Save the analysis prompt/data to a file for inspection."""
    if save_path is None:
        save_path = Path.home() / ".speedrun_tutor_last_analysis.json"
    
    data = {
        "timestamp": datetime.now().isoformat(),
        "analysis_prompt": prompt,
    }
    save_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\n📄 Analysis data saved to: {save_path}")
    print(f"   View with: cat {save_path}")


def run_diagnostic_checks(args: argparse.Namespace) -> None:
    """Run Minecraft setup diagnostics and exit."""
    if args.source != "minecraft":
        print("Diagnostics only work with --source minecraft.")
        return

    minecraft_dir = Path(args.minecraft_dir).expanduser().resolve()
    print("\n=== Minecraft Setup Diagnostic ===")
    print(f"\nChecking directory: {minecraft_dir}\n")

    # Check main directory
    if not minecraft_dir.exists():
        print("[FAIL] CRITICAL: Minecraft directory not found")
        print(f"   Expected: {minecraft_dir}")
        print(f"   Please verify --minecraft-dir is correct.\n")
        return
    else:
        print("[OK] Minecraft directory found")

    # Check root stats folder and files
    stats_dir = minecraft_dir / "stats"
    print(f"\n[Check] Root stats folder: {stats_dir}")
    if stats_dir.exists():
        stat_files = list(stats_dir.glob("*.json"))
        if stat_files:
            print(f"   [OK] Found {len(stat_files)} stat file(s)")
            for f in sorted(stat_files)[-3:]:
                size_kb = f.stat().st_size / 1024
                print(f"      - {f.name} ({size_kb:.1f} KB)")
        else:
            print("   [WARN] No stat files yet. Play a run and close the world to generate them.")
    else:
        print("   [INFO] Root stats folder does not exist (normal for many save-based setups).")

    # Check root advancements folder
    advancements_dir = minecraft_dir / "advancements"
    print(f"\n[Check] Root advancements folder: {advancements_dir}")
    if advancements_dir.exists():
        adv_files = list(advancements_dir.glob("*.json"))
        if adv_files:
            print(f"   [OK] Found {len(adv_files)} advancement file(s)")
            for f in sorted(adv_files)[-3:]:
                size_kb = f.stat().st_size / 1024
                print(f"      - {f.name} ({size_kb:.1f} KB)")
        else:
            print("   [WARN] No advancement files yet. Play a run and close the world to generate them.")
    else:
        print("   [INFO] Root advancements folder does not exist (normal for many save-based setups).")

    # Check top-level SpeedRunIGT folders
    print("\n[Check] Top-level SpeedRunIGT folders:")
    candidate_dirs = [
        minecraft_dir / "speedrunigt",
        minecraft_dir / "config" / "speedrunigt",
        minecraft_dir / "logs" / "speedrunigt",
    ]
    found_any_igt = False
    for candidate in candidate_dirs:
        status = "[OK]" if candidate.exists() else "[MISS]"
        print(f"   {status} {candidate}")
        if candidate.exists():
            json_files = list(candidate.rglob("*.json"))
            if json_files:
                found_any_igt = True
                print(f"      Found {len(json_files)} JSON file(s)")
                for f in sorted(json_files)[-2:]:
                    size_kb = f.stat().st_size / 1024
                    print(f"         - {f.name} ({size_kb:.1f} KB)")
            else:
                print(f"      Folder exists but no JSON files yet.")

    # Check world save folders, which is where your instance writes run data.
    saves_dir = minecraft_dir / "saves"
    world_hits = 0
    if saves_dir.exists():
        print("\n[Check] Save-world data folders:")
        for world_dir in sorted([d for d in saves_dir.iterdir() if d.is_dir()]):
            world_stats = world_dir / "stats"
            world_adv = world_dir / "advancements"
            world_igt = world_dir / "speedrunigt"

            stats_count = len(list(world_stats.glob("*.json"))) if world_stats.exists() else 0
            adv_count = len(list(world_adv.glob("*.json"))) if world_adv.exists() else 0
            igt_count = len(list(world_igt.glob("*.json"))) if world_igt.exists() else 0

            if stats_count or adv_count or igt_count:
                world_hits += 1
                print(f"   [WORLD] {world_dir.name}")
                print(f"      stats/*.json: {stats_count}")
                print(f"      advancements/*.json: {adv_count}")
                print(f"      speedrunigt/*.json: {igt_count}")

                if world_igt.exists() and igt_count:
                    newest_igt = max(world_igt.glob("*.json"), key=lambda p: p.stat().st_mtime)
                    print(f"      latest IGT file: {newest_igt.name}")

    if world_hits:
        print(
            "\n[OK] Found run data in save-world folders. "
            "This is expected for your MCSR setup."
        )

    if not found_any_igt:
        print("\n   [INFO] No top-level SpeedRunIGT records found.")
        print("          This is fine if records are under saves/<world>/speedrunigt.")

    # Summary
    print(f"\n=== Summary ===")
    print(f"Before running the tutor:")
    print(f"  1. Make sure you have a Fabric 1.16.1 instance with SpeedRunIGT mod installed.")
    print(f"  2. Play an Overworld split and return to title (to flush files).")
    print(f"  3. Verify one save-world has stats, advancements, and speedrunigt JSON files.")
    print(f"  4. Then run: python main.py --source minecraft")
    print()


def run_watch_mode(args: argparse.Namespace) -> None:
    if args.source != "minecraft":
        raise SystemExit("Watch mode currently supports only --source minecraft.")

    poll_seconds = max(1, args.poll_seconds)
    minecraft_dir = Path(args.minecraft_dir).expanduser().resolve()
    print("Tutor watcher started.")
    print(f"Monitoring folder: {minecraft_dir}")
    print(f"Watching Minecraft data every {poll_seconds}s...")
    print("Waiting for first complete run data export...\n")

    last_signature: Optional[str] = None
    last_error: str = ""
    idle_cycles = 0

    while True:
        try:
            prompt, signature = build_minecraft_prompt_and_signature(args)
        except Exception as exc:
            current_error = str(exc)
            if current_error != last_error:
                print(f"[watch] Waiting for data: {current_error}")
                last_error = current_error
            time.sleep(poll_seconds)
            continue

        last_error = ""
        idle_cycles += 1
        if signature == last_signature:
            if idle_cycles % max(1, 20 // poll_seconds) == 0:
                print("[watch] No new run yet. Still monitoring...")
            time.sleep(poll_seconds)
            continue

        idle_cycles = 0
        if last_signature is None:
            print("[watch] Found run data. Reading data and generating feedback...")
        else:
            print("[watch] Detected new/updated run. Reading data and generating feedback...")

        client = OllamaTutorClient(model=args.model)
        try:
            print("[watch] Sending to Ollama model...")
            feedback = generate_strict_initial_feedback(client, prompt)
        except Exception as exc:
            print(f"[watch] Ollama call failed: {exc}")
            time.sleep(poll_seconds)
            continue

        last_signature = signature
        print("\n========== Tutor Feedback ==========")
        print(feedback)
        print("========== End Feedback ==========\n")
        print("[watch] Ready for your next run. Monitoring for changes...\n")

        time.sleep(poll_seconds)


def main() -> None:
    args = parse_args()

    if args.check:
        run_diagnostic_checks(args)
        return

    start_ollama_service()
    wait_for_ollama_api()
    ensure_ollama_model(args.model)

    if args.watch:
        try:
            run_watch_mode(args)
        except KeyboardInterrupt:
            print("\nStopped watcher.")
        return

    client = OllamaTutorClient(model=args.model)

    if args.source == "minecraft":
        try:
            minecraft_dir = Path(args.minecraft_dir).expanduser().resolve()
            print(f"Reading Minecraft data from: {minecraft_dir}")
            initial_prompt, _ = build_minecraft_prompt_and_signature(args)
            print("✅ Successfully loaded Minecraft run data.\n")
        except Exception as exc:
            print(f"❌ Error reading Minecraft data: {exc}")
            print(f"\nRun 'python main.py --check' to diagnose your setup.\n")
            raise SystemExit(f"Minecraft data input error: {exc}") from exc
    else:
        try:
            json_path = prompt_for_json_path(args.file)
            run_data = read_json_file(json_path)
        except Exception as exc:
            raise SystemExit(f"Input error: {exc}") from exc

        compact_data = compact_run_data(run_data, args.max_events)
        initial_prompt = build_initial_prompt(compact_data, json_path)

    if args.save_data:
        save_analysis_data(initial_prompt)

    print("\\nAnalyzing your run...\\n")

    try:
        first_reply = generate_strict_initial_feedback(client, initial_prompt)
    except Exception as exc:
        raise SystemExit(f"Ollama call failed: {exc}") from exc

    print(first_reply)
    print("\\nYou can now chat with the tutor. Type 'exit' to quit.\\n")

    while True:
        user_text = input("You: ").strip()
        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit"}:
            print("Good luck on your next run.")
            break

        try:
            reply = client.send(user_text, system_instruction=SYSTEM_PROMPT)
        except Exception as exc:
            print(f"Error: {exc}")
            continue

        print(f"\\nTutor: {reply}\\n")


if __name__ == "__main__":
    main()
