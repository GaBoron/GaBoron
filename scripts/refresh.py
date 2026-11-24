"""Refresh the profile dashboards from public GitHub statistics."""
import json
import os
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

ASSETS = Path(__file__).resolve().parents[1] / "assets"
LOGIN = os.environ.get("GITHUB_REPOSITORY_OWNER", "GaBoron")
PAPER, INK, ORANGE = "#fff2c8", "#31251c", "#ff682c"
HEAT = ["#e9dfc4", "#f3ca78", "#dea047", "#b96e31", "#854623"]
TYPES = [
    ("代码提交", "totalCommitContributions", "#c0531e"),
    ("代码审查", "totalPullRequestReviewContributions", "#f19a39"),
    ("发起 Issue", "totalIssueContributions", "#e8bf46"),
    ("发起 PR", "totalPullRequestContributions", "#92664b"),
    ("创建仓库", "totalRepositoryContributions", "#503b31"),
]


def api(*args):
    return json.loads(subprocess.check_output(["gh", "api", *args], encoding="utf-8"))


def load():
    end = datetime.now(timezone(timedelta(hours=8))).date()
    start = end - timedelta(days=364)
    fields = " ".join(key for _, key, _ in TYPES)
    query = """
    query($login:String!, $from:DateTime!, $to:DateTime!) {
      user(login:$login) {
        followers { totalCount }
        contributionsCollection(from:$from,to:$to) {
          FIELDS
          contributionCalendar { weeks { contributionDays { date contributionCount } } }
        }
      }
    }""".replace("FIELDS", fields)
    user = api("graphql", "-f", "query=" + query, "-f", "login=" + LOGIN,
               "-f", f"from={start}T00:00:00Z", "-f", f"to={end}T23:59:59Z")["data"]["user"]
    pages = api(f"users/{LOGIN}/repos?type=owner&per_page=100", "--paginate", "--slurp")
    repos = [repo for page in pages for repo in page if not repo["private"]]
    return start, end, user, repos


def render(start, end, user, repos, mobile):
    width, height = (800, 1580) if mobile else (1440, 880)
    root = ET.Element("svg", xmlns="http://www.w3.org/2000/svg", width=str(width),
                      height=str(height), viewBox=f"0 0 {width} {height}", role="img")
    ET.SubElement(root, "title").text = f"{LOGIN} 的 GitHub 数据，截至 {end}"
    root.set("font-family", "Arial, Microsoft YaHei, sans-serif")

    def element(tag, **attrs):
        return ET.SubElement(root, tag, {key: str(value) for key, value in attrs.items()})

    def rect(x, y, w, h, color, radius=0):
        element("rect", x=x, y=y, width=w, height=h, fill=color, rx=radius)

    def text(x, baseline, value, size=26, bold=False, **attrs):
        node = element("text", x=x, y=baseline, fill=INK, **attrs)
        node.set("font-size", str(size))
        node.set("font-weight", "700" if bold else "400")
        node.text = str(value)
        return node

    rect(0, 0, width, height, PAPER)
    data = user["contributionsCollection"]
    days = {date.fromisoformat(d["date"]): d["contributionCount"]
            for week in data["contributionCalendar"]["weeks"] for d in week["contributionDays"]}
    assert set(days) == {start + timedelta(days=i) for i in range(365)}
    original = sorted((r for r in repos if not r["fork"]),
                      key=lambda r: (-r["stargazers_count"], r["name"].lower()))
    stats = [(len(repos), "公开仓库"), (sum(r["stargazers_count"] for r in original), "非 Fork 仓库 Stars"),
             (user["followers"]["totalCount"], "关注者"), (sum(days.values()), "近一年贡献")]
    cols = 2 if mobile else 4
    for index, (value, label) in enumerate(stats):
        x = 48 + index % cols * (width // cols)
        y = 97 + index // cols * 153
        text(x, y, f"{value:,}", 78, True)
        text(x, y + 47, label, 28)

    top = 335 if mobile else 187
    rect(48, top, width - 96, 2, INK)
    text(48, top + 57, "贡献日历", 36, True)
    text(width - 48, top + 55, f"{start} — {end}", 25, **{"text-anchor": "end"})
    sunday = start - timedelta(days=(start.weekday() + 1) % 7)
    week_count = (end - sunday).days // 7 + 1
    split = week_count // 2 if mobile else week_count
    last_label = {}
    for day, value in sorted(days.items()):
        week, row = divmod((day - sunday).days, 7)
        band = int(mobile and week >= split)
        col = week - split * band
        y = top + 125 + band * 240
        x = 108 + col * 24
        if day.day == 1 and col - last_label.get(band, -5) >= 3:
            text(x, y - 11, f"{day.month}月", 20)
            last_label[band] = col
        level = sum(value >= k for k in (1, 5, 12, 25))
        rect(x, y + row * 24, 19, 19, HEAT[level], 3)
    for band in range(2 if mobile else 1):
        for row, label in [(1, "周一"), (3, "周三"), (5, "周五")]:
            text(48, top + 141 + band * 240 + row * 24, label, 19)
    summary = top + (578 if mobile else 338)
    text(48, summary, f"活跃 {sum(v > 0 for v in days.values())} 天   ·   单日最高 {max(days.values())} 次", 25)
    lx = width - 244
    text(lx, summary, "少", 20)
    for index, color in enumerate(HEAT):
        rect(lx + 31 + index * 25, summary - 17, 18, 18, color, 3)
    text(lx + 164, summary, "多", 20)
    lower = summary + 63
    rect(48, lower - 38, width - 96, 2, INK)
    text(48, lower + 15, "获星最多的项目", 32, True)
    peak = max((r["stargazers_count"] for r in original), default=0)
    for index, repo in enumerate(original[:4]):
        y = lower + 72 + index * 47
        name = repo["name"]
        # Reserve space for the bar even for very long repository names.
        attrs = {"textLength": str(min(len(name) * 15, 475)), "lengthAdjust": "spacingAndGlyphs"}
        text(48, y, name, 25, **attrs)
        stars = repo["stargazers_count"]
        rect(550, y - 18, 145 * stars / max(1, peak), 17, ORANGE)
        text(716, y, stars, 26, True)
    x = 48 if mobile else 838
    y = lower + (296 if mobile else 15)
    text(x, y, "近一年贡献构成", 32, True)
    values = [data[key] for _, key, _ in TYPES]
    bar = width - x - 50
    total = sum(values)
    offset = 0
    for index, ((label, _, color), value) in enumerate(zip(TYPES, values)):
        segment = bar * value / max(1, total)
        rect(x + offset, y + 26, segment, 16, color)
        offset += segment
        left = x + index % 2 * (bar // 2)
        baseline = y + 94 + index // 2 * 47
        rect(left, baseline - 15, 13, 13, color)
        text(left + 22, baseline, label, 23)
        text(left + 154, baseline, f"{value:,}", 24, True)
    ET.indent(root)
    return ET.tostring(root, encoding="utf-8")


if __name__ == "__main__":
    snapshot = load()
    for mobile, filename in [(False, "dashboard.svg"), (True, "dashboard-mobile.svg")]:
        (ASSETS / filename).write_bytes(render(*snapshot, mobile))
