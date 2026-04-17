#!/usr/bin/env python3
"""
Inspect a SpeedRunIGT JSON file and print all available fields and structure.
Usage:
  python3 inspect_json.py [path_to_json_file]

If no path is provided, auto-discovers the newest speedrunigt record from your Minecraft folder.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def find_newest_speedrunigt_record(minecraft_dir: Path) -> Optional[Path]:
    """Auto-find the newest speedrunigt/record.json across all save worlds."""
    saves_dir = minecraft_dir / "saves"
    if not saves_dir.exists():
        return None

    candidates: List[Path] = []
    for world_dir in saves_dir.iterdir():
        if not world_dir.is_dir():
            continue
        record_path = world_dir / "speedrunigt" / "record.json"
        if record_path.exists():
            candidates.append(record_path)

    if not candidates:
        return None

    return max(candidates, key=lambda p: p.stat().st_mtime)


def print_structure(
    data: Any,
    prefix: str = "",
    max_depth: int = 10,
    depth: int = 0,
    visited_ids: Optional[Set[int]] = None,
) -> None:
    """Recursively print JSON structure with indentation."""
    if visited_ids is None:
        visited_ids = set()

    if depth > max_depth:
        print(f"{prefix}[... max depth reached]")
        return

    # Detect cycles
    data_id = id(data)
    if data_id in visited_ids:
        print(f"{prefix}[... circular ref]")
        return
    if isinstance(data, (dict, list)):
        visited_ids.add(data_id)

    if isinstance(data, dict):
        if not data:
            print(f"{prefix}{{}} (empty dict)")
            return
        print(f"{prefix}{{")
        keys = sorted(data.keys())
        for i, key in enumerate(keys):
            value = data[key]
            is_last = i == len(keys) - 1
            comma = "" if is_last else ","
            type_name = type(value).__name__

            if isinstance(value, dict):
                print(f"{prefix}  '{key}': {{")
                print_structure(value, prefix + "    ", max_depth, depth + 1, visited_ids)
                print(f"{prefix}  }}{comma}")
            elif isinstance(value, list):
                if not value:
                    print(f"{prefix}  '{key}': [] (empty list){comma}")
                else:
                    item_type = type(value[0]).__name__
                    print(f"{prefix}  '{key}': [ {item_type}, ... ({len(value)} items) ]{comma}")
            elif isinstance(value, str):
                preview = value[:60] if len(value) > 60 else value
                preview = preview.replace("\n", "\\n")
                print(f"{prefix}  '{key}': \"{preview}\" ({type_name}){comma}")
            elif isinstance(value, bool):
                print(f"{prefix}  '{key}': {value} (bool){comma}")
            elif value is None:
                print(f"{prefix}  '{key}': null{comma}")
            else:
                print(f"{prefix}  '{key}': {value} ({type_name}){comma}")
        print(f"{prefix}}}")
    elif isinstance(data, list):
        if not data:
            print(f"{prefix}[] (empty list)")
            return
        print(f"{prefix}[")
        for i, item in enumerate(data[:5]):  # Show first 5 items
            is_last = i == min(4, len(data) - 1)
            comma = "" if is_last else ","
            if isinstance(item, dict):
                print(f"{prefix}  {{")
                print_structure(item, prefix + "    ", max_depth, depth + 1, visited_ids)
                print(f"{prefix}  }}{comma}")
            elif isinstance(item, list):
                print(f"{prefix}  [...list...]{comma}")
            else:
                print(f"{prefix}  {item} ({type(item).__name__}){comma}")
        if len(data) > 5:
            print(f"{prefix}  ...and {len(data) - 5} more items")
        print(f"{prefix}]")
    else:
        print(f"{prefix}{data} ({type_name})")


def collect_all_keys(data: Any, prefix: str = "", keys_set: Optional[Set[str]] = None) -> Set[str]:
    """Recursively collect all dictionary keys in the JSON structure."""
    if keys_set is None:
        keys_set = set()

    if isinstance(data, dict):
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            keys_set.add(full_key)
            collect_all_keys(value, full_key, keys_set)
    elif isinstance(data, list) and data:
        for item in data:
            collect_all_keys(item, prefix, keys_set)

    return keys_set


def collect_leaf_values(
    data: Any,
    prefix: str = "",
    leaves: Optional[Dict[str, List[Any]]] = None,
    max_items: int = 3,
) -> Dict[str, List[Any]]:
    """Collect sample leaf values for all keys."""
    if leaves is None:
        leaves = {}

    if isinstance(data, dict):
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, (dict, list)):
                collect_leaf_values(value, full_key, leaves, max_items)
            else:
                if full_key not in leaves:
                    leaves[full_key] = []
                if len(leaves[full_key]) < max_items:
                    leaves[full_key].append(value)
    elif isinstance(data, list):
        for item in data:
            collect_leaf_values(item, prefix, leaves, max_items)

    return leaves


def main() -> None:
    if len(sys.argv) > 1:
        file_path = Path(sys.argv[1]).expanduser().resolve()
    else:
        minecraft_dir = Path(
            "/Applications/MultiMC.app/Data/instances/Minecraft Tutor/.minecraft"
        )
        file_path = find_newest_speedrunigt_record(minecraft_dir)
        if file_path is None:
            print("Error: Could not find any speedrunigt/record.json files.")
            print("Usage: python3 inspect_json.py [path_to_json]")
            sys.exit(1)

    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    try:
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {file_path}: {e}")
        sys.exit(1)

    print(f"\n{'=' * 80}")
    print(f"Inspecting: {file_path}")
    print(f"File size: {file_path.stat().st_size / 1024:.1f} KB")
    print("=" * 80)

    # Print full structure
    print("\n=== FULL STRUCTURE ===\n")
    print_structure(data)

    # Collect and print all keys
    print("\n" + "=" * 80)
    print("=== ALL AVAILABLE KEYS ===\n")
    all_keys = collect_all_keys(data)
    for key in sorted(all_keys):
        print(f"  {key}")
    print(f"\nTotal unique keys: {len(all_keys)}")

    # Collect and print leaf values
    print("\n" + "=" * 80)
    print("=== SAMPLE VALUES FOR LEAF KEYS ===\n")
    leaves = collect_leaf_values(data, max_items=2)
    for key in sorted(leaves.keys()):
        values = leaves[key]
        value_strs = [repr(v)[:80] for v in values]
        print(f"  {key}:")
        for val_str in value_strs:
            print(f"    - {val_str}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
