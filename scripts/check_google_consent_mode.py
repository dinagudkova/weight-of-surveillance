"""Google requests before any choice or after Reject: Consent Mode pings or real tracking?

Usage:
  python scripts/check_google_consent_mode.py                              # page load before any choice
  python scripts/check_google_consent_mode.py --mode reject --phase window # 30 s after a verified Reject
  python scripts/check_google_consent_mode.py --db other.duckdb --sites 40

The last section is always printed: any tracking in the 30-second window, no choice vs Reject, on the same sites,
raw and after removing (B) Google Consent Mode pings that report everything denied (gcs=G100) and (C) also all
code loads (scripts, stylesheets, fonts of any tracker, Google service requests). It tests whether "tracking is
more common after Reject than without a choice" survives once consent-update pings and code loads are set aside.

Looks at requests to Google (owner 'Google LLC') in the chosen mode and phase (default: page load in mode "none",
phase 'pre'; usable visits of the main dataset) on sites with a consent banner, and reads the consent signal each request carries in its URL:

  gcs=G1xy        Google Consent Mode: x = ad_storage, y = analytics_storage (1 granted, 0 denied).
                  G100 = everything denied, i.e. a cookieless ping, which Consent Mode sends by design.
  gdpr_consent=   IAB TCF consent string. An empty string means "no consent yet". A non-empty string before any
                  choice is not consent by itself (a CMP can issue a string with no consents), so it is reported
                  separately for manual checks.
  npa=1           non-personalised ads requested.

Requests are split into "code" and "hits". Code: scripts, stylesheets, fonts, and service requests that load
code or configuration or run Google's ad-fraud checks without sending page data (SERVICE_PATTERN below:
/pagead/managed, /pagead/js, purl_config, sodar, adtrafficquality, generate_204, Maps API, ...). Hits:
everything else (analytics collect, conversion and Floodlight pixels, cookie matching, remarketing lists, ad
requests). URLs are stored cut at 500 characters, so a missing parameter on a 500-character URL is reported as
"truncated".

Not covered: Google tags routed through the site's own domain (server-side tagging, e.g. www.bwin.de/dlr/g/collect)
are not owned by 'Google LLC' in the classification and do not appear here.

Read-only. Indicators for manual checks, not proof of a violation.
"""
import argparse
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent

# Requests to Google that load code or configuration, or run ad-fraud checks, rather than send page data.
SERVICE_PATTERN = (
    r"^https?://[^/]*(adtrafficquality\.google|maps\.googleapis\.com|maps\.gstatic\.com|fonts\.(googleapis|gstatic)\.com"
    r"|storage\.googleapis\.com)/"
    r"|/pagead/(managed|js|purl_config|ppub_config|show_ads|expansion_embed|osd)"
    r"|/(getconfig|sodar)|/sodar|/generate_204|/gpt/|dfp\.min\.js|/gtag/js|/gtm\.js|/recaptcha/"
)

BASE = """
with v as (
    select visit_id, site_group_label, site_group_order
    from marts.fct_visits
    where dataset = '{dataset}' and mode = '{mode}' and is_usable and site_has_banner
),
r as (
    select
        p.site, p.site_domain, p.resource_type in ('script', 'stylesheet', 'font') as resource_type_is_script, v.site_group_label, v.site_group_order, p.tracking_type, p.host, p.url,
        case when p.resource_type in ('script', 'stylesheet', 'font')
               or regexp_matches(p.url, '{service}') then 'code' else 'hit' end as kind,
        regexp_extract(p.url, '[?&]gcs=(G1[0-9]{{2}})', 1)                  as gcs,
        regexp_matches(p.url, '[?&]gdpr_consent=')                          as has_tcf_param,
        regexp_extract(p.url, '[?&]gdpr_consent=([^&]*)', 1)                as tcf_string,
        regexp_matches(p.url, '[?&]npa=1(&|$)')                             as npa,
        length(p.url) >= 500                                                as truncated
    from prep.prep_requests_classified p
    join v on v.visit_id = p.visit_id
    where p.phase = '{phase}' and p.is_tracking and p.owner = 'Google LLC'
),
s as (
    select *,
        case
            when gcs <> '' and substr(gcs, 3, 1) = '1' then 'gcs: ad_storage granted'
            when gcs <> '' and substr(gcs, 4, 1) = '1' then 'gcs: ads denied, analytics granted'
            when gcs <> ''                             then 'gcs: all denied (cookieless ping)'
            when has_tcf_param and tcf_string = ''     then 'TCF: empty consent string'
            when has_tcf_param                         then 'TCF: consent string present'
            when npa                                   then 'npa=1 (non-personalised)'
            when truncated                             then 'no signal (URL truncated)'
            else 'no signal'
        end as signal
    from r
)
"""

SECTIONS = [
    ("Google requests ({when}), sites with a banner: by type, kind and consent signal", """
        select tracking_type, kind, signal, count(distinct site) as sites, count(*) as requests
        from s group by 1, 2, 3 order by 1, 2, 4 desc
    """),
    ("Per site: the strongest signal among its Google hits ({when})", """
        , per_site as (
            select site,
                   bool_or(signal = 'gcs: ad_storage granted')               as ads_granted,
                   bool_or(signal = 'gcs: ads denied, analytics granted')    as analytics_granted,
                   bool_or(signal in ('no signal', 'TCF: consent string present')) as unclear,
                   bool_or(signal = 'no signal (URL truncated)')             as truncated,
                   bool_or(tracking_type = 'advertising')                    as any_ad_hit
            from s where kind = 'hit' group by site
        )
        select
            case
                when ads_granted       then '1 ad_storage granted'
                when analytics_granted then '2 analytics granted (ads denied)'
                when unclear           then '3 hits without a denied signal (check by hand)'
                when truncated         then '4 signal unknown: URL cut before the parameter'
                else                        '5 only denied / empty / non-personalised signals'
            end as site_class,
            count(*) as sites,
            count(*) filter (where any_ad_hit) as with_ad_hits
        from per_site group by 1 order by 1
    """),
    ("Sites with Google hits that carry a granted signal or no denied signal, for manual checks", """
        select site_domain, site_group_label,
               count(*) filter (where signal = 'gcs: ad_storage granted')            as ads_granted,
               count(*) filter (where signal = 'gcs: ads denied, analytics granted') as analytics_granted,
               count(*) filter (where signal = 'no signal')                          as no_signal,
               count(*) filter (where signal = 'TCF: consent string present')        as tcf_string,
               string_agg(distinct host, ' ')                                        as hosts
        from s
        where kind = 'hit' and signal in ('gcs: ad_storage granted', 'gcs: ads denied, analytics granted',
                                          'no signal', 'TCF: consent string present')
        group by 1, 2
        order by ads_granted desc, analytics_granted desc, no_signal desc
        limit {limit}
    """),
    ("Google hits without any consent signal: host and path", """
        select host, regexp_extract(url, '^https?://[^/]+(/[^/?;]*(/[^/?;]*)?)', 1) as path, tracking_type,
               count(distinct site) as sites, count(*) as requests
        from s where kind = 'hit' and signal = 'no signal'
        group by 1, 2, 3 order by 4 desc limit 25
    """),
    ("Code and service requests (not counted as hits)", """
        select host, regexp_extract(url, '^https?://[^/]+(/[^/?;]*(/[^/?;]*)?)', 1) as path,
               count(distinct site) as sites, count(*) as requests
        from s where kind = 'code' and resource_type_is_script = false
        group by 1, 2 order by 3 desc limit 15
    """),
]

WINDOW_COMPARISON = """
with v as (
    select visit_id, site, mode
    from marts.fct_visits
    where dataset = '{dataset}' and is_usable and site_has_banner and mode in ('none', 'reject')
),
both_modes as (select site from v group by site having count(distinct mode) = 2),
r as (
    select p.site, p.mode, p.owner, p.tracking_type,
           p.owner = 'Google LLC' and regexp_extract(p.url, '[?&]gcs=(G1[0-9]{{2}})', 1) = 'G100' as google_denied,
           p.resource_type in ('script', 'stylesheet', 'font')
               or (p.owner = 'Google LLC' and regexp_matches(p.url, '{service}'))             as code
    from prep.prep_requests_classified p
    join v on v.visit_id = p.visit_id
    where p.phase = 'window' and p.is_tracking and p.site in (select site from both_modes)
),
per_site as (
    select b.site, m.mode,
           coalesce(bool_or(r.site is not null), false)                    as a_raw,
           coalesce(bool_or(not r.google_denied), false)                   as b_no_g100,
           coalesce(bool_or(not r.google_denied and not r.code), false)    as c_no_code
    from both_modes b
    cross join (select unnest(['none', 'reject']) as mode) m
    left join r on r.site = b.site and r.mode = m.mode
    group by 1, 2
),
wide as (
    select site,
           bool_or(mode = 'none'   and a_raw)     as a_none, bool_or(mode = 'reject' and a_raw)     as a_reject,
           bool_or(mode = 'none'   and b_no_g100) as b_none, bool_or(mode = 'reject' and b_no_g100) as b_reject,
           bool_or(mode = 'none'   and c_no_code) as c_none, bool_or(mode = 'reject' and c_no_code) as c_reject
    from per_site group by site
)
"""

WINDOW_SUMMARY = """
select tier, count(*) as sites,
       round(avg(case when no_choice then 1.0 else 0 end), 2) as share_no_choice,
       round(avg(case when after_reject then 1.0 else 0 end), 2) as share_after_reject,
       count(*) filter (where after_reject and not no_choice) as only_after_reject,
       count(*) filter (where no_choice and not after_reject) as only_without_choice
from (
    select 'A raw' as tier, a_none as no_choice, a_reject as after_reject from wide
    union all select 'B without Google G100 pings', b_none, b_reject from wide
    union all select 'C also without code loads', c_none, c_reject from wide
) t
group by tier order by tier
"""

WINDOW_ONLY_REJECT = """
, only_reject as (select site from wide where c_reject and not c_none)
select r.owner, r.tracking_type, count(distinct r.site) as sites, count(*) as requests
from r join only_reject o on o.site = r.site
where r.mode = 'reject' and not r.google_denied and not r.code
group by 1, 2 order by 3 desc limit 20
"""


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=str(ROOT / "data" / "warehouse" / "wos.duckdb"))
    p.add_argument("--dataset", default="real")
    p.add_argument("--sites", type=int, default=40, help="rows in the manual-check list")
    p.add_argument("--mode", choices=["none", "reject", "accept"], default="none")
    p.add_argument("--phase", choices=["pre", "window"], default="pre")
    args = p.parse_args()
    con = duckdb.connect(args.db, read_only=True)
    service = SERVICE_PATTERN.replace("'", "''")
    base = BASE.format(dataset=args.dataset, service=service, mode=args.mode, phase=args.phase)
    when = {("none", "pre"): "before any choice, page load", ("reject", "window"): "30 s after Reject",
            ("none", "window"): "30 s window without a choice", ("accept", "window"): "30 s after Accept"}.get(
        (args.mode, args.phase), f"mode {args.mode}, phase {args.phase}")
    for title, sql in SECTIONS:
        title = title.format(when=when)
        print(f"\n## {title}")
        con.sql(base + sql.format(limit=args.sites)).show(max_rows=100, max_width=220)

    comp = WINDOW_COMPARISON.format(dataset=args.dataset, service=service)
    print("\n## Any tracking in the 30 s window, no choice vs Reject (same sites; A raw, B without Google "
          "G100 pings, C also without code loads)")
    con.sql(comp + WINDOW_SUMMARY).show(max_rows=20, max_width=220)
    print("\n## What remains (tier C) on sites with tracking only after Reject: companies and types")
    con.sql(comp + WINDOW_ONLY_REJECT).show(max_rows=30, max_width=220)


if __name__ == "__main__":
    main()
