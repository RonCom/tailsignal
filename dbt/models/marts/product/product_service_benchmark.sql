-- Embedded Analytics / benchmarking feed: monthly utilization by market x channel,
-- plus each location's value so the partner portal can show "you vs. your market".
with m as (
    select date_trunc('month', event_date) as month, l.market, e.channel, e.location_id,
           count(*) as services, count(distinct e.pet_id) as active_pets, sum(e.amount) as revenue
    from {{ ref('fct_service_event') }} e join {{ ref('dim_location') }} l using (location_id)
    group by all
)
select month, market, channel, location_id, services, active_pets, round(revenue, 2) as revenue,
       round(revenue / nullif(active_pets, 0), 2) as revenue_per_active_pet,
       round(percent_rank() over (partition by month, market, channel order by revenue / nullif(active_pets, 0)), 3)
           as market_percentile_rev_per_pet,
       count(*) over (partition by month, market, channel) as locations_in_market
from m
