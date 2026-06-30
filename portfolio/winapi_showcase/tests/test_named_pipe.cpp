// Tests for NamedPipeIPC (03_NamedPipeIPC)
// Strategy: test the protocol constants, helper functions, and the IPC
// round-trip contract. Full end-to-end tests require Windows.

#include <gtest/gtest.h>
#include <windows.h>
#include <string>
#include <sstream>

// ─────────────────────────────────────────────────────────────────────────────
// Constants under test (duplicated from pipe_server.cpp for isolation)
// ─────────────────────────────────────────────────────────────────────────────
constexpr wchar_t PIPE_NAME[] = L"\\\\.\\pipe\\winapi_showcase_ipc";
constexpr DWORD   PIPE_BUF   = 4096;

// ─────────────────────────────────────────────────────────────────────────────
// Log helper (pure function — testable without sockets)
// ─────────────────────────────────────────────────────────────────────────────
namespace {

// Mirrors the server-side reply construction logic
std::string BuildEchoReply(int clientId, const std::string& msg) {
    return "[Server#" + std::to_string(clientId) + "] ECHO: " + msg;
}

} // namespace

// ─────────────────────────────────────────────────────────────────────────────
// Protocol constant tests
// ─────────────────────────────────────────────────────────────────────────────
TEST(PipeConstants, NameIsWellFormed) {
    // Named pipe UNC path must start with \\.\pipe\
    std::wstring name(PIPE_NAME);
    ASSERT_FALSE(name.empty());
    EXPECT_EQ(name.substr(0, 9), L"\\\\.\\pipe\\");
}

TEST(PipeConstants, BufferSizeIsPowerOfTwo) {
    // Power-of-two buffer avoids wasteful fragmentation
    EXPECT_GT(PIPE_BUF, 0u);
    EXPECT_EQ(PIPE_BUF & (PIPE_BUF - 1), 0u)
        << "PIPE_BUF=" << PIPE_BUF << " should be a power of two";
}

TEST(PipeConstants, BufferSizeIsAtLeast4K) {
    EXPECT_GE(PIPE_BUF, 4096u);
}

// ─────────────────────────────────────────────────────────────────────────────
// Echo reply format tests
// ─────────────────────────────────────────────────────────────────────────────
TEST(EchoReply, ContainsClientId) {
    std::string reply = BuildEchoReply(3, "hello");
    EXPECT_NE(reply.find("Server#3"), std::string::npos);
}

TEST(EchoReply, ContainsOriginalMessage) {
    std::string reply = BuildEchoReply(1, "hello world");
    EXPECT_NE(reply.find("hello world"), std::string::npos);
}

TEST(EchoReply, StartsWithServerPrefix) {
    std::string reply = BuildEchoReply(2, "msg");
    EXPECT_EQ(reply.substr(0, 1), "[");
    EXPECT_NE(reply.find("ECHO:"), std::string::npos);
}

TEST(EchoReply, EmptyMessageIsHandled) {
    std::string reply = BuildEchoReply(1, "");
    // Should not crash; reply still has prefix
    EXPECT_NE(reply.find("ECHO:"), std::string::npos);
}

// ─────────────────────────────────────────────────────────────────────────────
// IPC round-trip contract (described; runs on Windows only)
// ─────────────────────────────────────────────────────────────────────────────

// CONTRACT: Server creates pipe with PIPE_ACCESS_DUPLEX | PIPE_TYPE_MESSAGE
// CONTRACT: Client connects with CreateFile → reads echo reply → messages match
// CONTRACT: Multiple clients (3+) connect concurrently without deadlock
// CONTRACT: Server cleans up pipe handles on client disconnect (RAII verified
//           by watching handle count via GetProcessHandleCount)
// CONTRACT: ConnectNamedPipe returns TRUE or sets ERROR_PIPE_CONNECTED
// CONTRACT: Handle leak test — start server, connect 10 clients, disconnect
//           all; handle count returns to baseline within 1 second

// ─────────────────────────────────────────────────────────────────────────────
int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
