# LT25DEVLORA-1007 — LTX 2.5 Dev Character LoRA Lane

## Goal

Add a first-class `ltx25-dev` video model lane for character LoRAs trained against the
LTX 2.5 Dev transformer. Keep the existing `ltx25-fast` distilled two-stage lane as the
default fast renderer and never claim cross-checkpoint LoRA compatibility.

## Acceptance checks

- [x] Model catalog exposes an availability-checked `ltx25-dev` adapter.
- [x] Dev launcher uses the official one-stage pipeline and accepts approved identity and wardrobe LoRAs.
- [x] API provenance fingerprints the Dev transformer and Dev launcher accurately.
- [x] Character LoRA Registry rejects Dev-only LoRAs on `ltx25-fast` and accepts them on `ltx25-dev`.
- [x] Sandbox and Production Factory can select `ltx25-dev` and only show compatible LoRAs.
- [ ] Targeted Python tests, full Python suite, Node tests, TypeScript, production build, shell syntax and diff checks pass.
- [ ] A minimal GPU smoke proves the new launcher can load the Dev transformer and a character LoRA.

## Progress

- Complete: inspected the existing model registry, API environment/provenance path, Fast launcher,
  host-side LoRA Registry, Sandbox selector, and Production Factory Bible projection.
- Complete: added the Dev adapter, one-stage launcher/runner, provenance branch, Registry compatibility
  regression, Sandbox support, and Factory model selector with compatibility filtering.
- Verified so far: shell syntax, 10 targeted Python tests, and TypeScript compile.
- In progress: full regression/build and minimal GPU smoke.
- Not started: merge to `main`, formal Registry asset installation, and production service restart.

## Deployment boundary

This work order changes only the project worktree. Production deployment, copying an approved
LoRA into the runtime Registry, and restarting `ltx-api`/`ltx-web` require a separate matched
operation approval after the branch is merged.
