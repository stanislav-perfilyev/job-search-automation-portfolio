#include "ProcessInfo.h"
#include <iostream>
#include <iomanip>
#include <string>
#include <thread>
#include <atomic>
#include <mutex>
#include <chrono>
#include <sstream>

using namespace process_monitor;

namespace {
constexpr int kProcessNameColumnWidth = 38;
} // namespace

// Monitor: periodically refreshes snapshot in background thread
class ProcessMonitor {
public:
    explicit ProcessMonitor(std::unique_ptr<IProcessEnumerator> enumerator,
                            std::chrono::milliseconds interval = std::chrono::seconds(2))
        : m_enumerator(std::move(enumerator))
        , m_interval(interval)
        , m_running(false)
    {}

    void start() {
        if (m_running.exchange(true)) return;  // idempotent — safe to call multiple times
        m_worker = std::thread(&ProcessMonitor::workerLoop, this);
    }

    void stop() {
        m_running = false;
        if (m_worker.joinable()) m_worker.join();
    }

    std::vector<ProcessInfo> snapshot() const {
        std::lock_guard<std::mutex> lk(m_mutex);
        return m_snapshot;
    }

    ~ProcessMonitor() { stop(); }

private:
    void workerLoop() {
        while (m_running) {
            try {
                auto data = m_enumerator->enumerate();
                std::lock_guard<std::mutex> lk(m_mutex);
                m_snapshot = std::move(data);
            } catch (const std::exception& e) {
                std::wostringstream oss;
                oss << L"Monitor error: " << e.what() << L"\n";
                std::wcerr << oss.str();
            }
            std::this_thread::sleep_for(m_interval);
        }
    }

    std::unique_ptr<IProcessEnumerator> m_enumerator;
    std::chrono::milliseconds           m_interval;
    std::atomic<bool>                   m_running;
    std::thread                         m_worker;
    mutable std::mutex                  m_mutex;
    std::vector<ProcessInfo>            m_snapshot;
};

static void printSnapshot(const std::vector<ProcessInfo>& procs, size_t topN = 20) {
    std::wostringstream header;
    header << L"\n" << std::wstring(72, L'-') << L"\n"
           << std::left
           << std::setw(8)  << L"PID"
           << std::setw(kProcessNameColumnWidth) << L"Process"
           << std::setw(14) << L"WorkSet (MB)"
           << std::setw(8)  << L"Threads"
           << L"\n"
           << std::wstring(72, L'-') << L"\n";
    std::wcout << header.str();

    const size_t shown = std::min(topN, procs.size());
    for (size_t i = 0; i < shown; ++i) {
        const auto& p = procs[i];
        std::wostringstream row;
        row << std::left
            << std::setw(8)  << p.pid
            << std::setw(kProcessNameColumnWidth) << p.name.substr(0, kProcessNameColumnWidth - 1)
            << std::setw(14) << p.workingSetMB
            << std::setw(8)  << p.threadCount
            << L"\n";
        std::wcout << row.str();
    }

    std::wostringstream footer;
    footer << L"\nTotal: " << procs.size() << L" processes\n";
    std::wcout << footer.str();
}

int main() {
    std::wcout << L"=== Process Monitor v2 ===\n";
    std::wcout << L"Top-20 by Working Set. [Enter]=refresh  [q+Enter]=quit\n\n";

    ProcessMonitor monitor(std::make_unique<WinProcessEnumerator>());
    monitor.start();

    std::this_thread::sleep_for(std::chrono::milliseconds(600));

    std::string input;
    while (true) {
        printSnapshot(monitor.snapshot(), 20);
        std::wcout << L"\n> ";
        std::getline(std::cin, input);
        if (input == "q" || input == "Q") break;
    }
    return 0;
}
