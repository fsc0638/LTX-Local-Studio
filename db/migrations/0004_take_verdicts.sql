-- C2: takes carry a verdict, shots point at the take that goes to assembly.
--
-- accepted_take_id is a real foreign key with ON DELETE SET NULL: when a take row goes, the shot
-- stops claiming it rather than pointing at nothing. The partial unique index makes "one shot per
-- accepted take" a property of the table, not of the code that writes it.
--
-- deleted_at on takes is the recycle bin's mark. The row stays - its verdict and reason are
-- history the review page still shows - but its output is gone and it can no longer be accepted.
ALTER TABLE takes
    ADD COLUMN IF NOT EXISTS deleted_at double precision;
ALTER TABLE shots
    ADD COLUMN IF NOT EXISTS accepted_take_id uuid REFERENCES takes (id) ON DELETE SET NULL;
CREATE UNIQUE INDEX IF NOT EXISTS shots_accepted_take_id_key
    ON shots (accepted_take_id) WHERE accepted_take_id IS NOT NULL;
