# Ambientika RS485 Protocol

> Reverse engineering notes for the wired Südwind Ambientika control bus.

**Project status:** Work in progress


Related documents:

- [Complete frame database](frame_database.md)
- [Reverse engineering laboratory notes](reverse_engineering.md)

---

# Frame format

A control frame consists of four bytes.

| Byte | Meaning |
|------|---------|
| 1 | Frame type (currently always `0x01`) |
| 2 | Operating mode, fan speed and humidity threshold |
| 3 | Status flags |
| 4 | XOR checksum of bytes 1–3 |

---

# Byte 3

Currently known values:

| Value | Meaning | Status |
|------:|---------|:------:|
| `00` | Stable operating state | ✅ |
| `04` | Humidity alarm active | ✅ |
| `08` | Parameter change / transition | ✅ |
| `0C` | Parameter change while humidity alarm is active | ✅ |

---

# Manual operating modes

Humidity threshold set to **1 drop**

| Mode | Speed | Transition frame | Stable frame | Status |
|------|------:|------------------|--------------|:------:|
| Supply | 1 | `01390830` | `01390038` | ✅ |
| Supply | 2 | `013A0833` | `013A003B` | ✅ |
| Supply | 3 | `013B0832` | `013B003A` | ✅ |
| Extract | 1 | `0135083C` | `01350034` | ✅ |
| Extract | 2 | `0136083F` | `01360037` | ✅ |
| Extract | 3 | `0137083E` | `01370036` | ✅ |
| Master → Extract / Slave → Supply | 1 | `01290820` | `01290028` | ✅ |
| Master → Extract / Slave → Supply | 2 | `012A0823` | `012A002B` | ✅ |
| Master → Extract / Slave → Supply | 3 | `012B0822` | `012B002A` | ✅ |
| Master → Supply / Slave → Extract | 1 | `0125082C` | `01250024` | ✅ |
| Master → Supply / Slave → Extract | 2 | `0126082F` | `01260027` | ✅ |
| Master → Supply / Slave → Extract | 3 | `0127082E` | `01270026` | ✅ |

---

# Automatic mode

## Humidity alarm active

| Threshold | Transition frame | Stable frame | Status |
|-----------|------------------|--------------|:------:|
| 1 drop | `01360C3B` | `01360433` | ✅ |
| 2 drops | `01760C7B` | `01760473` | ✅ |
| 3 drops | `01B60CBB` | `01B604B3` | ✅ |

---

---

# Silent mode

The Silent (night) mode uses alternating heat-recovery ventilation.

Observed sequence:

| Phase | Frame | Duration | Status |
|------|---------|---------:|:------:|
| Mode selected (transition) | `0132083B` | ~1 s | ✅ |
| Mode active | `01320033` | ~9 s | ✅ |
| Direction phase A | `01280029` | ~60 s | ✅ |
| Transition | `01200021` | ~10 s | ✅ |
| Direction phase B | `01240025` | ~60 s | ✅ |
| Transition | `01200021` | ~10 s | ✅ |

Repeated observation confirms that the sequence continues cyclically.

Characteristics:

- alternating heat recovery
- humidity sensor inactive
- twilight sensor inactive
- reduced airflow

---

# Timed extract mode

According to the manufacturer documentation, this mode forces extract
ventilation for approximately 20 minutes before returning to the
previous operating mode.

Observed activation:

| Frame | Meaning | Status |
|-------|---------|:------:|
| `0132083B` | Mode transition | 🟡 |
| `01320033` | Mode transition | 🟡 |
| `01370036` | Extract, speed 3 | ✅ |

Observed timeout:

| Frame | Meaning | Status |
|-------|---------|:------:|
| `01330436` | Return transition | 🟡 |
| `01360433` | Return to previous mode (Automatic, humidity alarm active) | ✅ |

Measured duration:

- approximately **20 minutes**

Status: 🟡 Mostly understood
---


# Short frames

## Panel → Fans

| Frame | Meaning | Status |
|-------|---------|:------:|
| `020002` | Status request | ✅ |
| `020406` | Extended status request | ✅ |

## Fans → Panel

| Frame | Meaning | Status |
|-------|---------|:------:|
| `000202` | Status reply | ✅ |
| `000A0A` | Extended status reply | ✅ |

---

# Current understanding

## Byte 2

Current hypothesis:

- encodes operating mode
- encodes fan speed
- encodes humidity threshold

Status: 🟡

---

## Byte 3

Current understanding:

| Bit | Meaning | Status |
|----:|---------|:------:|
| `0x04` | Humidity alarm | ✅ |
| `0x08` | Parameter transition | ✅ |

---

# Open questions

- ⬜ Monitoring mode
- ⬜ Automatic mode (normal operation)
- ⬜ Automatic mode (direction changes)
- ⬜ Meaning of all Byte-2 bit fields
- ⬜ Complete state machine


---

# Reverse engineering status

| Area | Status |
|------|:------:|
| Manual modes | ✅ Complete |
| Automatic mode (alarm) | ✅ Complete |
| Automatic mode (normal) | 🟡 In progress |
| Monitoring mode | ⬜ Not analysed |
| Silent mode | ✅ Complete |
| Timed extract | ✅ Mostly understood |
| Byte 3 | ✅ Mostly understood |
| Byte 2 | 🟡 Partially understood |
| Checksum | ✅ Fully understood |

---

# Changelog

| Date | Notes |
|------|-------|
| 2026-07-15 | Manual operating modes fully mapped. Automatic mode with active humidity alarm decoded. Byte-3 status bits identified. |
