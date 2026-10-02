# Brief: Breed-Aware Drug Safety Monitoring

*For animal-health product safety and commercial leaders. One page.*

## What we found

1. **Some drug risks only show up when you look by breed.** Across all dogs in FDA's adverse-event database, heartworm/parasite drugs in the ivermectin family show no excess of neurologic side effects. In herding breeds that often carry the MDR1 gene (Collies, Australian Shepherds, Shetland Sheepdogs), the rate is about 20% higher than for dogs overall. Our model found this known breed risk automatically, from the reports alone.

2. **Our method doesn't cry wolf.** When we scrambled the data so that no real breed patterns remained, the standard breed comparison still raised about 7 false alarms per 1,000 checks, which would be thousands of alerts across a full product portfolio. Our model raised zero.

3. **Speed and accuracy pull in opposite directions, and we can quantify it.** For the flea-and-tick products FDA warned about in 2018, a simple screening statistic showed the seizure pattern about four and a half years before the warning, but it also flags roughly 1 in 20 drug–reaction pairs by chance. The strict Bayesian score flagged nothing by chance, but it also missed this signal until after the warning.

4. **At the same review workload, the Bayesian score points reviewers to the right problems sooner.** If a safety reviewer works down a product's list of reported reactions, the Bayesian score put the isoxazoline seizure signal about 3–5 times higher on the list than the simple screen did, two years before FDA's warning. For the MDR1 breed risk, it ranked the signal in the top 30 of up to 100,000 breed checks every quarter from 2013 to 2019; the standard comparison ranked it between 235th and 1,545th.

5. **Cats show the same pattern.** For a cat flea-and-tick product approved in 2018, seizures were at or near the top of its reaction list under every method as soon as enough reports came in.

## What it means for you

| If you are… | Use it to… |
|---|---|
| A manufacturer's safety team | Monitor your products by breed, and only escalate breed alerts that survive a near-zero false-alarm rate |
| A product or label team | Find breed groups that need specific label language or dosing guidance |
| A competitor-intelligence or commercial team | Track the safety profile of competing products by breed and reaction |
| A pet insurer | Add breed-specific drug risk to underwriting and care-management rules |

## What we recommend

- **Run two tiers:** a sensitive screen to queue cases for review, and the breed-aware Bayesian score to decide which cases get escalated.
- **Add partner clinic data next.** FDA reports have no count of how many dogs got each drug, so they can't give true risk rates. Linked clinic records (TailSignal's core platform) supply that missing count.

## How sure are we

- The breed result rests on about 31,000 reports from MDR1-prone breeds and was planned in advance.
- Breed comes from the report, not a DNA test, and many reports have no breed.
- Spontaneous reports go up after publicity, so report counts are not the same as risk in the dog population.
