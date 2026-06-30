#pragma once
#include <QAbstractTableModel>
#include <QString>

// Abstract interface for vacancy data sources.
// Decouples views from concrete SQL implementation.
// Follows ISP: only the minimum contract views need.
class IVacancyModel : public QAbstractTableModel {
    Q_OBJECT
    Q_DISABLE_COPY_MOVE(IVacancyModel)
public:
    enum Column {
        ColDate = 0,
        ColTitle,
        ColCompany,
        ColSource,
        ColStatus,
        ColSalaryMin,
        ColSalaryMax,
        ColCurrency,
        ColTemplate,
        ColUrl,
        ColNotes,
        ColCount
    };
    Q_ENUM(Column)

    explicit IVacancyModel(QObject* parent = nullptr) : QAbstractTableModel(parent) {}
    ~IVacancyModel() override = default;

    // Returns false and emits error() on failure.
    [[nodiscard]] virtual bool refresh() = 0;
    [[nodiscard]] virtual int  totalCount() const = 0;
    [[nodiscard]] virtual int  countByStatus(const QString& status) const = 0;

    // Health check: returns empty string if OK, error description otherwise.
    [[nodiscard]] virtual QString healthCheck() const = 0;

signals:
    // Emitted on any non-fatal error (query fail, etc.) for UI notification.
    void error(const QString& message);
};
