# GB10 setup scripts

Host-side installers for the models and tools that back the studio agent system
(everything except the OpenAI-hosted LLM/VLM). Run them on the GB10 in numeric order;
each one is idempotent and ends with a verification step. See `docs/GB10_SETUP.md`.

Nothing here is imported by the app. `infra/` is outside the git-sync test/restart triggers.
