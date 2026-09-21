# Windows operator extractor for the AC2003 first test

KaliPhoneStudio can build a short-lived **Windows operator extractor bundle** for the first physical AC2003 campaign. Its purpose is to remove one manual dependency from the day-of-test workflow: the exact `payload-dumper-go.exe` used to extract the stock `boot.img` from the matching OxygenOS OTA, together with any non-system MinGW runtime DLLs that exact executable needs.

This artifact is **not a Beta release**, does not contact a phone and grants no hardware/Beta credit.

## Exact source and native-build contract

The build reads [`tools/extractor-locks.json`](../tools/extractor-locks.json) as the only source of truth and refuses drift. The current Windows contract is:

- project: `ssut/payload-dumper-go`;
- source commit: `05fe59e21c9f271fba38398c7c040993313ecd04`;
- Go toolchain: `1.27.0`;
- target: `windows-amd64`;
- native environment: **MSYS2 mingw64** with the exact package revisions recorded in the lock;
- build flags: `-trimpath -buildvcs=false` plus `-buildid= -extldflags=-static`;
- packaging policy: **mixed side-by-side runtime closure**, not a false claim of a fully static executable;
- runtime policy: recursively inspect PE imports and bundle every non-system dependency from the exact locked MinGW environment;
- reviewed executable SHA-256: `9a4848ff93b28a9c2f9dbf52b11e09184242ff192032187d70079df5dfb9a616`.

Exact-head A/B reproducibility run `35587929913` on **2026-09-21** used the current locked MSYS2 mingw64 package set, including GCC `16.2.0-4`. It built the exact Windows executable twice and proved byte-for-byte equality at the digest above. The workflow then recursively staged the non-system PE runtime closure and passed the clean-PATH smoke before that digest was promoted into the lock. This supersedes the earlier executable digest produced under the previous GCC `16.2.0-3` native package revision.

The proof also keeps an important packaging fact explicit: `-extldflags=-static` does **not** eliminate every MinGW runtime DLL import on the Windows runner. KaliPhoneStudio therefore does not label the binary fully static. `stage_windows_extractor_runtime.ps1` recursively inspects the executable and every copied DLL with MinGW `objdump`, treats Windows system/API-set imports as operating-system dependencies, and copies each remaining MinGW dependency next to `payload-dumper-go.exe`. Every copied file is re-hashed, the complete closure is recorded in `operator-extractor-runtime.json`, and unresolved non-system imports fail the build.

The delivered directory must then start successfully with `PATH` restricted to Windows system directories. This proves the operator does not need the GitHub runner's MSYS2 installation or a manual DLL search on the user's PC.

The operator builder also verifies every recorded MSYS2 package version with `pacman -Q`, fetches the exact source commit, verifies `HEAD`, confirms the pinned `go.mod` requirement and refuses the artifact unless the executable digest matches the reviewed lock.

Upstream's own GoReleaser configuration uses MinGW and static external-link intent for Windows releases. KaliPhoneStudio keeps its own exact source/tool/native-package authority and additionally verifies the actual delivered runtime closure rather than assuming linker flags alone made the executable self-contained.

## License

`payload-dumper-go` is distributed under **Apache-2.0**. The workflow copies the exact upstream `LICENSE` from the pinned source checkout into the artifact as `payload-dumper-go-LICENSE.txt`. If the pinned source ever adds a root `NOTICE`, the builder also copies it.

The runtime DLLs come from the exact locked MSYS2/MinGW package set. Their names, byte sizes and SHA-256 digests are recorded in the runtime manifest so the delivered directory can be audited as one exact operator bundle.

## Artifact contents

A successful workflow artifact contains at least:

```text
payload-dumper-go.exe
payload-dumper-go.exe.sha256
payload-dumper-go-LICENSE.txt
operator-extractor-manifest.json
operator-extractor-runtime.json
payload-dumper-go-help.txt
<zero-or-more exact non-system MinGW runtime DLLs>
```

`operator-extractor-manifest.json` records the exact source commit, Go version, native dependency versions, build flags, executable/license/runtime-manifest hashes and explicit non-authorizing safety state. `operator-extractor-runtime.json` records the recursively closed non-system PE dependency set. The help capture is produced only after the bundled directory starts successfully with an isolated Windows system `PATH`.

## Use during the first AC2003 campaign

Extract the **whole operator-tools directory**, not only the `.exe`, beside the Windows KaliPhoneStudio Beta-test-candidate. Keep the runtime DLLs next to `payload-dumper-go.exe`. In the first-test runbook, use this exact executable whenever `--extractor` is requested:

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

`prepare-physical-candidate-offline` independently re-hashes the extractor before invoking the exact-OTA pipeline, so replacing the executable after the tool artifact was built does not bypass the source/hash lock. The operator bundle's own manifests additionally preserve the runtime closure used to start that exact executable.

## Android Platform-Tools remains separate

This artifact intentionally **does not bundle Android Platform-Tools / Fastboot**. Google’s official Platform-Tools download is distributed under a separate SDK terms flow, and the KaliPhoneStudio Fastboot policy remains an exact-version operator boundary. Do not replace it with an arbitrary Fastboot binary merely for convenience.

The phone-side sequence therefore remains:

1. use one reviewed Fastboot executable accepted by `fastboot-tool-policy.json` for the entire evidence session;
2. use the exact source/native-dependency/hash-verified `payload-dumper-go.exe` together with its exact side-by-side runtime closure for OTA extraction;
3. preserve all evidence under one fresh session directory;
4. stop on any identity, firmware, slot, provenance or hash drift;
5. perform the separately gated one-shot temporary boot only after recovery-readiness review.

Building or downloading this operator bundle performs **no phone interaction**, does not authorize a persistent write and does not change the project’s 58% roadmap value or blocked Beta gate.
