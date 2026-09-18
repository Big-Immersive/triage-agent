# Backfilling months of historical feedback

**For:** Product analytics

## The problem

A year of reviews sits in a spreadsheet; nobody knows which bugs were reported most.

## How the agents handle it

IMPORT FILE accepts JSON or CSV; RUN ALL QUEUED processes them in order so duplicates cluster. Memory (COMPLETED_WORK) and the tickets page become a map of recurring problems; usage shows the exact cost of the backfill.

## Example outcomes

- 2,000 reviews → ~140 tickets with +1 counts, ranked by comment volume.

## What to configure

- Cost awareness: settings › usage; consider a cheaper model for the backfill agent

## Value

Turns an archive into a ranked defect list.
