// Named Pipe Client — WinAPI IPC Showcase
// Demonstrates: WaitNamedPipe, CreateFile on pipe, message-mode I/O,
//               winapi::Handle RAII for correct lifetime management
#include "../common/win_handle.h"
#include <windows.h>
#include <iostream>
#include <string>

#pragma comment(lib, "kernel32.lib")

constexpr wchar_t PIPE_NAME[]  = L"\\\\.\\pipe\\winapi_showcase_ipc";
constexpr DWORD   PIPE_BUF    = 4096;
constexpr int     MAX_RETRIES  = 10;  // give up after ~50 s of waiting

int main() {
    std::wcout << L"=== Named Pipe Client (WinAPI IPC Showcase) ===\n";
    std::wcout << L"Connecting to: " << PIPE_NAME << L"\n";

    // Wait until pipe is available — with retry limit so we don't spin forever
    int retries = 0;
    while (!WaitNamedPipeW(PIPE_NAME, 5000)) {
        if (++retries >= MAX_RETRIES) {
            std::wcerr << L"Server not available after " << MAX_RETRIES << L" retries. Giving up.\n";
            return 1;
        }
        std::wcout << L"Pipe busy, retrying (" << retries << L"/" << MAX_RETRIES << L")...\n";
    }

    // RAII wrapper — CloseHandle called automatically on scope exit or exception
    winapi::Handle hPipe(
        CreateFileW(
            PIPE_NAME,
            GENERIC_READ | GENERIC_WRITE,
            0, nullptr,
            OPEN_EXISTING, 0, nullptr),
        winapi::Handle::Sentinel::Invalid);

    if (!hPipe) {
        std::wcerr << L"Cannot open pipe: " << GetLastError() << L"\n";
        return 1;
    }

    // Switch to message-read mode
    DWORD mode = PIPE_READMODE_MESSAGE;
    SetNamedPipeHandleState(hPipe.get(), &mode, nullptr, nullptr);

    std::wcout << L"Connected! Type messages (empty line to quit):\n";

    std::string line;
    char replyBuf[PIPE_BUF];
    DWORD bytesRead = 0, bytesWritten = 0;

    while (true) {
        std::cout << "> ";
        std::getline(std::cin, line);
        if (line.empty()) break;

        WriteFile(hPipe.get(), line.c_str(),
                  static_cast<DWORD>(line.size()), &bytesWritten, nullptr);

        if (ReadFile(hPipe.get(), replyBuf, sizeof(replyBuf) - 1, &bytesRead, nullptr)) {
            replyBuf[bytesRead] = '\0';
            std::cout << replyBuf << "\n";
        }
    }

    // hPipe destructor calls CloseHandle automatically
    return 0;
}
