# Facebook Source Setup

## Modes

- `manual_json` (recommended): import curated posts/comments from selected groups.
- `selenium` (optional): browser-based collector for explicitly approved/public pages.

## 1) Enable source in config

Edit [config.yaml](/Users/satish/Desktop/marketing_project/config.yaml):

- `sources.enabled` include `facebook`
- set `facebook.groups`
- keep `facebook.mode: manual_json` initially

## 2) Provide input data (manual_json)

Write rows to `data/import/facebook_posts.json`:

```json
[
  {
    "item_id": "fb_post_1",
    "type": "post",
    "group": "Stockholm Expats",
    "author": "user123",
    "permalink": "https://www.facebook.com/groups/stockholmexpats/posts/123",
    "text": "I am new to Stockholm and looking for friends to join events.",
    "created_utc": "2026-03-10T10:00:00Z"
  }
]
```

## 3) Run pipeline with both sources

```bash
./.venv/bin/python scripts/run_pipeline.py --sources reddit,facebook
```

## Selenium mode notes

- Set `facebook.mode: selenium` only after policy/legal approval.
- Set env `FACEBOOK_SCRAPE_ACKNOWLEDGED=true`.
- Configure `facebook.selenium.group_urls` map in config.
- This project does not implement login bypass/captcha bypass automation.
