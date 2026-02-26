"""seed_mock_data.py — generates mock Reddit posts for development and testing.

Covers all code paths:
  - Genuine interest matches (pub quiz, climbing, dance, social, coding)
  - Partial matches (vague interest, wrong context)
  - Non-matches (coffee, housing, unrelated)
  - Edge cases (short text, non-English, deleted author, removed content)
  - Both post and comment types
  - Multiple subreddits

Run: python3 scripts/seed_mock_data.py
Output: data/mock/mock_reddit_posts.json
"""
import json
import os
from datetime import datetime, timedelta, timezone

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "mock", "mock_reddit_posts.json")

now = datetime.now(tz=timezone.utc)


def ts(hours_ago: float) -> float:
    return (now - timedelta(hours=hours_ago)).timestamp()


MOCK_POSTS = [
    # --- Genuine interest matches ---
    {
        "item_id": "t3_mock001",
        "type": "post",
        "subreddit": "stockholm",
        "author": "quiz_lover_sthlm",
        "permalink": "https://www.reddit.com/r/stockholm/comments/mock001/",
        "text": "Anyone know good pub quiz spots in Stockholm this Friday? Looking for a fun trivia night with drinks.",
        "created_utc": ts(5),
    },
    {
        "item_id": "t3_mock002",
        "type": "post",
        "subreddit": "StockholmSocialClub",
        "author": "climbing_carl",
        "permalink": "https://www.reddit.com/r/StockholmSocialClub/comments/mock002/",
        "text": "Just moved to Stockholm and really miss climbing. Any good klättring walls or outdoor climbing groups here? Happy to join anyone!",
        "created_utc": ts(10),
    },
    {
        "item_id": "t3_mock003",
        "type": "post",
        "subreddit": "StockholmSocialClub",
        "author": "salsa_sara",
        "permalink": "https://www.reddit.com/r/StockholmSocialClub/comments/mock003/",
        "text": "Looking for bachata and salsa dance events in Stockholm. I'm intermediate level and want to meet people who love dancing as much as I do!",
        "created_utc": ts(15),
    },
    {
        "item_id": "t3_mock004",
        "type": "post",
        "subreddit": "TillSverige",
        "author": "newbie_in_sthlm",
        "permalink": "https://www.reddit.com/r/TillSverige/comments/mock004/",
        "text": "Recently moved to Stockholm and feeling a bit lonely. Looking for social events where I can meet new friends and strangers. Any recommendations?",
        "created_utc": ts(20),
    },
    {
        "item_id": "t3_mock005",
        "type": "post",
        "subreddit": "stockholm",
        "author": "dev_meetup_fan",
        "permalink": "https://www.reddit.com/r/stockholm/comments/mock005/",
        "text": "Are there any Python or developer meetups happening in Stockholm soon? I'm a programmer looking to meet other coders and talk about coding projects.",
        "created_utc": ts(8),
    },
    {
        "item_id": "t3_mock006",
        "type": "post",
        "subreddit": "StockholmSocialClub",
        "author": "pub_crawl_pete",
        "permalink": "https://www.reddit.com/r/StockholmSocialClub/comments/mock006/",
        "text": "Is there a pub crawl happening in Stockholm this weekend? I've done them before in other cities and they're a great way to meet people over drinks and explore bars.",
        "created_utc": ts(3),
    },
    {
        "item_id": "t3_mock007",
        "type": "post",
        "subreddit": "Uppsala",
        "author": "hiker_helena",
        "permalink": "https://www.reddit.com/r/Uppsala/comments/mock007/",
        "text": "Looking for hiking or nature walk groups near Uppsala. I love trails and being outdoors but prefer going with people rather than alone.",
        "created_utc": ts(12),
    },
    {
        "item_id": "t1_mock008",
        "type": "comment",
        "subreddit": "stockholm",
        "author": "trivia_thomas",
        "permalink": "https://www.reddit.com/r/stockholm/comments/mock008/",
        "text": "I've been going to the quiz nights at O'Learys every Thursday. Great atmosphere and the trivia is challenging. You should check it out!",
        "created_utc": ts(6),
    },
    {
        "item_id": "t1_mock009",
        "type": "comment",
        "subreddit": "StockholmSocialClub",
        "author": "social_butterfly_99",
        "permalink": "https://www.reddit.com/r/StockholmSocialClub/comments/mock009/",
        "text": "I'm also new to Stockholm and would love to meet people at social events. Anyone organizing something this month? Happy to join any meetup.",
        "created_utc": ts(18),
    },

    # --- Partial matches (some signal but vague) ---
    {
        "item_id": "t3_mock010",
        "type": "post",
        "subreddit": "Svenska",
        "author": "weekend_planner",
        "permalink": "https://www.reddit.com/r/Svenska/comments/mock010/",
        "text": "Looking for something fun to do this weekend in Stockholm. Maybe something social? Open to ideas.",
        "created_utc": ts(25),
    },
    {
        "item_id": "t3_mock011",
        "type": "post",
        "subreddit": "stockholm",
        "author": "drinks_maybe",
        "permalink": "https://www.reddit.com/r/stockholm/comments/mock011/",
        "text": "What are good places for drinks in Stockholm on a Tuesday evening? Not necessarily a bar crawl, just somewhere lively.",
        "created_utc": ts(30),
    },
    {
        "item_id": "t1_mock012",
        "type": "comment",
        "subreddit": "TillSverige",
        "author": "expat_eric",
        "permalink": "https://www.reddit.com/r/TillSverige/comments/mock012/",
        "text": "The expat community here is pretty active. There are some meetups but I haven't gone to any yet. Might be worth checking out.",
        "created_utc": ts(14),
    },

    # --- Non-matches (no event relevance) ---
    {
        "item_id": "t3_mock013",
        "type": "post",
        "subreddit": "stockholm",
        "author": "coffee_connoisseur",
        "permalink": "https://www.reddit.com/r/stockholm/comments/mock013/",
        "text": "Best coffee shops in Södermalm? Looking for a quiet place to work with good espresso.",
        "created_utc": ts(7),
    },
    {
        "item_id": "t3_mock014",
        "type": "post",
        "subreddit": "stockholm",
        "author": "apartment_hunter",
        "permalink": "https://www.reddit.com/r/stockholm/comments/mock014/",
        "text": "Anyone know how to navigate the Stockholm housing queue? Been waiting 3 years and still no apartment in sight.",
        "created_utc": ts(40),
    },
    {
        "item_id": "t3_mock015",
        "type": "post",
        "subreddit": "Svenska",
        "author": "grammar_question",
        "permalink": "https://www.reddit.com/r/Svenska/comments/mock015/",
        "text": "Can someone explain the difference between 'den' and 'det' in Swedish? I keep making mistakes with it.",
        "created_utc": ts(22),
    },
    {
        "item_id": "t3_mock016",
        "type": "post",
        "subreddit": "stockholm",
        "author": "weather_watcher",
        "permalink": "https://www.reddit.com/r/stockholm/comments/mock016/",
        "text": "Is the weather always this grey in November? Moving from Spain and really struggling with the darkness.",
        "created_utc": ts(11),
    },
    {
        "item_id": "t3_mock017",
        "type": "post",
        "subreddit": "Uppsala",
        "author": "restaurant_lover",
        "permalink": "https://www.reddit.com/r/Uppsala/comments/mock017/",
        "text": "What are the best restaurants in Uppsala for a date night? Looking for something cozy with good food.",
        "created_utc": ts(35),
    },
    {
        "item_id": "t1_mock018",
        "type": "comment",
        "subreddit": "stockholm",
        "author": "transit_tips",
        "permalink": "https://www.reddit.com/r/stockholm/comments/mock018/",
        "text": "The SL app is your best friend for getting around Stockholm. Just make sure to top up your card before rush hour.",
        "created_utc": ts(9),
    },

    # --- Edge cases ---

    # Very short post (<30 chars) — should be filtered by Node F
    {
        "item_id": "t3_mock019",
        "type": "post",
        "subreddit": "stockholm",
        "author": "brief_poster",
        "permalink": "https://www.reddit.com/r/stockholm/comments/mock019/",
        "text": "Any events?",
        "created_utc": ts(2),
    },

    # Non-English text (Swedish)
    {
        "item_id": "t3_mock020",
        "type": "post",
        "subreddit": "Svenska",
        "author": "swedish_user",
        "permalink": "https://www.reddit.com/r/Svenska/comments/mock020/",
        "text": "Hej alla! Söker efter roliga aktiviteter i Stockholm. Finns det några bra sociala evenemang för att träffa nya vänner?",
        "created_utc": ts(16),
    },

    # Deleted author
    {
        "item_id": "t3_mock021",
        "type": "post",
        "subreddit": "stockholm",
        "author": "[deleted]",
        "permalink": "https://www.reddit.com/r/stockholm/comments/mock021/",
        "text": "Looking for pub quiz events this week in Stockholm.",
        "created_utc": ts(4),
    },

    # Removed content
    {
        "item_id": "t3_mock022",
        "type": "post",
        "subreddit": "StockholmSocialClub",
        "author": "some_user",
        "permalink": "https://www.reddit.com/r/StockholmSocialClub/comments/mock022/",
        "text": "[removed]",
        "created_utc": ts(13),
    },

    # Same author appearing many times (dedup test for Node F)
    {
        "item_id": "t3_mock023",
        "type": "post",
        "subreddit": "stockholm",
        "author": "spam_poster",
        "permalink": "https://www.reddit.com/r/stockholm/comments/mock023/",
        "text": "I love going to social events and meeting new people in Stockholm every week!",
        "created_utc": ts(6),
    },
    {
        "item_id": "t3_mock024",
        "type": "post",
        "subreddit": "StockholmSocialClub",
        "author": "spam_poster",
        "permalink": "https://www.reddit.com/r/StockholmSocialClub/comments/mock024/",
        "text": "Going to another pub quiz tonight in Stockholm, anyone joining?",
        "created_utc": ts(7),
    },
    {
        "item_id": "t3_mock025",
        "type": "post",
        "subreddit": "TillSverige",
        "author": "spam_poster",
        "permalink": "https://www.reddit.com/r/TillSverige/comments/mock025/",
        "text": "Just attended a dance event last night, bachata is so much fun!",
        "created_utc": ts(8),
    },
    {
        "item_id": "t3_mock026",
        "type": "post",
        "subreddit": "stockholm",
        "author": "spam_poster",
        "permalink": "https://www.reddit.com/r/stockholm/comments/mock026/",
        "text": "Social climbing gym events are so popular in Stockholm right now.",
        "created_utc": ts(9),
    },
    {
        "item_id": "t3_mock027",
        "type": "post",
        "subreddit": "Svenska",
        "author": "spam_poster",
        "permalink": "https://www.reddit.com/r/Svenska/comments/mock027/",
        "text": "Found a great pub crawl group here for newcomers to Sweden.",
        "created_utc": ts(10),
    },
    {
        "item_id": "t3_mock028",
        "type": "post",
        "subreddit": "Uppsala",
        "author": "spam_poster",
        "permalink": "https://www.reddit.com/r/Uppsala/comments/mock028/",
        "text": "Weekly trivia nights in Uppsala are amazing, you should all come!",
        "created_utc": ts(11),
    },

    # Comment with strong signal
    {
        "item_id": "t1_mock029",
        "type": "comment",
        "subreddit": "StockholmSocialClub",
        "author": "kizomba_karen",
        "permalink": "https://www.reddit.com/r/StockholmSocialClub/comments/mock029/",
        "text": "I've been searching for kizomba and salsa classes in Stockholm for months. Would love to join a dance group or attend a social dancing event!",
        "created_utc": ts(20),
    },

    # High-quality coding match
    {
        "item_id": "t1_mock030",
        "type": "comment",
        "subreddit": "stockholm",
        "author": "python_dev_sthlm",
        "permalink": "https://www.reddit.com/r/stockholm/comments/mock030/",
        "text": "I'm a Python developer looking for programming meetups or developer events in Stockholm. Anyone know of any active coding communities?",
        "created_utc": ts(17),
    },
]


def main() -> None:
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(MOCK_POSTS, f, indent=2)
    print(f"Generated {len(MOCK_POSTS)} mock posts → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
