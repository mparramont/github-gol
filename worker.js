const GRID_W = 52;
const GRID_H = 7;

const SEEDS = {
  "glider": [
    [1, 0], [2, 1], [0, 2], [1, 2], [2, 2]
  ],
  "lwss": [
    [1, 0], [4, 0],
    [0, 1],
    [0, 2], [4, 2],
    [0, 3], [1, 3], [2, 3], [3, 3]
  ],
  "r_pentomino": [
    [25, 2], [26, 2],
    [24, 3], [25, 3],
    [25, 4]
  ],
  "acorn": [
    [22, 3], [24, 2], [24, 3], [26, 3], [27, 3], [28, 3], [29, 3]
  ],
  "triple_glider": [
    [1, 0], [2, 1], [0, 2], [1, 2], [2, 2],
    [25, 0], [26, 1], [24, 2], [25, 2], [26, 2],
    [10, 4], [11, 5], [9, 6], [10, 6], [11, 6]
  ]
};

function emptyGrid() {
  return Array.from({ length: GRID_H }, () => Array(GRID_W).fill(0));
}

function loadSeed(name, offsetX = 0, offsetY = 0) {
  const grid = emptyGrid();
  const seed = SEEDS[name];
  if (!seed) return grid;
  for (const [x, y] of seed) {
    grid[(y + offsetY) % GRID_H][(x + offsetX) % GRID_W] = 1;
  }
  return grid;
}

function step(grid) {
  const next = emptyGrid();
  for (let y = 0; y < GRID_H; y++) {
    for (let x = 0; x < GRID_W; x++) {
      let n = 0;
      for (const dy of [-1, 0, 1]) {
        for (const dx of [-1, 0, 1]) {
          if (dx === 0 && dy === 0) continue;
          const ny = (y + dy + GRID_H) % GRID_H;
          const nx = (x + dx + GRID_W) % GRID_W;
          n += grid[ny][nx];
        }
      }
      if (grid[y][x]) {
        next[y][x] = (n === 2 || n === 3) ? 1 : 0;
      } else {
        next[y][x] = (n === 3) ? 1 : 0;
      }
    }
  }
  return next;
}

function gridToTupleString(grid) {
  return JSON.stringify(grid);
}

function population(grid) {
  let count = 0;
  for (const row of grid) {
    for (const val of row) {
      if (val) count++;
    }
  }
  return count;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Opaque URL check
    if (url.pathname !== `/${env.SECRET_PATH}`) {
      return new Response("Not Found", { status: 404 });
    }

    const engine = url.searchParams.get("engine") || "github";

    if (engine === "github") {
      // Existing GitHub Actions trigger path
      const ghUrl = `https://api.github.com/repos/${env.GH_OWNER}/${env.GH_REPO}/actions/workflows/animate.yml/dispatches`;
      const response = await fetch(ghUrl, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${env.GH_PAT}`,
          "Accept": "application/vnd.github.v3+json",
          "User-Agent": "Cloudflare-Worker"
        },
        body: JSON.stringify({
          ref: "main",
          inputs: {
            fast_mode: "true"
          }
        })
      });

      if (response.ok) {
        return new Response("Fast mode triggered via GitHub Actions!", { status: 200 });
      } else {
        const err = await response.text();
        return new Response(`Failed to trigger GitHub Actions: ${err}`, { status: 500 });
      }
    }

    if (engine === "cloudflare") {
      const frameStr = url.searchParams.get("frame") || "0";
      const frameNum = parseInt(frameStr, 10);

      if (frameNum === 0) {
        // Run a short background loop of 15 frames on the worker (max waitUntil limit is 30s)
        const maxFrames = Math.min(parseInt(url.searchParams.get("frames") || "15", 10), 18);
        ctx.waitUntil((async () => {
          for (let f = 1; f <= maxFrames; f++) {
            try {
              await runCloudflareFrame(f, env);
            } catch (err) {
              console.error(`Error in background frame ${f}:`, err);
              break;
            }
            if (f < maxFrames) {
              await new Promise(resolve => setTimeout(resolve, 1000));
            }
          }
        })());
        return new Response(`Cloudflare background loop started for ${maxFrames} frames!`, { status: 200 });
      } else {
        // Run exactly one frame synchronously (driven by external client loop)
        try {
          await runCloudflareFrame(frameNum, env);
          return new Response(`Frame ${frameNum} completed successfully`, { status: 200 });
        } catch (err) {
          console.error(`Error in synchronous frame ${frameNum}:`, err);
          return new Response(`Frame ${frameNum} failed: ${err.message}`, { status: 500 });
        }
      }
    }

    return new Response("Invalid engine", { status: 400 });
  }
};

async function runCloudflareFrame(frameNum, env) {
  const owner = env.GH_OWNER;
  const repo = env.GH_REPO;
  const token = env.GH_PAT;
  const authorName = env.GIT_AUTHOR_NAME || "Miguel Parramon";
  const authorEmail = env.GIT_AUTHOR_EMAIL || "mparramont@gmail.com";

  const headers = {
    "Authorization": `Bearer ${token}`,
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "Cloudflare-Worker"
  };

  // 1. Get latest commit on main branch
  const refRes = await fetch(`https://api.github.com/repos/${owner}/${repo}/git/ref/heads/main`, { headers });
  if (!refRes.ok) throw new Error(`Failed to get main ref: ${await refRes.text()}`);
  const refData = await refRes.json();
  const parentCommitSha = refData.object.sha;

  // 2. Get tree of the parent commit
  const commitRes = await fetch(`https://api.github.com/repos/${owner}/${repo}/git/commits/${parentCommitSha}`, { headers });
  if (!commitRes.ok) throw new Error(`Failed to get parent commit: ${await commitRes.text()}`);
  const commitData = await commitRes.json();
  const parentTreeSha = commitData.tree.sha;

  // 3. Fetch current state.json
  const stateRes = await fetch(`https://api.github.com/repos/${owner}/${repo}/contents/state.json`, { headers });
  let state = { grid: null, seen_hashes: [], seed_idx: 0, frame_total: 0 };
  if (stateRes.ok) {
    const stateData = await stateRes.json();
    const content = atob(stateData.content);
    state = JSON.parse(content);
  }

  let grid = state.grid;
  let seenHashes = state.seen_hashes || [];
  let seedIdx = state.seed_idx || 0;
  let frameTotal = state.frame_total || 0;

  const seedNames = Object.keys(SEEDS);

  if (!grid) {
    grid = loadSeed(seedNames[seedIdx]);
    seenHashes = [];
  }

  // Stuck/dead detection
  let gHash = gridToTupleString(grid);
  if (seenHashes.includes(gHash) || population(grid) === 0) {
    seedIdx = (seedIdx + 1) % seedNames.length;
    grid = loadSeed(seedNames[seedIdx]);
    seenHashes = [];
    gHash = gridToTupleString(grid);
  }

  seenHashes.push(gHash);
  if (seenHashes.length > 6) {
    seenHashes.shift();
  }

  frameTotal++;

  // Step the grid for the NEXT iteration
  const nextGrid = step(grid);

  // Update state object
  const newState = {
    grid: nextGrid,
    seen_hashes: seenHashes,
    seed_idx: seedIdx,
    frame_total: frameTotal
  };

  // 4. Create blob for new state.json
  const blobRes = await fetch(`https://api.github.com/repos/${owner}/${repo}/git/blobs`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      content: JSON.stringify(newState, null, 2),
      encoding: "utf-8"
    })
  });
  if (!blobRes.ok) throw new Error(`Failed to create state.json blob: ${await blobRes.text()}`);
  const blobData = await blobRes.json();
  const stateBlobSha = blobData.sha;

  // 5. Create new tree containing the state.json blob
  const treeRes = await fetch(`https://api.github.com/repos/${owner}/${repo}/git/trees`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      base_tree: parentTreeSha,
      tree: [
        {
          path: "state.json",
          mode: "100644",
          type: "blob",
          sha: stateBlobSha
        }
      ]
    })
  });
  if (!treeRes.ok) throw new Error(`Failed to create tree: ${await treeRes.text()}`);
  const treeData = await treeRes.json();
  const newTreeSha = treeData.sha;

  // 6. Create the base commit
  const baseCommitRes = await fetch(`https://api.github.com/repos/${owner}/${repo}/git/commits`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      message: `gol base frame ${frameNum} (cf)`,
      tree: newTreeSha,
      parents: [parentCommitSha]
    })
  });
  if (!baseCommitRes.ok) throw new Error(`Failed to create base commit: ${await baseCommitRes.text()}`);
  const baseCommitData = await baseCommitRes.json();
  const baseCommitSha = baseCommitData.sha;

  // 7. Create pixel commits in parallel
  const now = new Date();
  const todayWeekday = now.getUTCDay();
  const ghWeekday = todayWeekday;

  const pixelPromises = [];
  for (let y = 0; y < GRID_H; y++) {
    for (let x = 0; x < GRID_W; x++) {
      if (grid[y][x]) {
        const daysBack = (51 - x) * 7 + (ghWeekday - y);
        const targetDate = new Date(now.getTime() - daysBack * 24 * 60 * 60 * 1000);
        if (targetDate > now) continue;
        const dateStr = targetDate.toISOString().replace(/\.\d+Z$/, "Z");

        pixelPromises.push((async () => {
          const res = await fetch(`https://api.github.com/repos/${owner}/${repo}/git/commits`, {
            method: "POST",
            headers,
            body: JSON.stringify({
              message: `gol ${x},${y}`,
              tree: newTreeSha,
              parents: [baseCommitSha],
              author: {
                name: authorName,
                email: authorEmail,
                date: dateStr
              },
              committer: {
                name: authorName,
                email: authorEmail,
                date: dateStr
              }
            })
          });
          if (!res.ok) throw new Error(`Failed to create pixel commit for ${x},${y}: ${await res.text()}`);
          const data = await res.json();
          return data.sha;
        })());
      }
    }
  }

  const pixelCommitShas = await Promise.all(pixelPromises);

  // 8. Create octopus merge commit
  const mergeRes = await fetch(`https://api.github.com/repos/${owner}/${repo}/git/commits`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      message: `gol merge frame ${frameNum} (cf)`,
      tree: newTreeSha,
      parents: [baseCommitSha, ...pixelCommitShas]
    })
  });
  if (!mergeRes.ok) throw new Error(`Failed to create merge commit: ${await mergeRes.text()}`);
  const mergeData = await mergeRes.json();
  const mergeCommitSha = mergeData.sha;

  // 9. Update heads/main ref
  const refUpdateRes = await fetch(`https://api.github.com/repos/${owner}/${repo}/git/refs/heads/main`, {
    method: "PATCH",
    headers,
    body: JSON.stringify({
      sha: mergeCommitSha,
      force: true
    })
  });
  if (!refUpdateRes.ok) throw new Error(`Failed to update ref: ${await refUpdateRes.text()}`);

  console.log(`Frame ${frameNum} pushed successfully! Population: ${population(grid)}`);
}
