import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Mapping


def run_cmd(
    args: list[str], cwd: Path, env: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    res = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env)
    assert res.returncode == 0, f"Command {' '.join(args)} failed: {res.stderr}"
    return res


def test_gol_end_to_end(tmp_path: Path) -> None:
    # Set up paths
    repo_dir = tmp_path / "repo"
    remote_dir = tmp_path / "remote.git"
    repo_dir.mkdir()

    # Create a bare repository to act as remote origin
    run_cmd(["git", "init", "--bare", str(remote_dir)], cwd=tmp_path)

    # Initialize the source repository
    run_cmd(["git", "init", "-b", "main"], cwd=repo_dir)
    run_cmd(["git", "config", "user.name", "Test User"], cwd=repo_dir)
    run_cmd(["git", "config", "user.email", "test@example.com"], cwd=repo_dir)
    run_cmd(["git", "remote", "add", "origin", str(remote_dir)], cwd=repo_dir)

    # Create an initial commit with files so there is something to push
    # We must have gol.py and any other project files in the branch
    # so they survive the --orphan checkout in apply_frame.
    real_gol_path = Path(__file__).parent.parent / "gol.py"
    dest_gol_path = repo_dir / "gol.py"
    dest_gol_path.write_text(
        real_gol_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    run_cmd(["git", "add", "gol.py"], cwd=repo_dir)
    run_cmd(["git", "commit", "-m", "initial commit"], cwd=repo_dir)

    # Push main to the bare remote to establish tracking
    run_cmd(["git", "push", "-u", "origin", "main"], cwd=repo_dir)

    # Run gol.py in single mode
    # Set environment variable so configure_remote_with_token doesn't fail or rewrite origin
    # since we want to push to our local filesystem path remote.
    env = os.environ.copy()
    # We don't set GH_PAT or GITHUB_TOKEN so it uses the existing file remote we set up
    res = run_cmd([sys.executable, "gol.py", "--mode", "single"], cwd=repo_dir, env=env)

    # Verify stdout outputs
    assert "=== Frame 1" in res.stdout
    assert "Created" in res.stdout
    assert "Pushed frame 1 successfully." in res.stdout

    # Verify state.json was created/updated
    state_file = repo_dir / "state.json"
    assert state_file.exists()
    with open(state_file, encoding="utf-8") as f:
        state = json.load(f)
    assert "grid" in state
    assert "seen_hashes" in state
    assert state["frame_total"] == 1

    # Verify remote has the pushed frame branch/main
    # Let's clone or check the remote log
    log_res = run_cmd(["git", "log", "main", "--oneline"], cwd=remote_dir)
    # The log should contain "gol base" and several "gol x,y" commits
    lines = log_res.stdout.splitlines()
    assert any("gol base" in line for line in lines)
    assert any("gol 0,2" in line or "gol 1,0" in line for line in lines)
    print("End-to-end integration test passed successfully!")


def test_empty_grid() -> None:
    from gol import empty_grid, GRID_W, GRID_H

    grid = empty_grid()
    assert len(grid) == GRID_H
    assert all(len(row) == GRID_W for row in grid)
    assert sum(sum(row) for row in grid) == 0


def test_load_seed() -> None:
    from gol import load_seed

    grid = load_seed("glider")
    # glider has 5 cells
    assert sum(sum(row) for row in grid) == 5
    # verify wrapping
    grid_wrapped = load_seed("glider", offset_x=52, offset_y=7)
    assert sum(sum(row) for row in grid_wrapped) == 5


def test_step_blinker() -> None:
    from gol import step, empty_grid

    # Create a simple blinker (horizontal bar of 3 cells)
    # . . . . .
    # . x x x .
    # . . . . .
    grid = empty_grid()
    grid[3][10] = 1
    grid[3][11] = 1
    grid[3][12] = 1

    # After step, it should become vertical bar:
    # . . x . .
    # . . x . .
    # . . x . .
    next_grid = step(grid)
    assert next_grid[2][11] == 1
    assert next_grid[3][11] == 1
    assert next_grid[4][11] == 1
    assert next_grid[3][10] == 0
    assert next_grid[3][12] == 0

    # After one more step, it should go back to horizontal
    back_grid = step(next_grid)
    assert back_grid[3][10] == 1
    assert back_grid[3][11] == 1
    assert back_grid[3][12] == 1
