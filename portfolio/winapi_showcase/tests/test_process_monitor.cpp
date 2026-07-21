#include <gtest/gtest.h>
#include "../01_ProcessMonitor/ProcessInfo.h"
#include <algorithm>
#include <vector>

using namespace process_monitor;

// --- Stub enumerator for unit tests (no real WinAPI calls) ---
class StubEnumerator : public IProcessEnumerator {
public:
    explicit StubEnumerator(std::vector<ProcessInfo> data)
        : m_data(std::move(data)) {}

    std::vector<ProcessInfo> enumerate() const override { return m_data; }

private:
    std::vector<ProcessInfo> m_data;
};

// Helper: build a ProcessInfo
static ProcessInfo make_proc(DWORD pid, const wchar_t* name,
                              SIZE_T wsMB, DWORD threads = 1) {
    ProcessInfo pi;
    pi.pid          = pid;
    pi.name         = name;
    pi.workingSetMB = wsMB;
    pi.threadCount  = threads;
    return pi;
}

// === Tests ===

TEST(ProcessInfoSortTest, SortedDescendingByWorkingSet) {
    std::vector<ProcessInfo> procs = {
        make_proc(1, L"low.exe",    10),
        make_proc(2, L"high.exe",  512),
        make_proc(3, L"medium.exe", 128),
    };
    std::sort(procs.begin(), procs.end());

    EXPECT_EQ(procs[0].workingSetMB, 512u);
    EXPECT_EQ(procs[1].workingSetMB, 128u);
    EXPECT_EQ(procs[2].workingSetMB,  10u);
}

TEST(ProcessInfoSortTest, EmptyListSortDoesNotCrash) {
    std::vector<ProcessInfo> procs;
    // Deliberately sorting an empty container — this test exists specifically
    // to prove that edge case doesn't crash, so the container being empty
    // here is intentional, not a bug. (cppcheck's inline "// cppcheck-suppress"
    // comment did not actually suppress this on the CI runner despite being
    // placed correctly, so it's silenced via --suppress=...:file:line in
    // winapi_showcase_ci.yml instead.)
    EXPECT_NO_THROW(std::sort(procs.begin(), procs.end()));
    EXPECT_TRUE(procs.empty());
}

TEST(ProcessInfoSortTest, EqualWorkingSetsStable) {
    std::vector<ProcessInfo> procs = {
        make_proc(10, L"a.exe", 100),
        make_proc(20, L"b.exe", 100),
    };
    std::sort(procs.begin(), procs.end());
    // Both equal — order undefined but no crash
    EXPECT_EQ(procs.size(), 2u);
}

TEST(StubEnumeratorTest, ReturnsInjectedData) {
    std::vector<ProcessInfo> expected = {
        make_proc(100, L"chrome.exe", 300, 32),
        make_proc(200, L"notepad.exe",  8,  2),
    };
    StubEnumerator stub(expected);
    auto result = stub.enumerate();

    ASSERT_EQ(result.size(), 2u);
    EXPECT_EQ(result[0].pid,         100u);
    EXPECT_EQ(result[0].name,        L"chrome.exe");
    EXPECT_EQ(result[0].workingSetMB, 300u);
    EXPECT_EQ(result[0].threadCount,   32u);
    EXPECT_EQ(result[1].pid,         200u);
}

TEST(StubEnumeratorTest, EmptyEnumeratorReturnsEmpty) {
    StubEnumerator stub({});
    EXPECT_TRUE(stub.enumerate().empty());
}

TEST(ProcessInfoTest, DefaultConstructedIsZero) {
    ProcessInfo pi;
    EXPECT_EQ(pi.pid,          0u);
    EXPECT_EQ(pi.workingSetMB, 0u);
    EXPECT_EQ(pi.threadCount,  0u);
    EXPECT_TRUE(pi.name.empty());
}

TEST(ProcessInfoTest, OperatorLessComparesWorkingSet) {
    auto big   = make_proc(1, L"big.exe",   500);
    auto small_ = make_proc(2, L"small.exe",  50);
    // operator< sorts descending — "big" < "small" means big comes FIRST
    EXPECT_TRUE(big < small_);
    EXPECT_FALSE(small_ < big);
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
