# Project Proposal: Minecraft 1.16 Speedrun Intelligent Tutoring System

_This was written with the help of Gemini._

## What is the problem you are solving?

Minecraft 1.16 speedrunning is incredibly hard to learn because players have to manage 3D navigation, random world generation, and precise movement all at once against a clock.

Right now, beginners can only learn by watching YouTube videos or through frustrating trial-and-error. There is no interactive way to get feedback on mistakes like bad routing, poor inventory management, or slow decision-making. This project builds an Intelligent Tutoring System (ITS) to act as an automated coach, giving players the active, guided practice they're currently missing.

## What will your prototype seek to teach?

The ultimate goal is to support practice across all segments of a 1.16 speedrun (Overworld, Bastion, Fortress, Stronghold, and End). Players will be able to practice individual sections or chain them together for holistic feedback.

**Note on Scope:** I plan to implement all segments eventually, but for this semester's prototype, I will guarantee the **"Overworld to Nether"** split is fully functional.

For this Overworld prototype, the system will teach:

- **Game Knowledge:** Knowing exact resource needs (e.g., exactly 3 iron for a bucket) and recognizing good natural terrain versus generated structures.
- **Routing Strategy:** The best path to gather resources and build a Nether portal without wasting time.
- **Inventory Management:** Spending less time in crafting menus and avoiding useless items (like making wooden tools instead of upgrading straight to stone).
- **Mechanics:** Building a lava pool portal quickly and safely.

_Note: Very similar types of knowledge components are present in each of the other splits and many overlap._

## How will your prototype support the learner?

The system uses "segment practice" paired with targeted feedback.

Players will load into a specific, pre-filtered game seed. While they play, a lightweight background script tracks their actions (timestamps, coordinates, inventory changes, crafting, and block breaking) and saves it to a JSON file.

After finishing the run, the player submits this log to the AI. The system compares their run against an expert's ideal run for that specific seed and provides direct, step-by-step feedback. Instead of just saying "You were slow," it gives actionable advice like: _"You spent 45 seconds chopping wood, but you only needed 3 logs. You also mined 15 iron, but optimal routing only requires 3 for a bucket."_

## What AI techniques will your system leverage?

To focus entirely on the AI and save time on complex graphics, this prototype runs purely on data analysis. The core engine uses Large Language Models (LLMs) to evaluate the player's game data.

- **Understanding Context:** The AI parses the JSON log to understand _why_ a player made a move. Speedrunning is highly situational, so rigid hard-coded scripts fail here. An LLM can actually infer player intent from their sequence of actions.
- **Expert Modeling:** I will use system prompts to "teach" the AI the optimal paths, resource minimums, and expected timings for version 1.16.
- **Providing Feedback:** The AI compares the student's data against the expert model to diagnose specific mistakes. It will pinpoint whether a slow time was caused by bad inventory management, poor routing, or slow movement, and generate plain-English feedback to fix it.
