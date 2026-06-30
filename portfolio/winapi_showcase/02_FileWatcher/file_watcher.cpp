// File System Watcher — WinAPI Showcase
// Demonstrates: ReadDirectoryChangesW, OVERLAPPED I/O, CreateEvent,
//               WaitForSingleObjectEx, winapi::Handle RAII, std::thread/mutex/queue

#include "../common/win_handle.h"
#include <windows.h>
#include <iostream>
#include <iomanip>
#include <string>
#include <thread>
#include <atomic>
#include <mutex>
#include <queue>
#include <functional>
#include <chrono>
#include <stdexcept>

#pragma comment(lib, "kernel32.lib")

struct FileEvent {
    DWORD       action;
    std::wstring filename;
    std::wstring timestamp;
};

std::wstring ActionToString(DWORD action) {
    switch (action) {
        case FILE_ACTION_ADDED:            return L"CREATED";
        case FILE_ACTION_REMOVED:          return L"DELETED";
        case FILE_ACTION_MODIFIED:         return L"MODIFIED";
        case FILE_ACTION_RENAMED_OLD_NAME: return L"RENAMED_FROM";
        case FILE_ACTION_RENAMED_NEW_NAME: return L"RENAMED_TO";
        default:                           return L"UNKNOWN";
    }
}

std::wstring NowTimestamp() {
    SYSTEMTIME st;
    GetLocalTime(&st);
    wchar_t buf[32];
    swprintf_s(buf, L"%02d:%02d:%02d.%03d",
        st.wHour, st.wMinute, st.wSecond, st.wMilliseconds);
    return buf;
}

// ─────────────────────────────────────────────────────────────────────────────
// DirectoryWatcher
// Wraps ReadDirectoryChangesW with OVERLAPPED I/O.
// m_hDir / m_hEvent are RAII-managed via winapi::Handle — no explicit
// CloseHandle anywhere in this class.
// ─────────────────────────────────────────────────────────────────────────────
class DirectoryWatcher {
public:
    using Callback = std::function<void(const FileEvent&)>;

    explicit DirectoryWatcher(std::wstring path)
        : m_path(std::move(path))
        , m_hDir (nullptr, winapi::Handle::Sentinel::Invalid)
        , m_hEvent(nullptr, winapi::Handle::Sentinel::Null)
        , m_running(false)
    {}

    // Non-copyable — owns a thread + OS handles
    DirectoryWatcher(const DirectoryWatcher&) = delete;
    DirectoryWatcher& operator=(const DirectoryWatcher&) = delete;

    ~DirectoryWatcher() { Stop(); }

    // Returns true on success, false if path is invalid or access denied.
    bool Start(Callback cb) {
        if (m_running) return false;  // idempotent

        m_callback = std::move(cb);

        // Open directory handle for overlapped I/O
        winapi::Handle hDir(
            CreateFileW(
                m_path.c_str(),
                FILE_LIST_DIRECTORY,
                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                nullptr,
                OPEN_EXISTING,
                FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OVERLAPPED,
                nullptr),
            winapi::Handle::Sentinel::Invalid);

        if (!hDir) {
            std::wcerr << L"CreateFile failed (" << GetLastError() << L"): "
                       << m_path << L"\n";
            return false;
        }

        // Auto-reset event — signals either a directory change or Stop()
        winapi::Handle hEvent(
            CreateEventW(nullptr, /*bManualReset=*/FALSE, /*bInitialState=*/FALSE, nullptr),
            winapi::Handle::Sentinel::Null);

        if (!hEvent) {
            std::wcerr << L"CreateEvent failed: " << GetLastError() << L"\n";
            return false;
        }

        m_hDir   = std::move(hDir);
        m_hEvent = std::move(hEvent);
        m_running = true;
        m_thread  = std::thread(&DirectoryWatcher::WatchLoop, this);
        return true;
    }

    void Stop() {
        if (!m_running.exchange(false)) return;
        // Signal the event so WatchLoop unblocks from WaitForSingleObjectEx
        if (m_hEvent) SetEvent(m_hEvent.get());
        if (m_thread.joinable()) m_thread.join();
        // Handles closed automatically by winapi::Handle destructor
    }

    // Thread-safe snapshot of accumulated events
    std::queue<FileEvent> DrainEvents() {
        std::lock_guard<std::mutex> lk(m_mtx);
        std::queue<FileEvent> out;
        std::swap(m_queue, out);
        return out;
    }

private:
    void WatchLoop() {
        alignas(DWORD) BYTE buffer[4096];
        OVERLAPPED ov{};
        ov.hEvent = m_hEvent.get();

        while (m_running) {
            DWORD bytesReturned = 0;

            BOOL ok = ReadDirectoryChangesW(
                m_hDir.get(),
                buffer, sizeof(buffer),
                /*bWatchSubtree=*/TRUE,
                FILE_NOTIFY_CHANGE_FILE_NAME  |
                FILE_NOTIFY_CHANGE_DIR_NAME   |
                FILE_NOTIFY_CHANGE_LAST_WRITE |
                FILE_NOTIFY_CHANGE_SIZE,
                /*lpBytesReturned=*/nullptr,   // must be null for async
                &ov,
                /*lpCompletionRoutine=*/nullptr);

            if (!ok) {
                const DWORD err = GetLastError();
                // ERROR_OPERATION_ABORTED == Stop() was called while we waited
                if (err != ERROR_OPERATION_ABORTED) {
                    std::wcerr << L"ReadDirectoryChangesW error: " << err << L"\n";
                }
                break;
            }

            DWORD wait = WaitForSingleObjectEx(m_hEvent.get(), INFINITE, FALSE);
            if (!m_running) break;
            if (wait != WAIT_OBJECT_0) continue;

            if (!GetOverlappedResult(m_hDir.get(), &ov, &bytesReturned, FALSE)) break;
            if (bytesReturned == 0) continue;

            // Walk the variable-length notification chain
            const BYTE* ptr = buffer;
            for (;;) {
                const auto* info = reinterpret_cast<const FILE_NOTIFY_INFORMATION*>(ptr);
                std::wstring fname(info->FileName,
                                   info->FileNameLength / sizeof(WCHAR));
                FileEvent ev{ info->Action, std::move(fname), NowTimestamp() };

                {
                    std::lock_guard<std::mutex> lk(m_mtx);
                    m_queue.push(ev);
                }
                if (m_callback) m_callback(ev);

                if (info->NextEntryOffset == 0) break;
                ptr += info->NextEntryOffset;
            }
        }
    }

    std::wstring          m_path;
    winapi::Handle        m_hDir;
    winapi::Handle        m_hEvent;
    std::atomic<bool>     m_running;
    std::thread           m_thread;
    std::mutex            m_mtx;
    std::queue<FileEvent> m_queue;
    Callback              m_callback;
};

// ─────────────────────────────────────────────────────────────────────────────
int wmain(int argc, wchar_t* argv[]) {
    std::wstring watchPath = (argc > 1) ? argv[1] : L".";

    std::wcout << L"=== File System Watcher (WinAPI showcase) ===\n";
    std::wcout << L"Watching: " << watchPath << L"\n";
    std::wcout << L"Press Enter to stop.\n\n";

    DirectoryWatcher watcher(watchPath);

    std::mutex printMtx;
    bool started = watcher.Start([&](const FileEvent& ev) {
        std::lock_guard<std::mutex> lk(printMtx);
        std::wcout << L"[" << ev.timestamp << L"] "
                   << std::left << std::setw(14) << ActionToString(ev.action)
                   << L" " << ev.filename << L"\n";
    });

    if (!started) {
        std::wcerr << L"Failed to start watcher for: " << watchPath << L"\n";
        return 1;
    }

    std::string dummy;
    std::getline(std::cin, dummy);
    watcher.Stop();

    std::wcout << L"Watcher stopped.\n";
    return 0;
}
