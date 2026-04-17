# Project Update

## What has been achieved so far?

The core tutoring workflow is implemented and working end-to-end. The project can analyze either direct JSON input or Minecraft-generated run data, send that context to the model, and then continue with interactive follow-up coaching.

Minecraft is now connected successfully. The parser can discover SpeedRunIGT records, stats, and advancements in real MultiMC/MCSR save-world folder layouts (not just top-level `.minecraft` folders). The diagnostic mode confirms whether the required files are present, and watch mode can monitor for new run data and re-analyze automatically.

The data extraction is now much richer than the initial version. In addition to basic timing and resources, the parser can include detailed movement, run metadata, split/timeline information, advancement timing data, mining/crafting/usage signals, and milestone checks to provide stronger context for coaching.

## What has changed from your original proposal?

The largest change is architecture maturity. The proposal framed Minecraft integration as a major future milestone, but this is now implemented and testable with real local run files.

The model backend is currently local Ollama rather than a cloud API. This was a practical decision to make development faster, cheaper, and easier to test repeatedly without external API setup. It also keeps the workflow private and fully local.

Another meaningful change is quality-of-life tooling that was not central in the original proposal: setup diagnostics, automatic data discovery, and watch mode for continuous practice feedback.

## What is left to do?

The main remaining work is refining AI feedback quality and analysis depth. At this point, the bottleneck is no longer data ingestion; it is how well the model interprets the data and translates it into precise, actionable coaching.

Immediate next steps:

1. Improve prompt design to better identify split-specific mistakes (routing, mechanics, inventory) and produce clearer corrective drills.
2. Tune analysis format and prioritization so feedback focuses on the biggest time losses first.
3. Add evaluation runs to compare feedback quality across multiple attempts and confirm consistency.
4. Consider upgrading or adding a cloud backend (for example ChatGPT) to compare coaching quality against the current Ollama model.

In short: Minecraft connectivity is done; the project is now in the feedback-quality and model-improvement phase.
