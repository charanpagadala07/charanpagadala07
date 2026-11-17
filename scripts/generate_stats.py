#!/usr/bin/env python3
"""Generates self-hosted GitHub stats cards (SVG) so nothing depends on third-party widget servers.

Usage:
    GH_TOKEN=... python scripts/generate_stats.py <username>
    python scripts/generate_stats.py --demo          # preview with sample data
"""
import json
import math
import os
import sys
import urllib.request
from html import escape

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100, privacy: PUBLIC) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
    }
  }
}
"""

STYLE = """<style>
:root{--bg:#0d1117;--border:#30363d;--fg:#e6edf3;--muted:#8b949e;--track:#21262d;--accent:#58a6ff}
@media (prefers-color-scheme: light){:root{--bg:#ffffff;--border:#d0d7de;--fg:#1f2328;--muted:#656d76;--track:#eaeef2;--accent:#0969da}}
text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif}
.title{font-size:15px;font-weight:600;fill:var(--fg)}
.label{font-size:11px;fill:var(--muted);letter-spacing:.4px;text-transform:uppercase}
.value{font-size:24px;font-weight:600;fill:var(--fg)}
.lang{font-size:12px;fill:var(--fg)}
.pct{font-size:12px;fill:var(--muted)}
.sub{font-size:11px;fill:var(--muted)}
</style>"""


def fetch(login, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if "errors" in payload:
        raise SystemExit(f"GraphQL error: {payload['errors']}")
    u = payload["data"]["user"]
    c = u["contributionsCollection"]
    langs = {}
    stars = 0
    for repo in u["repositories"]["nodes"]:
        stars += repo["stargazerCount"]
        for e in repo["languages"]["edges"]:
            n = e["node"]
            d = langs.setdefault(n["name"], {"size": 0, "color": n["color"] or "#8b949e"})
            d["size"] += e["size"]
    return {
        "login": login,
        "commits": c["totalCommitContributions"],
        "prs": c["totalPullRequestContributions"],
        "issues": c["totalIssueContributions"],
        "reviews": c["totalPullRequestReviewContributions"],
        "stars": stars,
        "repos": u["repositories"]["totalCount"],
        "followers": u["followers"]["totalCount"],
        "langs": langs,
    }


def stats_svg(d):
    items = [
        ("Commits (12 mo)", d["commits"]),
        ("Pull requests", d["prs"]),
        ("Issues", d["issues"]),
        ("Stars earned", d["stars"]),
        ("Public repos", d["repos"]),
        ("Followers", d["followers"]),
    ]
    cells = []
    for i, (label, val) in enumerate(items):
        x = 28 + (i % 3) * 150
        y = 78 + (i // 3) * 62
        cells.append(
            f'<text class="value" x="{x}" y="{y}">{val:,}</text>'
            f'<text class="label" x="{x}" y="{y + 18}">{escape(label)}</text>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="495" height="215" viewBox="0 0 495 215" role="img" aria-label="GitHub activity summary">
{STYLE}
<rect x=".5" y=".5" width="494" height="214" rx="10" fill="var(--bg)" stroke="var(--border)"/>
<text class="title" x="28" y="36">GitHub Activity</text>
<text class="sub" x="467" y="36" text-anchor="end">@{escape(d['login'])}</text>
<line x1="28" y1="48" x2="467" y2="48" stroke="var(--border)"/>
{''.join(cells)}
</svg>"""


def langs_svg(d, top=6):
    total = sum(v["size"] for v in d["langs"].values()) or 1
    ranked = sorted(d["langs"].items(), key=lambda kv: kv[1]["size"], reverse=True)
    shown = ranked[:top]
    rest = sum(v["size"] for _, v in ranked[top:])
    rows = [(n, v["size"] / total * 100, v["color"]) for n, v in shown]
    if rest:
        rows.append(("Other", rest / total * 100, "#6e7681"))

    cx, cy, r, sw = 105, 128, 50, 20
    circ = 2 * math.pi * r
    arcs, offset = [], 0.0
    for _, pct, color in rows:
        seg = circ * pct / 100
        gap = 1.5 if len(rows) > 1 else 0
        arcs.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="{sw}" '
            f'stroke-dasharray="{max(seg - gap, 0.1):.2f} {circ:.2f}" stroke-dashoffset="{-offset:.2f}" '
            f'transform="rotate(-90 {cx} {cy})"/>'
        )
        offset += seg

    legend = []
    for i, (name, pct, color) in enumerate(rows):
        y = 74 + i * 22
        legend.append(
            f'<circle cx="215" cy="{y - 4}" r="4" fill="{color}"/>'
            f'<text class="lang" x="228" y="{y}">{escape(name)}</text>'
            f'<text class="pct" x="467" y="{y}" text-anchor="end">{pct:.1f}%</text>'
            f'<rect x="228" y="{y + 5}" width="239" height="3" rx="1.5" fill="var(--track)"/>'
            f'<rect x="228" y="{y + 5}" width="{max(239 * pct / 100, 2):.1f}" height="3" rx="1.5" fill="{color}"/>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="495" height="215" viewBox="0 0 495 215" role="img" aria-label="Most used languages">
{STYLE}
<rect x=".5" y=".5" width="494" height="214" rx="10" fill="var(--bg)" stroke="var(--border)"/>
<text class="title" x="28" y="36">Languages</text>
<text class="sub" x="467" y="36" text-anchor="end">by code size</text>
<line x1="28" y1="48" x2="467" y2="48" stroke="var(--border)"/>
<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="var(--track)" stroke-width="{sw}"/>
{''.join(arcs)}
{''.join(legend)}
</svg>"""


DEMO = {
    "login": "demo", "commits": 412, "prs": 18, "issues": 6, "reviews": 3,
    "stars": 27, "repos": 14, "followers": 31,
    "langs": {
        "JavaScript": {"size": 52000, "color": "#f1e05a"},
        "Python": {"size": 31000, "color": "#3572A5"},
        "Java": {"size": 22000, "color": "#b07219"},
        "CSS": {"size": 9000, "color": "#563d7c"},
        "HTML": {"size": 6000, "color": "#e34c26"},
        "TypeScript": {"size": 4000, "color": "#3178c6"},
        "Shell": {"size": 1500, "color": "#89e051"},
    },
}


def main():
    if "--demo" in sys.argv:
        data, out = DEMO, os.path.join("/tmp", "demo")
    else:
        if len(sys.argv) < 2 or not os.environ.get("GH_TOKEN"):
            raise SystemExit("usage: GH_TOKEN=... generate_stats.py <username>")
        data, out = fetch(sys.argv[1], os.environ["GH_TOKEN"]), OUT_DIR
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "stats.svg"), "w", encoding="utf-8") as f:
        f.write(stats_svg(data))
    with open(os.path.join(out, "languages.svg"), "w", encoding="utf-8") as f:
        f.write(langs_svg(data))
    print("written to", out)


if __name__ == "__main__":
    main()
