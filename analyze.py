"""Pilot analysis v2 for "The Weight of Surveillance".

Usage: python analyze.py results
Writes results/pilot_report.md, results/summary_by_visit.csv, results/review_domains.csv

Main metrics use only requests that START inside the fixed observation window after t0
(t0 = consent click for accept/reject, end of settling for none), so all modes are observed equally long.
"""
import sys
from pathlib import Path

import pandas as pd

out = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
req = pd.read_json(out / "requests.jsonl", lines=True)
vis = pd.read_json(out / "visits.jsonl", lines=True)
key = ["site", "mode", "rep"]
L = []  # report lines


def md(df, **kw):
    return df.to_markdown(**kw) if len(df) else "_none_"


def pct(x):
    return f"{x:.0%}" if pd.notna(x) else "n/a"


# Keep the latest visit per (site, mode, rep); crashes have no requests column.
for col in ["memoryAbort", "botBlocked", "navError", "consentVerified", "consentMethod", "payOrOkay", "bannerPre", "cmp", "requests"]:
    if col not in vis:
        vis[col] = None
vis = vis.sort_values("date").drop_duplicates(key, keep="last").reset_index(drop=True)
vis["botBlocked"] = vis["botBlocked"].fillna(False).astype(bool)
vis["memoryAbort"] = vis["memoryAbort"].fillna(False).astype(bool)
valid = vis[vis.navError.isna() & ~vis.botBlocked & ~vis.memoryAbort & (vis.requests.fillna(0) > 1)].copy()
req = req[req.visitId.isin(valid.visitId)]
if "trackingType" not in req:
    req["trackingType"] = None
win = req[req.phase == "window"]
sites = vis.site.unique()

# ---------------------------------------------------------------- 1. coverage
L += ["# Pilot report", "", "## 1. Which sites could be measured", ""]
blocked = vis[vis.botBlocked].site.unique()
errors = vis[vis.navError.notna()][["site", "mode", "navError"]]
empty = vis[vis.navError.isna() & ~vis.botBlocked & ~vis.memoryAbort & (vis.requests.fillna(0) <= 1)].site.unique()
L += [f"- Sites in list: **{len(sites)}**, measured in all three modes: **{(valid.groupby('site')['mode'].nunique() == 3).sum()}**, repeats per site and mode: up to {int(vis.rep.max()) + 1}",
      f"- Bot protection page: **{len(blocked)}** {', '.join(blocked)}",
      f"- Empty page (≤1 request): {len(empty)} {', '.join(empty)}",
      f"- Aborted for memory (page with a request flood): {vis[vis.memoryAbort].site.nunique()} {', '.join(vis[vis.memoryAbort].site.unique())}",
      f"- Navigation errors: {len(errors)}",
      f"- Window length: {int(vis.windowMs.dropna().iloc[0] / 1000) if 'windowMs' in vis and vis.windowMs.notna().any() else '?'} s", ""]
if len(errors):
    L += [md(errors, index=False), ""]

# ---------------------------------------------------------------- 2. banners
L += ["## 2. Consent banners", ""]
per_site = valid.groupby("site").agg(
    banner=("bannerPre", lambda s: bool(s.fillna(False).any())),
    cmp=("cmp", lambda s: s.dropna().iloc[0] if s.notna().any() else None),
    payOrOkay=("payOrOkay", lambda s: bool(s.fillna(False).any())),
)
per_site["banner"] = per_site.banner | per_site.cmp.notna()
with_banner = per_site[per_site.banner].index
L += [f"Sites with a visible banner or detected CMP: **{len(with_banner)} of {per_site.shape[0]}** measured sites. "
      "The percentages below use these sites as the denominator.", ""]
rows = []
for mode in ["accept", "reject"]:
    m = valid[(valid["mode"] == mode) & valid.site.isin(with_banner)]
    if not len(m):
        continue
    rows.append({
        "mode": mode, "sites": m.site.nunique(), "visits": len(m),
        "clicked (claimed)": pct(m.consentMethod.notna().mean()),
        "banner closed (verified)": pct((m.consentVerified == True).mean()),  # noqa: E712
        "via autoconsent": pct(m.consentMethod.fillna("").str.startswith("autoconsent").mean()),
        "via text fallback": pct(m.consentMethod.fillna("").str.contains("text-fallback").mean()),
    })
L += [md(pd.DataFrame(rows), index=False), "",
      "_claimed_ = the crawler clicked something; _verified_ = a banner was visible before and is gone after the click.", ""]
fail = valid[(valid["mode"] != "none") & valid.site.isin(with_banner) & (valid.consentVerified != True)]  # noqa: E712
L += ["Visits where the banner was **not** verifiably closed (check screenshots):", "",
      md(fail[["site", "mode", "cmp", "consentMethod", "fallbackLabel", "consentVerified", "payOrOkay"]], index=False), ""]
poo = per_site[per_site.payOrOkay].index.tolist()
L += [f"Pay-or-okay banners (subscription instead of a first-layer reject): **{len(poo)}** {', '.join(poo)}", ""]

# ---------------------------------------------------------------- 3. data quality
L += ["## 3. Data quality", ""]
zero = (req.bytes == 0) & ~req.failed
L += [f"- Requests with size 0 (excluding failed): {zero.mean():.1%}"]
trk = win[win.isTracking]
for col in ["viaTds", "viaEasyPrivacy", "viaEasyList", "viaCname"]:
    L.append(f"- tracking requests matched {col}: {trk[col].mean():.1%}" if len(trk) else f"- {col}: n/a")
cat_bytes = win.groupby("category").bytes.sum()
L += ["", "Bytes in the window by category (all visits):", "",
      md((cat_bytes / cat_bytes.sum()).round(3).rename("share").to_frame()), ""]
review = (win[win.category == "other"].groupby("regDomain")
          .agg(bytes=("bytes", "sum"), requests=("url", "size"), sites=("site", "nunique"),
               example=("url", "first")).sort_values("bytes", ascending=False).head(40))
review.to_csv(out / "review_domains.csv")
L += ["Top third-party domains classified as _other_ (not tracking). Review these; add trackers to "
      "`lists/custom_trackers.csv` and same-owner domains to `lists/site_aliases.csv` (full list: review_domains.csv):", "",
      md(review.drop(columns="example").head(15)), ""]

# ---------------------------------------------------------------- 4. per-visit summary
# Per-visit window metrics (column arithmetic + groupby, robust also when there are no window requests)
w = win.assign(
    trk_bytes=win.bytes.where(win.isTracking, 0),
    consent_bytes=win.bytes.where(win.isConsent.astype(bool), 0),
    trk_owner=win.owner.where(win.isTracking),
)
s = (w.groupby("visitId")
     .agg(win_requests=("url", "size"), win_bytes=("bytes", "sum"), trk_requests=("isTracking", "sum"),
          trk_bytes=("trk_bytes", "sum"), consent_bytes=("consent_bytes", "sum"), trk_companies=("trk_owner", "nunique"))
     .reset_index())
summary = valid.merge(s, on="visitId", how="left").fillna({"win_requests": 0, "win_bytes": 0, "trk_requests": 0, "trk_bytes": 0, "consent_bytes": 0, "trk_companies": 0})
summary["trk_share_bytes"] = (summary.trk_bytes / summary.win_bytes.where(summary.win_bytes > 0)).round(3)
summary["cookies_tracker_pre"] = summary.cookiesPre.apply(lambda c: c.get("tracker") if isinstance(c, dict) else None)
summary["cookies_tracker_end"] = summary.cookiesEnd.apply(lambda c: c.get("tracker") if isinstance(c, dict) else None)
summary.drop(columns=["cookiesPre", "cookiesEnd", "acErrors", "bannerText"], errors="ignore").to_csv(out / "summary_by_visit.csv", index=False)

# ---------------------------------------------------------------- 5. results
L += ["## 4. Tracking weight in the observation window", "",
      "Accept/reject values only count if the banner was verifiably closed (otherwise the cell is empty).", ""]
use = summary[(summary["mode"] == "none") | (summary.consentVerified == True) | ~summary.site.isin(with_banner)]  # noqa: E712
pv = use.pivot_table(index="site", columns="mode", values=["trk_requests", "trk_bytes"], aggfunc="median")
tab = pd.DataFrame(index=pv.index)
for mode in ["none", "accept", "reject"]:
    if ("trk_requests", mode) in pv:
        tab[f"{mode} req"] = pv[("trk_requests", mode)]
        tab[f"{mode} KB"] = (pv[("trk_bytes", mode)] / 1024).round(0)
if {"none req", "accept req"} <= set(tab):
    tab["accept/none"] = (tab["accept req"] / tab["none req"].where(tab["none req"] > 0)).round(1)
L += [md(tab), ""]
L += ["Median across sites:", "",
      md(use.groupby("mode")[["trk_requests", "trk_bytes", "trk_share_bytes", "trk_companies", "consent_bytes", "scriptMs"]].median().round(3)), "",
      "_scriptMs_ = main-thread script time over the whole visit (not only the window)._", ""]
bytype = (win[win.isTracking].merge(use[["visitId"]], on="visitId")
          .groupby(["mode", "trackingType"]).agg(requests=("url", "size"), KB=("bytes", lambda b: round(b.sum() / 1024)),
                                                 sites=("site", "nunique")).reset_index())
L += ["Tracking by type in the window (all measured sites together):", "", md(bytype, index=False), "",
      "_advertising_ = ad requests and ad pixels; _analytics_ = analytics and audience measurement; "
      "_identity_ = ID syncing, cookie matching, telco identifiers. Telemetry (error/performance monitoring, "
      "A/B testing) is not counted as tracking.", ""]
if "accept/none" in tab:
    both = tab[["none req", "accept req"]].dropna()
    tenx = (both["accept req"] >= 10 * both["none req"].clip(lower=1)).sum()
    zero_to_some = ((both["none req"] == 0) & (both["accept req"] > 0)).sum()
    L += [f"Sites where accepting raises tracking requests at least tenfold: **{tenx} of {len(both)}** "
          f"(plus {zero_to_some} sites going from zero to some tracking)", ""]

# ---------------------------------------------------------------- 5b. variation between repeats
if vis.rep.max() > 0:
    rv = use.groupby(["site", "mode"]).agg(n=("trk_requests", "size"), med=("trk_requests", "median"),
                                           lo=("trk_requests", "min"), hi=("trk_requests", "max"),
                                           kb_med=("trk_bytes", lambda b: b.median() / 1024),
                                           kb_lo=("trk_bytes", lambda b: b.min() / 1024), kb_hi=("trk_bytes", lambda b: b.max() / 1024))
    rv = rv[(rv.n >= 2) & (rv.med >= 20)].copy()
    rv["spread_req"] = ((rv.hi - rv.lo) / rv.med).round(2)
    rv["spread_kb"] = ((rv.kb_hi - rv.kb_lo) / rv.kb_med).round(2)
    L += ["## 4b. Variation between repeats", "",
          "Relative spread = (max − min) / median across repeats, for site/mode pairs with ≥2 valid repeats and ≥20 tracking requests.", "",
          f"Pairs: **{len(rv)}**, median spread: **{rv.spread_req.median():.0%}** of requests, **{rv.spread_kb.median():.0%}** of bytes; "
          f"max: {rv.spread_req.max():.0%} / {rv.spread_kb.max():.0%}", "",
          md(rv.round(0).drop(columns=["spread_req", "spread_kb"]).join(rv[["spread_req", "spread_kb"]])), ""]

# ---------------------------------------------------------------- 6. before consent, after reject
L += ["## 5. Tracking without consent", ""]
none = summary[summary["mode"] == "none"]
pre_all = req[(req["mode"] == "none") & (req.phase == "pre")]
pre_req = pre_all[pre_all.isTracking]
pre_by_site = pre_req.groupby("site").agg(
    requests=("url", "size"),
    third_party=("thirdParty", "sum"),
    advertising=("trackingType", lambda t: (t == "advertising").sum()),
    analytics=("trackingType", lambda t: (t == "analytics").sum()),
    identity=("trackingType", lambda t: (t == "identity").sum()),
    companies=("owner", lambda o: ", ".join(sorted(set(map(str, o)))[:5])))
tele = pre_all[pre_all.category == "telemetry"].site.nunique()
L += [f"Sites with tracking requests **before any interaction** (none mode, load + settle phase): "
      f"**{pre_by_site.shape[0]} of {len(none)}**. Requests alone are not proof of a violation "
      "(e.g. tag managers, consent-mode pings); tracker cookies below are the stricter signal.", "",
      md(pre_by_site.sort_values("requests", ascending=False)), "",
      f"Separately, {tele} sites send telemetry (error/performance monitoring, A/B testing) before consent.", ""]
pre_trk = none[none.cookies_tracker_pre.fillna(0) > 0]
L += [f"Sites with tracker cookies **before any interaction** (none mode, PRE snapshot): **{len(pre_trk)} of {len(none)}**", ""]
if len(pre_trk):
    L += [md(pre_trk.assign(owners=pre_trk.cookiesPre.apply(lambda c: ", ".join(c.get("trackerOwners", [])[:6])))
             [["site", "cookies_tracker_pre", "owners"]], index=False), ""]
if {"none", "reject"} <= set(use["mode"]):
    rr = use.pivot_table(index="site", columns="mode", values=["trk_requests", "cookies_tracker_end"], aggfunc="median")
    cmp_ = pd.DataFrame({"none req": rr[("trk_requests", "none")], "reject req": rr[("trk_requests", "reject")],
                         "none tracker cookies": rr[("cookies_tracker_end", "none")],
                         "reject tracker cookies": rr[("cookies_tracker_end", "reject")]}).dropna(subset=["reject req"])
    more = cmp_[cmp_["reject req"] > cmp_["none req"]]
    rej = win[win.isTracking & (win["mode"] == "reject")].merge(use[use["mode"] == "reject"][["visitId"]], on="visitId")
    rej_t = rej.groupby("site").agg(advertising=("trackingType", lambda t: (t == "advertising").sum()),
                                    analytics=("trackingType", lambda t: (t == "analytics").sum()),
                                    identity=("trackingType", lambda t: (t == "identity").sum()),
                                    companies=("owner", lambda o: ", ".join(sorted(set(map(str, o)))[:6])))
    L += ["Tracking **after verified reject**, by type (identity and analytics are the stronger signals; "
          "advertising after reject can be legitimate non-personalised ads):", "", md(rej_t.sort_values("identity", ascending=False)), ""]
    L += [f"Sites where verified **reject** leads to more tracking requests than no interaction: "
          f"**{len(more)} of {len(cmp_)}** (strictly more; single run, so small differences are noise)", "",
          md(more), ""]

top = trk[trk["mode"] == "accept"].groupby("owner").agg(KB=("bytes", lambda b: round(b.sum() / 1024)), sites=("site", "nunique")).sort_values("KB", ascending=False).head(12)
L += ["Top tracking companies after accept (window):", "", md(top), ""]

rt = (win[win.isTracking].groupby(["regDomain", "owner", "trackingType"])
      .agg(bytes=("bytes", "sum"), requests=("url", "size"), sites=("site", "nunique"),
           viaTds=("viaTds", "mean"), viaEasyPrivacy=("viaEasyPrivacy", "mean"), viaEasyList=("viaEasyList", "mean"),
           example=("url", "first")).sort_values("bytes", ascending=False).head(60))
rt.round(2).to_csv(out / "review_tracking.csv")
L += ["Also review `review_tracking.csv`: the top domains classified as tracking, to catch false positives.", ""]

(out / "pilot_report.md").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
