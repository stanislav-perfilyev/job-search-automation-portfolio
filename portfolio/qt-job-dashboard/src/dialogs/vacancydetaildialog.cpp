#include "vacancydetaildialog.h"
#include "models/vacancysqlmodel.h"
#include "models/ivacancymodel.h"
#include <QLabel>
#include <QTextEdit>
#include <QPushButton>
#include <QFormLayout>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QDialogButtonBox>
#include <QDesktopServices>
#include <QUrl>

VacancyDetailDialog::VacancyDetailDialog(VacancySqlModel* model, int row, QWidget* parent)
    : QDialog(parent)
{
    setWindowTitle("Детали вакансии");
    resize(540, 400);

    m_titleLabel = new QLabel(this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    m_titleLabel->setWordWrap(true);
    m_titleLabel->setStyleSheet("font-size:16px;font-weight:bold;");

    m_metaLabel = new QLabel(this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    m_metaLabel->setWordWrap(true);

    m_notesEdit = new QTextEdit(this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    m_notesEdit->setReadOnly(true);

    m_urlBtn = new QPushButton("Открыть вакансию ↗", this);  // NOLINT(cppcoreguidelines-owning-memory)

    auto* btnBox = new QDialogButtonBox(QDialogButtonBox::Close, this);  // NOLINT(cppcoreguidelines-owning-memory)

    auto* root = new QVBoxLayout(this);  // NOLINT(cppcoreguidelines-owning-memory) — Qt-parented
    root->addWidget(m_titleLabel);
    root->addWidget(m_metaLabel);
    root->addWidget(new QLabel("Заметки:", this));  // NOLINT(cppcoreguidelines-owning-memory)
    root->addWidget(m_notesEdit);
    auto* bottomRow = new QHBoxLayout;  // NOLINT(cppcoreguidelines-owning-memory) — reparented by addLayout below
    bottomRow->addWidget(m_urlBtn);
    bottomRow->addStretch();
    bottomRow->addWidget(btnBox);
    root->addLayout(bottomRow);

    populate(model, row);

    connect(m_urlBtn,   &QPushButton::clicked,  [this]{ QDesktopServices::openUrl(QUrl(m_url)); });
    connect(btnBox,     &QDialogButtonBox::rejected, this, &QDialog::reject);
}

void VacancyDetailDialog::populate(VacancySqlModel* model, int row)
{
    auto d = [&](int col){ return model->data(model->index(row, col)).toString(); };

    m_titleLabel->setText(d(IVacancyModel::ColTitle));
    m_url = d(IVacancyModel::ColUrl);
    m_urlBtn->setVisible(!m_url.isEmpty());

    const QString salary = [&]() -> QString {
        int lo = model->data(model->index(row, IVacancyModel::ColSalaryMin)).toInt();
        int hi = model->data(model->index(row, IVacancyModel::ColSalaryMax)).toInt();
        QString cur = d(IVacancyModel::ColCurrency);
        if (lo > 0 && hi > 0) return QString("%1 – %2 %3").arg(lo).arg(hi).arg(cur);
        if (lo > 0) return QString("от %1 %2").arg(lo).arg(cur);
        return "—";
    }();

    m_metaLabel->setText(
        QString("<b>%1</b> · %2 · %3<br>Статус: <b>%4</b> · Зарплата: %5")
            .arg(d(IVacancyModel::ColCompany),
                 d(IVacancyModel::ColDate),
                 d(IVacancyModel::ColSource),
                 d(IVacancyModel::ColStatus),
                 salary));

    m_notesEdit->setPlainText(d(IVacancyModel::ColNotes));
}
