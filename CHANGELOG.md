# Changelog

Active development changes are listed here. Older detailed entries remain in [`CHANGELOG_HISTORY.md`](CHANGELOG_HISTORY.md).

## 0.6.66-dev — cross-campaign release audit and multi-device identity hardening

- Closed the host-side temporary-boot probe-to-execution TOCTOU window: after the fresh read-only Fastboot probe and slot-context checks, the executor now re-verifies the exact Fastboot executable, candidate `boot.img`, boot-identity/authorization/baseline bindings and matching local stock `boot.img` recovery-readiness material immediately before the single permitted `fastboot boot` invocation. Drift fails closed with no boot subprocess, no persistent write and no hardware/Beta credit; the execution policy is versioned and focused CI covers ordering plus post-probe candidate/recovery drift.
- Added formal Draft 2020-12 `devices/profile.schema.json` for profile schema v3 and a pinned CI-only validator that also runs the runtime semantic profile validator.
- Replaced flat safety-sensitive alias matching with profile-driven typed identity signals: strong product/model values may identify a device, while weak contextual values such as a shared bootloader board can never identify a phone by themselves.
- Upgraded the registry audit so every strong identity value must resolve exactly one profile across the complete catalogue; shared weak values are allowed only while weak-only resolution remains impossible. The same contract is executed through the frozen Windows CLI.
- Migrated `oneplus/avicii` to schema v3 with strong `avicii`/AC2003 identity and weak `lito` board context; this is a host-side safety contract and does not add physical hardware support.
- Updated multi-device documentation, README/ROADMAP status wording, BUILD_STATUS and regression coverage; removed legacy text-art progress meters from maintained README/ROADMAP while preserving the numeric fallback and deterministic SWIR Progress SVG PRO presentation.
- Project completion remains **58%** and Beta remains **BLOCKED** because no new physical AC2003 gate was passed.
- Added `kaliphonestudio.physical_release_gate_audit` as a schema-v1 fail-closed audit packet joining one accepted exact physical bring-up dossier/review chain to one exact physical functional-result campaign.
- The audit requires the canonical physical bring-up dossier, independent post-copy dossier verification, accepted dossier review, exact functional-result bundle, canonical functional-test plan and accepted independent test-plan review as exact non-symlink files with SHA-256/size and TOCTOU checks.
- Cross-campaign validation now rejects profile/device drift and requires the exact physical boot observation, rescue diagnostics, raw rescue transcript and rescue probe identity to agree between the bring-up/storage dossier and the functional-test plan; the exact functional-hardware contract is also cross-checked.
- The functional-result bundle must bind the exact supplied plan and exact supplied accepted plan-review file, while the dossier review must bind the exact supplied dossier and verification. This prevents unrelated real-device campaigns from being combined for release review.
- Added immutable canonical audit evidence, `scripts/build_physical_release_gate_audit.py`, focused fail-closed regression tests, dedicated `physical-release-gate-audit` CI and `docs/PHYSICAL_RELEASE_GATE_AUDIT.md`.
- Even when every Beta-required functional test is independently reviewed as passing, the audit forces `manual_release_gate_review_required=true`, `physical_gate_still_incomplete=true`, and keeps target/path/write/support/hardware/Beta authorization false.
- Synchronized README, ROADMAP, BUILD_STATUS, Beta gate wording, version state and deterministic SWIR progress presentation with the new host-side milestone.
- Project completion remains **58%** and Beta remains **BLOCKED** because no real AC2003 physical campaign has yet produced the required baseline, temporary boot, storage/hardware evidence, early-userspace proof and exercised recovery/rollback.

## 0.6.65-dev — exact-file physical functional result bundle

- Added `kaliphonestudio.physical_hardware_result_bundle` as a schema-v1 fail-closed audit layer for one exact physical functional-test campaign.
- The bundle verifies canonical SHA-256/size identities for the exact test plan, accepted exact-plan review, every supplied schema-v2 observation, every supplied independent result review and the aggregate summary.
- Every schema-v2 observation is rechecked against the accepted plan-review evidence/file/review-record/review-notes identities and reviewer; every result review must bind the exact bundled observation for the same unique test id.
- The supplied summary is freshly recomputed from the exact bundled reviews and must match byte-for-byte semantic state; detached, duplicate or drifted result files fail closed.
- Added immutable bundle load/write validation, symlink/TOCTOU/file-size hardening, `scripts/build_physical_hardware_result_bundle.py`, operator documentation and focused regression coverage.
- Even complete Beta-required reviewed-pass coverage remains release-gate input only: project support, persistent writes, phone-storage writes, hardware verification and Beta credit remain forced false.
- Extended `physical-hardware-functional-results` CI to compile and test the exact-file bundle chain.
- Project completion remains **58%** and Beta remains **BLOCKED** because no real AC2003 physical functional campaign has passed the mandatory gate.

## 0.6.64-dev — accepted-plan-review-bound physical observations and deterministic progress SVGs

- Upgraded `kaliphonestudio.physical_hardware_test_observation` to schema-v2 so no physical per-test observation can be prepared or bound unless the original canonical test plan has a separate `accepted_for_physical_execution=true` exact-plan review.
- Every schema-v2 observation now carries the exact plan-review evidence SHA-256, canonical plan-file SHA-256, review-record SHA-256, review-notes SHA-256 and reviewer identity in addition to the existing profile/device/survey/boot/rescue/transcript/probe/contract chain.
- Added fail-closed cross-checking for plan/review profile and serial identity, semantic plan digest, canonical plan bytes/size, test counts, upstream evidence digests and plan readiness. Rejected, detached or drifted plan reviews cannot produce valid physical observation evidence.
- Updated the safe observation-template and observation-recording CLIs to require `--test-plan-review-evidence`; neither command performs phone I/O or grants hardware/Beta credit.
- Extended focused regression tests and `physical-hardware-functional-results` CI around rejected/detached review handling, immutable schema-v2 round trips and forbidden write/hardware/Beta promotion.
- Implemented **SWIR Progress SVG PRO v1** with deterministic `progress-card.svg`, `progress-mini.svg`, a reusable N/A template, generator/check, XML/geometry/math tests and dedicated CI. The assets read the authoritative `BUILD_STATUS.json` project ledger and render Beta readiness separately.
- For the current 58% ledger value, the generated fill is exactly 638/1100 px on the card and 406/700 px on the mini. Unknown progress renders N/A with no fabricated fill.
- Embedded the card in README and mini in ROADMAP with textual fallback while preserving SWIR README PRO v2 and Search Keywords.
- Project completion remains **58%** and Beta remains **BLOCKED** because no new physical AC2003 gate has been passed.

## 0.6.63-dev — independent exact physical test-plan manual review

- Added `kaliphonestudio.physical_hardware_test_plan_review` as a separate fail-closed review boundary between deterministic plan generation and any real-device functional-test session.
- The review binds the original canonical test-plan file by SHA-256 and byte size in addition to the plan semantic evidence digest, preventing a reviewer from approving only a detached downstream hash.
- Exact profile/device, survey-review, survey, boot, rescue, transcript, rescue-probe and functional-hardware-contract identities are carried into the review evidence.
- `decision="accepted"` requires explicit review of exact plan bytes, identity chain, functional contract, Beta-required scope, context readiness, no-write policy and limitations; a plan that is not itself ready still cannot become `accepted_for_physical_execution=true`.
- Added rejected-by-default review templates, separate UTF-8 review notes, immutable canonical evidence output and offline operator CLIs. No command performs phone I/O or hardware activation.
- Even accepted plan review forces manual test execution and keeps functional execution/verification, phone-storage writes, hardware verification and Beta credit false.
- Added focused fail-closed tests, dedicated `physical-hardware-test-plan-review` CI and `docs/PHYSICAL_HARDWARE_TEST_PLAN_REVIEW.md`.
- Synchronized README/ROADMAP/BUILD_STATUS/Beta-gate wording with SWIR README PRO v2; project completion remains **58%** and Beta remains **BLOCKED** because no real AC2003 plan or physical functional result has passed the gate.

## 0.6.62-dev — exact physical functional-test observation and review

- Added `kaliphonestudio.physical_hardware_test_observation` to bind one actually executed physical functional test to one exact pending profile-driven test plan, exact device/candidate context, canonical operator record and separate notes.
- `pass_candidate` now requires every exact `required_observations` item from the selected plan test to be satisfied; missing context signals, identity drift, changed files and any persistent-write claim fail closed.
- Added a safe observation-template CLI that starts `inconclusive`, not executed, with candidate/device confirmation false and all observation checks false; it cannot be bound until edited after a real physical test.
- Added `kaliphonestudio.physical_hardware_test_review` as an independent exact manual-review layer. Accepted pass/fail/inconclusive decisions must match the bound observation outcome and require exact-plan, exact-observation, physical-context, required-observation, notes/limitations and no-write checks.
- Added rejected-by-default review templates plus offline observation/review binder CLIs. A reviewed pass remains test-level evidence only and cannot authorize a public support claim or Beta release.
- Added `kaliphonestudio.physical_hardware_test_summary` to aggregate exact-plan statuses (`pending`, `reviewed_pass`, `reviewed_fail`, `reviewed_inconclusive`, `rejected`) and count Beta-required reviewed passes while forcing project-support/hardware/Beta promotion false.
- Added focused fail-closed tests and dedicated `physical-hardware-functional-results` CI covering exact binding, canonical round trips, outcome/review matching, duplicate/detached review rejection, safe template defaults and forbidden support/write/Beta promotion.
- Added `docs/PHYSICAL_HARDWARE_FUNCTIONAL_TESTS.md` and synchronized README/ROADMAP/version state with SWIR README PRO v2.
- Project completion remains **58%** and Beta remains **BLOCKED** because no real AC2003 functional test result has been captured/reviewed and the mandatory physical release gate remains open.

## 0.6.61-dev — fail-closed physical hardware survey manual review

- Added `kaliphonestudio.physical_hardware_review` as a schema-v1 offline manual-review layer for one exact bounded `PhysicalHardwareSurveyEvidence` record.
- Bound the exact hardware survey, physical boot/rescue/transcript/probe identity, canonical review-record bytes and separate UTF-8 review-notes bytes by SHA-256 and size.
- Context acceptance requires a non-empty recorded survey plus explicit review of physical context, survey integrity, USB presence, network/radio presence, audio presence, input/display presence, thermal/power presence and the limitation that sysfs presence is not functionality.
- Added a rejected-by-default template generator, `scripts/prepare_physical_hardware_review.py`, and the offline binder `scripts/review_physical_hardware_survey.py`; neither command performs phone I/O.
- `accepted_as_context=true` means only that the exact survey may be used as contextual input for later subsystem-specific physical functional tests. It never promotes display/touch/USB/Wi-Fi/Bluetooth/audio/modem/power/thermal/storage/recovery/hardware verification or Beta credit.
- Added fail-closed tests covering contextual acceptance, incomplete/empty survey rejection, identity drift, canonical JSON, exact file binding, safe template defaults and forbidden functional/Beta promotion.
- Extended `rescue-readonly-diagnostics` CI to compile and test the manual survey-review contract together with the existing rescue observation/diagnostic/survey layers.
- Added `docs/PHYSICAL_HARDWARE_SURVEY_REVIEW.md` and synchronized README/ROADMAP/BUILD_STATUS with SWIR README PRO v2 while keeping all release and compatibility claims unchanged.
- Project completion remains **58%** because no real AC2003 survey has been captured/reviewed and no subsystem has passed a physical functional test.

## 0.6.60-dev — bounded physical hardware-presence survey