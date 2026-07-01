# AGENTS.md

## Project overview

This is a small BOOTH new-item notification app.

The app periodically checks BOOTH listing/search URLs, detects newly listed items, and sends new-item notifications to Discord via a Discord Webhook.

It is currently designed to run on GitHub Actions, not on a dedicated server.

## Current structure

```text
.github/workflows/booth-watch.yml
scripts/check_booth.py
requirements.txt
targets.json
seen_items.json
```

## How it works

1. GitHub Actions runs the watcher on a schedule or manually.
2. `scripts/check_booth.py` reads BOOTH target settings from `targets.json`.
3. It fetches each BOOTH page and extracts item IDs from item links.
   For targets with `free_only: true`, it checks product details and keeps
   products that have at least one free variation.
4. It compares extracted IDs with `seen_items.json`.
5. On the first run, it saves current item IDs without sending notifications.
6. On later runs, it sends only newly detected items to Discord.
7. Updated `seen_items.json` is committed back to the repository by GitHub Actions.

## Important notes

* Discord Webhook URL is stored as the GitHub Actions secret `DISCORD_WEBHOOK_URL`.
* Do not commit the actual Webhook URL.
* `seen_items.json` stores already detected BOOTH item IDs.
  It also caches free-variation checks to avoid fetching every product detail
  on every run.
* `targets.json` contains each BOOTH URL, its Webhook name, and whether to
  notify only items with a free variation (`free_only`).
* Run `python3 scripts/add_target.py` to add a target and its local Discord
  Webhook Secret interactively.
* Run `python3 scripts/list_targets.py` to list targets.
* Run `python3 scripts/remove_target.py` to remove a target interactively.
* Avoid aggressive crawling. Use a small number of URLs and low frequency.
* During testing, the GitHub Actions schedule may run every 5 minutes.
* For normal use, change it to around once per hour.
