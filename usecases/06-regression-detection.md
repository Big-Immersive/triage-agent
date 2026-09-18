# Regression detection

**For:** QA / release managers

## The problem

A bug fixed in 2.3.8 comes back in 2.4.1. A naive duplicate check would mark it duplicate of the closed ticket and nobody would look.

## How the agents handle it

`record_investigation` refuses a duplicate claim against a closed ticket whose `fixed_in` version is older than the reported version, and instructs the agent to file it as NEW with the old ticket referenced as a possible regression.

## Example outcomes

- Report on 2.4.1 matches closed OR-101 (fixed_in 2.3.8) → new ticket 'possible regression of OR-101'.

## What to configure

- Tracker export includes status and fixed_in
- Reports carry app_version (metadata or text)

## Value

Regressions surface as new, high-visibility tickets instead of vanishing into closed history.
