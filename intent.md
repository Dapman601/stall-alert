# intent.md — stall-alert

## Who it's for
A recruiter or recruiting coordinator managing a hiring board with many candidates across several roles and stages.

## The problem
Candidates quietly stall. Someone sits in "final interview" for two weeks because feedback was never chased, or an offer goes cold because nobody followed up. On a busy board, the recruiter only notices once the candidate has gone elsewhere.

## What the tool does
Reads a CSV export of the hiring board and:
1. finds candidates who have been in their current stage longer than allowed for that stage,
2. ranks who to follow up first, with a score a human can check,
3. suggests one specific next action per stalled candidate.

A human reads every suggestion. Nothing is sent automatically.

## What "done" looks like
- Runs from the command line on a CSV and prints a ranked list.
- Stall detection and ranking are deterministic, explainable, and fully tested, with no AI involved.
- The AI only writes the suggested action, and code checks every suggestion before it's shown: no invented names, dates, or numbers.
- If the AI fails or can't be trusted, the tool still works and says why it fell back.
- Bad input is reported clearly, never silently dropped.
- A README that lets someone else run it and its tests.

## In scope
- One CSV format with known columns
- Per-stage thresholds and ranking weights in a config file
- Business-day counting (Mon–Fri)
- Terminal stages (hired / rejected / withdrawn) and on-hold candidates handled separately
- An optional AI layer with validation and a rule-based fallback

## Out of scope
- Sending messages or updating the hiring system
- Connecting to a live ATS (Greenhouse, Lever, etc.)
- Public holidays and per-person calendars
- A user interface beyond the command line

## How I'll judge it
- I can verify every flag and score by hand on the sample data.
- Suggested actions are specific to the stage, not generic "follow up" advice.
- I record what breaks when the input gets harder, and I don't hide it.
