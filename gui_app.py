import json
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from main import (
    SYSTEM_PROMPT,
    build_minecraft_prompt_and_signature,
    ensure_ollama_model,
    generate_strict_initial_feedback,
    start_ollama_service,
    wait_for_ollama_api,
)
from ollama_client import OllamaTutorClient
from speedrun_data_parser import SpeedrunDataParser


DEFAULT_MINECRAFT_DIR = "/Applications/MultiMC.app/Data/instances/Minecraft Tutor/.minecraft"
CONFIG_PATH = Path.home() / ".minecraft_speedrun_tutor_gui.json"


class SpeedrunTutorGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Minecraft Speedrun Tutor")
        self.root.geometry("1100x740")

        self.event_queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.watch_thread: threading.Thread | None = None

        self.session_counter = 0
        self.sessions: dict[str, dict] = {}

        self._build_ui()
        self._load_config()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(150, self._process_events)

    def _build_ui(self) -> None:
        settings = ttk.LabelFrame(self.root, text="Setup")
        settings.pack(fill="x", padx=12, pady=10)

        ttk.Label(settings, text="Minecraft Dir").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        self.minecraft_dir_var = tk.StringVar(value=DEFAULT_MINECRAFT_DIR)
        ttk.Entry(settings, textvariable=self.minecraft_dir_var, width=70).grid(
            row=0, column=1, padx=6, pady=6, sticky="ew"
        )
        ttk.Button(settings, text="Browse", command=self._browse_minecraft_dir).grid(
            row=0, column=2, padx=6, pady=6
        )

        ttk.Label(settings, text="UUID (optional)").grid(row=1, column=0, padx=6, pady=6, sticky="w")
        self.uuid_var = tk.StringVar(value="")
        ttk.Entry(settings, textvariable=self.uuid_var, width=40).grid(
            row=1, column=1, padx=6, pady=6, sticky="w"
        )

        ttk.Label(settings, text="IGT File (optional)").grid(row=2, column=0, padx=6, pady=6, sticky="w")
        self.igt_file_var = tk.StringVar(value="")
        ttk.Entry(settings, textvariable=self.igt_file_var, width=70).grid(
            row=2, column=1, padx=6, pady=6, sticky="ew"
        )
        ttk.Button(settings, text="Browse", command=self._browse_igt_file).grid(
            row=2, column=2, padx=6, pady=6
        )

        ttk.Label(settings, text="Model").grid(row=3, column=0, padx=6, pady=6, sticky="w")
        self.model_var = tk.StringVar(value="llama3.3")
        ttk.Entry(settings, textvariable=self.model_var, width=20).grid(
            row=3, column=1, padx=6, pady=6, sticky="w"
        )

        ttk.Label(settings, text="Poll Seconds").grid(row=3, column=1, padx=(210, 6), pady=6, sticky="w")
        self.poll_var = tk.StringVar(value="3")
        ttk.Spinbox(settings, from_=1, to=30, textvariable=self.poll_var, width=6).grid(
            row=3, column=1, padx=(300, 6), pady=6, sticky="w"
        )

        button_row = ttk.Frame(settings)
        button_row.grid(row=4, column=0, columnspan=3, sticky="w", padx=6, pady=8)

        ttk.Button(button_row, text="Save Settings", command=self._save_config).pack(side="left", padx=(0, 8))
        ttk.Button(button_row, text="Validate Paths", command=self._validate_paths).pack(side="left", padx=(0, 8))
        ttk.Button(button_row, text="Generate Feedback", command=self._generate_feedback).pack(side="left", padx=(0, 8))

        self.start_button = ttk.Button(button_row, text="Start Watch", command=self._start_watch)
        self.start_button.pack(side="left", padx=(0, 8))

        self.stop_button = ttk.Button(button_row, text="Stop Watch", command=self._stop_watch, state="disabled")
        self.stop_button.pack(side="left", padx=(0, 8))

        settings.grid_columnconfigure(1, weight=1)

        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(self.root, textvariable=self.status_var, anchor="w").pack(fill="x", padx=14, pady=(0, 8))

        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        intro = ttk.Frame(self.tabs)
        self.tabs.add(intro, text="Overview")
        ttk.Label(
            intro,
            text=(
                "Click Start Watch to monitor run data.\n"
                "When a new run is detected, the app will open a chat tab automatically."
            ),
            justify="left",
        ).pack(anchor="w", padx=14, pady=14)

    def _browse_minecraft_dir(self) -> None:
        selected = filedialog.askdirectory(title="Select .minecraft directory")
        if selected:
            self.minecraft_dir_var.set(selected)

    def _browse_igt_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select SpeedRunIGT JSON",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
        )
        if selected:
            self.igt_file_var.set(selected)

    def _args_namespace(self) -> SimpleNamespace:
        return SimpleNamespace(
            minecraft_dir=self.minecraft_dir_var.get().strip(),
            uuid=self.uuid_var.get().strip(),
            igt_file=self.igt_file_var.get().strip(),
        )

    def _load_config(self) -> None:
        if not CONFIG_PATH.exists():
            return
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return

        self.minecraft_dir_var.set(data.get("minecraft_dir", DEFAULT_MINECRAFT_DIR))
        self.uuid_var.set(data.get("uuid", ""))
        self.igt_file_var.set(data.get("igt_file", ""))
        self.model_var.set(data.get("model", "llama3.3"))
        self.poll_var.set(str(data.get("poll_seconds", 3)))

    def _save_config(self) -> None:
        payload = {
            "minecraft_dir": self.minecraft_dir_var.get().strip(),
            "uuid": self.uuid_var.get().strip(),
            "igt_file": self.igt_file_var.get().strip(),
            "model": self.model_var.get().strip() or "llama3.3",
            "poll_seconds": max(1, int(self.poll_var.get().strip() or "3")),
        }
        CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._set_status(f"Saved settings to {CONFIG_PATH}")

    def _validate_paths(self) -> None:
        self._set_status("Validating data paths...")
        threading.Thread(target=self._validate_paths_worker, daemon=True).start()

    def _validate_paths_worker(self) -> None:
        try:
            args = self._args_namespace()
            parser = SpeedrunDataParser(
                minecraft_dir=Path(args.minecraft_dir).expanduser().resolve(),
                uuid=args.uuid or None,
                igt_file=Path(args.igt_file).expanduser().resolve() if args.igt_file else None,
            )
            parser.load_data()
            self.event_queue.put(
                (
                    "validation_ok",
                    {
                        "stats": str(parser.stats_path),
                        "advancements": str(parser.advancements_path),
                        "igt": str(parser.resolved_igt_path),
                    },
                )
            )
        except Exception as exc:
            self.event_queue.put(("error", f"Validation failed: {exc}"))

    def _generate_feedback(self) -> None:
        """Generate feedback for the most recent run (one-shot, no watch)."""
        self._save_config()
        self._set_status("Initializing Ollama and model...")
        threading.Thread(target=self._generate_feedback_worker, daemon=True).start()

    def _generate_feedback_worker(self) -> None:
        try:
            model = self.model_var.get().strip() or "llama3.3"
            start_ollama_service()
            wait_for_ollama_api()
            ensure_ollama_model(model)
        except Exception as exc:
            self.event_queue.put(("error", f"Initialization failed: {exc}"))
            return

        try:
            args = self._args_namespace()
            prompt, _ = build_minecraft_prompt_and_signature(args)
            self.event_queue.put(
                (
                    "run_detected",
                    {
                        "prompt": prompt,
                        "detected_at": datetime.now().strftime("%H:%M:%S"),
                    },
                )
            )
        except Exception as exc:
            self.event_queue.put(("error", f"Failed to load run data: {exc}"))

    def _start_watch(self) -> None:
        try:
            _ = max(1, int(self.poll_var.get().strip() or "3"))
        except Exception:
            messagebox.showerror("Invalid Poll Seconds", "Poll seconds must be a positive integer.")
            return

        if self.watch_thread and self.watch_thread.is_alive():
            return

        self._save_config()
        self.stop_event.clear()
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self._set_status("Initializing Ollama and model...")

        threading.Thread(target=self._start_watch_worker, daemon=True).start()

    def _start_watch_worker(self) -> None:
        try:
            model = self.model_var.get().strip() or "llama3.3"
            start_ollama_service()
            wait_for_ollama_api()
            ensure_ollama_model(model)
        except Exception as exc:
            self.event_queue.put(("watch_failed", str(exc)))
            return

        self.watch_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self.watch_thread.start()
        self.event_queue.put(("status", "Watcher started. Waiting for first complete run..."))

    def _watch_loop(self) -> None:
        args = self._args_namespace()
        poll_seconds = max(1, int(self.poll_var.get().strip() or "3"))
        last_signature = None
        last_error = ""

        while not self.stop_event.is_set():
            try:
                prompt, signature = build_minecraft_prompt_and_signature(args)
            except Exception as exc:
                current_error = str(exc)
                if current_error != last_error:
                    last_error = current_error
                    self.event_queue.put(("status", f"Waiting for data: {current_error}"))
                self.stop_event.wait(poll_seconds)
                continue

            last_error = ""
            if signature == last_signature:
                self.stop_event.wait(poll_seconds)
                continue

            last_signature = signature
            self.event_queue.put(
                (
                    "run_detected",
                    {
                        "prompt": prompt,
                        "detected_at": datetime.now().strftime("%H:%M:%S"),
                    },
                )
            )

            self.stop_event.wait(poll_seconds)

    def _stop_watch(self) -> None:
        self.stop_event.set()
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self._set_status("Watcher stopped.")

    def _create_run_tab(self, detected_at: str) -> str:
        self.session_counter += 1
        run_id = f"run_{self.session_counter}"

        frame = ttk.Frame(self.tabs)
        self.tabs.add(frame, text=f"Run {self.session_counter} | {detected_at}")
        self.tabs.select(frame)

        text_frame = ttk.Frame(frame)
        text_frame.pack(fill="both", expand=True, padx=10, pady=10)

        transcript = tk.Text(text_frame, wrap="word", state="disabled")
        transcript.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=transcript.yview)
        scrollbar.pack(side="right", fill="y")
        transcript.config(yscrollcommand=scrollbar.set)

        input_frame = ttk.Frame(frame)
        input_frame.pack(fill="x", padx=10, pady=(0, 10))

        entry = ttk.Entry(input_frame)
        entry.pack(side="left", fill="x", expand=True)

        send_button = ttk.Button(
            input_frame,
            text="Send",
            state="disabled",
            command=lambda rid=run_id: self._send_chat(rid),
        )
        send_button.pack(side="left", padx=(8, 0))

        entry.bind("<Return>", lambda _event, rid=run_id: self._send_chat(rid))

        self.sessions[run_id] = {
            "frame": frame,
            "text": transcript,
            "entry": entry,
            "send_button": send_button,
            "client": None,
            "waiting": False,
        }

        self._append_text(run_id, "system", "Analyzing detected run with Ollama...")
        return run_id

    def _append_text(self, run_id: str, speaker: str, text: str) -> None:
        session = self.sessions.get(run_id)
        if not session:
            return

        transcript: tk.Text = session["text"]
        transcript.config(state="normal")
        transcript.insert("end", f"{speaker.upper()}: {text}\n\n")
        transcript.config(state="disabled")
        transcript.see("end")

    def _set_chat_enabled(self, run_id: str, enabled: bool) -> None:
        session = self.sessions.get(run_id)
        if not session:
            return
        state = "normal" if enabled else "disabled"
        session["entry"].config(state=state)
        session["send_button"].config(state=state)
        session["waiting"] = not enabled

    def _start_analysis(self, run_id: str, prompt: str) -> None:
        threading.Thread(target=self._analysis_worker, args=(run_id, prompt), daemon=True).start()

    def _analysis_worker(self, run_id: str, prompt: str) -> None:
        try:
            model = self.model_var.get().strip() or "llama3.3"
            client = OllamaTutorClient(model=model)
            feedback = generate_strict_initial_feedback(client, prompt)
            self.event_queue.put(
                (
                    "analysis_ready",
                    {
                        "run_id": run_id,
                        "client": client,
                        "feedback": feedback,
                    },
                )
            )
        except Exception as exc:
            self.event_queue.put(("analysis_error", {"run_id": run_id, "error": str(exc)}))

    def _send_chat(self, run_id: str) -> None:
        session = self.sessions.get(run_id)
        if not session or session.get("waiting"):
            return

        entry: ttk.Entry = session["entry"]
        user_text = entry.get().strip()
        if not user_text:
            return

        client: OllamaTutorClient | None = session.get("client")
        if client is None:
            messagebox.showerror("Not Ready", "Initial analysis has not finished yet.")
            return

        entry.delete(0, "end")
        self._append_text(run_id, "you", user_text)
        self._set_chat_enabled(run_id, False)
        threading.Thread(
            target=self._chat_worker,
            args=(run_id, user_text, client),
            daemon=True,
        ).start()

    def _chat_worker(self, run_id: str, user_text: str, client: OllamaTutorClient) -> None:
        try:
            reply = client.send(user_text, system_instruction=SYSTEM_PROMPT)
            self.event_queue.put(("chat_reply", {"run_id": run_id, "reply": reply}))
        except Exception as exc:
            self.event_queue.put(("chat_error", {"run_id": run_id, "error": str(exc)}))

    def _process_events(self) -> None:
        while True:
            try:
                event_type, payload = self.event_queue.get_nowait()
            except queue.Empty:
                break

            if event_type == "status":
                self._set_status(str(payload))
            elif event_type == "run_detected":
                run_id = self._create_run_tab(payload["detected_at"])
                self._set_status(f"New run detected at {payload['detected_at']}. Generating feedback...")
                self._start_analysis(run_id, payload["prompt"])
            elif event_type == "analysis_ready":
                run_id = payload["run_id"]
                self.sessions[run_id]["client"] = payload["client"]
                self._append_text(run_id, "tutor", payload["feedback"])
                self._set_chat_enabled(run_id, True)
                self._set_status("Feedback ready. You can chat in the new tab.")
            elif event_type == "analysis_error":
                run_id = payload["run_id"]
                self._append_text(run_id, "system", f"Analysis failed: {payload['error']}")
                self._set_status("Analysis failed. See tab for details.")
            elif event_type == "chat_reply":
                run_id = payload["run_id"]
                self._append_text(run_id, "tutor", payload["reply"])
                self._set_chat_enabled(run_id, True)
            elif event_type == "chat_error":
                run_id = payload["run_id"]
                self._append_text(run_id, "system", f"Chat error: {payload['error']}")
                self._set_chat_enabled(run_id, True)
            elif event_type == "validation_ok":
                self._set_status("Validation succeeded.")
                messagebox.showinfo(
                    "Validation Succeeded",
                    "Found required files:\n"
                    f"Stats: {payload['stats']}\n"
                    f"Advancements: {payload['advancements']}\n"
                    f"SpeedRunIGT: {payload['igt']}",
                )
            elif event_type == "watch_failed":
                self._stop_watch()
                messagebox.showerror("Watch Startup Failed", str(payload))
            elif event_type == "error":
                self._set_status(str(payload))
                messagebox.showerror("Error", str(payload))

        self.root.after(150, self._process_events)

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _on_close(self) -> None:
        self.stop_event.set()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = SpeedrunTutorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
