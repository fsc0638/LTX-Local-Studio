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
- [x] Targeted Python tests, full Python suite, Node tests, TypeScript, production build, shell syntax and diff checks pass.
- [x] A minimal GPU smoke proves the new launcher can load the Dev transformer and a character LoRA.

## Progress

- Complete: inspected the existing model registry, API environment/provenance path, Fast launcher,
  host-side LoRA Registry, Sandbox selector, and Production Factory Bible projection.
- Complete: added the Dev adapter, one-stage launcher/runner, provenance branch, Registry compatibility
  regression, Sandbox support, and Factory model selector with compatibility filtering.
- Verified: shell syntax and diff check; 10 targeted Python tests; 459 full Python tests with 7
  skips; 108 Node tests; TypeScript compile; and the production build.
- Verified on NVIDIA GB10: the new launcher loaded the official LTX 2.5 Dev transformer plus
  `mikamiu` step-200 identity LoRA at strength 1.0, ran 3 denoise steps, and emitted an H.264
  256×320, 9-frame, 24 FPS MP4. Smoke SHA-256:
  `dd5f90cd970b822f72298808a55862a2c196380d7825df37ad38c46293285665`.
- Complete in branch: implementation and verification.
- Waiting: user merge, production deployment approval, approved Registry metadata/asset placement,
  service restart, and authenticated UI smoke.
- Not started: merge to `main`, formal Registry asset installation, and production service restart.

## Deployment boundary

This work order changes only the project worktree. Production deployment, copying an approved
LoRA into the runtime Registry, and restarting `ltx-api`/`ltx-web` require a separate matched
operation approval after the branch is merged.
