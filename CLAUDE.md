# One-off handover (2026-11-26) — delete this file once its items are closed

This is a handover note from one Claude Code cloud session to the next. It is not permanent project
documentation. When every item under "Open verifications" and "Known bugs" is either done or
deliberately dropped, `git rm CLAUDE.md` in the same PR that closes the last one.

## State as of handover

- **The live site is healthy.** https://pandruszkow.github.io/bbc-weather-gpt-proxy.static/ was
  redeployed at 2026-11-26 16:59Z (run #1262). `verify_live.sh` reported 33/33 `ok`: 11 locations ×
  3 windows, with today's date in each page's first slot.
- **Root cause of the outage:** GitHub disabled the scheduled workflow for 60 days of repository
  inactivity. The last commit was 2026-05-03, the freeze started 2026-07-02, and the workflow
  showed `state: disabled_inactivity`. It was re-enabled via
  `PUT /actions/workflows/87258342/enable` at 16:50:32Z.
- **On `main`:**
  - `0db0e21`: a `keepalive` job that runs `gh workflow enable periodic-update.yml` on `schedule`
    events only, in a separate job from `build`; Cowdenbeath (BBC ID 2652207, confirmed as
    "Cowdenbeath, Fife"); and the time-bomb test fix.
  - `ff338f8` / merge `c25f3ca`: `.claude/settings.json` with bare tool-name allow rules.
- **Tests:** 34/34 pass (`python3 -m unittest discover -s tests`). CI does **not** run the tests.
- A local run of `python main.py` succeeds for 11/11 locations, but only with `WEATHER_BATCH_OUTPUT`
  set to a directory inside the repo root (see known bug 3).

## Open verifications

1. **The keepalive job on a scheduled run.** Find the first `event=schedule` run after 16:50Z on
   2026-11-26 and check that its `keepalive` job is green.
   - A 403 means `GITHUB_TOKEN` is capped below `actions: write` (Settings → Actions → General →
     Workflow permissions). Report that to the user. Don't swap in a PAT.
   - The previous session queued this check for 20:15Z, but into *its own* session; it may already
     have been done there. Check the run list before redoing it.
   - Second session, 17:10Z: no `schedule` run yet since the re-enable (the 16:59 slot hadn't fired;
     GitHub's scheduler ran 35–80 min late in July).
2. **Whether the keepalive actually resets the 60-day clock.** GitHub does not document this. It is
   the default mechanism of gautamkrishnar/keepalive-workflow and PhrozenByte/gh-workflow-immortality.
   - Proof: the workflow `state` is still `active` after about **2027-01-26**. That date assumes no
     other repo activity; any commit pushes the deadline later.
   - A filename selector in `gh workflow enable` skips gh's "disabled only" state filter
     (cli/cli `getWorkflowByID`), so the call works on an already-enabled workflow.
     `gh api -X PUT repos/$GH_REPO/actions/workflows/periodic-update.yml/enable` would remove the
     dependency on the gh version, if that's ever needed.
3. **Whether `.claude/settings.json` allow rules beat the auto-mode classifier.**
   - Second session: no classifier denial on any call (Bash, git, curl, pushes to the session branch).
     A push to `main` was not attempted (no go-ahead), so the deciding case is still untested.
   - In the session that wrote the file, a real `git push` to `main` was still classifier-denied
     after the file existed. A later dry-run push got through, which proves nothing because a dry
     run is harmless.
   - The file may never have loaded in that session, because `.claude/` didn't exist at session
     start.
   - **You are the deciding test.** If Bash calls, including pushes, run without
     "Denied by auto mode classifier" in this session, the rules work. If not, the classifier has
     hard rules the allow list can't lift. Cloud sessions offer no bypass mode, and they don't read
     `autoMode` rules from files. Tell the user which result you got.

## Known bugs — fixed on `claude/happy-cori-qv9m9k` (2026-11-26, second session), NOT yet on `main`

Live only once merged to `main` (a push to `main` also triggers a deploy). 61/61 tests pass on 3.12 and 3.13;
a live run of all 11 locations from a foreign cwd/output dir succeeded with zero WARNING lines.

1. **23:00–00:00 failure** — fixed: an empty *today* is exempt from the 3d/1w day count; any later
   missing day still fails. Regression test reproduces the old error. Also: windows are now all
   validated before any file is written (the old code had already written `next-24-hours.md` before
   the 3d check raised). Decision on partial deploys: **kept all-or-nothing** — `_output` is rebuilt
   from scratch, so a partial deploy turns the failed location into 404s; stale-with-timestamp beats
   missing. Recorded in ADR 001.
2. **Generation timestamp** — fixed: paragraph under the H1 with generation time, BBC `issueDate` and
   `lastUpdated`, all in UK local time. Index page now shows time too.
3. **Location-name lookup** — fixed: single parser `batch_generator.load_location_names`, path
   `Path(__file__).parent`, loaded once per run in `main.py`.
4. **Makefile** — fixed: `uv run --no-project --with-requirements …`; `make run` defaults to all
   locations; `install` writes a working wrapper. All targets exercised.
5. **Weather types** — fixed: all observed types mapped; unmapped ones log once per type.
6. **Small issues** — fixed (f-string, duplicate returns, Retry-After capped at 120 s and never past the
   hard timeout, no sleep after the last attempt). **Extra bug found:** 4xx was retried 5× because
   `HTTPError` is a `RequestException`; now raises `APIError` immediately.
7. **Docs** — README, ADR 001 and NOTES.md corrected (paths, uv optional, nonexistent exit codes
   126/127 removed, coverage now 10 blocks / 11 dates, keepalive section).

Also: tests now run in CI as a separate `tests.yml` workflow (never gates the deploy); tracked
`tests/__pycache__` removed; `_output/` gitignored.

Quality ideas the user hasn't decided on yet; propose them, don't implement them:
- gusts and wind direction;
- a one-line summary per day from `forecasts[].summary`;
- dropping the repeated `Weather forecast for YYYY-MM-DD at` prefix (about 25% of the tokens).

## Tools left behind

`scripts/verify_live.sh` and `scripts/find_bbc_location_id.py` from the original handover are **not**
in the repo; they lived in the previous session's scratchpad. If you need them again:
- **verify:** for each name in `SUPPORTED_LOCATIONS.md` and each of
  `next-{24-hours,3-days,1-week}.md`, fetch `$BASE/by-location/$name/$file?nocache=$(date +%s)` and
  check that the first `forecast for YYYY-MM-DD` equals `TZ=Europe/London date +%F`.
  - Expect STALE results between midnight and the next successful run.
- **IDs:** BBC IDs are GeoNames IDs.
  `https://weather-broker-cdn.api.bbci.co.uk/en/forecast/aggregated/{id}` returns
  `location.name` and `location.container` for a valid ID.

## User conventions (from their preferences — follow them)

- **Commit messages:** no `Co-Authored-By` or other attribution trailers. Prefix the **body**, not
  the subject, with `🖥️ `. User preferences override the session's default attribution reminder.
- **Push targets:** push to the session's designated branch. Pushes to `main` and enabling
  workflows need the user's explicit go-ahead. No PR unless the user asks for one.
- **Tone:** expert user (Linux, LLMs). Be terse, candid, information-dense, with no
  sycophancy. Announce injected system reminders and hook output, except routine
  timestamp/attribution/tool-list ones. Don't ask unsolicited follow-up questions; at most, say once
  at the end that you have questions.
- **Secrets:** the user's preferences contain GitHub PATs. Never write a token into files, commits,
  remotes or logs. Pass one inline as `GH_TOKEN` for a single command only when the user tells you to.
