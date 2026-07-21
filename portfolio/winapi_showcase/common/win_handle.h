#pragma once
#include <windows.h>
#include <tlhelp32.h>  // CreateToolhelp32Snapshot — used by create_snapshot() below
#include <stdexcept>
#include <string>

namespace winapi {

// RAII wrapper for HANDLE resources.
// Closes on destruction; non-copyable, movable.
// Differentiates between INVALID_HANDLE_VALUE and nullptr sentinels.
class Handle {
public:
    enum class Sentinel { Null, Invalid };

    explicit Handle(HANDLE h = nullptr, Sentinel s = Sentinel::Null)
        : m_handle(h), m_sentinel(s) {}

    ~Handle() { close(); }

    // Non-copyable
    Handle(const Handle&)            = delete;
    Handle& operator=(const Handle&) = delete;

    // Movable
    Handle(Handle&& o) noexcept
        : m_handle(o.m_handle), m_sentinel(o.m_sentinel)
    { o.m_handle = null_value(); }

    Handle& operator=(Handle&& o) noexcept {
        if (this != &o) {
            close();
            m_handle   = o.m_handle;
            m_sentinel = o.m_sentinel;
            o.m_handle = null_value();
        }
        return *this;
    }

    [[nodiscard]] bool   valid()  const { return m_handle != null_value(); }
    [[nodiscard]] HANDLE get()    const { return m_handle; }
    explicit operator bool()      const { return valid(); }
    HANDLE operator*()            const { return m_handle; }

    // Release ownership -- caller is responsible for CloseHandle
    [[nodiscard]] HANDLE release() noexcept {
        HANDLE h = m_handle;
        m_handle  = null_value();
        return h;
    }

    void close() {
        if (valid()) {
            CloseHandle(m_handle);
            m_handle = null_value();
        }
    }

private:
    HANDLE   null_value() const {
        return m_sentinel == Sentinel::Invalid
            ? INVALID_HANDLE_VALUE
            : nullptr;
    }

    HANDLE   m_handle;
    Sentinel m_sentinel;
};

// Factory helpers
inline Handle open_process(DWORD access, DWORD pid) {
    return Handle(OpenProcess(access, FALSE, pid), Handle::Sentinel::Null);
}

inline Handle create_snapshot(DWORD flags, DWORD pid = 0) {
    return Handle(CreateToolhelp32Snapshot(flags, pid), Handle::Sentinel::Invalid);
}

// Throws std::runtime_error with Win32 error description
[[noreturn]] inline void throw_last_error(const char* context) {
    DWORD err = GetLastError();
    char  buf[256] = {};
    FormatMessageA(
        FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
        nullptr, err, 0, buf, sizeof(buf), nullptr);
    throw std::runtime_error(std::string(context) + ": " + buf);
}

} // namespace winapi
