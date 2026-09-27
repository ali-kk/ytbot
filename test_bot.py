"""Run: venv/bin/python test_bot.py"""
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
print("ok")
