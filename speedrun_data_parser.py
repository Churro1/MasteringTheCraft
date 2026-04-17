from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass
class SpeedrunFeatureBundle:
    """Container for extracted speedrun coaching features."""

    movement: Dict[str, Optional[float]]
    resources: Dict[str, int]
    milestones: Dict[str, bool]
    run_timing: Dict[str, Any]
    crafting_stats: Dict[str, int]
    mining_stats: Dict[str, int]
    item_usage: Dict[str, int]
    key_advancements: Dict[str, Any]
    run_metadata: Dict[str, Any]
    detailed_movement: Dict[str, Any]


class SpeedrunDataParser:
    """Parse Minecraft and SpeedRunIGT JSON artifacts for tutoring analysis.

    This class intentionally only handles data loading and feature extraction.
    LLM request logic should remain in a separate module.
    """

    def __init__(
        self,
        minecraft_dir: Path,
        uuid: Optional[str] = None,
        igt_file: Optional[Path] = None,
    ) -> None:
        """Initialize parser with local Minecraft data paths.

        Args:
            minecraft_dir: The `.minecraft` directory path.
            uuid: Player UUID string used by stats/advancements JSON files.
                If omitted, the parser auto-detects the newest stats file UUID.
            igt_file: Path to a SpeedRunIGT JSON record file.
                If omitted, parser attempts to auto-detect the newest record file.
        """
        self.minecraft_dir: Path = minecraft_dir.expanduser().resolve()
        self.uuid: Optional[str] = uuid
        self.igt_file: Optional[Path] = igt_file.expanduser().resolve() if igt_file else None

        self.stats_data: Optional[Dict[str, Any]] = None
        self.advancements_data: Optional[Dict[str, Any]] = None
        self.igt_data: Optional[Dict[str, Any]] = None

        self.stats_path: Optional[Path] = None
        self.advancements_path: Optional[Path] = None
        self.resolved_igt_path: Optional[Path] = None

    def load_data(self) -> None:
        """Load stats, advancements, and SpeedRunIGT JSON files.

        Raises:
            FileNotFoundError: If any required file cannot be found.
            JSONDecodeError: If a JSON file exists but is malformed.
            ValueError: If JSON content has an unexpected top-level structure.
        """
        self.resolved_igt_path = self._resolve_igt_file()
        self.stats_path, self.advancements_path = self._resolve_stats_and_advancements_paths(
            self.resolved_igt_path
        )

        self.stats_data = self._load_json_file(self.stats_path)
        self.advancements_data = self._load_json_file(self.advancements_path)
        self.igt_data = self._load_json_file(self.resolved_igt_path)

    def extract_movement_efficiency(self) -> Dict[str, Optional[float]]:
        """Extract movement totals and sprint-to-walk efficiency.

        Returns:
            Dictionary containing walk/sprint distances in blocks and sprint/walk ratio.
            Ratio is `None` when walk distance is zero.

        Raises:
            RuntimeError: If data has not been loaded yet.
        """
        stats = self._require_stats()
        custom = self._get_nested_dict(stats, ["stats", "minecraft:custom"])

        walk_cm = int(custom.get("minecraft:walk_one_cm", 0) or 0)
        sprint_cm = int(custom.get("minecraft:sprint_one_cm", 0) or 0)

        walk_blocks = walk_cm / 100.0
        sprint_blocks = sprint_cm / 100.0
        ratio = None if walk_blocks <= 0 else sprint_blocks / walk_blocks

        return {
            "walk_blocks": round(walk_blocks, 2),
            "sprint_blocks": round(sprint_blocks, 2),
            "sprint_to_walk_ratio": round(ratio, 3) if ratio is not None else None,
        }

    def extract_resource_totals(self) -> Dict[str, int]:
        """Extract core Overworld gathering metrics from mined block stats.

        Returns:
            Dictionary with total logs, iron ore, and stone mined counts.

        Raises:
            RuntimeError: If data has not been loaded yet.
        """
        stats = self._require_stats()
        mined = self._get_nested_dict(stats, ["stats", "minecraft:mined"])

        total_logs = self._sum_matching_keys(
            mined,
            includes=("log",),
            excludes=("stripped_",),
        )
        total_iron_ore = self._sum_matching_keys(
            mined,
            includes=("iron_ore",),
            excludes=(),
        )
        total_stone = int(mined.get("minecraft:stone", 0) or 0)

        return {
            "total_logs_mined": total_logs,
            "total_iron_ore_mined": total_iron_ore,
            "total_stone_mined": total_stone,
        }

    def extract_overworld_milestones(self) -> Dict[str, bool]:
        """Extract key progress milestones from advancements data.

        Tries separate advancements JSON first, then falls back to checking inline
        advancements in the SpeedRunIGT record if available.

        Returns:
            Dictionary containing milestone booleans for smelted iron and entered nether.

        Raises:
            RuntimeError: If data has not been loaded yet.
        """
        advancements = self._require_advancements()

        smelt_iron_ids = (
            "minecraft:story/smelt_iron",
            "minecraft:story/obtain_armor",
        )
        enter_nether_ids = (
            "minecraft:story/enter_the_nether",
            "minecraft:nether/root",
        )

        smelted_iron = self._any_advancement_done(advancements, smelt_iron_ids)
        entered_nether = self._any_advancement_done(advancements, enter_nether_ids)

        # Fallback: check SpeedRunIGT inline advancements if main ones aren't found
        if not entered_nether and self.igt_data:
            igt_advancements = self._get_nested_dict(self.igt_data, ["advancements"])
            if igt_advancements:
                entered_nether = self._any_advancement_done(igt_advancements, enter_nether_ids)

        if not smelted_iron and self.igt_data:
            igt_advancements = self._get_nested_dict(self.igt_data, ["advancements"])
            if igt_advancements:
                smelted_iron = self._any_advancement_done(igt_advancements, smelt_iron_ids)

        return {
            "smelted_iron": smelted_iron,
            "entered_nether": entered_nether,
        }

    def extract_run_timing(self) -> Dict[str, Any]:
        """Extract best-effort split/time information from SpeedRunIGT JSON.

        Returns:
            Dictionary containing source path, optional final timings, and split list.

        Raises:
            RuntimeError: If data has not been loaded yet.
        """
        data = self._require_igt()

        summary: Dict[str, Any] = {
            "igt_file": str(self.resolved_igt_path) if self.resolved_igt_path else None,
            "final_igt": self._find_first_value_by_keys(data, ("igt", "final_igt", "total_igt", "time_igt")),
            "final_rta": self._find_first_value_by_keys(data, ("rta", "final_rta", "total_rta", "time_rta")),
            "portal_split": self._find_first_value_by_keys(
                data,
                ("enter_nether", "nether_entry", "overworld_split", "portal_time"),
            ),
            "splits": self._extract_splits(data),
        }
        return summary

    def extract_crafting_stats(self) -> Dict[str, int]:
        """Extract crafting activity from stats.

        Returns:
            Dictionary with counts of items crafted, focusing on speedrun-relevant items.
        """
        stats = self._require_stats()
        crafted = self._get_nested_dict(stats, ["stats", "minecraft:crafted"])

        speedrun_relevant_items = (
            "minecraft:wood_planks",
            "minecraft:crafting_table",
            "minecraft:wooden_pickaxe",
            "minecraft:stone_pickaxe",
            "minecraft:iron_pickaxe",
            "minecraft:sticks",
            "minecraft:wooden_sword",
            "minecraft:stone_sword",
            "minecraft:iron_sword",
            "minecraft:flint_and_steel",
            "minecraft:bucket",
            "minecraft:furnace",
            "minecraft:nether_portal",
        )

        result = {}
        for item in speedrun_relevant_items:
            count = int(crafted.get(item, 0) or 0)
            if count > 0:
                result[item.replace("minecraft:", "")] = count

        return result

    def extract_mining_stats(self) -> Dict[str, int]:
        """Extract mining activity from stats.

        Returns:
            Dictionary with counts of block types mined.
        """
        stats = self._require_stats()
        mined = self._get_nested_dict(stats, ["stats", "minecraft:mined"])

        speedrun_relevant_blocks = (
            "minecraft:oak_log",
            "minecraft:birch_log",
            "minecraft:spruce_log",
            "minecraft:iron_ore",
            "minecraft:stone",
            "minecraft:deepslate",
            "minecraft:grass_block",
            "minecraft:dirt",
        )

        result = {}
        for block in speedrun_relevant_blocks:
            count = int(mined.get(block, 0) or 0)
            if count > 0:
                result[block.replace("minecraft:", "")] = count

        return result

    def extract_item_usage(self) -> Dict[str, int]:
        """Extract item usage activity from stats.

        Returns:
            Dictionary with counts of items used (e.g., swords, tools).
        """
        stats = self._require_stats()
        used = self._get_nested_dict(stats, ["stats", "minecraft:used"])

        speedrun_relevant_items = (
            "minecraft:wooden_pickaxe",
            "minecraft:stone_pickaxe",
            "minecraft:iron_pickaxe",
            "minecraft:wooden_sword",
            "minecraft:stone_sword",
            "minecraft:iron_sword",
            "minecraft:bucket",
            "minecraft:flint_and_steel",
        )

        result = {}
        for item in speedrun_relevant_items:
            count = int(used.get(item, 0) or 0)
            if count > 0:
                result[item.replace("minecraft:", "")] = count

        return result

    def extract_key_advancements(self) -> Dict[str, Any]:
        """Extract key advancement timings and completion status.

        Returns:
            Dictionary with speedrun milestone advancements and their IGT/RTA times.
        """
        igt_data = self._require_igt()
        advancements = self._get_nested_dict(igt_data, ["advancements"])

        if not advancements:
            return {}

        key_advancement_ids = (
            "minecraft:story/get_tools",
            "minecraft:story/upgrade_tools",
            "minecraft:story/smelt_iron",
            "minecraft:story/obtain_armor",
            "minecraft:story/lava_bucket",
            "minecraft:story/enter_the_nether",
            "minecraft:nether/root",
            "minecraft:adventure/find_biome",
        )

        result = {}
        for adv_id in key_advancement_ids:
            if adv_id in advancements:
                adv_node = advancements[adv_id]
                if isinstance(adv_node, dict):
                    result[adv_id.replace("minecraft:", "")] = {
                        "complete": bool(adv_node.get("complete", False)),
                        "igt": adv_node.get("igt", 0),
                        "rta": adv_node.get("rta", 0),
                    }

        return result

    def extract_detailed_movement(self) -> Dict[str, Any]:
        """Extract detailed movement and positioning stats.

        Returns:
            Dictionary with walk, sprint, jump, fall, and position-related metrics.
        """
        stats = self._require_stats()
        custom = self._get_nested_dict(stats, ["stats", "minecraft:custom"])

        return {
            "walk_blocks": round(int(custom.get("minecraft:walk_one_cm", 0) or 0) / 100.0, 2),
            "sprint_blocks": round(int(custom.get("minecraft:sprint_one_cm", 0) or 0) / 100.0, 2),
            "fly_blocks": round(int(custom.get("minecraft:fly_one_cm", 0) or 0) / 100.0, 2),
            "jump_count": int(custom.get("minecraft:jump", 0) or 0),
            "fall_distance_cm": int(custom.get("minecraft:fall_one_cm", 0) or 0),
            "water_traverse_blocks": round(
                int(custom.get("minecraft:walk_on_water_one_cm", 0) or 0) / 100.0, 2
            ),
            "time_alive_ticks": int(custom.get("minecraft:play_one_minute", 0) or 0),
        }

    def extract_run_metadata(self) -> Dict[str, Any]:
        """Extract run metadata: category, seed type, completion state, etc.

        Returns:
            Dictionary with run configuration and status.
        """
        igt_data = self._require_igt()

        return {
            "world_name": igt_data.get("world_name", "Unknown"),
            "category": igt_data.get("category", "Unknown"),
            "run_type": igt_data.get("run_type", "Unknown"),
            "is_completed": bool(igt_data.get("is_completed", False)),
            "is_hardcore": bool(igt_data.get("is_hardcore", False)),
            "is_coop": bool(igt_data.get("is_coop", False)),
            "mc_version": igt_data.get("mc_version", "Unknown"),
            "speedrunigt_version": igt_data.get("speedrunigt_version", "Unknown"),
        }

    def generate_llm_context(self) -> str:
        """Generate a clean text context block for LLM tutoring prompts.

        Returns:
            A readable multi-line summary string built from extracted features.

        Raises:
            FileNotFoundError: If required files are missing.
            JSONDecodeError: If input JSON is malformed.
            ValueError: If loaded JSON structure is invalid.
        """
        self.load_data()

        movement = self.extract_movement_efficiency()
        resources = self.extract_resource_totals()
        milestones = self.extract_overworld_milestones()
        run_timing = self.extract_run_timing()
        crafting_stats = self.extract_crafting_stats()
        mining_stats = self.extract_mining_stats()
        item_usage = self.extract_item_usage()
        key_advancements = self.extract_key_advancements()
        detailed_movement = self.extract_detailed_movement()
        run_metadata = self.extract_run_metadata()

        bundle = SpeedrunFeatureBundle(
            movement=movement,
            resources=resources,
            milestones=milestones,
            run_timing=run_timing,
            crafting_stats=crafting_stats,
            mining_stats=mining_stats,
            item_usage=item_usage,
            key_advancements=key_advancements,
            detailed_movement=detailed_movement,
            run_metadata=run_metadata,
        )
        return self._format_context(bundle)

    def _resolve_stats_and_advancements_paths(self, igt_path: Path) -> Tuple[Path, Path]:
        """Resolve stats and advancements files from root or save-world layout.

        Priority:
        1) If SpeedRunIGT file is inside a world save, use that same world folder.
        2) Otherwise, use newest matching files from discovered stats/advancement dirs.
        """
        stats_file = self._resolve_stats_path(igt_path)
        uuid = stats_file.stem
        advancements_file = self._resolve_advancements_path(uuid, stats_file)
        return stats_file, advancements_file

    def _resolve_stats_path(self, igt_path: Path) -> Path:
        """Resolve stats file path, preferring the world matching the selected IGT record."""
        world_stats_dir = self._world_stats_dir_from_igt(igt_path)
        if world_stats_dir is not None:
            if self.uuid:
                candidate = world_stats_dir / f"{self.uuid}.json"
                if candidate.exists():
                    return candidate
            newest = self._newest_json_file(world_stats_dir)
            if newest is not None:
                return newest

        stats_dirs = self._candidate_stats_dirs()
        if not stats_dirs:
            raise FileNotFoundError(
                "No stats directories found. Expected one of: "
                "<.minecraft>/stats or <.minecraft>/saves/<world>/stats"
            )

        if self.uuid:
            uuid_candidates: List[Path] = []
            for directory in stats_dirs:
                candidate = directory / f"{self.uuid}.json"
                if candidate.exists():
                    uuid_candidates.append(candidate)
            if uuid_candidates:
                return max(uuid_candidates, key=lambda p: p.stat().st_mtime)
            raise FileNotFoundError(
                f"Could not find stats file for UUID {self.uuid} in discovered stats folders."
            )

        newest_candidates: List[Path] = []
        for directory in stats_dirs:
            newest = self._newest_json_file(directory)
            if newest is not None:
                newest_candidates.append(newest)

        if not newest_candidates:
            searched = ", ".join(str(d) for d in stats_dirs)
            raise FileNotFoundError(
                "No stats JSON files found. Searched: "
                f"{searched}. Start and close a world once to generate them."
            )

        return max(newest_candidates, key=lambda p: p.stat().st_mtime)

    def _resolve_advancements_path(self, uuid: str, stats_path: Path) -> Path:
        """Resolve advancements path for the same UUID, preferring same-world sibling folder."""
        stats_parent = stats_path.parent
        if stats_parent.name == "stats":
            sibling_adv = stats_parent.parent / "advancements" / f"{uuid}.json"
            if sibling_adv.exists():
                return sibling_adv

        candidate_dirs = self._candidate_advancements_dirs()
        candidates: List[Path] = []
        for directory in candidate_dirs:
            candidate = directory / f"{uuid}.json"
            if candidate.exists():
                candidates.append(candidate)

        if candidates:
            return max(candidates, key=lambda p: p.stat().st_mtime)

        searched = ", ".join(str(d) for d in candidate_dirs)
        raise FileNotFoundError(
            "Could not find matching advancements JSON for UUID "
            f"{uuid}. Searched: {searched}"
        )

    def _candidate_stats_dirs(self) -> List[Path]:
        """Return candidate stats directories across root and world saves."""
        dirs: List[Path] = []

        root_stats = self.minecraft_dir / "stats"
        if root_stats.exists():
            dirs.append(root_stats)

        saves_dir = self.minecraft_dir / "saves"
        if saves_dir.exists():
            for world_dir in saves_dir.iterdir():
                if not world_dir.is_dir():
                    continue
                world_stats = world_dir / "stats"
                if world_stats.exists():
                    dirs.append(world_stats)

        return dirs

    def _candidate_advancements_dirs(self) -> List[Path]:
        """Return candidate advancements directories across root and world saves."""
        dirs: List[Path] = []

        root_advancements = self.minecraft_dir / "advancements"
        if root_advancements.exists():
            dirs.append(root_advancements)

        saves_dir = self.minecraft_dir / "saves"
        if saves_dir.exists():
            for world_dir in saves_dir.iterdir():
                if not world_dir.is_dir():
                    continue
                world_advancements = world_dir / "advancements"
                if world_advancements.exists():
                    dirs.append(world_advancements)

        return dirs

    def _world_stats_dir_from_igt(self, igt_path: Path) -> Optional[Path]:
        """If IGT file is in a save world folder, return that world's stats dir."""
        # Expected shape: <.minecraft>/saves/<world>/speedrunigt/record.json
        if igt_path.parent.name != "speedrunigt":
            return None

        world_dir = igt_path.parent.parent
        if world_dir.parent.name != "saves":
            return None

        stats_dir = world_dir / "stats"
        return stats_dir if stats_dir.exists() else None

    @staticmethod
    def _newest_json_file(directory: Path) -> Optional[Path]:
        """Return newest JSON file in a directory, or None if empty."""
        files = [path for path in directory.glob("*.json") if path.is_file()]
        if not files:
            return None
        return max(files, key=lambda p: p.stat().st_mtime)

    def _resolve_igt_file(self) -> Path:
        """Resolve SpeedRunIGT record file path from explicit argument or known folders."""
        if self.igt_file:
            if not self.igt_file.exists():
                raise FileNotFoundError(f"SpeedRunIGT file not found: {self.igt_file}")
            return self.igt_file

        candidate_dirs = [
            self.minecraft_dir / "speedrunigt",
            self.minecraft_dir / "config" / "speedrunigt",
            self.minecraft_dir / "logs" / "speedrunigt",
            self.minecraft_dir / "saves",
        ]

        json_candidates: List[Path] = []
        for directory in candidate_dirs:
            if not directory.exists():
                continue
            if directory.name == "saves":
                json_candidates.extend(directory.rglob("speedrunigt/*.json"))
            else:
                json_candidates.extend(directory.rglob("*.json"))

        if not json_candidates:
            searched = ", ".join(str(d) for d in candidate_dirs)
            raise FileNotFoundError(
                "No SpeedRunIGT JSON records found. Searched: "
                f"{searched}. Configure SpeedRunIGT to export JSON and finish a run first."
            )

        return max(json_candidates, key=lambda p: p.stat().st_mtime)

    @staticmethod
    def _load_json_file(path: Path) -> Dict[str, Any]:
        """Load a JSON file and enforce dictionary top-level structure."""
        if not path.exists():
            raise FileNotFoundError(f"Required file not found: {path}")

        try:
            with path.open("r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
        except JSONDecodeError as exc:
            raise JSONDecodeError(f"Invalid JSON in {path}: {exc.msg}", exc.doc, exc.pos) from exc

        if not isinstance(data, dict):
            raise ValueError(f"Top-level JSON in {path} must be an object.")

        return data

    def _require_stats(self) -> Dict[str, Any]:
        """Return loaded stats data or raise if not yet loaded."""
        if self.stats_data is None:
            raise RuntimeError("Stats data not loaded. Call load_data() first.")
        return self.stats_data

    def _require_advancements(self) -> Dict[str, Any]:
        """Return loaded advancements data or raise if not yet loaded."""
        if self.advancements_data is None:
            raise RuntimeError("Advancements data not loaded. Call load_data() first.")
        return self.advancements_data

    def _require_igt(self) -> Dict[str, Any]:
        """Return loaded SpeedRunIGT data or raise if not yet loaded."""
        if self.igt_data is None:
            raise RuntimeError("SpeedRunIGT data not loaded. Call load_data() first.")
        return self.igt_data

    @staticmethod
    def _get_nested_dict(data: Dict[str, Any], path: List[str]) -> Dict[str, Any]:
        """Safely retrieve nested dictionary; returns empty dict if missing/wrong type."""
        current: Any = data
        for key in path:
            if not isinstance(current, dict):
                return {}
            current = current.get(key, {})
        return current if isinstance(current, dict) else {}

    @staticmethod
    def _sum_matching_keys(
        data: Dict[str, Any],
        includes: Tuple[str, ...],
        excludes: Tuple[str, ...],
    ) -> int:
        """Sum integer values for keys matching include/exclude substring filters."""
        total = 0
        for key, value in data.items():
            if any(marker in key for marker in includes) and not any(block in key for block in excludes):
                try:
                    total += int(value or 0)
                except (TypeError, ValueError):
                    continue
        return total

    @staticmethod
    def _any_advancement_done(advancements: Dict[str, Any], ids: Iterable[str]) -> bool:
        """Check whether any listed advancement IDs are marked done."""
        for advancement_id in ids:
            node = advancements.get(advancement_id, {})
            if not isinstance(node, dict):
                continue
            if bool(node.get("done", False)) or bool(node.get("complete", False)):
                return True
        return False

    @staticmethod
    def _find_first_value_by_keys(data: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[Any]:
        """Search for the first value where key name matches candidates, prioritizing exact matches."""

        # First pass: try exact matches at top level
        if isinstance(data, dict):
            for key in keys:
                if key in data:
                    return data[key]

        # Second pass: try case-insensitive substring matches at top level
        if isinstance(data, dict):
            for key, value in data.items():
                normalized = key.lower().replace("-", "_")
                for candidate in keys:
                    if candidate.lower() == normalized:
                        return value

        # Third pass: depth-first search for substring matches
        def search(node: Any, depth: int = 0) -> Optional[Any]:
            if depth > 5:  # Limit depth to avoid deep nested searches
                return None
            if isinstance(node, dict):
                for key, value in node.items():
                    normalized = key.lower().replace("-", "_")
                    if any(candidate in normalized for candidate in keys):
                        return value
                    found = search(value, depth + 1)
                    if found is not None:
                        return found
            elif isinstance(node, list):
                for item in node:
                    found = search(item, depth + 1)
                    if found is not None:
                        return found
            return None

        return search(data)

    @staticmethod
    def _extract_splits(data: Dict[str, Any]) -> List[str]:
        """Extract a human-readable split summary from common SpeedRunIGT-like shapes."""
        # Try "timelines" first (SpeedRunIGT 16.0+), then fallback to "splits"
        splits = data.get("timelines") or data.get("splits", [])
        if not isinstance(splits, list):
            return []

        lines: List[str] = []
        for split in splits:
            if not isinstance(split, dict):
                continue
            name = str(split.get("name", "unknown_split"))
            value = (
                split.get("time")
                or split.get("igt")
                or split.get("rta")
                or split.get("duration")
                or split.get("value")
            )
            if value is not None:
                lines.append(f"{name}: {value}")
        return lines

    @staticmethod
    def _format_context(bundle: SpeedrunFeatureBundle) -> str:
        """Format extracted features into a comprehensive LLM-ready context block."""
        lines = [
            "=" * 80,
            "Minecraft 1.16 Speedrun Analysis (Parsed from SpeedRunIGT + Minecraft stats)",
            "=" * 80,
            "",
        ]

        # Run metadata
        if bundle.run_metadata:
            lines.append("RUN METADATA:")
            lines.append(f"  World: {bundle.run_metadata.get('world_name', 'Unknown')}")
            lines.append(f"  Category: {bundle.run_metadata.get('category', 'Unknown')}")
            lines.append(f"  Type: {bundle.run_metadata.get('run_type', 'Unknown')}")
            lines.append(f"  Completed: {bundle.run_metadata.get('is_completed', False)}")
            lines.append(f"  Hardcore: {bundle.run_metadata.get('is_hardcore', False)}")
            lines.append("")

        # Timing summary
        if bundle.run_timing:
            lines.append("OVERALL TIMING:")
            final_igt = bundle.run_timing.get("final_igt", 0)
            final_rta = bundle.run_timing.get("final_rta", 0)
            try:
                final_igt = int(final_igt) if final_igt else 0
                final_rta = int(final_rta) if final_rta else 0
                lines.append(f"  Final IGT: {final_igt} ms ({final_igt // 1000 // 60}:{(final_igt // 1000) % 60:02d})")
                lines.append(f"  Final RTA: {final_rta} ms ({final_rta // 1000 // 60}:{(final_rta // 1000) % 60:02d})")
            except (ValueError, TypeError):
                lines.append(f"  Final IGT: {final_igt}")
                lines.append(f"  Final RTA: {final_rta}")
            
            portal_split = bundle.run_timing.get("portal_split")
            if portal_split:
                try:
                    portal_split = int(portal_split) if portal_split else 0
                    lines.append(f"  Portal entry: {portal_split} ms ({portal_split // 1000 // 60}:{(portal_split // 1000) % 60:02d})")
                except (ValueError, TypeError):
                    lines.append(f"  Portal entry: {portal_split}")
            lines.append("")

        # Key advancements with timings
        if bundle.key_advancements:
            lines.append("KEY ADVANCEMENTS & TIMING:")
            for key, data in sorted(bundle.key_advancements.items()):
                if data.get("complete"):
                    igt_time = data.get("igt", 0)
                    if igt_time:
                        try:
                            igt_time = int(igt_time)
                            lines.append(
                                f"  ✓ {key}: {igt_time} ms "
                                f"({igt_time // 1000 // 60}:{(igt_time // 1000) % 60:02d})"
                            )
                        except (ValueError, TypeError):
                            lines.append(f"  ✓ {key}: {igt_time}")
                    else:
                        lines.append(f"  ✓ {key}: completed (no timing)")
            lines.append("")

        # Detailed movement analysis
        if bundle.detailed_movement:
            lines.append("MOVEMENT & POSITIONING:")
            walk = bundle.detailed_movement.get("walk_blocks", 0)
            sprint = bundle.detailed_movement.get("sprint_blocks", 0)
            fly = bundle.detailed_movement.get("fly_blocks", 0)
            jump_count = bundle.detailed_movement.get("jump_count", 0)
            fall_cm = bundle.detailed_movement.get("fall_distance_cm", 0)
            water_walk = bundle.detailed_movement.get("water_traverse_blocks", 0)

            total_movement = walk + sprint + fly
            lines.append(f"  Total distance: {total_movement:.0f} blocks")
            lines.append(f"    - Walked: {walk:.0f} blocks")
            lines.append(f"    - Sprinted: {sprint:.0f} blocks")
            lines.append(f"    - Flew: {fly:.0f} blocks")
            if water_walk:
                lines.append(f"    - Walked on water: {water_walk:.0f} blocks")
            lines.append(f"  Jump count: {jump_count}")
            lines.append(f"  Fall distance: {fall_cm} cm ({fall_cm / 100:.1f} blocks)")

            if walk + sprint > 0:
                ratio = sprint / (walk + sprint) if walk + sprint > 0 else 0
                lines.append(f"  Sprint ratio: {ratio:.1%}")
            lines.append("")

        # Crafting patterns
        if bundle.crafting_stats:
            lines.append("CRAFTING ACTIVITY:")
            for item, count in sorted(bundle.crafting_stats.items()):
                lines.append(f"  - {item}: {count}")
            lines.append("")

        # Mining patterns
        if bundle.mining_stats:
            lines.append("MINING ACTIVITY:")
            total_mined = sum(bundle.mining_stats.values())
            for block, count in sorted(bundle.mining_stats.items(), key=lambda x: -x[1]):
                lines.append(f"  - {block}: {count}")
            lines.append(f"  Total blocks mined: {total_mined}")
            lines.append("")

        # Item usage
        if bundle.item_usage:
            lines.append("ITEM USAGE:")
            for item, count in sorted(bundle.item_usage.items()):
                lines.append(f"  - {item}: {count} times")
            lines.append("")

        # Resource summary (traditional totals)
        if bundle.resources:
            lines.append("RESOURCE SUMMARY:")
            lines.append(f"  Total logs mined: {bundle.resources.get('total_logs_mined', 0)}")
            lines.append(f"  Total iron ore mined: {bundle.resources.get('total_iron_ore_mined', 0)}")
            lines.append(f"  Total stone mined: {bundle.resources.get('total_stone_mined', 0)}")
            lines.append("")

        # Milestones
        if bundle.milestones:
            lines.append("PROGRESS MILESTONES:")
            lines.append(f"  Smelted iron: {bundle.milestones.get('smelted_iron', False)}")
            lines.append(f"  Entered nether: {bundle.milestones.get('entered_nether', False)}")
            lines.append("")

        # Splits
        split_lines = bundle.run_timing.get("splits", []) if bundle.run_timing else []
        if isinstance(split_lines, list) and split_lines:
            lines.append("RUN SPLITS:")
            for entry in split_lines[:15]:
                lines.append(f"  - {entry}")
            lines.append("")

        lines.append("=" * 80)
        lines.append("Analysis Notes:")
        lines.append("Use the data above to identify specific areas for improvement:")
        lines.append("- Movement: Check sprint ratio and unnecessary movement")
        lines.append("- Crafting: Look for wasted resources or unnecessary crafting")
        lines.append("- Mining: Identify over-mining or inefficient block targeting")
        lines.append("- Advancements: Compare actual vs optimal timing for each stage")
        lines.append("=" * 80)

        return "\n".join(lines)
