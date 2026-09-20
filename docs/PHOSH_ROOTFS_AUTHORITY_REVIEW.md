# Phosh rootfs authority review

PR #132 now has an explicit promotion boundary between a real A/B Phosh ARM64
rootfs candidate and a reviewed host-side reproducibility authority.

The real-build workflow remains non-destructive. After build A and build B are
byte-identical and the build-A payload has been materialized, it creates
`phosh-rootfs-review-packet.json`. The packet cross-binds the exact rootfs
payload evidence, package manifest, selected real-build evidence, A/B comparison,
GitHub run/attempt and exact source commit.

The packet is **review input only**:

- `ready_for_authority_review=true`
- `reviewed=false`
- `reproducibility_authority=false`
- `physical_validation_required=true`
- `hardware_verified=false`
- `beta_gate_credit=false`

## Automatic review-packet creation

```bash
python scripts/prepare_phosh_rootfs_review_packet.py \
  --candidate-artifact phosh-rootfs-candidate-artifact.json \
  --reproducibility-candidate phosh-rootfs-reproducibility-candidate.json \
  --build-evidence phosh-build-a.json \
  --repository Swir/KaliPhoneStudio \
  --source-run-id 123456 \
  --source-run-attempt 1 \
  --source-commit 0123456789abcdef0123456789abcdef01234567 \
  --out phosh-rootfs-review-packet.json
```

## Explicit authority promotion

Authority promotion is deliberately not performed by CI. After the A/B evidence,
candidate payload and review packet have been inspected, an operator must pass
`--reviewed` explicitly and bind the reviewed GitHub run, source commit and
uploaded artifact ID:

```bash
python scripts/review_phosh_rootfs_authority.py \
  --review-packet phosh-rootfs-review-packet.json \
  --authority-name phosh-arm64-reviewed \
  --authority-run-id 123456 \
  --authority-commit 0123456789abcdef0123456789abcdef01234567 \
  --authority-artifact-id 987654 \
  --reviewed \
  --out phosh-rootfs-authority.json
```

The authority is host-side provenance only. It means the exact Phosh rootfs was
reviewed as a reproducible A/B artifact and is ready for the next first-boot
binding step. It does **not** prove AC2003 boot, display, touch, storage, charging,
recovery, modem, audio, Wi-Fi/Bluetooth or any other hardware function, and it
does not authorize Beta.
