select membership_id, cast(campaign_date as date) as campaign_date, arm
from read_csv('{{ var("raw_dir") }}/wellplan_campaign.csv', header = true, all_varchar = true)
