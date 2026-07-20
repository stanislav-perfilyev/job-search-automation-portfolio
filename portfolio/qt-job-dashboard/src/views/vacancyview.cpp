#include "vacancyview.h"
#include "models/vacancysqlmodel.h"
#include "models/vacancyfiltermodel.h"
#include "models/ivacancymodel.h"
#include "widgets/statusdelegate.h"
#include "utils/status.h"
#include <QTableView>
#include <QLineEdit>
#include <QComboBox>
#include <QPushButton>
#include <QLabel>
#include <QHBoxLayout>
#include <QVBoxLayout>
#include <QHeaderView>
#include <QMessageBox>

namespace {
constexpr int kColWidthDate      = 90;
constexpr int kColWidthCompany   = 150;
constexpr int kColWidthSource    = 90;
constexpr int kColWidthStatus    = 110;
constexpr int kColWidthSalaryMin = 80;
constexpr int kColWidthSalaryMax = 80;
constexpr int kColWidthCurrency  = 60;
constexpr int kSearchEditStretch = 3;
constexpr int kStatusComboStretch = 1;
}  // namespace

VacancyView::VacancyView(VacancySqlModel* model, QWidget* parent)
    : QWidget(parent), m_srcModel(model)
{
    m_filterModel = new VacancyFilterModel(this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    m_filterModel->setSourceModel(m_srcModel);

    auto* toolbar = setupToolbar();
    setupTable();

    auto* root = new QVBoxLayout(this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    root->addLayout(toolbar);
    root->addWidget(m_table);

    // Surface model errors to the user
    connect(m_srcModel, &IVacancyModel::error,
            this, [this](const QString& msg){
                QMessageBox::warning(this, "Ошибка модели", msg);
            });
}

QHBoxLayout* VacancyView::setupToolbar()
{
    m_searchEdit = new QLineEdit(this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    m_searchEdit->setPlaceholderText("Поиск по названию / компании…");
    m_searchEdit->setClearButtonEnabled(true);

    m_statusCombo = new QComboBox(this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    m_statusCombo->addItem("Все статусы", "");
    for (const auto& s : Status::all())
        m_statusCombo->addItem(s, s);

    auto* refreshBtn = new QPushButton("⟳ Обновить", this);  // NOLINT(cppcoreguidelines-owning-memory)

    auto* toolbar = new QHBoxLayout;  // NOLINT(cppcoreguidelines-owning-memory) — reparented by addLayout
    toolbar->addWidget(new QLabel("Фильтр:", this));  // NOLINT(cppcoreguidelines-owning-memory)
    toolbar->addWidget(m_searchEdit, kSearchEditStretch);
    toolbar->addWidget(m_statusCombo, kStatusComboStretch);
    toolbar->addWidget(refreshBtn);

    connect(m_searchEdit,  &QLineEdit::textChanged,
            this, &VacancyView::onSearch);
    connect(m_statusCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, &VacancyView::onStatusFilter);
    connect(refreshBtn,    &QPushButton::clicked,
            this, &VacancyView::refreshRequested);

    return toolbar;
}

void VacancyView::setupTable()
{
    m_table = new QTableView(this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    m_table->setModel(m_filterModel);
    m_table->setItemDelegate(new StatusDelegate(IVacancyModel::ColStatus, this));  // NOLINT(cppcoreguidelines-owning-memory)
    m_table->horizontalHeader()->setSectionResizeMode(IVacancyModel::ColTitle, QHeaderView::Stretch);
    m_table->horizontalHeader()->setSectionResizeMode(IVacancyModel::ColNotes, QHeaderView::Stretch);
    m_table->setColumnWidth(IVacancyModel::ColDate,      kColWidthDate);
    m_table->setColumnWidth(IVacancyModel::ColCompany,   kColWidthCompany);
    m_table->setColumnWidth(IVacancyModel::ColSource,    kColWidthSource);
    m_table->setColumnWidth(IVacancyModel::ColStatus,    kColWidthStatus);
    m_table->setColumnWidth(IVacancyModel::ColSalaryMin, kColWidthSalaryMin);
    m_table->setColumnWidth(IVacancyModel::ColSalaryMax, kColWidthSalaryMax);
    m_table->setColumnWidth(IVacancyModel::ColCurrency,  kColWidthCurrency);
    m_table->setColumnHidden(IVacancyModel::ColUrl,     true);
    m_table->setColumnHidden(IVacancyModel::ColTemplate,true);
    m_table->setSortingEnabled(true);
    m_table->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_table->setEditTriggers(QAbstractItemView::DoubleClicked);
    m_table->verticalHeader()->hide();
    m_table->setAlternatingRowColors(false);

    connect(m_table, &QTableView::doubleClicked,
            this, &VacancyView::onDoubleClick);
}

void VacancyView::onSearch(const QString& text)
{
    m_filterModel->setTextFilter(text);
}

void VacancyView::onStatusFilter(int idx)
{
    m_filterModel->setStatusFilter(m_statusCombo->itemData(idx).toString());
}

void VacancyView::onDoubleClick(const QModelIndex& proxyIdx)
{
    emit vacancyDoubleClicked(m_filterModel->mapToSource(proxyIdx).row());
}
