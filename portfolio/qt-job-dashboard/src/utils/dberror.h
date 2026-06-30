#pragma once
#include <stdexcept>
#include <string>

// Custom exception hierarchy for the dashboard.
// Keeps error propagation explicit and typed.

namespace Dashboard {

// Base for all dashboard exceptions
struct Error : std::runtime_error {
    explicit Error(const std::string& msg) : std::runtime_error(msg) {}
};

// Database connection / query failures
struct DbError : Error {
    explicit DbError(const std::string& msg) : Error("DB: " + msg) {}
};

// I/O failures (file export, etc.)
struct IoError : Error {
    explicit IoError(const std::string& msg) : Error("IO: " + msg) {}
};

// Invalid argument / programming error caught at runtime
struct LogicError : Error {
    explicit LogicError(const std::string& msg) : Error("Logic: " + msg) {}
};

} // namespace Dashboard
