"""Run: venv/bin/python test_bot.py  (no network needed)"""
import bot
from bot import LINK, clock, human

VID = "dQw4w9WgXcQ"
for url in [
    f"https://www.youtube.com/watch?v={VID}",
    f"https://youtube.com/watch?v={VID}&t=42s",
    f"https://m.youtube.com/watch?app=desktop&v={VID}",
    f"https://music.youtube.com/watch?v={VID}&list=RDAMVM",
    f"https://youtu.be/{VID}?si=abc",
    f"https://www.youtube.com/shorts/{VID}",
    f"https://www.youtube.com/live/{VID}",
    f"https://www.youtube.com/embed/{VID}",
    f"listen to this youtu.be/{VID} !!",
]:
    assert (m := LINK.search(url)) and m[1] == VID, url
for text in ["fairuz kifak inta", "https://example.com/watch?v=dQw4w9WgXcQ", "https://www.youtube.com/@channel"]:
    assert not LINK.search(text), text

assert human(1234567) == "1.2M" and human(999) == "999" and human(None) == "?"
assert clock(212) == "3:32" and clock(3725) == "1:02:05"


# Route rotation, with a fake YoutubeDL that records which proxy each attempt used.
class FakeYDL:
    calls, errors = [], {}

    def __init__(self, opts):
        self.proxy = opts.get("proxy")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def extract_info(self, url, download):
        FakeYDL.calls.append(self.proxy)
        route = self.proxy.split("-")[0] if self.proxy else None  # strip the {session} part
        if route in FakeYDL.errors:
            raise Exception(FakeYDL.errors[route])
        return {"proxy": self.proxy}


def run(errors=None):
    FakeYDL.calls, FakeYDL.errors = [], errors or {}
    return bot.extract({}, "u", download=False)


bot.YoutubeDL = FakeYDL
bot.ROUTES = ["socks5://a", "http://b-{session}", "direct"]

# healthy routes are used in turn (round robin), "direct" means no proxy
used = [run()["proxy"] for _ in range(3)]
assert len({str(u).split("-")[0] for u in used}) == 3, used  # 3 calls -> 3 different routes
# {session} is filled with a new random id every time
sessions = {run()["proxy"] for _ in range(6)} - {"socks5://a", None}
assert len(sessions) == 2 and all(s.startswith("http://b-") and "{session}" not in s for s in sessions), sessions

# a bot-checked route is skipped to the next one, then tried last until it works again
bot.blocked_at.clear(), bot.used_at.clear()
assert run({"socks5://a": "Sign in to confirm you're not a bot"})["proxy"] != "socks5://a"
assert "socks5://a" in bot.blocked_at
for _ in range(4):
    run()
    assert FakeYDL.calls[0] != "socks5://a", "blocked route must not be first while others work"
run({"http://b": "HTTP Error 429", None: "not a bot"})  # everything else fails -> a gets used and recovers
assert FakeYDL.calls[-1] == "socks5://a" and "socks5://a" not in bot.blocked_at

# an unreachable proxy sinks too; a broken video does not demote a healthy route
bot.blocked_at.clear(), bot.used_at.clear()  # fresh state: route a goes first
run({"socks5://a": "Unable to download API page (caused by TransportError('refused'))"})
assert "socks5://a" in bot.blocked_at
bot.blocked_at.clear(), bot.used_at.clear()
try:
    run({"socks5://a": "Private video", "http://b": "Private video", None: "Private video"})
except Exception:
    pass
assert not bot.blocked_at

# an error on every route: each route tried exactly once, then the error is raised
try:
    run({"socks5://a": "Video unavailable", "http://b": "Video unavailable", None: "Video unavailable"})
    raise AssertionError("should have raised")
except Exception as e:
    assert "Video unavailable" in str(e) and len(FakeYDL.calls) == 3

print("ok")
