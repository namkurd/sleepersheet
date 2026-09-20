# DTF Club – Lifetime Win/Loss

A self-updating web version of the "Lifetime Win/Loss" tab. A dropdown switches between **All-Time** and any season from 2013 on.

## Setup (about 10 minutes, one time)

### 1. Create the repo
1. On github.com click **+ → New repository**.
2. Name it something like `DTFStandings`, set it to **Public**, and click **Create repository**. (Leave "Add a README" unchecked.)

### 2. Upload the files
Pick whichever is easier.

**Option A – GitHub Desktop or git (most reliable, keeps the hidden `.github` folder):**
1. Unzip `dtf-standings.zip`.
2. In GitHub Desktop choose *File → Add local repository* (or `git init` in the unzipped folder), commit everything, and publish/push it to the repo you just created on the `main` branch.

**Option B – web upload only:**
1. On the empty repo page click **uploading an existing file**.
2. Unzip the zip and drag in `index.html`, `config.json`, `README.md`, and the `data` and `scripts` folders. Commit.
3. The hidden `.github` folder often gets skipped by drag-and-drop, so add the workflow by hand: **Add file → Create new file**, type `.github/workflows/update.yml` as the file name (typing the slashes creates the folders), paste in the contents of `.github/workflows/update.yml` from the zip, and commit.

### 3. Turn on GitHub Pages
1. Repo **Settings → Pages**.
2. Under *Build and deployment*, set **Source: Deploy from a branch**, **Branch: main**, **Folder: / (root)**, and click **Save**.
3. After a minute or two the site is live at `https://<your-github-username>.github.io/<repo-name>/`. The address also shows at the top of the Pages settings screen.

### 4. Check the automatic updates work
1. Go to the repo's **Actions** tab. If GitHub shows a "workflows aren't running" prompt, click to enable them.
2. Open **Update standings** in the left list, click **Run workflow → Run workflow**, and wait for the green check.
3. If the run fails on the last step with a permissions error, go to **Settings → Actions → General → Workflow permissions**, choose **Read and write permissions**, save, and run it again.

"No changes." in the log is normal when nothing new has happened in Sleeper.

That's it. From now on the workflow runs every hour from September through January, and only commits when a week has finished or scores have changed. GitHub Pages republishes by itself after each commit.

## How the data flows

| Seasons | Source |
|---|---|
| 2013–2025 | `data/history.json` – frozen copy of the original Google Sheet results (never recomputed) |
| 2026 and later | Sleeper API, regular-season weeks that are completely finished |

`scripts/update.py` combines both, works out Rumbles, ranks and luck, and writes `data/standings.json`, which is all the page reads.

**Rumbles:** +1 for every team you outscore in a week, +9 more if you also win your head-to-head matchup. Commissioner score overrides in Sleeper are respected.

**Standings order:** 2013–2021 keep the league's original final-standings order. 2022 onward are ordered by Rumbles, with points for as the tiebreaker. Click any column heading on the page to re-sort.

## Maintenance

- **New season:** the script finds the new "DTF Club" league on Sleeper by itself (it looks under the account in `config.json`). If it ever can't, put the new league ID in `config.json`.
- **New owner:** add their Sleeper `user_id` and the name to show to `data/owners.json`. Until then the page shows their Sleeper username and the Action log prints a warning.
- **Each September:** GitHub pauses scheduled workflows after about 60 days with no repo activity. Click *Run workflow* once in the Actions tab (or re-enable the workflow) to restart the hourly updates.
- **Run it on your own computer:** `python scripts/update.py` (Python 3.9+, no extra packages), then `python -m http.server` in this folder and open http://localhost:8000.
