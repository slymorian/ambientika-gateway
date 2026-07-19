# Ambientika RS485 Frame Database

> Alphabetical reference of observed frames on the wired Südwind Ambientika control bus.

**Status:** Work in progress

## Status legend

| Symbol | Meaning |
|:------:|---------|
| ✅ | Verified by repeated observation |
| 🟡 | Plausible interpretation, not fully verified |
| ⬜ | Unknown |

---

## Four-byte control frames

The fourth byte is the XOR checksum of bytes 1–3.

| Frame | Direction | Mode / meaning | Speed / threshold | State | Status |
|-------|-----------|----------------|-------------------|-------|:------:|
| `01250024` | Panel → Fans | Master supply, slave extract | Speed 1 | Stable | ✅ |
| `0125082C` | Panel → Fans | Master supply, slave extract | Speed 1 | Setting change | ✅ |
| `01260027` | Panel → Fans | Master supply, slave extract | Speed 2 | Stable | ✅ |
| `0126082F` | Panel → Fans | Master supply, slave extract | Speed 2 | Setting change | ✅ |
| `01270026` | Panel → Fans | Master supply, slave extract | Speed 3 | Stable | ✅ |
| `0127082E` | Panel → Fans | Master supply, slave extract | Speed 3 | Setting change | ✅ |
| `01280029` | Panel → Fans | Silent | Direction phase A | Stable | ✅ |
| `01290028` | Panel → Fans | Master extract, slave supply | Speed 1 | Stable | ✅ |
| `01290820` | Panel → Fans | Master extract, slave supply | Speed 1 | Setting change | ✅ |
| `012A002B` | Panel → Fans | Master extract, slave supply | Speed 2 | Stable | ✅ |
| `012A0823` | Panel → Fans | Master extract, slave supply | Speed 2 | Setting change | ✅ |
| `012B002A` | Panel → Fans | Master extract, slave supply | Speed 3 | Stable | ✅ |
| `012B0822` | Panel → Fans | Master extract, slave supply | Speed 3 | Setting change | ✅ |
| `01320033` | Panel → Fans | Generic Mode Active | ✅ |
| `0132083B` | Panel → Fans | Generic Mode Transition | ✅ |
| `01330436` | Return transition from timed extract | 🟡 |
| `01350034` | Panel → Fans | Extract | Speed 1 | Stable | ✅ |
| `0135083C` | Panel → Fans | Extract | Speed 1 | Setting change | ✅ |
| `01360037` | Panel → Fans | Extract | Speed 2 | Stable | ✅ |
| `01360433` | Panel → Fans | Automatic | Humidity threshold 1 | Humidity alarm active | ✅ |
| `0136083F` | Panel → Fans | Extract | Speed 2 | Setting change | ✅ |
| `01360C3B` | Panel → Fans | Automatic | Humidity threshold 1 | Setting change with alarm | ✅ |
| `01370036` | Panel → Fans | Extract | Speed 3 | Stable | ✅ |
| `0137083E` | Panel → Fans | Extract | Speed 3 | Setting change | ✅ |
| `01390038` | Panel → Fans | Supply | Speed 1 | Stable | ✅ |
| `01390830` | Panel → Fans | Supply | Speed 1 | Setting change | ✅ |
| `013A003B` | Panel → Fans | Supply | Speed 2 | Stable | ✅ |
| `013A0833` | Panel → Fans | Supply | Speed 2 | Setting change | ✅ |
| `013B003A` | Panel → Fans | Supply | Speed 3 | Stable | ✅ |
| `013B0832` | Panel → Fans | Supply | Speed 3 | Setting change | ✅ |
| `01760473` | Panel → Fans | Automatic | Humidity threshold 2 | Humidity alarm active | ✅ |
| `01760C7B` | Panel → Fans | Automatic | Humidity threshold 2 | Setting change with alarm | ✅ |
| `01A100A0` | Panel → Fans | Manual alternating | Speed 1 | Transition | ✅ |
| `01A200A3` | Panel → Fans | Manual alternating | Speed 2 | Transition | ✅ |
| `01A300A2` | Panel → Fans | Manual alternating | Speed 3 | Transition | 🟡 |
| `01A500A4` | Panel → Fans | Manual alternating | Speed 1 | Direction phase A | ✅ |
| `01A600A7` | Panel → Fans | Manual alternating | Speed 2 | Direction phase B | ✅ |
| `01A700A6` | Panel → Fans | Manual alternating | Speed 3 | Direction phase A | 🟡 |
| `01A900A8` | Panel → Fans | Manual alternating | Speed 1 | Direction phase B | ✅ |
| `01AA00AB` | Panel → Fans | Manual alternating | Speed 2 | Direction phase A | ✅ |
| `01B604B3` | Panel → Fans | Automatic | Humidity threshold 3 | Humidity alarm active | ✅ |
| `01B60CBB` | Panel → Fans | Automatic | Humidity threshold 3 | Setting change with alarm | ✅ |

---

## Short frames

### Panel → Fans

| Frame | Meaning | Status |
|-------|---------|:------:|
| `020002` | Status request | ✅ |
| `020406` | Extended status request | ✅ |

### Fans → Panel

| Frame | Meaning | Status |
|-------|---------|:------:|
| `000000` | Startup / initialization | 🟡 |
| `000101` | Startup / initialization | 🟡 |
| `000202` | Status reply | ✅ |
| `000A0A` | Extended status reply | ✅ |

---

## Known frame flags

| Byte 3 value | Meaning | Status |
|-------------:|---------|:------:|
| `00` | Stable operating state | ✅ |
| `04` | Humidity alarm active | ✅ |
| `08` | Setting change / transition flag | ✅ |
| `0C` | Setting change while humidity alarm is active | ✅ |

---

## Notes

- Full packets are transmitted as ASCII hexadecimal characters between `STX` (`0x02`) and `ETX` (`0x03`).
- The fourth byte of four-byte control frames is the XOR checksum of bytes 1–3.
- Bits in byte 2 appear to encode humidity threshold, mode and fan speed.
- The same selected humidity threshold appears to remain encoded even in modes where humidity regulation is inactive.
