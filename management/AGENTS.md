# Agent instructions: project management

This project tracks work via **GitHub Issues** and a **GitHub
Project board** on
[Valentins-and-Veyas-42-group-projects/pac-man](https://github.com/Valentins-and-Veyas-42-group-projects/pac-man),
not via markdown docs in this directory. GitHub is the source of
truth; the snapshot below is a cached convenience for agents that
can't hit the GitHub API, and can go stale.

## Rules for any agent (human-directed or autonomous) working here

1. Before starting work, check open issues:
   ```bash
   gh issue list --repo Valentins-and-Veyas-42-group-projects/pac-man --state open
   ```
2. When you start implementing a stub, comment on or self-assign its
   issue rather than leaving it silently in progress.
3. When a stub is implemented and passing `make lint-strict` +
   `make test`, close its issue with a reference to the commit:
   ```bash
   gh issue close <n> --repo Valentins-and-Veyas-42-group-projects/pac-man -c "Implemented in <sha>"
   ```
4. If new work is discovered (a bug, a missing piece, a design
   question), open a new issue rather than silently fixing/deciding
   it, so the team has visibility:
   ```bash
   gh issue create --repo Valentins-and-Veyas-42-group-projects/pac-man --title "..." --body "..."
   ```
5. Project board: once `gh auth refresh -s project,read:project` has
   been run (interactive, human-only), link issues to the board with
   `gh project item-add`. Until then, issues alone are the tracker.
6. After creating/closing issues, refresh the snapshot below:
   ```bash
   gh issue list --repo Valentins-and-Veyas-42-group-projects/pac-man --state all --json number,title,state,url
   ```

## Snapshot (last synced: 2026-08-27)

| # | Title | State |
| --- | --- | --- |
| 1 | Implement config loading (`pacman/config.py`) | CLOSED |
| 2 | Implement A-Maze-ing adapter (`pacman/maze_loader.py`) | CLOSED |
| 3 | Implement SQLite highscore store (`pacman/highscores/store.py`) | CLOSED |
| 4 | Implement game state machine (`pacman/game/state.py`) | OPEN |
| 5 | Implement player movement (`pacman/game/player.py`) | OPEN |
| 6 | Implement ghost AI (`pacman/game/ghosts.py`) | OPEN |
| 7 | Implement pygame renderer (`pacman/visualizer/renderer.py`) | OPEN |
| 8 | Wire up cheat mode | OPEN |
| 9 | Package for a public gaming platform | OPEN |
| 10 | Fill in project management docs | OPEN |
| 11 | Default teammate onboarding and help guide | OPEN |
| 13 | Idea: asynchronous death analysis with counterfactual replays | OPEN |
| 14 | Idea: autoplay spectator mode | OPEN |

Project board: not yet created (blocked on `project` OAuth scope).

Team: vsack, sfurst.
