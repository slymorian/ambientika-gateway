# Ambientika RS485 Reverse Engineering Notes

> Laboratory notes, observations, hypotheses and unresolved questions.

This document contains working notes. Confirmed protocol information should be copied to `protocol.md` and `frame_database.md`.

---

## Hardware setup

- Raspberry Pi 3B+
- Two DSD TECH SH-U10 USB-to-RS485 adapters
- Wired Südwind Ambientika wall controller
- One master fan
- One slave fan
- Panel bus and fan bus physically separated
- Gateway forwards traffic between both bus segments

### Bus configuration

- 9600 baud
- 8 data bits
- no parity
- 1 stop bit
- half-duplex RS485
- A, B and reference GND connected
- Adapter 5 V terminals unused

---

## Gateway architecture

```text
Wall controller
      │
USB-RS485 adapter
      │
Raspberry Pi gateway
      │
USB-RS485 adapter
      │
Master + slave fans
```

### Transparent mode

All panel traffic is forwarded to the fans. All fan replies are forwarded to the panel.

### Override mode

- Four-byte panel control frames are blocked.
- Short status requests are forwarded.
- Fan replies are always forwarded to the panel.
- The gateway generates replacement control frames.

---

## Confirmed communication roles

### Wall controller

The wall controller sends:

- recurring four-byte control frames, approximately twice per second
- periodic short status requests, approximately every six seconds

### Master fan

The master sends:

- short responses to panel status requests
- startup frames after power-up

The fan segment is otherwise mostly silent when no request is received.

---

## Packet framing

Observed packets use:

```text
STX + ASCII hexadecimal payload + ETX
```

Example:

```text
02 30 31 33 39 30 30 33 38 03
```

represents:

```text
01390038
```

---

## Checksum

For four-byte frames:

```text
byte4 = byte1 XOR byte2 XOR byte3
```

Example:

```text
01 XOR 39 XOR 00 = 38
```

Therefore:

```text
01390038
```

is valid.

Status: ✅ Confirmed

---

## Byte 3 observations

| Value | Observation |
|------:|-------------|
| `00` | Stable operating state |
| `04` | Humidity alarm active |
| `08` | Temporary setting-change state |
| `0C` | Setting change while humidity alarm is active |

Current interpretation:

```text
0x0C = 0x08 + 0x04
```

Status: ✅ Strongly confirmed

---

## Humidity threshold encoding

Observed automatic alarm frames:

| Threshold | Byte 2 | Stable frame |
|-----------|-------:|--------------|
| 1 drop | `36` | `01360433` |
| 2 drops | `76` | `01760473` |
| 3 drops | `B6` | `01B604B3` |

The values differ by `0x40`.

Current hypothesis:

```text
humidity threshold 1 → 0x00
humidity threshold 2 → 0x40
humidity threshold 3 → 0x80
```

These bits appear to remain present in other operating modes, even where the humidity sensor is inactive.

Status: 🟡 Strong hypothesis

---

## Fixed-direction mode encoding

With humidity threshold set to one drop, stable byte-2 values are:

| Mode | Speed 1 | Speed 2 | Speed 3 |
|------|--------:|--------:|--------:|
| Master supply, slave extract | `25` | `26` | `27` |
| Master extract, slave supply | `29` | `2A` | `2B` |
| Extract | `35` | `36` | `37` |
| Supply | `39` | `3A` | `3B` |

Current interpretation:

- adjacent speed levels increment byte 2 by one
- mode and direction are encoded in the remaining bits
- humidity-level bits can be ORed into byte 2

Status: 🟡 Strong hypothesis

---

## Manual alternating mode

Observed sequence for speed 2:

```text
01AA00AB  phase A
01A200A3  transition
01A600A7  phase B
01A200A3  transition
```

Measured timing:

| Phase | Duration |
|-------|---------:|
| Direction phase A | 60 seconds |
| Transition | 10 seconds |
| Direction phase B | 60 seconds |
| Transition | 10 seconds |

Total sequence duration:

```text
140 seconds
```

The wall controller actively generates the direction sequence. The master does not create the timing independently.

Status: ✅ Confirmed for speed 2

### Speed 1

Observed:

```text
01A500A4  phase A
01A100A0  transition
01A900A8  phase B
```

Status: ✅ Confirmed

### Speed 3

Observed or provisionally assigned:

```text
01A700A6  phase A
01A300A2  transition
```

The second direction frame is still missing.

Status: 🟡 Incomplete

---

## Automatic mode

According to the manufacturer documentation:

- normal operation uses heat-recovery alternating ventilation
- humidity alarm switches both fans to extract

### Alarm state

Confirmed stable frames:

| Threshold | Frame |
|-----------|-------|
| 1 drop | `01360433` |
| 2 drops | `01760473` |
| 3 drops | `01B604B3` |

Both master and slave physically operate in extract mode.

Status: ✅ Confirmed

### Normal state

Previously observed:

```text
012A002B
```

This may belong to a normal automatic phase, but the exact context is not yet sufficiently controlled.

Testing requires humidity below the configured threshold.

Status: ⬜ Unresolved

---

## Monitoring mode

Expected behavior from manufacturer documentation:

- fans remain idle while humidity is below the threshold
- both fans switch to extract during humidity alarm

Open questions:

- Are the alarm frames identical to automatic alarm frames?
- What stable frame represents idle monitoring?
- Does the selected threshold remain encoded in byte 2?
- Are periodic control frames still sent while the fans are idle?

Status: ⬜ Not yet systematically tested

---
## Silent mode

Manufacturer description:

- heat recovery
- humidity sensor inactive
- twilight sensor inactive
- reduced airflow

Observed activation:

```text
0132083B
01320033
```

Observed repeating sequence:

```text
01280029
01200021
01240025
01200021
```

Measured timing:

| Phase | Duration |
|-------|---------:|
| Direction phase A | ~60 s |
| Transition | ~10 s |
| Direction phase B | ~60 s |
| Transition | ~10 s |

The sequence repeats continuously.

Current interpretation:

| Frame | Meaning | Status |
|-------|---------|:------:|
| `0132083B` | Generic mode transition | ✅ |
| `01320033` | Generic mode transition | ✅ |
| `01280029` | Direction phase A | ✅ |
| `01200021` | Direction transition | ✅ |
| `01240025` | Direction phase B | ✅ |

The sequence is structurally identical to the manual alternating mode but uses its own dedicated frame set.

Status: ✅ Confirmed


---

## Timed extract mode

Observed sequence:

```
0132083B
01320033
01370036
```

Twenty minutes later:

```
01330436
01360433
```

Interpretation:

- `0132083B` and `01320033` appear to be generic mode-transition frames.
- During the timed interval the controller continuously transmits the normal Extract Speed 3 frame (`01370036`).
- After approximately 20 minutes the controller restores the previous operating mode.
- Because humidity was still above the configured threshold, the controller returned directly to the automatic humidity-alarm frame (`01360433`).

Open question:

- Does `01330436` represent a generic return transition or an alarm-specific return frame?

---


## Short request and response frames

Observed pattern:

```text
Panel → Fans: 020002
Fans  → Panel: 000202
```

and:

```text
Panel → Fans: 020406
Fans  → Panel: 000A0A
```

The request/reply exchange occurs approximately every six seconds.

Current hypothesis:

- `020002` requests basic status
- `020406` requests extended or alarm-related status
- replies encode current master status

Status: 🟡 Meaning not fully decoded

---

## Discarded or corrected hypotheses

### Short frames were invalid packets

Initial assumption:

> Three-byte frames were malformed because they did not use the four-byte XOR format.

Correction:

> They are legitimate request and response frames with a different structure.

### Humidity alarm uses opposing fan directions

Initial assumption:

> One fan supplies air while the other extracts during alarm.

Correction:

> Both master and slave operate in extract mode during humidity alarm.

### Fixed modes had one permanent frame each

Initial assumption:

> Each fixed mode and speed had one globally constant frame.

Correction:

> Byte 2 also carries the currently selected humidity threshold, even when the mode itself does not use humidity regulation.

---

## Next experiments


1. Map Monitoring for all three humidity thresholds.
2. Record Automatic normal operation below the humidity threshold.
3. Identify manual speed-3 direction phase B.
4. Decode the short fan response payloads.
5. Verify byte-2 humidity bits using fixed modes at thresholds 2 and 3.
6. Determine whether transition frames must be sent by the gateway or are optional.

---

## Experimental procedure

For each test:

1. Record initial mode and selected humidity threshold.
2. Start the transparent decoder gateway.
3. Change exactly one panel setting.
4. Wait at least 10–15 seconds.
5. Record:
   - first control frame
   - stable control frame
   - master airflow direction
   - slave airflow direction
   - request frame
   - reply frame
6. Repeat the same setting from a different previous state.
7. Mark results as verified only after repeated observation.
