---
name: job-matching
description: Score and rank job postings against a candidate profile. Apply in-context when deciding which jobs to pursue.
---

# Job ↔ profile matching

## Rubric (score each posting 0–100)
Weight the signals below, then sum:

| Signal | Weight | How to score |
|---|---|---|
| Skills overlap | 40 | Fraction of the posting's required skills the candidate demonstrably has. |
| Seniority fit | 20 | Full points when the candidate's level matches; halve for one level off; zero for two+. |
| Years of experience | 15 | Full points at/above the stated minimum; scale down proportionally below it. |
| Location / remote fit | 15 | Full points if the location or remote policy matches a candidate location. |
| Domain / industry match | 10 | Full points when prior domains align with the posting's industry. |

## Procedure
1. Use the ChromaDB `match_jobs` semantic scores as a first-pass retrieval filter.
2. Apply the rubric above to each retrieved posting to produce an explainable 0–100 score.
3. Rank descending. For every posting, record a one-line justification citing the driving signals.
4. Never inflate a score for a signal the candidate does not actually satisfy.

## Output
Return `[{job_id, score, reasons}]`, highest score first.
