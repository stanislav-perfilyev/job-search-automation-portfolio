// Named Pipe Server — WinAPI IPC Showcase
// Demonstrates: CreateNamedPipe, ConnectNamedPipe, overlapped accept,
//               per-client threads, ReadFile/WriteFile, multi-client IPC,
//               winapi::Handle RAII for correct lifetime management

#include "../common/win_handle.h"
#include <windows.h>
#include <iostream>
#include <string>
#include <thread>
#include <atomic>
#include <vector>
#include <mutex>
#include <sstream>

#pragma comment(lib, "kernel32.lib")

constexpr wchar_t PIPE_NAME[] = L"\\\\.\\pipe\\winapi_showcase_ipc";
constexpr DWORD   PIPE_BUF   = 4096;

std::atomic<int>  g_clientCount{0};
std::mutex        g_printMtx;

void Log(const std::wstring& msg) {
    std::lock_guard<std::mutex> lk(g_printMtx);
    const std::wstring line = msg + L"\n";
    std::wcout << line;
}

// ─────────────────────────────────────────────────────────────────────────────
// HandleClient — takes *ownership* of the pipe handle.
// winapi::Handle ensures CloseHandle is called even if an exception is thrown.
// DisconnectNamedPipe must be called *before* Close, so we do it explicitly.
// ─────────────────────────────────────────────────────────────────────────────
void HandleClient(HANDLE rawPipe, int clientId) {
    // Transfer ownership to RAII wrapper immediately
    winapi::Handle hPipe(rawPipe, winapi::Handle::Sentinel::Invalid);

    Log(L"[Server] Client #" + std::to_wstring(clientId) + L" connected");

    char   buf[PIPE_BUF];
    DWORD  bytesRead    = 0;
    DWORD  bytesWritten = 0;

    while (true) {
        BOOL ok = ReadFile(hPipe.get(), buf, sizeof(buf) - 1, &bytesRead, nullptr);
        if (!ok || bytesRead == 0) break;

        buf[bytesRead] = '\0';
        std::string msg(buf, bytesRead);

        std::string reply = "[Server#" + std::to_string(clientId) + "] ECHO: " + msg;

        Log(L"[Server] Client #" + std::to_wstring(clientId) +
            L" sent: " + std::wstring(msg.begin(), msg.end()));

        WriteFile(hPipe.get(), reply.c_str(), static_cast<DWORD>(reply.size()),
                  &bytesWritten, nullptr);
    }

    Log(L"[Server] Client #" + std::to_wstring(clientId) + L" disconnected");
    DisconnectNamedPipe(hPipe.get());   // must precede Close
    hPipe.close();                      // explicit close before logging
    --g_clientCount;
}

// ─────────────────────────────────────────────────────────────────────────────
// Server — creates a new pipe instance per connection, dispatches each
// client to its own thread. Threads are detached (fire-and-forget).
// ─────────────────────────────────────────────────────────────────────────────
int main() {
    std::wcout << L"=== Named Pipe Server (WinAPI IPC Showcase) ===\n";
    Log(std::wstring(L"Pipe: ") + PIPE_NAME);
    std::wcout << L"Waiting for clients... (Ctrl+C to stop)\n\n";

    int nextId = 1;

    while (true) {
        winapi::Handle hPipe(
            CreateNamedPipeW(
                PIPE_NAME,
                PIPE_ACCESS_DUPLEX,
                PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
                PIPE_UNLIMITED_INSTANCES,
                PIPE_BUF, PIPE_BUF,
                0,       // default timeout
                nullptr  // default security attributes
            ),
            winapi::Handle::Sentinel::Invalid);

        if (!hPipe) {
            std::wostringstream oss;
            oss << L"CreateNamedPipe failed: " << GetLastError() << L"\n";
            std::wcerr << oss.str();
            break;
        }

        Log(L"[Server] Waiting for connection...");

        // Blocking accept — unblocks when a client calls CreateFile on the pipe
        BOOL connected = ConnectNamedPipe(hPipe.get(), nullptr)
                       ? TRUE
                       : (GetLastError() == ERROR_PIPE_CONNECTED);

        if (connected) {
            ++g_clientCount;
            // Release raw handle to the client thread — it takes ownership
            std::thread(HandleClient, hPipe.release(), nextId++).detach();
        }
        // If !connected, hPipe RAII closes it here automatically
    }

    return 0;
}
