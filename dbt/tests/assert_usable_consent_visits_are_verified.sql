-- On sites with a banner, accept/reject visits only enter the analysis if the banner was verifiably closed.
select visit_id, site, mode
from {{ ref('prep_visits') }}
where is_usable and mode <> 'none' and site_has_banner and not coalesce(consent_verified, false)
  and not is_lower_bound  -- memory-aborted accept visits are deliberately kept as lower bounds
