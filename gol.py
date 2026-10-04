#!/usr/bin/env python3
"""
Game of Life on GitHub Contributions Calendar.

Rewrites the commit history of this repo so that the contribution graph
on github.com/mparramont shows an evolving Game of Life animation.

The grid is 52 columns (weeks) x 7 rows (days, Sun=0 .. Sat=6).
Each "live" cell gets one empty commit dated to the corresponding day.
The entire history is replaced on every frame via force-push.
"""

import os
import sys
import json
import time
import argparse
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Any, TypeAlias

GRID_W = 52  # weeks shown on GitHub
GRID_H = 7  # days per week
Grid: TypeAlias = list[list[int]]
State: TypeAlias = dict[str, Any]

# ── Seeds (all coordinates must satisfy 0 <= x < 52, 0 <= y < 7) ──────────

SEEDS = {
    # Classic glider, placed near top-left so it travels across the grid
    "glider": [
        (1, 0),
        (2, 1),
        (0, 2),
        (1, 2),
        (2, 2),
    ],
    # Lightweight spaceship, placed at left edge
    "lwss": [
        (1, 0),
        (4, 0),
        (0, 1),
        (0, 2),
        (4, 2),
        (0, 3),
        (1, 3),
        (2, 3),
        (3, 3),
    ],
    # R-pentomino: small seed that produces long-lived chaos
    "r_pentomino": [
        (25, 2),
        (26, 2),
        (24, 3),
        (25, 3),
        (25, 4),
    ],
    # Acorn: takes 5206 generations to stabilize, very long-lived
    "acorn": [
        (22, 3),
        (24, 2),
        (24, 3),
        (26, 3),
        (27, 3),
        (28, 3),
        (29, 3),
    ],
    # 3 gliders launched from different corners for visual interest
    "triple_glider": [
        # glider 1 at top-left
        (1, 0),
        (2, 1),
        (0, 2),
        (1, 2),
        (2, 2),
        # glider 2 at mid
        (25, 0),
        (26, 1),
        (24, 2),
        (25, 2),
        (26, 2),
        # glider 3 at left, lower
        (10, 4),
        (11, 5),
        (9, 6),
        (10, 6),
        (11, 6),
    ],
}


def empty_grid() -> Grid:
    return [[0] * GRID_W for _ in range(GRID_H)]


def load_seed(name: str, offset_x: int = 0, offset_y: int = 0) -> Grid:
    grid = empty_grid()
    for x, y in SEEDS[name]:
        grid[(y + offset_y) % GRID_H][(x + offset_x) % GRID_W] = 1
    return grid


def step(grid: Grid) -> Grid:
    """Advance one generation. Wrapping (toroidal) boundary."""
    new = empty_grid()
    for y in range(GRID_H):
        for x in range(GRID_W):
            n = 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    n += grid[(y + dy) % GRID_H][(x + dx) % GRID_W]
            if grid[y][x]:
                new[y][x] = 1 if n in (2, 3) else 0
            else:
                new[y][x] = 1 if n == 3 else 0
    return new


def grid_to_tuple(grid: Grid) -> tuple[tuple[int, ...], ...]:
    return tuple(tuple(row) for row in grid)


def population(grid: Grid) -> int:
    return sum(sum(row) for row in grid)


# ── Git helpers ────────────────────────────────────────────────────────────


def git(
    *args: str, check: bool = True, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a git command, letting stdout/stderr flow to the CI log."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    result = subprocess.run(
        ["git"] + list(args),
        env=merged_env,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        print(f"  [git stdout] {result.stdout.strip()}")
    if result.stderr.strip():
        print(f"  [git stderr] {result.stderr.strip()}")
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (rc={result.returncode}): {result.stderr}"
        )
    return result


def configure_remote_with_token() -> None:
    """
    If GH_PAT is in the environment, rewrite the origin URL to use it.
    This survives orphan-branch switches that lose the actions/checkout
    extraheader config.
    """
    token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("WARNING: No GH_PAT or GITHUB_TOKEN found; push may fail.")
        return

    # Get current remote URL
    result = git("remote", "get-url", "origin", check=False)
    url = result.stdout.strip()
    if not url:
        print("WARNING: Could not read origin URL.")
        return

    # Rewrite https://github.com/owner/repo to https://x-access-token:<token>@github.com/owner/repo
    if url.startswith("https://github.com/"):
        new_url = url.replace(
            "https://github.com/",
            f"https://x-access-token:{token}@github.com/",
        )
        git("remote", "set-url", "origin", new_url)
        print("Configured origin with token auth.")
    elif "x-access-token" in url:
        print("Origin already has token auth.")
    else:
        print(f"WARNING: Unexpected origin URL format: {url}")


def apply_frame(grid: Grid, frame_num: int) -> None:
    """
    Rewrite the repo history so that one commit exists per live cell,
    dated to the correct day in the past year, then force-push.
    """
    now = datetime.now(timezone.utc)
    # GitHub calendar: column 0 = 52 weeks ago Sunday, column 51 = this week
    # Row 0 = Sunday, row 6 = Saturday
    # The rightmost column (51) starts on the most recent Sunday
    today_weekday = now.weekday()  # Mon=0 .. Sun=6
    gh_weekday = (today_weekday + 1) % 7  # Sun=0 .. Sat=6

    print(
        f"  Frame {frame_num}: population={population(grid)}, date={now.strftime('%Y-%m-%d')}, gh_weekday={gh_weekday}"
    )

    # Step 1: create orphan branch (starts with the current index)
    git("checkout", "--orphan", "new_frame")

    # Step 2: stage and commit the code files so they survive
    git("add", "-A")
    git(
        "commit",
        "-m",
        "gol base",
        env={
            "GIT_AUTHOR_DATE": now.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "GIT_COMMITTER_DATE": now.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        },
    )

    # Step 3: create empty commits for each live cell
    commit_count = 0
    for y in range(GRID_H):
        for x in range(GRID_W):
            if grid[y][x]:
                # x = week column (0 = 52 weeks ago, 51 = current week)
                # y = day-of-week row (0 = Sun, 6 = Sat)
                days_back = (51 - x) * 7 + (gh_weekday - y)
                target = now - timedelta(days=days_back)
                if target > now:
                    continue  # skip future dates
                ds = target.strftime("%Y-%m-%dT12:00:00+00:00")
                git(
                    "commit",
                    "--allow-empty",
                    "-m",
                    f"gol {x},{y}",
                    env={"GIT_AUTHOR_DATE": ds, "GIT_COMMITTER_DATE": ds},
                )
                commit_count += 1

    print(f"  Created {commit_count} pixel commits.")

    # Step 4: force-push the orphan branch over main
    git("push", "--force", "origin", "new_frame:main")
    print(f"  Pushed frame {frame_num} successfully.")

    # Step 5: clean up local branches for next iteration
    # Detach HEAD first, then delete branches
    git("checkout", "--detach", check=False)
    git("branch", "-D", "new_frame", check=False)
    git("branch", "-D", "main", check=False)
    # Fetch the newly pushed main so we have a clean starting point
    git("fetch", "origin", "main")
    git("checkout", "-b", "main", "origin/main")


# ── Main ───────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Game of Life on GitHub contributions")
    parser.add_argument(
        "--mode",
        choices=["single", "fast"],
        default="single",
        help="single = one frame; fast = continuous for --duration seconds",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=55,
        help="Seconds to run in fast mode (default 55, leaving headroom in the 60s trigger)",
    )
    args = parser.parse_args()

    state_file = "state.json"
    state: State = {}
    if os.path.exists(state_file):
        with open(state_file) as f:
            try:
                state = json.load(f)
            except (json.JSONDecodeError, ValueError):
                pass

    grid = state.get("grid")
    seen_hashes = state.get("seen_hashes", [])
    seed_idx = state.get("seed_idx", 0)
    frame_total = state.get("frame_total", 0)

    seed_names = list(SEEDS.keys())

    if not grid:
        print(f"Starting with seed: {seed_names[seed_idx]}")
        grid = load_seed(seed_names[seed_idx])
        seen_hashes = []

    # Configure auth before any push
    configure_remote_with_token()

    start = time.time()
    frame_num = 0
    errors = 0

    while True:
        frame_num += 1
        frame_total += 1
        g_hash = str(grid_to_tuple(grid))

        # Detect stuck / dead states: if we've seen this exact grid in the
        # last 6 frames, or population is 0, cycle to next seed.
        if g_hash in seen_hashes or population(grid) == 0:
            seed_idx = (seed_idx + 1) % len(seed_names)
            print(f"Grid stuck or dead; cycling to seed: {seed_names[seed_idx]}")
            grid = load_seed(seed_names[seed_idx])
            seen_hashes = []
            g_hash = str(grid_to_tuple(grid))

        seen_hashes.append(g_hash)
        if len(seen_hashes) > 6:
            seen_hashes.pop(0)

        # Save state BEFORE applying so state.json is included in the commit
        with open(state_file, "w") as f:
            json.dump(
                {
                    "grid": grid,
                    "seen_hashes": seen_hashes,
                    "seed_idx": seed_idx,
                    "frame_total": frame_total,
                },
                f,
            )

        print(f"\n=== Frame {frame_num} (total {frame_total}) ===")
        try:
            apply_frame(grid, frame_num)
        except Exception as e:
            print(f"ERROR applying frame: {e}", file=sys.stderr)
            errors += 1
            # In single mode, fail hard. In fast mode, try to continue
            # but cap consecutive errors.
            if args.mode == "single" or errors >= 3:
                print("Too many errors, aborting.", file=sys.stderr)
                sys.exit(1)
            time.sleep(2)
            continue

        errors = 0  # reset on success
        grid = step(grid)

        if args.mode == "single":
            break

        elapsed = time.time() - start
        if elapsed >= args.duration:
            print(f"\nFast mode complete: {frame_num} frames in {elapsed:.1f}s")
            break

        # Wait before next frame
        time.sleep(1)

    print(f"\nDone. Total frames applied this run: {frame_num}")


if __name__ == "__main__":
    main()
