# Physical hardware-presence survey

KaliPhoneStudio 0.6.60 adds a bounded, read-only hardware-presence survey to the rescue userspace. The purpose is to make the **first real temporary-boot session more informative** without activating hardware, writing storage, or pretending that sysfs presence proves a subsystem works.

## What it is

After the exact rescue stage/probe markers and the existing `readonly-sysfs-inventory-v1` diagnostic block, rescue `init` emits exactly one:

```text
KPS_SURVEY_BEGIN=readonly-hardware-presence-v1
...
KPS_SURVEY_END=readonly-hardware-presence-v1
```

The block is parsed offline by `kaliphonestudio.physical_hardware_survey` and bound to:

- the exact `PhysicalBootObservationEvidence`;
- the exact `PhysicalRescueDiagnosticsEvidence`;
- the exact console transcript SHA-256/size;
- the exact deterministic rescue probe id;
- the exact profile/device serial carried by the physical observation chain.

The parser performs no phone I/O.

## Bounded observations

Each category is capped at **32 records** in rescue userspace. Every emitted field is reduced to a bounded ASCII token before it enters machine-readable evidence.

| Record | Read-only source | What it means |
|---|---|---|
| `KPS_SURVEY_USB_UDC` | `/sys/class/udc/*` | a USB device controller is exposed by sysfs |
| `KPS_SURVEY_USB_DEVICE` | `/sys/bus/usb/devices/*/{idVendor,idProduct,bDeviceClass}` | a USB device entry is exposed; no serial string is collected |
| `KPS_SURVEY_NET` | `/sys/class/net/*/{type,operstate}` | a network interface object exists and has a reported state |
| `KPS_SURVEY_RFKILL` | `/sys/class/rfkill/rfkill*/{name,type,state,soft,hard}` | a radio-kill object exists; the survey never changes it |
| `KPS_SURVEY_SOUND` | `/sys/class/sound/card*/id` | a sound-card object exists |
| `KPS_SURVEY_THERMAL` | `/sys/class/thermal/thermal_zone*/{type,temp}` | a thermal-zone object exists and may expose a reading |
| `KPS_SURVEY_INPUT` | `/sys/class/input/event*/device/name` | an input event device is registered; no event stream is opened |
| `KPS_SURVEY_GRAPHICS` | `/sys/class/graphics/fb*/name` | a framebuffer object exists |
| `KPS_SURVEY_DRM` | `/sys/class/drm/card*-*/status` | a DRM connector object exposes a status |
| `KPS_SURVEY_POWER` | `/sys/class/power_supply/*/{type,status,capacity}` | a power-supply object exposes bounded state |

The survey intentionally does **not** capture network MAC addresses, USB serial strings, arbitrary sysfs text, block contents, input events, audio streams or framebuffer contents.

## What the survey never does

The automatic survey does not:

- run `fastboot` or `adb`;
- bring a network interface up or down;
- unblock or toggle rfkill;
- associate Wi-Fi or initialize Bluetooth;
- start audio playback/recording;
- initialize or reconfigure DRM/framebuffer state;
- read touch/key event streams;
- change thermal, battery or charging policy;
- mount, repair, decrypt, format or write persistent storage;
- select a rootfs target;
- authorize a persistent operation.

The only storage-related functional read probe remains the **separate manual** `/run/kps-readonly-probe --confirm-read-only` path with its existing 4096-byte bound.

## Offline recording

After a real rescue console transcript and its exact prior evidence files exist:

```bash
python scripts/record_physical_hardware_survey.py \
  --profile-id oneplus/avicii \
  --observation-evidence evidence/physical-boot-observation.json \
  --rescue-diagnostics-evidence evidence/physical-rescue-diagnostics.json \
  --console-transcript evidence/rescue-transcript.log \
  --out evidence/physical-hardware-survey.json
```

The command only reads local files and validated device-profile data. It does not connect to a phone.

## Presence is not functionality

Fields such as:

- `usb_signal_observed=true`;
- `wifi_signal_observed=true`;
- `bluetooth_signal_observed=true`;
- `audio_signal_observed=true`;
- `display_signal_observed=true`;
- `input_signal_observed=true`;
- `power_signal_observed=true`;

mean only that the bounded survey found corresponding sysfs signals in the exact transcript.

They **do not** mean USB transfer, Wi-Fi connectivity, Bluetooth transport, audio, display scan-out, touch, charging safety or another hardware function has been verified.

Every survey evidence record therefore requires manual review and enforces:

```text
display_verified=false
touch_verified=false
usb_verified=false
wifi_verified=false
bluetooth_verified=false
audio_verified=false
modem_verified=false
power_charging_verified=false
thermal_verified=false
storage_verified=false
recovery_verified=false
phone_storage_written=false
hardware_verified=false
beta_gate_credit=false
```

Functional hardware milestones remain the separate physical gates in `BETA_RELEASE_GATE.md` and `ROADMAP.md`.

## Fail-closed properties

The recorder rejects, among other things:

- a transcript different from the exact boot observation;
- a rescue-diagnostics record detached from that boot observation;
- profile, serial, transcript or probe-id drift;
- missing, duplicated or reordered BEGIN/END proof structure;
- survey markers outside the locked block;
- unsupported marker kinds or field counts;
- non-ASCII or unbounded machine-readable field data;
- mutation of the transcript while it is being verified;
- evidence with promoted hardware/Beta claims;
- overwriting an existing evidence output.

This layer is intended to reduce the number of risky physical iterations while preserving the rule that **real hardware support is proven only by reviewed physical behavior, never inferred from host CI or device-node presence**.
