# Ambientika RS485 Protocol

> Reverse engineering notes for the wired Südwind Ambientika control bus.

## Frame format

A control frame consists of four bytes.

| Byte | Meaning |
|------|---------|
| 1 | Frame type (currently always `0x01`) |
| 2 | Mode / speed / humidity threshold |
| 3 | Status flags |
| 4 | XOR checksum of bytes 1–3 |

---

## Byte 3

Known values:

| Value | Meaning |
|-------:|---------|
| `00` | Stable operating state |
| `04` | Humidity alarm active |
| `08` | Parameter change / transition |
| `0C` | Parameter change while humidity alarm active |

---

## Manual operating modes (humidity threshold = 1)

| Mode | Speed | Transition | Stable |
|------|------:|------------|--------|
| Supply | 1 | `01390830` | `01390038` |
| Supply | 2 | `013A0833` | `013A003B` |
| Supply | 3 | `013B0832` | `013B003A` |
| Extract | 1 | `0135083C` | `01350034` |
| Extract | 2 | `0136083F` | `01360037` |
| Extract | 3 | `0137083E` | `01370036` |
| Master → Supply / Slave → Extract | 1 | `01290820` | `01290028` |
| Master → Supply / Slave → Extract | 2 | `012A0823` | `012A002B` |
| Master → Supply / Slave → Extract | 3 | `012B0822` | `012B002A` |
| Master → Extract / Slave → Supply | 1 | `0125082C` | `01250024` |
| Master → Extract / Slave → Supply | 2 | `0126082F` | `01260027` |
| Master → Extract / Slave → Supply | 3 | `0127082E` | `01270026` |

---

## Automatic mode

### Humidity alarm active

| Threshold | Stable frame |
|-----------|--------------|
| 1 drop | `01360433` |
| 2 drops | `01760473` |
| 3 drops | `01B604B3` |

Transition frames:

| Threshold | Transition |
|-----------|------------|
| 1 drop | `01360C3B` |
| 2 drops | `01760C7B` |
| 3 drops | `01B60CBB` |

---

## Notes

The protocol is still under investigation.

Current hypotheses:

- Byte 2 encodes operating mode, fan speed and humidity threshold.
- Byte 3 contains status flags.
- Byte 4 is the XOR checksum.
