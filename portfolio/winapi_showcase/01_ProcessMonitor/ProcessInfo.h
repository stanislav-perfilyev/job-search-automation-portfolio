#pragma once
#include <windows.h>
#include <string>
#include <vector>
#include <optional>

namespace process_monitor {

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

// Abstract interface — allows unit-testing without real WinAPI calls
class IProcessEnumerator {
public:
    virtual ~IProcessEnumerator() = default;
    virtual std::vector<ProcessInfo> enumerate() const = 0;
};

// Concrete WinAPI implementation
class WinProcessEnumerator : public IProcessEnumerator {
public:
    std::vector<ProcessInfo> enumerate() const override;


    // Implementation note: per-process helpers (getProcessName, getThreadCount,
    // getWorkingSetMB) were inlined or promoted to module-level static functions
    // (buildNameMap / buildThreadCountMap) in ProcessMonitor.cpp for O(N) performance.
};

} // namespace process_monitor
