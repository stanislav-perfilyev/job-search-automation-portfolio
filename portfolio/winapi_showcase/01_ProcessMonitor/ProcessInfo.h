#pragma once
#include <windows.h>
#include <string>
#include <vector>
#include <optional>

namespace process_monitor {

/// Snapshot of one running process: identity, memory and thread footprint.
/// Sorts descending by working-set size via operator< (see below), which is
/// what powers the "top-N by memory" view in process_monitor.cpp.
struct ProcessInfo {
    DWORD        pid         = 0;
    std::wstring name;
    SIZE_T       workingSetMB = 0;
    DWORD        threadCount  = 0;

    // For sorting / display
    bool operator<(const ProcessInfo& o) const {
        return workingSetMB > o.workingSetMB; // descending by memory
    }
};

/// Abstract interface — allows unit-testing without real WinAPI calls.
/// Production code uses WinProcessEnumerator; tests inject a stub that
/// returns canned data with zero WinAPI dependency.
class IProcessEnumerator {
public:
    virtual ~IProcessEnumerator() = default;
    [[nodiscard]] virtual std::vector<ProcessInfo> enumerate() const = 0;
};

/// Concrete WinAPI implementation: EnumProcesses + ToolHelp32 snapshots.
class WinProcessEnumerator : public IProcessEnumerator {
public:
    [[nodiscard]] std::vector<ProcessInfo> enumerate() const override;


    // Implementation note: per-process helpers (getProcessName, getThreadCount,
    // getWorkingSetMB) were inlined or promoted to module-level static functions
    // (buildNameMap / buildThreadCountMap) in ProcessMonitor.cpp for O(N) performance.
};

} // namespace process_monitor
