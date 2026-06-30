#pragma once
#include <QString>
#include <QStringList>

// Single source of truth for vacancy status strings.
// Eliminates magic strings scattered across multiple files.
namespace Status {
    inline constexpr char Applied[]   = "Откликнулся";
    inline constexpr char Viewed[]    = "Просмотрено";
    inline constexpr char Interview[] = "Интервью";
    inline constexpr char Offer[]     = "Оффер";
    inline constexpr char Rejected[]  = "Отказ";

    inline QStringList all() {
        return { Applied, Viewed, Interview, Offer, Rejected };
    }
    // Returns true if this status counts as "active" (in pipeline)
    inline bool isActive(const QString& s) {
        return s == Applied || s == Viewed;
    }
} // namespace Status
