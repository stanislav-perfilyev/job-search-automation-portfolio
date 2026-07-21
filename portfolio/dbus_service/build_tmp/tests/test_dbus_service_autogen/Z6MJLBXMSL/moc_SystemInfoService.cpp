/****************************************************************************
** Meta object code from reading C++ file 'SystemInfoService.h'
**
** Created by: The Qt Meta Object Compiler version 68 (Qt 6.4.2)
**
** WARNING! All changes made in this file will be lost!
*****************************************************************************/

#include <memory>
#include "../../../../service/SystemInfoService.h"
#include <QtCore/qmetatype.h>
#if !defined(Q_MOC_OUTPUT_REVISION)
#error "The header file 'SystemInfoService.h' doesn't include <QObject>."
#elif Q_MOC_OUTPUT_REVISION != 68
#error "This file was generated using the moc from 6.4.2. It"
#error "cannot be used with the include files from this version of Qt."
#error "(The moc has changed too much.)"
#endif

#ifndef Q_CONSTINIT
#define Q_CONSTINIT
#endif

QT_BEGIN_MOC_NAMESPACE
QT_WARNING_PUSH
QT_WARNING_DISABLE_DEPRECATED
namespace {
struct qt_meta_stringdata_SystemInfoService_t {
    uint offsetsAndSizes[24];
    char stringdata0[18];
    char stringdata1[16];
    char stringdata2[24];
    char stringdata3[13];
    char stringdata4[1];
    char stringdata5[5];
    char stringdata6[12];
    char stringdata7[14];
    char stringdata8[12];
    char stringdata9[10];
    char stringdata10[5];
    char stringdata11[8];
};
#define QT_MOC_LITERAL(ofs, len) \
    uint(sizeof(qt_meta_stringdata_SystemInfoService_t::offsetsAndSizes) + ofs), len 
Q_CONSTINIT static const qt_meta_stringdata_SystemInfoService_t qt_meta_stringdata_SystemInfoService = {
    {
        QT_MOC_LITERAL(0, 17),  // "SystemInfoService"
        QT_MOC_LITERAL(18, 15),  // "D-Bus Interface"
        QT_MOC_LITERAL(34, 23),  // "ru.perfilyev.SystemInfo"
        QT_MOC_LITERAL(58, 12),  // "StatsUpdated"
        QT_MOC_LITERAL(71, 0),  // ""
        QT_MOC_LITERAL(72, 4),  // "info"
        QT_MOC_LITERAL(77, 11),  // "GetHostname"
        QT_MOC_LITERAL(89, 13),  // "GetMemoryInfo"
        QT_MOC_LITERAL(103, 11),  // "GetCpuCount"
        QT_MOC_LITERAL(115, 9),  // "GetUptime"
        QT_MOC_LITERAL(125, 4),  // "Echo"
        QT_MOC_LITERAL(130, 7)   // "message"
    },
    "SystemInfoService",
    "D-Bus Interface",
    "ru.perfilyev.SystemInfo",
    "StatsUpdated",
    "",
    "info",
    "GetHostname",
    "GetMemoryInfo",
    "GetCpuCount",
    "GetUptime",
    "Echo",
    "message"
};
#undef QT_MOC_LITERAL
} // unnamed namespace

Q_CONSTINIT static const uint qt_meta_data_SystemInfoService[] = {

 // content:
      10,       // revision
       0,       // classname
       1,   14, // classinfo
       6,   16, // methods
       0,    0, // properties
       0,    0, // enums/sets
       0,    0, // constructors
       0,       // flags
       1,       // signalCount

 // classinfo: key, value
       1,    2,

 // signals: name, argc, parameters, tag, flags, initial metatype offsets
       3,    1,   52,    4, 0x06,    1 /* Public */,

 // slots: name, argc, parameters, tag, flags, initial metatype offsets
       6,    0,   55,    4, 0x10a,    3 /* Public | MethodIsConst  */,
       7,    0,   56,    4, 0x10a,    4 /* Public | MethodIsConst  */,
       8,    0,   57,    4, 0x10a,    5 /* Public | MethodIsConst  */,
       9,    0,   58,    4, 0x10a,    6 /* Public | MethodIsConst  */,
      10,    1,   59,    4, 0x10a,    7 /* Public | MethodIsConst  */,

 // signals: parameters
    QMetaType::Void, QMetaType::QString,    5,

 // slots: parameters
    QMetaType::QString,
    QMetaType::QVariantMap,
    QMetaType::Int,
    QMetaType::QString,
    QMetaType::QString, QMetaType::QString,   11,

       0        // eod
};

Q_CONSTINIT const QMetaObject SystemInfoService::staticMetaObject = { {
    QMetaObject::SuperData::link<QObject::staticMetaObject>(),
    qt_meta_stringdata_SystemInfoService.offsetsAndSizes,
    qt_meta_data_SystemInfoService,
    qt_static_metacall,
    nullptr,
    qt_incomplete_metaTypeArray<qt_meta_stringdata_SystemInfoService_t,
        // Q_OBJECT / Q_GADGET
        QtPrivate::TypeAndForceComplete<SystemInfoService, std::true_type>,
        // method 'StatsUpdated'
        QtPrivate::TypeAndForceComplete<void, std::false_type>,
        QtPrivate::TypeAndForceComplete<const QString &, std::false_type>,
        // method 'GetHostname'
        QtPrivate::TypeAndForceComplete<QString, std::false_type>,
        // method 'GetMemoryInfo'
        QtPrivate::TypeAndForceComplete<QVariantMap, std::false_type>,
        // method 'GetCpuCount'
        QtPrivate::TypeAndForceComplete<int, std::false_type>,
        // method 'GetUptime'
        QtPrivate::TypeAndForceComplete<QString, std::false_type>,
        // method 'Echo'
        QtPrivate::TypeAndForceComplete<QString, std::false_type>,
        QtPrivate::TypeAndForceComplete<const QString &, std::false_type>
    >,
    nullptr
} };

void SystemInfoService::qt_static_metacall(QObject *_o, QMetaObject::Call _c, int _id, void **_a)
{
    if (_c == QMetaObject::InvokeMetaMethod) {
        auto *_t = static_cast<SystemInfoService *>(_o);
        (void)_t;
        switch (_id) {
        case 0: _t->StatsUpdated((*reinterpret_cast< std::add_pointer_t<QString>>(_a[1]))); break;
        case 1: { QString _r = _t->GetHostname();
            if (_a[0]) *reinterpret_cast< QString*>(_a[0]) = std::move(_r); }  break;
        case 2: { QVariantMap _r = _t->GetMemoryInfo();
            if (_a[0]) *reinterpret_cast< QVariantMap*>(_a[0]) = std::move(_r); }  break;
        case 3: { int _r = _t->GetCpuCount();
            if (_a[0]) *reinterpret_cast< int*>(_a[0]) = std::move(_r); }  break;
        case 4: { QString _r = _t->GetUptime();
            if (_a[0]) *reinterpret_cast< QString*>(_a[0]) = std::move(_r); }  break;
        case 5: { QString _r = _t->Echo((*reinterpret_cast< std::add_pointer_t<QString>>(_a[1])));
            if (_a[0]) *reinterpret_cast< QString*>(_a[0]) = std::move(_r); }  break;
        default: ;
        }
    } else if (_c == QMetaObject::IndexOfMethod) {
        int *result = reinterpret_cast<int *>(_a[0]);
        {
            using _t = void (SystemInfoService::*)(const QString & );
            if (_t _q_method = &SystemInfoService::StatsUpdated; *reinterpret_cast<_t *>(_a[1]) == _q_method) {
                *result = 0;
                return;
            }
        }
    }
}

const QMetaObject *SystemInfoService::metaObject() const
{
    return QObject::d_ptr->metaObject ? QObject::d_ptr->dynamicMetaObject() : &staticMetaObject;
}

void *SystemInfoService::qt_metacast(const char *_clname)
{
    if (!_clname) return nullptr;
    if (!strcmp(_clname, qt_meta_stringdata_SystemInfoService.stringdata0))
        return static_cast<void*>(this);
    if (!strcmp(_clname, "QDBusContext"))
        return static_cast< QDBusContext*>(this);
    return QObject::qt_metacast(_clname);
}

int SystemInfoService::qt_metacall(QMetaObject::Call _c, int _id, void **_a)
{
    _id = QObject::qt_metacall(_c, _id, _a);
    if (_id < 0)
        return _id;
    if (_c == QMetaObject::InvokeMetaMethod) {
        if (_id < 6)
            qt_static_metacall(this, _c, _id, _a);
        _id -= 6;
    } else if (_c == QMetaObject::RegisterMethodArgumentMetaType) {
        if (_id < 6)
            *reinterpret_cast<QMetaType *>(_a[0]) = QMetaType();
        _id -= 6;
    }
    return _id;
}

// SIGNAL 0
void SystemInfoService::StatsUpdated(const QString & _t1)
{
    void *_a[] = { nullptr, const_cast<void*>(reinterpret_cast<const void*>(std::addressof(_t1))) };
    QMetaObject::activate(this, &staticMetaObject, 0, _a);
}
QT_WARNING_POP
QT_END_MOC_NAMESPACE
