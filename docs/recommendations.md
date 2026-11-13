# Recommendations (draft)

Draft for stand-up 3. Every number comes from [results_numbers.md](results_numbers.md); medians are over sites
with a consent banner. The data shows **indicators, not legal findings**: whether a given request is allowed
(consent, "legitimate interest", consent-free measurement) is for lawyers and data protection authorities to decide.

Tracking also pays for free content, and a paid, tracking-free subscription ("pay or okay") is a business model
that some regulators accept. The recommendations below aim at a choice that is real and visible, not at removing
advertising.

## For publishers and site owners (primary users)

**1. Test the reject, not only the banner.** After a working "Reject all", 57% of sites still send at least one
tracking request within 30 seconds, against 32% when the user does nothing (McNemar, p < 0.001). Consent pings
and code loads do not explain the gap; most of it is ad delivery declared as non-personalised.
*Action:* after each change to the banner or the tag manager, run one Reject visit, list the third parties that
receive requests and document why each one is allowed.

**2. Check what loads before the choice.** 195 of 446 sites with a banner send advertising requests while the page
loads, and 93 set a tracker cookie before any click. On 6 sites Google Consent Mode reported "ad_storage granted"
before any click (bwin.de confirmed by hand).
*Action:* fire marketing tags only after consent, with Consent Mode defaults set to "denied".

**3. Ask consent only for partners you actually use.** On TCF sites the banner lists far more vendors than the
browser sees after "Accept all": media 210 promised vs 101 seen, shopping 102 vs 12, services 221 vs 36 (medians).
7 sites ask consent for the entire IAB list of 900+ vendors.
*Action:* trim the vendor list to the partners in use; a shorter list is also easier for users to understand.

**4. If the banner offers a subscription, keep the free choice findable.** 148 banners offer a paid option. On every
one of them the free reject is below the first layer (66) or the crawler found none (82). Pre-ticked categories
turn "Save" into consent (novoline.de, checked by hand).
*Action:* say on the first layer where the free option is; no pre-ticked optional categories.

**5. Benchmark against your group.** Median tracking requests after Accept: media 1,069–1,347, services 91,
shopping 81, gambling 37, finance & health 28, public sector 0.5. The dashboard's "Check a site" view puts one
site next to its group.

## For data protection authorities and consumer organisations (decision makers)

**1. Start with media sites.** They carry the heaviest load after Accept (median 1,069–1,347 tracking requests to
100–114 companies, first tracking request 68 ms after the click), 113 of the 148 paid options and 65 of the 82
banners where no free reject was found.

**2. Look at the few places that shape many sites.** Two consent platforms run most of the subscription banners
(Sourcepoint on 78 sites with a paid option, consentmanager on 38), and one publisher network (Ippen, opencmp)
syncs IDs before a choice. Reviewing a platform's default setup or a network's configuration reaches dozens of
sites at once.

**3. Clarify what may happen after a reject.** On more than half of the sites with a working reject, ad-tech
companies receive requests within 30 seconds, mostly for ads labelled non-personalised or "legitimate interest".
On nzz.ch the identity providers ID5 and Lotame were also contacted after "Reject all" (checked by hand). Guidance
on what non-personalised ad delivery may include would make such cases easier to judge.

**4. Use automated crawls for screening, manual checks for evidence.** Of 10 flagged Reject visits, 5 were
confirmed by hand and 3 partly; of 4 "granted" Consent Mode signals, 1 was confirmed. A crawl finds the candidates;
a manual check is needed before any conclusion about a single site.

## For internet users (beneficiaries)

**1. Rejecting makes a large difference.** Median tracking requests in 30 seconds: 138 after Accept, 2 after
Reject; Accept is higher than Reject on 90% of sites. Reject does not mean zero contact with ad tech, but it removes
most of it.

**2. Look past the first layer.** When the banner offers only "Accept" or a subscription, a free reject is
sometimes in the settings (66 sites). Check that optional categories are not switched on in advance.

**3. Ignoring the banner is not the same as rejecting.** While the banner stays unanswered, little happens after
the page has loaded (median 0 requests), but what loads with the page already reaches third parties: 406 of 503
sites send at least one tracking request during page load.

## Limits of these recommendations

Home pages only, without login; one visit per site and consent state; Accept counts on the heaviest media sites are
lower bounds; Reject results cover only sites where a free reject worked (media: 81 of 165). The data does not show
what happens to the data on the servers or how much consent earns publishers.

## Open for the final version

- Publisher revenue side: no data in this project; name it as the natural follow-up.
- Dedicated ID-sync mart, to back recommendation 2 for regulators with a count instead of hand-checked examples.
- Review the wording with the dashboard captions so both use the same numbers.
