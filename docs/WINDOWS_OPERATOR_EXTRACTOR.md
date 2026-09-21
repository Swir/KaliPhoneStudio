# Windows operator extractor for the AC2003 first test

KaliPhoneStudio can build a short-lived **Windows operator extractor artifact** for the first physical AC2003 campaign. Its purpose is to remove one manual dependency from the day-of-test workflow: the exact `payload-dumper-go.exe` used to extract the stock `boot.img` from the matching OxygenOS OTA.

This artifact is **not a Beta release**, does not contact a phone and grants no hardware/Beta credit.

## Exact source contract

The build reads [`tools/extractor-locks.json`](../tools/extractor-locks.json) as the only source of truth and refuses drift. The current Windows contract is:

- project: `ssut/payload-dumper-go`;
- source commit: `05fe59e21c9f271fba38398c7c040993313ecd04`;
- Go toolchain: `1.27.0`;
- target: `windows-amd64`;
- build flags: `-trimpath -buildvcs=false -ldflags=-buildid=`;
- required executable SHA-256: `35fbcd36c553f81375a904ceca58aef5289da2e2e067fc0e6c835390588edfa5`.

The builder fetches that exact commit, verifies `HEAD`, builds with the exact Go toolchain/flags, hashes the resulting executable and refuses the artifact unless the digest matches the already reviewed lock.

## License

`payload-dumper-go` is distributed under **Apache-2.0**. The workflow copies the exact upstream `LICENSE` from the pinned source checkout into the artifact as `payload-dumper-go-LICENSE.txt`. If the pinned source ever adds a root `NOTICE`, the builder also copies it.

## Artifact contents

A successful workflow artifact contains at least:

```text
payload-dumper-go.exe
payload-dumper-go.exe.sha256
payload-dumper-go-LICENSE.txt
operator-extractor-manifest.json
```

The manifest records the exact source commit, Go version, build flags, executable/license hashes and explicit non-authorizing safety state.

## Use during the first AC2003 campaign

Extract the artifact beside the Windows KaliPhoneStudio Beta-test-candidate. In the first-test runbook, use this exact executable whenever `--extractor` is requested:

```powershell
$Extractor = (Resolve-Path ".\operator-tools\payload-dumper-go.exe").Path

& $Cli prepare-physical-candidate-offline `
  --profile-id oneplus/avicii `
  --session-dir "$Session" `
  --ota "<PATH_TO_EXACT_MATCHING_OXYGENOS_OTA>" `
  --extractor "$Extractor" `
  --extractor-platform windows-amd64 `
  --first-boot-manifest "<EXACT_FIRST_BOOT_MANIFEST_JSON>" `
  --authority-bundle "<EXACT_AUTHORITY_BUNDLE_JSON>" `
  --boot-authorization "<EXACT_TEMPORARY_BOOT_AUTHORIZATION_JSON>" `
  --boot-plan "<EXACT_BOOT_PLAN_JSON>" `
  --candidate-boot "<EXACT_CANDIDATE_BOOT_IMG>" `
  --candidate-dtbo "<EXACT_CANDIDATE_DTBO_IMG>" `
  --fastboot-executable "<PATH_TO_REVIEWED_FASTBOOT_EXE>"
```

`prepare-physical-candidate-offline` independently re-hashes the extractor before invoking the exact-OTA pipeline, so replacing the executable after the tool artifact was built does not bypass the source/hash lock.

## Android Platform-Tools remains separate

This artifact intentionally **does not bundle Android Platform-Tools / Fastboot**. Google’s official Platform-Tools download is distributed under a separate SDK terms flow, and the KaliPhoneStudio Fastboot policy remains an exact-version operator boundary. Do not replace it with an arbitrary Fastboot binary merely for convenience.

The phone-side sequence therefore remains:

1. use one reviewed Fastboot executable accepted by `fastboot-tool-policy.json` for the entire evidence session;
2. use the exact source/hash-verified `payload-dumper-go.exe` from this artifact for OTA extraction;
3. preserve all evidence under one fresh session directory;
4. stop on any identity, firmware, slot, provenance or hash drift;
5. perform the separately gated one-shot temporary boot only after recovery-readiness review.

Building or downloading this operator artifact performs **no phone interaction**, does not authorize a persistent write and does not change the project’s 58% roadmap value or blocked Beta gate.
