-- B4: the LLM screenwriting draft.
--
-- Token spend is tracked per project rather than per account: a project is what a person budgets
-- and what they abandon, and a runaway loop should cost that project its allowance without
-- stopping every other project the account owns.
--
-- One jsonb column rather than a table of calls. What the cap needs is a running total, and a row
-- per call would grow without bound for a number nobody reads back individually.
ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS draft_usage jsonb NOT NULL DEFAULT '{}'::jsonb;
