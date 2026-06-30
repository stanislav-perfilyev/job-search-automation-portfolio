find_package(Qt6 REQUIRED COMPONENTS Test Sql Widgets Charts)

# ── Shared test utils ────────────────────────────────────────
set(SHARED_SRCS
    ../src/utils/logging.cpp
)

# ── Test 1: VacancyModel (uses seeded SQLite via named connection) ──
add_executable(test_vacancy_model
    test_vacancy_model.cpp
    ../src/models/vacancysqlmodel.cpp
    ../src/models/vacancyfiltermodel.cpp
    ${SHARED_SRCS}
)
target_include_directories(test_vacancy_model PRIVATE ../src)
target_link_libraries(test_vacancy_model PRIVATE
    Qt6::Test Qt6::Sql Qt6::Core Qt6::Widgets Qt6::Charts)
add_test(NAME VacancyModelTests COMMAND test_vacancy_model)

# ── Test 2: CsvExporter ──────────────────────────────────────
add_executable(test_csv_exporter
    test_csv_exporter.cpp
    ../src/utils/csvexporter.cpp
    ${SHARED_SRCS}
)
target_include_directories(test_csv_exporter PRIVATE ../src)
target_link_libraries(test_csv_exporter PRIVATE
    Qt6::Test Qt6::Core Qt6::Widgets)
add_test(NAME CsvExporterTests COMMAND test_csv_exporter)
