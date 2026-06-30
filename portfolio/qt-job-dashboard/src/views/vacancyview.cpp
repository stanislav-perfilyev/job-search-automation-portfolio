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

VacancyView::VacancyView(VacancySqlModel* model, QWidget* parent)
    : QWidget(parent), m_srcModel(model)
{
    m_filterModel = new VacancyFilterModel(this);
    m_filterModel->setSourceModel(m_srcModel);

    // Toolbar
    m_searchEdit = new QLineEdit(this);
    m_searchEdit->setPlaceholderText("Поиск по названию / компании…");
    m_searchEdit->setClearButtonEnabled(true);

    m_statusCombo = new QComboBox(this);
    m_statusCombo->addItem("Все статусы", "");
    for (const auto& s : Status::all())
        m_statusCombo->addItem(s, s);

    auto* refreshBtn = new QPushButton("⟳ Обновить", this);

    auto* toolbar = new QHBoxLayout;
    toolbar->addWidget(new QLabel("Фильтр:", this));
    toolbar->addWidget(m_searchEdit, 3);
    toolbar->addWidget(m_statusCombo, 1);
    toolbar->addWidget(refreshBtn);

    // Table
    m_table = new QTableView(this);
    m_table->setModel(m_filterModel);
    m_table->setItemDelegate(new StatusDelegate(IVacancyModel::ColStatus, this));
    m_table->horizontalHeader()->setSectionResizeMode(IVacancyModel::ColTitle, QHeaderView::Stretch);
    m_table->horizontalHeader()->setSectionResizeMode(IVacancyModel::ColNotes, QHeaderView::Stretch);
    m_table->setColumnWidth(IVacancyModel::ColDate,      90);
    m_table->setColumnWidth(IVacancyModel::ColCompany,  150);
    m_table->setColumnWidth(IVacancyModel::ColSource,    90);
    m_table->setColumnWidth(IVacancyModel::ColStatus,   110);
    m_table->setColumnWidth(IVacancyModel::ColSalaryMin, 80);
    m_table->setColumnWidth(IVacancyModel::ColSalaryMax, 80);
    m_table->setColumnWidth(IVacancyModel::ColCurrency,  60);
    m_table->setColumnHidden(IVacancyModel::ColUrl,     true);
    m_table->setColumnHidden(IVacancyModel::ColTemplate,true);
    m_table->setSortingEnabled(true);
    m_table->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_table->setEditTriggers(QAbstractItemView::DoubleClicked);
    m_table->verticalHeader()->hide();
    m_table->setAlternatingRowColors(false);

    auto* root = new QVBoxLayout(this);
    root->addLayout(toolbar);
    root->addWidget(m_table);

    // Wire signals
    connect(m_searchEdit,  &QLineEdit::textChanged,
            this, &VacancyView::onSearch);
    connect(m_statusCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, &VacancyView::onStatusFilter);
    connect(m_table,       &QTableView::doubleClicked,
            this, &VacancyView::onDoubleClick);
    connect(refreshBtn,    &QPushButton::clicked,
            this, &VacancyView::refreshRequested);

    // Surface model errors to the user
    connect(m_srcModel, &IVacancyModel::error,
            this, [this](const QString& msg){
                QMessageBox::warning(this, "Ошибка модели", msg);
            });
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
