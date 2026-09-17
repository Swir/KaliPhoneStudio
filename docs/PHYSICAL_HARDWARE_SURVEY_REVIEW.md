# Physical hardware survey manual review

KaliPhoneStudio 0.6.61 adds a fail-closed **manual review** layer for one exact bounded physical hardware-presence survey.

This review does **not** prove that any hardware subsystem works. It only records that a human reviewed the exact survey as contextual evidence for later subsystem-specific functional testing.

## Safety boundary

The source survey remains sysfs-only and observational. The review layer:

- performs no phone I/O;
- does not activate USB, Wi-Fi, Bluetooth, audio, display, input, modem, charging or thermal controls;
- does not mount, decrypt, format or write storage;
- cannot set any functional hardware verification flag;
- cannot grant Beta credit;
- requires a separate later functional test for every supported hardware capability.

`accepted_as_context=true` therefore means only: **this exact reviewed survey may be used as contextual input for later functional testing**.

## 1. Create a rejected-by-default template

After real `physical-hardware-survey.json` evidence exists:

```bash
python scripts/prepare_physical_hardware_review.py \
  --survey-evidence evidence/physical-hardware-survey.json \
  --reviewer operator-1 \
  --out evidence/operator-hardware-review.json
```

The generated record starts with:

- `decision="rejected"`;
- every review check set to `false`;
- `functional_hardware_verified=false`;
- `beta_gate_credit=false`.

## 2. Review the exact physical context

A reviewer may change the decision to `accepted_as_context` only after explicitly reviewing:

1. physical device/session context;
2. exact survey/transcript integrity;
3. USB presence records;
4. network/radio presence records;
5. audio presence records;
6. input/display presence records;
7. thermal/power presence records;
8. the limitation that presence is **not** functionality.

Keep separate UTF-8 review notes describing what was observed, anomalies, and the functional tests still required.

An empty survey cannot be accepted as context.

## 3. Bind the exact record and notes

```bash
python scripts/review_physical_hardware_survey.py \
  --survey-evidence evidence/physical-hardware-survey.json \
  --review-record evidence/operator-hardware-review.json \
  --review-notes evidence/operator-hardware-review-notes.txt \
  --out evidence/physical-hardware-review.json
```

The binder records exact SHA-256/size identities for the review record and notes and binds them to the exact hardware survey, rescue transcript and rescue probe id.

## Interpretation

Even a complete accepted review keeps all of these false:

- `display_verified`
- `touch_verified`
- `usb_verified`
- `wifi_verified`
- `bluetooth_verified`
- `audio_verified`
- `modem_verified`
- `power_charging_verified`
- `thermal_verified`
- `storage_verified`
- `recovery_verified`
- `hardware_verified`
- `beta_gate_credit`

The next step after accepted contextual review is **real functional testing on the same physical candidate**, not release publication.
