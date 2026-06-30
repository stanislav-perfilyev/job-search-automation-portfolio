# MIL-STD-1553B Protocol Analyzer
### Анализатор протокола МКО (Мультиплексный Канал Обмена)

> Object Pascal / Delphi · Serial Bus Protocol · Avionics & Defense Systems

---

## Overview

A professional **MIL-STD-1553B protocol decoder and bus simulator** written in Object Pascal (Delphi).  
MIL-STD-1553B (known in Russian avionics as **МКО — Мультиплексный Канал Обмена**) is a military data bus standard used in aircraft, spacecraft, and defense systems since the 1970s. It operates at 1 Mbit/s with Manchester II encoding and supports up to 31 Remote Terminals on a dual-redundant serial bus.

This project demonstrates deep understanding of the protocol used at companies like **МКО Системы**, **ПАО «ОАК»**, and other defense/avionics integrators.

---

## Features

- **Full protocol decoder** — stateful machine that processes command, data, and status words
- **All message types** — BC→RT, RT→BC, RT→RT, Mode Codes, Broadcast
- **Bit-accurate word parsing** — RT address, T/R bit, subaddress, word count, all status flags
- **Error detection** — parity errors, sync errors, Manchester encoding errors, response timeouts
- **Bus simulator** — generates realistic traffic for 4 scenarios: Normal, Flight Data, High Error, Mode Code Sweep
- **Statistics** — message rates, error rates, per-type counters
- **Export** — CSV and human-readable log output
- **DUnit test suite** — 40+ tests covering every component

---

## Protocol Reference

```
MIL-STD-1553B Word Format (20 bits on wire: 3 sync + 16 data + 1 parity)

Command Word:
  [15..11] RT Address  (5 bits, 0–30 = RTs, 31 = Broadcast)
  [10]     T/R Bit     (1 = RT Transmit, 0 = RT Receive)
  [9..5]   Subaddress  (5 bits; 00000/11111 = Mode Code)
  [4..0]   Word Count  (5 bits; 0 = 32 words)

Status Word:
  [15..11] RT Address
  [10]     Message Error
  [9]      Instrumentation Bit
  [8]      Service Request
  [7..5]   Reserved
  [4]      Broadcast Command Received
  [3]      Busy
  [2]      Subsystem Flag
  [1]      Dynamic Bus Control Acceptance
  [0]      Terminal Flag (hardware fault)
```

**Message transaction examples:**

| Type | Sequence |
|------|----------|
| BC→RT | BC sends CW(Receive) → RT sends Status → BC sends N×DW |
| RT→BC | BC sends CW(Transmit) → RT sends Status + N×DW |
| RT→RT | BC sends CW(Receive, dst) + CW(Transmit, src) → RT_src sends Status + N×DW → RT_dst sends Status |
| Mode Code | BC sends CW(SA=0/31) → RT sends Status (+ optional DW) |

---

## Project Structure

```
mil1553_analyzer/
├── mil1553_analyzer.dpr      # Main Delphi project / console demo
├── src/
│   ├── MIL1553Types.pas      # Protocol types, constants, word records
│   └── MIL1553Protocol.pas   # Decoder state machine + simulator
├── tests/
│   └── TestMIL1553Protocol.pas  # DUnit test suite (40+ tests)
└── docs/
    └── mil1553b_overview.md  # Protocol quick reference
```

---

## Building

**Requires:** Delphi 10.3+ (Rio) or Lazarus 2.2+ with Free Pascal 3.2+

```bash
# Delphi (command line)
dcc32 mil1553_analyzer.dpr -I src

# Lazarus / Free Pascal
lazbuild mil1553_analyzer.lpr --build-mode=Release

# Run tests (DUnit)
dcc32 mil1553_analyzer_tests.dpr -I src -I tests
./mil1553_analyzer_tests --all
```

---

## Usage

```pascal
uses MIL1553Types, MIL1553Protocol;

// Decode a real word stream from hardware
var Decoder: TMil1553Decoder;
begin
  Decoder := TMil1553Decoder.Create('A');
  Decoder.OnMessage := procedure(const Msg: TMil1553Message)
  begin
    WriteLn(Msg.ToLogLine);
  end;

  // Feed words as they arrive from the MIL-1553 card
  // (sync type determined by hardware interface)
  Decoder.ProcessWord(HardwareReadWord, stCommand, Now, CheckParity(word));
end;
```

```pascal
// Generate test traffic (no hardware needed)
var
  Sim  : TMil1553Simulator;
  List : TObjectList;
begin
  Sim  := TMil1553Simulator.Create(ssFlightData, 'A');
  List := TObjectList.Create(True);
  try
    Sim.Generate(Now, 100, List);
    ExportToCSV(TList(List), 'flight_data.csv');
  finally
    Sim.Free;
    List.Free;
  end;
end;
```

---

## Sample Output

```
#1      BC→RT       Bus-A  RT=01  SA=01  WC=01  DC=1
#2      RT→BC       Bus-A  RT=02  SA=02  WC=02  DC=2
#3      BC→RT       Bus-A  RT=03  SA=03  WC=01  DC=1
#4      Mode Code   Bus-A  RT=04  SA=00  WC=01  DC=0
#5      RT→RT       Bus-A  RT=08  SA=03  WC=02  DC=2

Summary: 30 total, 30 valid (100%), 0 errors
```

---

## Test Coverage

| Module | Tests | Coverage |
|--------|-------|----------|
| TMil1553CommandWord | 12 | Bit extraction, direction, mode code detection |
| TMil1553StatusWord  | 11 | All status flags, IsHealthy, ToString |
| TMil1553Message     | 7  | IsValid, ErrorSummary, ToLogLine |
| TMil1553Decoder     | 9  | All message types, errors, sequential messages |
| TMil1553Simulator   | 5  | All scenarios, monotonic timestamps |
| Utility functions   | 5  | Mode codes, type names, timestamp format |

---

## Author

**Stanislav Perfilyev** — C++/Delphi systems developer  
GitHub: [github.com/stanislav-perfilyev](https://github.com/stanislav-perfilyev)  
Stack: C++17/20 · Object Pascal · Qt · Python · FastAPI · Docker · PostgreSQL

---

## License

MIT — see LICENSE file
