#include "ProcessInfo.h"
#include "../common/win_handle.h"
#include <psapi.h>
#include <tlhelp32.h>
#include <algorithm>
#include <unordered_map>

#pragma comment(lib, "psapi.lib")

namespace process_monitor {

// ─────────────────────────────────────────────────────────────────────────────
// Build pid→name map from a single SNAPPROCESS snapshot  O(N)
// ─────────────────────────────────────────────────────────────────────────────
static std::unordered_map<DWORD, std::wstring> buildNameMap() {
    std::unordered_map<DWORD, std::wstring> map;

    auto snap = winapi::create_snapshot(TH32CS_SNAPPROCESS);
    if (!snap) return map;

    PROCESSENTRY32W pe{};
    pe.dwSize = sizeof(pe);

    if (Process32FirstW(*snap, &pe)) {
        do {
            map[pe.th32ProcessID] = pe.szExeFile;
        } while (Process32NextW(*snap, &pe));
    }
    return map;
}

// ─────────────────────────────────────────────────────────────────────────────
// Build pid→threadCount map from a single SNAPTHREAD snapshot  O(N)
// ─────────────────────────────────────────────────────────────────────────────
static std::unordered_map<DWORD, DWORD> buildThreadCountMap() {
    std::unordered_map<DWORD, DWORD> map;

    auto snap = winapi::create_snapshot(TH32CS_SNAPTHREAD);
    if (!snap) return map;

    THREADENTRY32 te{};
    te.dwSize = sizeof(te);

    if (Thread32First(*snap, &te)) {
        do {
            ++map[te.th32OwnerProcessID];
        } while (Thread32Next(*snap, &te));
    }
    return map;
}

// ─────────────────────────────────────────────────────────────────────────────
// enumerate() — O(N log N) total (sorting dominates)
// Previously O(N²): 2 new snapshots per process.
// Now: 2 snapshots total, then O(1) hash-map lookups per process.
// ─────────────────────────────────────────────────────────────────────────────
namespace {
constexpr DWORD  kMaxTrackedProcesses = 2048;
constexpr SIZE_T kBytesPerMB          = 1024 * 1024;
} // namespace

std::vector<ProcessInfo> WinProcessEnumerator::enumerate() const {
    DWORD pids[kMaxTrackedProcesses];
    DWORD cbNeeded = 0;

    if (!EnumProcesses(pids, sizeof(pids), &cbNeeded)) {
        winapi::throw_last_error("EnumProcesses");
    }

    // Build lookup maps once (2 snapshots total, not 2×N)
    const auto nameMap    = buildNameMap();
    const auto threadMap  = buildThreadCountMap();

    const DWORD count = cbNeeded / sizeof(DWORD);
    std::vector<ProcessInfo> result;
    result.reserve(count);

    constexpr DWORD ACCESS = PROCESS_QUERY_INFORMATION | PROCESS_VM_READ;

    for (DWORD i = 0; i < count; ++i) {
        const DWORD pid = pids[i];
        if (pid == 0) continue;  // System Idle

        ProcessInfo pi;
        pi.pid = pid;

        if (auto it = nameMap.find(pid); it != nameMap.end())
            pi.name = it->second;
        else
            pi.name = L"<unknown>";

        if (auto it = threadMap.find(pid); it != threadMap.end())
            pi.threadCount = it->second;

        // OpenProcess per-pid is unavoidable — no snapshot alternative
        if (winapi::Handle hProc = winapi::open_process(ACCESS, pid)) {
            PROCESS_MEMORY_COUNTERS pmc{};
            pmc.cb = sizeof(pmc);
            if (GetProcessMemoryInfo(*hProc, &pmc, sizeof(pmc)))
                pi.workingSetMB = pmc.WorkingSetSize / kBytesPerMB;
        }

        result.push_back(std::move(pi));
    }

    std::sort(result.begin(), result.end());
    return result;
}

} // namespace process_monitor
