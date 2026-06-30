# DAQ File-Thread Bug Fix — EDR5COM Portable Accelerometer

**Project type:** C++ / Qt bug fix + code review  
**Domain:** Embedded / portable DAQ instruments  
**File:** `HFileThreads.cpp` — USB download and UDF/CSV export threads

---

## What this is

The EDR5COM is a portable data acquisition instrument that records 3-axis accelerometer data onto an SD card. This repository contains a cleaned-up and bug-fixed version of `HFileThreads.cpp`, the Qt C++ source file that:

1. Downloads accelerometer data from the instrument over USB
2. Writes it to a UDF (User Data File) format (`HUdfFileWriteThread`)
3. Alternatively exports it as a UTF-16 CSV file (`HExportFileWriteThread`)

Both thread classes use Qt's `QThread` / `QMutex` / `QWaitCondition` for threading and support both block-by-block and USB streaming read modes.

---

## Bugs fixed

### BUG-1 — Double-free in `cleanup()`

**Location:** `HUdfFileWriteThread::cleanup()` and `HExportFileWriteThread::cleanup()`

**Root cause:**  
Both classes allocate `data_buffer` and `event_buffer` in `setupThread()`, then free them in `cleanup()`. The original `cleanup()` deleted the pointers but did not null them out:

```cpp
// BEFORE (broken)
void HUdfFileWriteThread::cleanup(void)
{
    if (data_buffer)  delete [] data_buffer;    // pointer not nulled
    if (event_buffer) delete [] event_buffer;   // pointer not nulled
}
```

`addRecorder()` calls `cleanup()` before allocating new buffers. If `addRecorder()` was called more than once (e.g., multi-recorder download), the second `cleanup()` call saw non-null dangling pointers and attempted a second `delete[]` on already-freed memory — **undefined behaviour**, typically a crash.

**Fix:**

```cpp
// AFTER (fixed)
void HUdfFileWriteThread::cleanup(void)
{
    delete [] data_buffer;
    data_buffer = nullptr;    // prevents dangling pointer

    delete [] event_buffer;
    event_buffer = nullptr;   // prevents dangling pointer
}
```

Note: `delete[] nullptr` is a no-op in C++, so the `if` guards are unnecessary and were removed.

---

### BUG-2 — Partial allocation leak on `std::bad_alloc`

**Location:** `run()` impact-event loop in both classes (~line 370 and ~line 470 in the original)

**Root cause:**  
Inside the impact-event loop, three float arrays (`xAxis`, `yAxis`, `zAxis`) are allocated in sequence. If the second or third allocation throws `std::bad_alloc`, the already-allocated arrays are not freed before the exception is caught:

```cpp
// BEFORE (broken)
try {
    xAxis = new float[numSamples + 2*SAMPLES_PER_BLOCK];  // succeeds
    yAxis = new float[numSamples + 2*SAMPLES_PER_BLOCK];  // succeeds
    zAxis = new float[numSamples + 2*SAMPLES_PER_BLOCK];  // throws bad_alloc
}
catch (std::bad_alloc &ba) {
    // xAxis and yAxis are already allocated — they leak here
    emit some_error(FILETHREAD_ERROR_BAD_ALLOC);
    running = false;
    break;
}
```

Under low-memory conditions this causes a memory leak for the lifetime of the process.

**Fix:**

```cpp
// AFTER (fixed)
catch (std::bad_alloc &)
{
    delete [] xAxis; xAxis = nullptr;
    delete [] yAxis; yAxis = nullptr;
    delete [] zAxis; zAxis = nullptr;

    emit some_error(FILETHREAD_ERROR_BAD_ALLOC);
    running = false;
    break;
}
```

The same fix was applied to the slow-track channel arrays (`slwIntTemp`, `slwExtTemp`, `slwBattery`, `slwHumidity`) in the slow-track sub-loop.

---

## Additional improvements

| Item | Original | Fixed |
|---|---|---|
| Null literal | `NULL` (C-style macro) | `nullptr` (C++11 type-safe) |
| `logfile` after `fclose()` | not nulled — potential use-after-close | nulled immediately after `fclose()` |
| Dead-code note | `if (udfFile == NULL) return false;` — unreachable because `new` throws, never returns null in C++ | kept with explanatory comment |
| Section comments | minimal | added threading protocol description, phase labels for `run()`, per-method doc comments |

---

## Code structure

```
HFileThreads.cpp
├── HUdfFileWriteThread           — produces UDF binary files
│   ├── Constructor / Destructor
│   ├── setUsbCom()               — connects USB signal → fillStreamBuffer slot
│   ├── cleanup()                 — BUG-1 fix: delete + nullptr
│   ├── initFile() / addRecorder() / setupFileInfo()
│   ├── setupThread()             — allocates download buffers
│   ├── fillBuffer()              — block-by-block USB read path
│   ├── fillStreamBuffer()        — streaming USB path (got_stream signal)
│   ├── run()                     — main loop: read tags → count events → download
│   ├── processBuffer()           — ADC raw → float g-values
│   ├── processWindowMode()       — window-mode event culling
│   ├── savePsuedoEvents()        — split packed pseudo-events
│   ├── extractEventConditions()  — temperature / battery from slow-track tags
│   └── logEvent()                — human-readable event log
│
└── HExportFileWriteThread        — produces UTF-16 CSV files
    ├── (mirrors HUdfFileWriteThread structure)
    └── saveEvent()               — writes time,X,Y,Z rows to QTextStream
```

---

## Why these bugs matter in practice

Both bugs are **triggered only under specific runtime conditions** that don't occur in normal single-recorder use:

- **BUG-1** surfaces during a **multi-recorder download** — the code path that calls `addRecorder()` more than once per session. On crash-prone hardware this path can be hit surprisingly often.
- **BUG-2** surfaces only when the OS is under **memory pressure** — large datasets on instruments with long recordings, or when the host PC is low on RAM. The leak is small per event but accumulates over a long download session, eventually triggering the very `bad_alloc` it was meant to handle.

---

## Testing the fixes

Unit testing this code requires a mock USB layer. To verify the BUG-1 fix manually:

1. Set a breakpoint at the second `cleanup()` call in `addRecorder()`.
2. Inspect `data_buffer` and `event_buffer` — they must be `nullptr` after the first call.
3. Confirm no crash or heap error on the second `delete[]`.

To stress-test BUG-2: use Valgrind or AddressSanitizer with a small custom allocator that fails on the 3rd allocation call inside the try block.

---

## Skills demonstrated

- Manual memory management in C++ (`new[]` / `delete[]`, `nullptr` discipline)
- Qt threading model (`QThread`, `QMutex`, `QWaitCondition`, signals/slots)
- Exception-safe resource management (`std::bad_alloc`, partial allocation cleanup)
- Code archaeology — reading and reasoning about legacy Qt C++ without full project context
- Minimal-diff bug fixing — preserving original logic while correcting only the defects
