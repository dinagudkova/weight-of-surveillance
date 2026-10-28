"""Visual review of problem visits: unverified consent clicks and memory aborts.

Usage: python scripts/review_consent.py data/raw/study_merged
Writes <folder>/review_consent.html (open it in a browser) and prints a short summary.

For every listed visit it shows the screenshots before the click, right after the click and at the end
of the window, so you can decide quickly whether the click really failed or only the check was wrong.
"""
import html
import sys
from pathlib import Path

import pandas as pd

if len(sys.argv) < 2:
    sys.exit("Usage: python scripts/review_consent.py <folder>")
out = Path(sys.argv[1])
vis = pd.read_json(out / "visits.jsonl", lines=True)
key = ["site", "mode", "rep"]
for col in ["memoryAbort", "botBlocked", "navError", "consentVerified", "consentMethod", "payOrOkay", "bannerPre",
            "cmp", "fallbackLabel", "requests", "requestsDropped"]:
    if col not in vis:
        vis[col] = None
vis = vis.sort_values("date").drop_duplicates(key, keep="last")
vis["memoryAbort"] = vis["memoryAbort"].fillna(False).astype(bool)

mem = vis[vis.memoryAbort]
print(f"Memory aborts: {len(mem)} visits on {mem.site.nunique()} sites")
print(mem.groupby("mode").size().to_string())

measured = vis[vis.navError.isna() & ~vis.botBlocked.fillna(False).astype(bool) & ~vis.memoryAbort]
banner_sites = set(measured[measured.bannerPre.fillna(False).astype(bool) | measured.cmp.notna()].site)
bad = measured[(measured["mode"] != "none") & measured.site.isin(banner_sites) & (measured.consentVerified != True)]  # noqa: E712
print(f"\nUnverified consent clicks: {len(bad)} visits")
print(bad.groupby(["mode", bad.payOrOkay.fillna(False).astype(bool)]).size().rename("visits").to_string())


def num(x):
    """Integer for display; older visits have no requestsDropped field (NaN)."""
    return int(x) if pd.notna(x) else 0


def shots(r):
    host = r.site.split("//")[1].split("/")[0]
    cells = []
    for tag, label in [("1pre", "before click"), ("2consent", "after click"), ("3end", "end of window")]:
        name = f"{host}_{r['mode']}_{r.rep}_{tag}.jpg"
        if (out / "screens" / name).exists():
            cells.append(f'<figure><a href="screens/{name}" target="_blank"><img src="screens/{name}" loading="lazy"></a><figcaption>{label}</figcaption></figure>')
        else:
            cells.append(f"<figure><div class=missing>no screenshot</div><figcaption>{label}</figcaption></figure>")
    return "".join(cells)


def section(title, df):
    rows = []
    for _, r in df.sort_values(["mode", "site"]).iterrows():
        meta = (f"cmp: {html.escape(str(r.cmp))} · method: {html.escape(str(r.consentMethod))} · "
                f"label: {html.escape(str(r.fallbackLabel))} · pay-or-okay: {bool(r.payOrOkay)} · "
                f"requests: {num(r.requests)} (+{num(r.requestsDropped)} dropped)")
        rows.append(f'<section><h3>{html.escape(r.site)} — {r["mode"]}</h3><p>{meta}</p><div class=row>{shots(r)}</div></section>')
    return f"<h2>{title} ({len(df)})</h2>" + "".join(rows)


page = f"""<!doctype html><meta charset=utf-8><title>Consent review</title>
<style>body{{font-family:system-ui,sans-serif;margin:24px;color:#1d2329}}h3{{margin:24px 0 4px}}p{{margin:0 0 8px;color:#4a535c;font-size:13px}}
.row{{display:flex;gap:8px;flex-wrap:wrap}}figure{{margin:0;width:320px}}img{{width:320px;border:1px solid #ccc}}
figcaption{{font-size:12px;color:#4a535c}}.missing{{width:320px;height:200px;background:#eee;display:flex;align-items:center;justify-content:center}}</style>
<h1>Consent review: {html.escape(str(out))}</h1>
<p>For each unverified click: if the banner is gone after the click, the check was wrong (false negative); if it is still there, the click failed.</p>
{section("Unverified Accept", bad[bad["mode"] == "accept"])}
{section("Unverified Reject", bad[bad["mode"] == "reject"])}
{section("Memory aborts", mem)}
"""
(out / "review_consent.html").write_text(page, encoding="utf-8")
print(f"\nWritten: {out / 'review_consent.html'}")
