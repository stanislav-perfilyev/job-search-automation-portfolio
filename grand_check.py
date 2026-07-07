#!/usr/bin/env python3
"""
ГРАНД ЧЕК v2.4 — полный senior-контроль проекта.
Языки: C++, Python, Java, смешанные.
Использование: python3 grand_check.py [PROJECT_DIR] [--strict] [--compile] [--test]
              [--gtest] [--asan] [--tsan] [--cppcheck] [--mypy] [--bandit] [--coverage] [--all]
"""

import sys, re, os, pathlib, ast, subprocess, argparse, collections

# ── Аргументы ─────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser(description='ГРАНД ЧЕК v2')
ap.add_argument('project_dir', nargs='?', default='.')
ap.add_argument('--strict',  action='store_true', help='WARN → FAIL (нет терпимости к предупреждениям)')
ap.add_argument('--compile', action='store_true', help='Попытка сборки (cmake / py_compile)')
ap.add_argument('--test',    action='store_true', help='Запуск тестов (требует --compile для C++)')
ap.add_argument('--gtest',   action='store_true', help='Прямая GTest компиляция через g++ (без cmake)')
ap.add_argument('--asan',    action='store_true', help='GTest + AddressSanitizer+UBSan (память, UB)')
ap.add_argument('--tsan',    action='store_true', help='GTest + ThreadSanitizer (гонки данных)')
ap.add_argument('--cppcheck',action='store_true', help='cppcheck статический анализ C++')
ap.add_argument('--mypy',    action='store_true', help='mypy — проверка типов Python')
ap.add_argument('--bandit',  action='store_true', help='bandit — security Python')
ap.add_argument('--coverage',action='store_true', help='Покрытие тестами (gcov/coverage.py)')
ap.add_argument('--all',     action='store_true', help='Запустить ВСЁ (активирует все флаги)')
args = ap.parse_args()

# --all активирует все флаги
if args.all:
    args.compile = args.test = args.gtest = args.asan = args.tsan = \
        args.cppcheck = args.mypy = args.bandit = args.coverage = True

DIR    = pathlib.Path(args.project_dir).resolve()
STRICT = args.strict

# ── Цвета ─────────────────────────────────────────────────────────────────────
R = "\033[0;31m"; G = "\033[0;32m"; Y = "\033[1;33m"; B = "\033[1;34m"; NC = "\033[0m"
errors = 0; warns = 0; passed = 0

def fail(msg):
    global errors; errors += 1; print(f"{R}[FAIL]{NC} {msg}")

def warn(msg):
    global warns
    if STRICT:
        global errors; errors += 1; print(f"{R}[FAIL]{NC} [strict] {msg}")
    else:
        warns += 1; print(f"{Y}[WARN]{NC} {msg}")

def ok(msg):
    global passed; passed += 1; print(f"{G}[ OK ]{NC} {msg}")

def hdr(msg):
    print(f"\n{B}── {msg} {'─'*max(1,58-len(msg))}{NC}")

def rel(p):
    try: return str(p.relative_to(DIR))
    except: return str(p)

def read(p):
    try: return p.read_text(encoding='utf-8', errors='replace')
    except: return ""

def run(cmd, cwd=None, timeout=60):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -2, "", "not found"

# ── Поиск файлов ──────────────────────────────────────────────────────────────
SKIP_DIRS = {
    'build','cmake-build-debug','cmake-build-release','_deps','.git',
    '__pycache__','.venv','venv','env','node_modules','.mypy_cache',
    '.pytest_cache','dist','.eggs','target','out','.gradle','build_tmp',
}

def find_files(exts, base=DIR):
    result = []
    for root, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        rp = pathlib.Path(root)
        for f in sorted(files):
            if any(f.endswith(e) for e in exts) and f != 'vmlinux.h':
                result.append(rp / f)
    return result

# ── Определение языков ────────────────────────────────────────────────────────
cpp_h    = find_files(['.h'])
cpp_src  = find_files(['.cpp','.cxx','.cc'])
c_src    = find_files(['.c'])
py_files = find_files(['.py'])
java_files = find_files(['.java'])
all_src  = cpp_h + cpp_src + c_src + py_files + java_files

HAS_CPP  = bool(cpp_h or cpp_src)
HAS_C    = bool(c_src)
HAS_PY   = bool(py_files)
HAS_JAVA = bool(java_files)
PY_DOMINANT = HAS_PY and (not HAS_CPP or len(py_files) >= 3)

# ── Заголовок ─────────────────────────────────────────────────────────────────
print(f"\n{B}{'═'*62}{NC}")
print(f"{B}  ГРАНД ЧЕК v2: {DIR.name}{NC}")
langs = []
if HAS_CPP:  langs.append(f"C++ ({len(cpp_h)}h/{len(cpp_src)}src)")
if HAS_C:    langs.append(f"C ({len(c_src)}src)")
if HAS_PY:   langs.append(f"Python ({len(py_files)}py)")
if HAS_JAVA: langs.append(f"Java ({len(java_files)}java)")
print(f"  Языки: {', '.join(langs) or 'не определён'}")
flags = []
if STRICT:        flags.append("--strict")
if args.compile:  flags.append("--compile")
if args.test:     flags.append("--test")
if args.gtest:    flags.append("--gtest")
if args.asan:     flags.append("--asan")
if args.tsan:     flags.append("--tsan")
if args.cppcheck: flags.append("--cppcheck")
if args.mypy:     flags.append("--mypy")
if args.bandit:   flags.append("--bandit")
if args.coverage: flags.append("--coverage")
if args.all:      flags.append("--all")
if flags: print(f"  Флаги: {' '.join(flags)}")
print(f"{B}{'═'*62}{NC}")

# ══════════════════════════════════════════════════════════════════════
# БЛОК 0: ОБЩАЯ СТРУКТУРА
# ══════════════════════════════════════════════════════════════════════
hdr("БЛОК 0: ОБЩАЯ СТРУКТУРА")

if (DIR/'README.md').exists(): ok("README.md: есть")
else: warn("README.md: отсутствует")

if (DIR/'.gitignore').exists(): ok(".gitignore: есть")
else: warn(".gitignore: отсутствует")

def find_ci(d):
    for p in [d, d.parent, d.parent.parent]:
        wf = p / '.github' / 'workflows'
        if wf.exists():
            ymls = list(wf.glob('*.yml'))
            if ymls: return ymls, ('' if p == d else f' (в {p.name}/)')
    return [], ''
ci_ymls, ci_note = find_ci(DIR)
if ci_ymls: ok(f"CI workflow{ci_note}: {', '.join(f.name for f in ci_ymls)}")
else: fail("CI workflow: .github/workflows/*.yml не найден")

# Секреты
SECRET_RE = re.compile(
    r'(?:api_key|apikey|secret_key|password|passwd|private_key|access_token)\s*=\s*["\'][^"\']{6,}["\']',
    re.IGNORECASE
)
sec = []
for f in all_src:
    for i, line in enumerate(read(f).splitlines(), 1):
        s = line.strip()
        if s.startswith(('//', '#', '*')): continue
        if SECRET_RE.search(line) and 'os.getenv' not in line and 'environ' not in line and 'example' not in line.lower():
            sec.append(f"  {rel(f)}:{i}: {s[:80]}")
if sec:
    fail(f"Возможные hardcoded секреты ({len(sec)}):")
    for s in sec[:5]: print(s)
else:
    ok("Секреты: hardcoded не обнаружено")

# Дублирующиеся имена файлов
name_map = collections.defaultdict(list)
for f in all_src:
    name_map[f.name].append(f)
dups = [(n, ps) for n, ps in name_map.items() if len(ps) > 1]
if dups:
    for n, ps in dups[:5]:
        warn(f"Дублир. файл '{n}': {', '.join(rel(p) for p in ps[:3])}")
else:
    ok("Дублирующихся файлов: нет")

# Большие файлы (>1000 строк)
big = [(f, read(f).count('\n')) for f in all_src if read(f).count('\n') > 1000]
if big:
    for f, n in big[:5]: warn(f"Файл >{n} строк (нарушение SRP?): {rel(f)}")
else:
    ok("Размер файлов: все ≤1000 строк")

# TODO/FIXME
TODO_RE = re.compile(r'\b(TODO|FIXME|HACK|XXX)\b')
todo_hits = []
for f in all_src:
    for i, line in enumerate(read(f).splitlines(), 1):
        if TODO_RE.search(line):
            todo_hits.append(f"  {rel(f)}:{i}")
if len(todo_hits) > 10:
    warn(f"TODO/FIXME: {len(todo_hits)} мест — проверить перед релизом")
    for s in todo_hits[:3]: print(s)
elif todo_hits:
    ok(f"TODO/FIXME: {len(todo_hits)} мест — в норме")
else:
    ok("TODO/FIXME: нет")

# ══════════════════════════════════════════════════════════════════════
# БЛОК 1: C++ — СТРУКТУРА
# ══════════════════════════════════════════════════════════════════════
if HAS_CPP:
    hdr("БЛОК 1: C++ — СТРУКТУРА")

    def has_guard(f):
        txt = read(f)
        return '#pragma once' in txt or (
            re.search(r'^#ifndef\s+\w', txt, re.MULTILINE) and
            re.search(r'^#define\s+\w', txt, re.MULTILINE))
    miss_pragma = [f for f in cpp_h if not has_guard(f)]
    if miss_pragma:
        for f in miss_pragma: fail(f"#pragma once / include guard missing: {rel(f)}")
    else:
        ok(f"#pragma once / include guard: все {len(cpp_h)} заголовков защищены")

    cmake_files = find_files(['CMakeLists.txt'])
    all_cmake = "\n".join(read(f) for f in cmake_files)
    if re.search(r'-Werror\b|"Werror"', all_cmake): ok("CMake -Werror: есть")
    else: fail("CMake -Werror: не найден")
    if re.search(r'-Wall\b', all_cmake) and re.search(r'-Wextra\b', all_cmake): ok("CMake -Wall -Wextra: есть")
    else: warn("CMake -Wall -Wextra: не найден")

# ══════════════════════════════════════════════════════════════════════
# БЛОК 2: C++ — [[nodiscard]]
# ══════════════════════════════════════════════════════════════════════
if HAS_CPP:
    hdr("БЛОК 2: C++ — [[nodiscard]]")

    NODISCARD_TYPE = re.compile(
        r'\b(bool|uint8_t|uint16_t|uint32_t|uint64_t|int8_t|int16_t|int32_t|int64_t'
        r'|size_t|ssize_t|ptrdiff_t|int)\b'
        r'|std::(optional|string\b|string_view|vector|list|map|set|pair|tuple'
        r'|unique_ptr|shared_ptr|expected|variant|array)\b'
    )
    COROUTINE_NAMES = {
        'initial_suspend','final_suspend','yield_value','get_return_object',
        'await_ready','await_suspend','await_resume','return_value','return_void','unhandled_exception',
    }
    KEYWORDS = {'if','for','while','switch','catch','return','else','do','sizeof','alignof',
                'decltype','typeof','static_assert','assert','new','delete','throw','case','default'}
    FUNC_LINE = re.compile(
        r'^(\s*)(?:(?:static|inline|virtual|constexpr|const|explicit|override|friend|auto)\s+)*(.+?)\s+(\w+)\s*\('
    )

    nd_issues = []
    for f in cpp_h:
        text = read(f); lines = text.splitlines()
        in_promise = False; brace_depth = 0; promise_depth = 0
        for lineno, line in enumerate(lines, 1):
            brace_depth += line.count('{') - line.count('}')
            if 'promise_type' in line and '{' in line: in_promise = True; promise_depth = brace_depth
            if in_promise and brace_depth < promise_depth: in_promise = False
            stripped = line.strip()
            if not stripped or stripped.startswith(('//', '*', '#')): continue
            if '[[nodiscard]]' in line or in_promise: continue
            p = line.find('(')
            if p < 0: continue
            if '=' in line[:p]: continue
            if ';' in line[:p]: continue  # поле структуры или конец стейтмента
            m = FUNC_LINE.match(line)
            if not m: continue
            type_part, func_name = m.group(2).strip(), m.group(3)
            if func_name in KEYWORDS | COROUTINE_NAMES: continue
            if '(' in type_part: continue  # не тип возврата (ctor init list, throw)
            # Пропустить: переменная-ctor вида Type<T> var(expr);
            # Глубокий отступ (≥8) + строка оканчивается на ); + без типов в скобках
            if len(line) - len(line.lstrip()) >= 8 and line.rstrip().endswith(');'):
                _pm = re.search(r'\(([^)]*)\)', line)
                if _pm and not re.search(
                    r'\b(?:const|int|long|bool|char|float|double|size_t|uint|std::)\b',
                    _pm.group(1)):
                    continue  # ctor call: results(n), count(0), etc.
            if re.search(r'operator\b|~\w', line[:p]): continue
            if re.search(r'\bvoid\b', type_part) or re.search(r'cast<|static_assert|assert\b', line): continue
            if NODISCARD_TYPE.search(type_part):
                nd_issues.append(f"  {rel(f)}:{lineno}: {line.rstrip()}")
    if nd_issues:
        fail(f"[[nodiscard]] missing ({len(nd_issues)} мест):")
        for s in nd_issues[:15]: print(s)
    else:
        ok("[[nodiscard]]: все non-void функции покрыты")

# ══════════════════════════════════════════════════════════════════════
# БЛОК 3: C++ — СТАНДАРТЫ КАЧЕСТВА
# ══════════════════════════════════════════════════════════════════════
if HAS_CPP:
    hdr("БЛОК 3: C++ — explicit / const / override / noexcept / RAII / thread")

    # explicit: одноаргументные конструкторы
    CTOR_1ARG = re.compile(r'^\s*([A-Z]\w+)\s*\(([^,)]+)\)\s*[{;:]')
    CLASS_DECL = re.compile(r'^\s*(?:class|struct)\s+(\w+)')
    expl_issues = []
    for f in cpp_h:
        lines = read(f).splitlines()
        class_names = {m.group(1) for l in lines if (m := CLASS_DECL.match(l))}
        for i, line in enumerate(lines, 1):
            s = line.strip()
            if s.startswith(('//', '*')): continue
            if 'explicit' in line or 'operator' in line or '~' in line: continue
            if '= delete' in line or '= default' in line: continue
            m = CTOR_1ARG.match(line)
            if m and m.group(1) in class_names:
                arg = m.group(2).strip()
                if arg and arg != 'void':
                    expl_issues.append(f"  {rel(f)}:{i}: {s[:80]}")
    if expl_issues:
        fail(f"explicit missing для конструктора ({len(expl_issues)}):")
        for s in expl_issues[:5]: print(s)
    else:
        ok("explicit: нарушений не найдено")

    # const-correctness: геттеры без const
    # Только ОБЪЯВЛЕНИЯ функций (FUNC_LINE), имя которых начинается на get/is/has/count/size/empty
    GETTER_NAME_RE = re.compile(r'^(?:get|is|has|count|size|empty)\w*$')
    const_issues = []
    for f in cpp_h:
        for i, line in enumerate(read(f).splitlines(), 1):
            s = line.strip()
            if not s or s.startswith(('//', '*', '#')): continue
            # Только методы внутри класса (с отступом)
            if not (line.startswith('    ') or line.startswith('\t')): continue
            if re.search(r'\bstatic\b|\bfriend\b', line): continue
            # Уже имеет const квалификатор
            if re.search(r'\)\s*(?:noexcept\s*)?(?:override\s*)?const\b', line): continue
            if re.search(r'\bvoid\b', line): continue
            # Пропустить вызовы (if/while/for/switch, -> или .)
            if re.search(r'\b(?:if|while|for|switch|return)\s*\(', line): continue
            if re.search(r'(?:->|\.)[a-z]\w*\s*\(', line): continue  # obj->method() или obj.method()
            if '=' in line.split('(')[0]: continue  # инициализация переменной
            # Проверяем что это объявление функции через FUNC_LINE
            m = FUNC_LINE.match(line)
            if not m: continue
            func_name = m.group(3)
            if func_name in KEYWORDS: continue  # sizeof, alignof, etc.
            if func_name in COROUTINE_NAMES: continue  # promise_type методы
            if GETTER_NAME_RE.match(func_name):
                const_issues.append(f"  {rel(f)}:{i}: {s[:80]}")
    if const_issues:
        for s in const_issues[:5]: warn(f"const missing на геттере: {s.strip()}")
    else:
        ok("const-correctness: геттеры корректны")

    # override: virtual в производном классе без override
    INHERITS_RE = re.compile(r'class\s+\w+\s*:\s*(?:public|protected|private)')
    VIRTUAL_METHOD = re.compile(r'^\s+virtual\b')
    override_issues = []
    for f in cpp_h:
        text = read(f)
        if not INHERITS_RE.search(text): continue
        for i, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if s.startswith(('//', '*')): continue
            if VIRTUAL_METHOD.match(line) and '= 0' not in line:  # не pure virtual в базовом
                if not re.search(r'\boverride\b|\bfinal\b', line):
                    override_issues.append(f"  {rel(f)}:{i}: {s[:80]}")
    if override_issues:
        for s in override_issues[:5]: warn(f"virtual без override: {s.strip()}")
    else:
        ok("override: виртуальные методы корректны")

    # noexcept + std::function — конкретная функция
    ne_issues = []
    for f in cpp_h:
        for i, line in enumerate(read(f).splitlines(), 1):
            s = line.strip()
            if s.startswith(('//', '*')): continue
            if 'noexcept' in line and 'std::function' in line:
                ne_issues.append(f"  {rel(f)}:{i}: {s[:80]}")
    if ne_issues:
        for s in ne_issues[:3]: warn(f"noexcept+std::function: {s.strip()}")
    else:
        ok("noexcept+std::function: конфликтов нет")

    # std::string по значению (должен быть const std::string& или std::string&&)
    STR_BY_VAL = re.compile(r'(?:\(|,)\s*std::string\s+\w')
    str_val_issues = []
    for f in cpp_h + cpp_src:
        for i, line in enumerate(read(f).splitlines(), 1):
            s = line.strip()
            if s.startswith(('//', '*')): continue
            if '[' in line.split('(')[0]: continue  # лямбда — по значению OK
            if STR_BY_VAL.search(line):
                # Пропустить если это const std::string& или std::string&&
                if re.search(r'const\s+std::string\s*&|std::string\s*&&|std::string_view', line): continue
                str_val_issues.append(f"  {rel(f)}:{i}: {s[:80]}")
    if str_val_issues:
        for s in str_val_issues[:5]: warn(f"std::string по значению (→ const&): {s.strip()}")
    else:
        ok("std::string: передача по ссылке корректна")

    # RAII: сырые new/delete
    RAW_NEW_RE = re.compile(r'\bnew\s+\w')
    RAW_DEL_RE = re.compile(r'\bdelete\s+\w|\bdelete\s*\[')
    raii_issues = []
    for f in cpp_h + cpp_src:
        for i, line in enumerate(read(f).splitlines(), 1):
            s = line.strip()
            if s.startswith(('//', '*')): continue
            if re.search(r'=\s*delete\b|=\s*default\b', line): continue
            code_part = line.split('//')[0]  # игнорировать // комментарии
            if RAW_NEW_RE.search(code_part) or RAW_DEL_RE.search(code_part):
                raii_issues.append(f"  {rel(f)}:{i}: {s[:80]}")
    if raii_issues:
        for s in raii_issues[:5]: warn(f"сырой new/delete: {s.strip()}")
    else:
        ok("RAII: сырых new/delete не найдено")

    # Thread safety
    DIRECT_MT = re.compile(r'\bstd::thread\s*[{(<]|\bstd::(mutex|shared_mutex|unique_lock|lock_guard)\s+\w')
    MULTI_COUT = re.compile(r'(?:cout|cerr)\s*<<[^;]*<<')
    ts_issues = []
    for f in cpp_h + cpp_src:
        text = read(f)
        if DIRECT_MT.search(text):
            for i, line in enumerate(text.splitlines(), 1):
                s = line.strip()
                if s.startswith('//'): continue
                if MULTI_COUT.search(line):
                    ts_issues.append(f"  {rel(f)}:{i}: {s[:80]}")
    if ts_issues:
        for s in ts_issues: fail(f"multi-<< в MT-файле: {s.strip()}")
    else:
        ok("thread safety: cout chains не найдены")


    # ── MT-проверки (v2.2) ────────────────────────────────────────────────────

    # 1. raw mutex.lock() / mutex.unlock() без RAII (опасно: утечка лока при исключении)
    RAW_LOCK_RE   = re.compile(r'\w+\.(lock|try_lock)\s*\(\s*\)')
    RAW_UNLOCK_RE = re.compile(r'\w+\.unlock\s*\(\s*\)')
    RAII_LOCK_RE  = re.compile(r'(?:std::)?(unique_lock|lock_guard|scoped_lock|shared_lock)')
    raw_lock_issues = []
    for f in cpp_h + cpp_src:
        text = read(f)
        if not RAW_LOCK_RE.search(text): continue
        # WARN только если в том же файле нет RAII-обёртки
        has_raii = bool(RAII_LOCK_RE.search(text))
        for i, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if s.startswith(('//', '*')): continue
            if RAW_LOCK_RE.search(line) or RAW_UNLOCK_RE.search(line):
                if not has_raii:  # только если совсем нет RAII
                    raw_lock_issues.append(f"  {rel(f)}:{i}: {s[:80]}")
    if raw_lock_issues:
        for s in raw_lock_issues[:5]: warn(f"raw mutex.lock() без RAII: {s.strip()}")
    else:
        ok("MT: raw lock/unlock — RAII обёртки используются корректно")

    # 2. volatile используется как механизм синхронизации (частая ошибка в C++)
    #    volatile корректен для MMIO/signal, но не для межпоточной синхронизации
    VOLATILE_VAR_RE = re.compile(r'volatile\s+(?:int|long|bool|uint|char|double|float|std::)')
    volatile_issues = []
    for f in cpp_h + cpp_src:
        for i, line in enumerate(read(f).splitlines(), 1):
            s = line.strip()
            if s.startswith(('//', '*')): continue
            if 'sig_atomic_t' in line: continue   # корректное использование volatile
            if VOLATILE_VAR_RE.search(line):
                volatile_issues.append(f"  {rel(f)}:{i}: {s[:80]}")
    if volatile_issues:
        for s in volatile_issues[:5]: warn(f"volatile как MT-синхронизация (→ std::atomic): {s.strip()}")
    else:
        ok("MT: volatile не используется как синхронизация")

    # 3. std::atomic без явного memory_order (неявный seq_cst — может быть излишне тяжёлым)
    ATOMIC_OP_RE      = re.compile(r'\w+\.(load|store|fetch_add|fetch_sub|fetch_or|fetch_and|compare_exchange_weak|compare_exchange_strong)\s*\(')
    EXPLICIT_MO_RE    = re.compile(r'memory_order_')
    atomic_mo_issues  = []
    for f in cpp_h + cpp_src:
        for i, line in enumerate(read(f).splitlines(), 1):
            s = line.strip()
            if s.startswith(('//', '*')): continue
            if ATOMIC_OP_RE.search(line) and not EXPLICIT_MO_RE.search(line):
                atomic_mo_issues.append(f"  {rel(f)}:{i}: {s[:80]}")
    if atomic_mo_issues:
        for s in atomic_mo_issues[:5]:
            warn(f"atomic без явного memory_order (seq_cst по умолчанию): {s.strip()}")
    else:
        ok("MT: std::atomic — явные memory_order указаны")

# ══════════════════════════════════════════════════════════════════════
# БЛОК 4: C++ — ТЕСТЫ
# ══════════════════════════════════════════════════════════════════════
if HAS_CPP:
    hdr("БЛОК 4: C++ — тесты")
    test_cpp = [f for f in cpp_src + find_files(['.cxx','.cc','.c'])
                if re.search(r'test', f.name, re.IGNORECASE)
                or re.search(r'test', f.parent.name, re.IGNORECASE)]
    cmake_has_tests = any(
        re.search(r'\badd_test\s*\(', read(f), re.MULTILINE)
        for f in find_files(['CMakeLists.txt']))
    if test_cpp:
        ok(f"Тесты C++: {len(test_cpp)} файлов — {', '.join(f.name for f in test_cpp[:5])}")
    elif cmake_has_tests:
        ok("Тесты C++: CTest add_test() зарегистрированы")
    else:
        fail("Тесты C++: test_*.cpp не найдено и add_test() не зарегистрированы")

# ══════════════════════════════════════════════════════════════════════
# БЛОК 5: Python — синтаксис + mypy
# ══════════════════════════════════════════════════════════════════════
if HAS_PY:
    hdr("БЛОК 5: Python — синтаксис + mypy")

    test_py = [f for f in py_files if re.search(r'^test_|_test\.py$', f.name)]
    prod_py = [f for f in py_files if not re.search(r'^test_|_test\.py$', f.name)]

    syn_errors = []
    for f in py_files:
        try: ast.parse(read(f), filename=str(f))
        except SyntaxError as e: syn_errors.append(f"  {rel(f)}: строка {e.lineno}: {e.msg}")
    if syn_errors:
        fail(f"Синтаксис Python ({len(syn_errors)} ошибок):")
        for s in syn_errors: print(s)
    else:
        ok(f"Синтаксис Python: все {len(py_files)} файлов корректны")

    # mypy
    rc_mypy, _, _ = run(['mypy', '--version'])
    if rc_mypy == 0:
        rc2, out2, err2 = run(['mypy', '--ignore-missing-imports', '--no-error-summary', str(DIR)])
        mypy_errs = [l for l in out2.splitlines() if ': error:' in l]
        if mypy_errs:
            warn(f"mypy: {len(mypy_errs)} ошибок типов:")
            for l in mypy_errs[:5]: print(f"  {l}")
        else:
            ok("mypy: нет ошибок типов")
    else:
        ok("mypy: не установлен — пропущено (pip install mypy)")

# ══════════════════════════════════════════════════════════════════════
# БЛОК 6: Python — качество кода
# ══════════════════════════════════════════════════════════════════════
if HAS_PY:
    hdr("БЛОК 6: Python — качество кода")

    # Голые except:
    BARE_EXCEPT = re.compile(r'^\s*except\s*:')
    bare_exc = []
    for f in py_files:
        for i, line in enumerate(read(f).splitlines(), 1):
            if BARE_EXCEPT.match(line):
                bare_exc.append(f"  {rel(f)}:{i}: {line.strip()}")
    if bare_exc:
        for s in bare_exc[:5]: fail(f"bare except: {s.strip()}")
    else:
        ok("except: голых except: не найдено")

    # f-string SQL injection
    FSQL_RE = re.compile(r'f["\'].*?(?:SELECT|INSERT|UPDATE|DELETE|DROP|CREATE)\b.*?\{', re.IGNORECASE)
    fsql_issues = []
    for f in py_files:
        for i, line in enumerate(read(f).splitlines(), 1):
            s = line.strip()
            if s.startswith('#'): continue
            if FSQL_RE.search(line):
                fsql_issues.append(f"  {rel(f)}:{i}: {s[:80]}")
    if fsql_issues:
        for s in fsql_issues: fail(f"SQL injection risk: {s.strip()}")
    else:
        ok("f-string SQL: инъекций не обнаружено")

    if PY_DOMINANT:
        # requirements.txt
        has_req = (DIR/'requirements.txt').exists() or (DIR/'pyproject.toml').exists()
        if has_req:
            ok(f"Зависимости: {'requirements.txt' if (DIR/'requirements.txt').exists() else 'pyproject.toml'}")
        else:
            warn("Зависимости: requirements.txt / pyproject.toml не найден")

        # Тесты
        if test_py: ok(f"Тесты Python: {len(test_py)} файлов")
        else: fail("Тесты Python: test_*.py не найдено")

        # print() в проде
        print_hits = []
        for f in prod_py:
            for i, line in enumerate(read(f).splitlines(), 1):
                if line.strip().startswith('#'): continue
                if re.match(r'^\s*print\s*\(', line):
                    print_hits.append(f"  {rel(f)}:{i}")
        if print_hits:
            warn(f"print() в продакшн-коде: {len(print_hits)} мест")
            for s in print_hits[:3]: print(s)
        else:
            ok("logging: print() в продакшн-файлах не найдено")

        # Type hints
        if prod_py:
            total  = sum(len(re.findall(r'^\s*def ', read(f), re.MULTILINE)) for f in prod_py)
            hinted = sum(len(re.findall(r'^\s*def \w+\([^)]*:.*\)', read(f), re.MULTILINE)) for f in prod_py)
            if total > 0:
                pct = int(100 * hinted / total)
                if pct >= 50:   ok(f"Type hints: ~{pct}% ({hinted}/{total})")
                elif pct >= 20: warn(f"Type hints: только ~{pct}% ({hinted}/{total})")
                else:           warn(f"Type hints: менее 20% ({hinted}/{total})")

# ══════════════════════════════════════════════════════════════════════
# БЛОК 7: Java
# ══════════════════════════════════════════════════════════════════════
if HAS_JAVA:
    hdr("БЛОК 7: Java")

    # Build system
    if (DIR/'pom.xml').exists(): ok("Build: pom.xml (Maven) есть")
    elif (DIR/'build.gradle').exists() or (DIR/'build.gradle.kts').exists(): ok("Build: build.gradle (Gradle) есть")
    else: fail("Build: pom.xml / build.gradle не найден")

    # Тесты
    test_java = [f for f in java_files
                 if 'Test' in f.name or 'test' in str(f.parent).lower() or 'Test' in str(f.parent)]
    if test_java: ok(f"Тесты Java: {len(test_java)} файлов")
    else: fail("Тесты Java: *Test.java / test/ директория не найдена")

    # System.out.println в продакшн-коде
    prod_java = [f for f in java_files if f not in test_java]
    sout_hits = []
    for f in prod_java:
        for i, line in enumerate(read(f).splitlines(), 1):
            s = line.strip()
            if s.startswith('//'): continue
            if 'System.out.print' in line or 'System.err.print' in line:
                sout_hits.append(f"  {rel(f)}:{i}: {s[:80]}")
    if sout_hits:
        for s in sout_hits[:5]: warn(f"System.out.print (→ Logger): {s.strip()}")
    else:
        ok("Logging: System.out.print не найден")

    # Пустые catch-блоки
    EMPTY_CATCH_JAVA = re.compile(r'catch\s*\([^)]+\)\s*\{\s*\}')
    empty_catch = []
    for f in java_files:
        text = read(f)
        for i, line in enumerate(text.splitlines(), 1):
            if EMPTY_CATCH_JAVA.search(line):
                empty_catch.append(f"  {rel(f)}:{i}: {line.strip()[:80]}")
    if empty_catch:
        for s in empty_catch[:5]: fail(f"Пустой catch: {s.strip()}")
    else:
        ok("catch: пустых блоков нет")

    # @SuppressWarnings без комментария
    SUPPRESS_RE = re.compile(r'@SuppressWarnings')
    suppress_issues = []
    for f in java_files:
        lines = read(f).splitlines()
        for i, line in enumerate(lines, 1):
            if SUPPRESS_RE.search(line):
                # Проверяем есть ли комментарий на этой или предыдущей строке
                prev = lines[i-2].strip() if i > 1 else ""
                if not prev.startswith('//') and '//' not in line:
                    suppress_issues.append(f"  {rel(f)}:{i}: {line.strip()[:80]}")
    if suppress_issues:
        for s in suppress_issues[:3]: warn(f"@SuppressWarnings без объяснения: {s.strip()}")
    else:
        ok("@SuppressWarnings: все аннотированы")

# ══════════════════════════════════════════════════════════════════════
# БЛОК 8: --compile (опционально)
# ══════════════════════════════════════════════════════════════════════
if args.compile:
    hdr("БЛОК 8: КОМПИЛЯЦИЯ")

    if HAS_CPP and cmake_files:
        build_dir = DIR / 'build_tmp'
        build_dir.mkdir(exist_ok=True)
        print(f"  cmake configure...")
        rc, out, err = run(['cmake', '-S', str(DIR), '-B', str(build_dir), '-DCMAKE_BUILD_TYPE=Debug'], cwd=DIR, timeout=120)
        if rc != 0:
            fail(f"cmake configure: FAILED\n{err[:500]}")
        else:
            print(f"  cmake build...")
            rc2, out2, err2 = run(['cmake', '--build', str(build_dir), '--parallel'], cwd=DIR, timeout=300)
            if rc2 != 0:
                fail(f"cmake build: FAILED\n{err2[:500]}")
            else:
                ok("cmake build: SUCCESS")

    if HAS_PY:
        import py_compile
        compile_errors = []
        for f in py_files:
            try: py_compile.compile(str(f), doraise=True)
            except py_compile.PyCompileError as e: compile_errors.append(f"  {e}")
        if compile_errors:
            fail(f"py_compile: {len(compile_errors)} ошибок:")
            for e in compile_errors[:3]: print(e)
        else:
            ok(f"py_compile: все {len(py_files)} файлов скомпилированы")

# ══════════════════════════════════════════════════════════════════════
# БЛОК 9: --test (опционально)
# ══════════════════════════════════════════════════════════════════════
if args.test:
    hdr("БЛОК 9: ТЕСТЫ")

    if HAS_CPP:
        build_dir = DIR / 'build_tmp'
        if build_dir.exists():
            rc, out, err = run(['ctest', '--output-on-failure', '--parallel', '4'], cwd=build_dir, timeout=120)
            if rc == 0:
                passed_tests = re.search(r'(\d+) tests? passed', out)
                ok(f"ctest: {passed_tests.group(0) if passed_tests else 'OK'}")
            else:
                fail(f"ctest: тесты упали\n{out[-500:]}")
        else:
            warn("ctest: build_tmp не найден — сначала запустить с --compile")

    if HAS_PY and PY_DOMINANT:
        rc, out, err = run(['pytest', '--tb=short', '-q', str(DIR)], cwd=DIR, timeout=120)
        if rc == 0:
            summary = [l for l in out.splitlines() if 'passed' in l or 'failed' in l]
            ok(f"pytest: {summary[-1] if summary else 'OK'}")
        elif rc == -2:
            warn("pytest: не установлен (pip install pytest)")
        else:
            fail(f"pytest: тесты упали\n{out[-500:]}")

# ══════════════════════════════════════════════════════════════════════
# Вспомогательная функция: сборка + прогон GTest с заданными флагами
# ══════════════════════════════════════════════════════════════════════
def _gtest_build_run(extra_flags: list, out_name: str = '/tmp/gc_gtest_run'):
    """Компилирует GTest-тесты с extra_flags, запускает, возвращает (ok, n_pass, n_fail, err_text)."""
    gtest_files = [f for f in sorted(DIR.rglob('test_*.cpp'))
                   if 'gtest' in f.read_text(errors='ignore').lower()
                   and 'build' not in str(f) and 'build_tmp' not in str(f)]
    if not gtest_files:
        return None, 0, 0, "test_*.cpp с GTest не найдены"

    glib_candidates = [pathlib.Path('/tmp/libgtest_main.a'),
                       pathlib.Path('/usr/lib/libgtest_main.a'),
                       pathlib.Path('/usr/local/lib/libgtest_main.a'),
                       pathlib.Path('/usr/lib/x86_64-linux-gnu/libgtest_main.a')]
    ginc_candidates = [pathlib.Path('/tmp/gtest-src/googletest/include'),
                       pathlib.Path('/usr/include'), pathlib.Path('/usr/local/include')]
    glib = next((p for p in glib_candidates if p.exists()), None)
    ginc = next((p for p in ginc_candidates if (p / 'gtest/gtest.h').exists()), None)
    if not (glib and ginc):
        return None, 0, 0, "libgtest_main.a или gtest.h не найдены"

    def _has_main(f):
        try: return bool(re.search(r'int\s+main\s*\(', f.read_text(errors='ignore')))
        except: return True

    src_cpps = [f for f in sorted(DIR.rglob('*.cpp'))
                if not any(x in str(f) for x in ['test_', '/build', 'build_tmp', '_test.cpp'])
                and not _has_main(f)]
    inc_dirs = [str(ginc), str(DIR)] + [str(d) for d in [DIR/'include', DIR/'src'] if d.exists()]

    cmd = (['g++', '-std=c++20', '-O1', '-pthread'] + extra_flags +
           [f'-I{d}' for d in inc_dirs] +
           [str(f) for f in src_cpps + gtest_files] +
           [str(glib), '-o', out_name])
    rc, out, err = run(cmd, cwd=DIR, timeout=180)
    if rc != 0:
        return False, 0, 0, err[:500]

    rc2, out2, err2 = run([out_name, '--gtest_color=no'], cwd=DIR, timeout=90)
    combined = out2 + err2
    m_pass = re.search(r'\[  PASSED  \] (\d+) test', combined)
    m_fail = re.search(r'\[  FAILED  \] (\d+) test', combined)
    n_pass = int(m_pass.group(1)) if m_pass else 0
    n_fail = int(m_fail.group(1)) if m_fail else 0
    return (rc2 == 0 and n_fail == 0), n_pass, n_fail, combined[-400:]

# ══════════════════════════════════════════════════════════════════════
# БЛОК 10: --gtest (прямая компиляция GTest через g++, без cmake)
# ══════════════════════════════════════════════════════════════════════
if args.gtest:
    hdr("БЛОК 10: GTEST (прямой g++)")
    if not HAS_CPP:
        warn("GTest: C++ файлов не найдено")
    else:
        ok_flag, n_pass, n_fail, detail = _gtest_build_run([], '/tmp/gc_gtest_direct')
        if ok_flag is None:
            warn(f"GTest: {detail}")
        elif ok_flag:
            ok(f"GTest прямой: {n_pass} тестов ✓")
        else:
            fail(f"GTest прямой: {n_fail} тестов упали")
            for line in detail.splitlines()[-10:]:
                print(f"    {line}")

# ══════════════════════════════════════════════════════════════════════
# БЛОК 11: --asan (AddressSanitizer + UBSanitizer)
# ══════════════════════════════════════════════════════════════════════
if args.asan:
    hdr("БЛОК 11: ASAN+UBSAN (память и неопределённое поведение)")
    if not HAS_CPP:
        warn("ASAN: C++ файлов не найдено")
    else:
        asan_flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-g']
        ok_flag, n_pass, n_fail, detail = _gtest_build_run(asan_flags, '/tmp/gc_asan')
        if ok_flag is None:
            warn(f"ASAN: {detail}")
        elif ok_flag:
            # Дополнительно проверяем что ASAN не выдал ошибки в stderr
            asan_hit = re.search(r'ERROR: (AddressSanitizer|LeakSanitizer)|runtime error:', detail)
            if asan_hit:
                fail(f"ASAN: {n_pass} тестов прошли, но ASAN поймал ошибку памяти/UB!")
                for line in detail.splitlines():
                    if 'ERROR' in line or 'runtime error' in line:
                        print(f"    {line}")
            else:
                ok(f"ASAN+UBSAN: {n_pass} тестов ✓ — утечек и UB не найдено")
        else:
            asan_hit = re.search(r'ERROR: (AddressSanitizer|LeakSanitizer)|runtime error:', detail)
            if asan_hit:
                fail(f"ASAN: {n_fail} тестов упали + ASAN ошибка памяти/UB!")
            else:
                fail(f"ASAN: {n_fail} тестов упали")
            for line in detail.splitlines()[-12:]:
                print(f"    {line}")

# ══════════════════════════════════════════════════════════════════════
# БЛОК 12: --tsan (ThreadSanitizer — гонки данных)
# ══════════════════════════════════════════════════════════════════════
if args.tsan:
    hdr("БЛОК 12: TSAN (гонки данных)")
    if not HAS_CPP:
        warn("TSAN: C++ файлов не найдено")
    else:
        tsan_flags = ['-fsanitize=thread', '-g']
        ok_flag, n_pass, n_fail, detail = _gtest_build_run(tsan_flags, '/tmp/gc_tsan')
        if ok_flag is None:
            warn(f"TSAN: {detail}")
        elif ok_flag:
            race_hit = re.search(r'WARNING: ThreadSanitizer|DATA RACE', detail)
            if race_hit:
                fail(f"TSAN: {n_pass} тестов прошли, но найдена гонка данных!")
                for line in detail.splitlines():
                    if 'WARNING' in line or 'DATA RACE' in line or 'race' in line.lower():
                        print(f"    {line}")
            else:
                ok(f"TSAN: {n_pass} тестов ✓ — гонок данных не найдено")
        else:
            race_hit = re.search(r'WARNING: ThreadSanitizer|DATA RACE', detail)
            if race_hit:
                fail(f"TSAN: {n_fail} тестов упали + найдена гонка данных!")
            else:
                fail(f"TSAN: {n_fail} тестов упали")
            for line in detail.splitlines()[-12:]:
                print(f"    {line}")

# ══════════════════════════════════════════════════════════════════════
# БЛОК 13: --cppcheck (статический анализ C++)
# ══════════════════════════════════════════════════════════════════════
if args.cppcheck:
    hdr("БЛОК 13: cppcheck (статический анализ)")
    if not HAS_CPP:
        warn("cppcheck: C++ файлов не найдено")
    else:
        rc, out, err = run(['cppcheck', '--version'], timeout=5)
        if rc != 0:
            warn("cppcheck: не установлен — apt-get install cppcheck")
        else:
            cpp_src_dirs = list({str(f.parent) for f in cpp_src + cpp_h})
            rc2, out2, err2 = run(
                ['cppcheck', '--enable=all', '--error-exitcode=1',
                 '--suppress=missingIncludeSystem', '--suppress=unmatchedSuppression',
                 '--suppress=missingInclude', '--inline-suppr',
                 f'--std=c++20', str(DIR)],
                cwd=DIR, timeout=120
            )
            issues = [l for l in (out2 + err2).splitlines()
                      if ': error:' in l or ': warning:' in l or ': style:' in l
                      or ': performance:' in l or ': portability:' in l]
            errors_only = [l for l in issues if ': error:' in l]
            if errors_only:
                fail(f"cppcheck: {len(errors_only)} ошибок")
                for l in errors_only[:5]: print(f"    {l}")
            elif issues:
                warn(f"cppcheck: {len(issues)} предупреждений (ошибок нет)")
                for l in issues[:3]: print(f"    {l}")
            else:
                ok("cppcheck: ошибок не найдено")

# ══════════════════════════════════════════════════════════════════════
# БЛОК 14: --mypy (типы Python)
# ══════════════════════════════════════════════════════════════════════
if args.mypy:
    hdr("БЛОК 14: mypy (типы Python)")
    if not HAS_PY:
        warn("mypy: Python файлов не найдено")
    else:
        rc, out, err = run(['mypy', '--version'], timeout=5)
        if rc != 0:
            warn("mypy: не установлен — pip install mypy --break-system-packages")
        else:
            rc2, out2, err2 = run(
                ['mypy', '--ignore-missing-imports', '--no-error-summary', str(DIR)],
                cwd=DIR, timeout=120
            )
            type_errors = [l for l in (out2 + err2).splitlines() if ': error:' in l]
            type_notes  = [l for l in (out2 + err2).splitlines() if ': note:' in l]
            if type_errors:
                fail(f"mypy: {len(type_errors)} ошибок типов")
                for l in type_errors[:5]: print(f"    {l}")
            else:
                ok(f"mypy: ошибок типов нет ({'есть заметки' if type_notes else 'чисто'})")

# ══════════════════════════════════════════════════════════════════════
# БЛОК 15: --bandit (security Python)
# ══════════════════════════════════════════════════════════════════════
if args.bandit:
    hdr("БЛОК 15: bandit (безопасность Python)")
    if not HAS_PY:
        warn("bandit: Python файлов не найдено")
    else:
        rc, out, err = run(['bandit', '--version'], timeout=5)
        if rc != 0:
            warn("bandit: не установлен — pip install bandit --break-system-packages")
        else:
            rc2, out2, err2 = run(
                ['bandit', '-r', str(DIR), '-ll', '-q', '--format', 'txt'],
                cwd=DIR, timeout=120
            )
            combined = out2 + err2
            highs   = [l for l in combined.splitlines() if 'Severity: High' in l]
            mediums = [l for l in combined.splitlines() if 'Severity: Medium' in l]
            issues_block = [l for l in combined.splitlines() if l.startswith('>> Issue')]
            if highs:
                fail(f"bandit: {len(highs)} HIGH severity проблем безопасности!")
                for l in issues_block[:5]: print(f"    {l}")
            elif mediums:
                warn(f"bandit: {len(mediums)} MEDIUM severity — проверить вручную")
                for l in issues_block[:3]: print(f"    {l}")
            else:
                ok("bandit: критических уязвимостей не найдено")

# ══════════════════════════════════════════════════════════════════════
# БЛОК 16: --coverage (покрытие тестами)
# ══════════════════════════════════════════════════════════════════════
if args.coverage:
    hdr("БЛОК 16: ПОКРЫТИЕ ТЕСТАМИ")

    # Python coverage
    if HAS_PY and PY_DOMINANT:
        rc, out, err = run(['coverage', '--version'], timeout=5)
        if rc != 0:
            warn("coverage.py: не установлен — pip install coverage --break-system-packages")
        else:
            test_dirs = [str(d) for d in [DIR/'tests', DIR/'test', DIR] if (DIR if d == DIR else d).exists()]
            rc2, out2, err2 = run(
                ['coverage', 'run', f'--source={DIR}', '-m', 'pytest', '-q', str(DIR)],
                cwd=DIR, timeout=120
            )
            rc3, out3, err3 = run(['coverage', 'report', '--skip-empty'], cwd=DIR, timeout=30)
            cov_line = next((l for l in (out3 + err3).splitlines() if 'TOTAL' in l), None)
            if cov_line:
                pct_m = re.search(r'(\d+)%', cov_line)
                pct = int(pct_m.group(1)) if pct_m else 0
                if pct >= 80:
                    ok(f"coverage.py: {pct}% ✓")
                elif pct >= 60:
                    warn(f"coverage.py: {pct}% (цель ≥80%)")
                else:
                    fail(f"coverage.py: {pct}% — критически низкое покрытие (цель ≥80%)")
            else:
                warn("coverage.py: не удалось получить отчёт")

    # C++ coverage (gcov)
    if HAS_CPP:
        cov_flags = ['--coverage', '-O0', '-g']
        ok_flag, n_pass, n_fail, detail = _gtest_build_run(cov_flags, '/tmp/gc_cov')
        if ok_flag is None:
            warn(f"gcov: {detail}")
        elif not ok_flag:
            fail(f"gcov: {n_fail} тестов упали при сборке с --coverage")
        else:
            # Собрать gcov-отчёт
            gcda_files = list(pathlib.Path('/tmp').glob('*.gcda'))
            if not gcda_files:
                # gcda могут быть рядом с obj файлами
                gcda_files = list(DIR.rglob('*.gcda'))
            rc_gcov, gcov_out, _ = run(
                ['gcov', '-b'] + [str(f) for f in gcda_files[:20]], cwd=DIR, timeout=30
            )
            lines_executed = re.findall(r'Lines executed:(\d+\.\d+)%', gcov_out)
            if lines_executed:
                avg = sum(float(x) for x in lines_executed) / len(lines_executed)
                if avg >= 80:
                    ok(f"gcov: {avg:.1f}% строк покрыто ✓")
                elif avg >= 60:
                    warn(f"gcov: {avg:.1f}% строк покрыто (цель ≥80%)")
                else:
                    fail(f"gcov: {avg:.1f}% — критически низкое покрытие")
            else:
                ok(f"gcov: {n_pass} тестов ✓ (coverage data сгенерированы)")

# ══════════════════════════════════════════════════════════════════════
# ИТОГ
# ══════════════════════════════════════════════════════════════════════
print(f"\n{B}{'═'*62}{NC}")
mode = " [STRICT]" if STRICT else ""
print(f"  ИТОГ{mode}: {R}FAIL: {errors}{NC}  |  {Y}WARN: {warns}{NC}  |  {G}OK: {passed}{NC}")
print(f"{B}{'═'*62}{NC}")
if errors == 0 and warns == 0:
    print(f"{G}  ✓ ПРОЕКТ ПРОШЁЛ ГРАНД ЧЕК — ИДЕАЛ ДОСТИГНУТ{NC}")
elif errors == 0:
    print(f"{Y}  ~ FAIL нет, есть WARN — проверить вручную{NC}")
else:
    print(f"{R}  ✗ НАЙДЕНЫ ОШИБКИ — исправить до коммита{NC}")
print()
sys.exit(errors)
