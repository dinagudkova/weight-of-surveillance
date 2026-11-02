"""Print the headline numbers of the study from the DuckDB warehouse.

Usage:
  python scripts/results_numbers.py                 # data/warehouse/wos.duckdb
  python scripts/results_numbers.py --db other.duckdb

Every number in docs/results_numbers.md, the README results section, the dashboard captions and the
presentation should come from this output (run it after every `scripts/dbt.py build`). Read-only.
"""
import argparse
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent

SECTIONS = [
    ("Sample", """
        select
            (select count(*) from seeds.sites)                                    as sites_in_sample,
            (select count(*) from marts.mart_site_consent_effect)                 as sites_with_data,
            (select count(*) from marts.mart_site_consent_effect where has_banner) as sites_with_banner,
            (select count(*) from marts.mart_site_consent_effect where site_country <> 'DE') as sites_outside_de
    """),
    ("Sites outside Germany (by top-level domain)", """
        select site_domain, site_country, site_group_label, has_banner
        from marts.mart_site_consent_effect where site_country <> 'DE' order by 1
    """),
    ("Groups: sites, banner, consent effect (medians per site; accept/reject over sites with a banner)", """
        select group_label, sites, sites_with_banner, sites_outside_de,
               median_none_tracking_requests   as none_req,
               median_reject_tracking_requests as reject_req,
               median_accept_tracking_requests as accept_req,
               median_accept_tracking_companies as accept_companies,
               sites_accept_lower_bound        as accept_lower_bound
        from marts.mart_group_summary order by group_order
    """),
    ("Groups: freedom of choice", """
        select group_label, sites_with_banner, sites_pay_or_okay as paid_option, sites_no_free_reject as no_free_reject
        from marts.mart_group_summary order by group_order
    """),
    ("Reject options (sites with a banner)", """
        select reject_option, count(*) as sites,
               count(*) filter (where site_group_label = 'Media') as media_sites
        from marts.mart_site_consent_effect where has_banner group by 1 order by 2 desc
    """),
    ("Share of tracking in page weight after Accept (pre + window; lower-bound visits excluded)", """
        select site_group_label, count(accept_tracking_share_bytes) as sites,
               round(median(accept_tracking_share_bytes), 3) as median_share
        from marts.mart_site_consent_effect where has_banner
        group by 1 order by min(site_group_order)
    """),
    ("Consent platforms (sites with a banner, one platform per site)", """
        select cmp, sites, sites_pay_or_okay as paid_option
        from marts.mart_cmp_market order by sites desc limit 12
    """),
    ("Consent platforms: total", """
        select sum(sites) as sites, sum(sites_pay_or_okay) as paid_option, count(*) as platforms
        from marts.mart_cmp_market
    """),
    ("First tracker after Accept (usable visits on sites with a banner, no lower bounds)", """
        select site_group_label, count(*) as visits,
               median(ms_to_first_tracking) as ms_first_tracking,
               median(companies_1s) as companies_1s, median(companies_5s) as companies_5s,
               median(companies_30s) as companies_30s
        from marts.mart_first_tracker where mode = 'accept'
        group by 1 order by min(site_group_order)
    """),
    ("Timeline, all sites: companies by the end of second 1-6, share of sites where tracking started", """
        select mode, second + 1 as by_end_of_second, visits, median_cum_companies,
               round(share_sites_tracking_started, 2) as share_started
        from marts.mart_consent_timeline
        where site_group_label = 'All sites' and second < 6 order by mode, second
    """),
    ("Companies: top 15 after Accept and after Reject (sites with a banner)", """
        select mode, rank_in_mode as rank, owner, sites, sites_measured, round(share_of_sites, 2) as share,
               tracking_types
        from marts.mart_company_sites
        where rank_in_mode <= 15 and mode in ('accept', 'reject') order by mode, rank_in_mode
    """),
    ("Promise vs reality (sites with an IAB TCF banner)", """
        select site_group_label,
               count(*) filter (where promised_vendors_total is not null)                          as tcf_sites,
               median(promised_vendors_total)                                                     as promised,
               median(observed_companies) filter (where promised_vendors_total is not null)       as seen,
               count(*) filter (where promised_vendors_total is not null and observed_is_lower_bound) as seen_lower_bound,
               count(*) filter (where asks_full_gvl)                                              as full_vendor_list
        from marts.mart_promise_vs_reality
        group by 1 order by min(site_group_order)
    """),
    ("Before any choice (mode none): sites with tracking / identity requests in the load phase", """
        select count(*) as sites,
               count(*) filter (where pre_tracking_requests > 0) as with_tracking,
               count(*) filter (where pre_identity_requests > 0) as with_identity_requests,
               count(*) filter (where tracker_cookies_before_choice > 0) as with_tracker_cookies
        from marts.mart_pre_consent
    """),
    ("After Reject: sites with identity requests in the window (sites with a banner)", """
        select count(*) filter (where reject_tracking_requests is not null) as sites_reject_measured,
               count(*) filter (where reject_identity_requests > 0)         as with_identity_requests
        from marts.mart_site_consent_effect where has_banner
    """),
    ("Sensitivity: Germany only vs all sites (median accept requests, sites with a banner)", """
        select site_group_label,
               median(accept_tracking_requests)                                     as all_sites,
               median(accept_tracking_requests) filter (where site_country = 'DE')  as de_only,
               median(accept_tracking_companies)                                    as all_companies,
               median(accept_tracking_companies) filter (where site_country = 'DE') as de_only_companies
        from marts.mart_site_consent_effect where has_banner
        group by 1 order by min(site_group_order)
    """),
]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=str(ROOT / "data" / "warehouse" / "wos.duckdb"))
    args = p.parse_args()
    con = duckdb.connect(args.db, read_only=True)
    for title, sql in SECTIONS:
        print(f"\n## {title}")
        con.sql(sql).show(max_rows=60, max_width=200)


if __name__ == "__main__":
    main()
