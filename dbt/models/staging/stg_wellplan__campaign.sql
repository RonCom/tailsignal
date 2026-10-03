select membership_id, cast(campaign_date as date) as campaign_date, arm
from {{ raw_csv('wellplan_campaign.csv', 'wellplan_campaign') }}
