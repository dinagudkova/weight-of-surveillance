-- Within each dataset, all usable visits must have the same observation window, otherwise modes are not comparable.
select dataset, count(distinct window_ms) as window_lengths
from {{ ref('prep_visits') }}
where is_usable
group by dataset
having count(distinct window_ms) > 1
