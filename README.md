# GolfCore — Realme 9i 4G / RMX3491

Экспериментальное ядро **4.19.157-perf+ для Realme 9i 4G / RMX3491**.
Базовая версия v0.1.0-abi-v2 загружена на телефоне с crDroid GSI Android 14
и патченными boot/vendor с отключённым FBE. Следующий кандидат —
**GolfCore v0.2.0-rc1 Balanced**: исправления ION, проверки флагов zram
и порядка работы touch IRQ при пробуждении. Цель — совместимость с GSI
и баланс плавности и автономности. Настройки частот и zram пока сохранены.
Изменения и ограничения кандидата: [docs/GOLFCORE_V0.2.md](docs/GOLFCORE_V0.2.md).

## Что находится в репозитории

- `kernel/msm-4.19/`, `vendor/`: полный снимок использованных исходников;
- `patches/`: применённые изменения;
- `config/stock.config`: конфиг работающего штатного ядра;
- `config/vendor-abi-reference.json`: CRC импортов/экспортов и SHA-256
  33 штатных vendor-модулей, без самих бинарных модулей;
- `certs/`: публичный сертификат, которым подписаны штатные модули;
- `build.sh`, `tools/`: сборка, проверка ABI и упаковка boot;
- `docs/TESTED.md`: результат проверки и известные ограничения.
- `tests/check_regressions.py`: проверки порядка touch resume и флагов выделения памяти;
- `tools/capture_state.py`: чтение показателей телефона для сравнения сборок.

Готовые `Image.gz`, DFE boot и контрольные суммы находятся в **Releases**.
Резервные образы исходных boot/vendor, личные логи телефона и приватные ключи подписи
в репозиторий не включены.

## Основа

Использована цельная публикация Realme SM6225 2024 года для RMX3521:

- [kernel](https://github.com/realme-kernel-opensource/realme9-AndroidU-kernel-source),
  commit `47aea2263f9c671c290c3663e42e82c7b20f06f3`;
- [vendor](https://github.com/realme-kernel-opensource/realme9-AndroidU-vendor-source),
  commit `d3cba492880add3c5493c08a119b09bdbc385180`.

Фактически проверенное устройство — **RMX3491**. Его рабочий ramdisk и DTB
сохранены в опубликованном тестовом boot. Происхождение и хеши патчей:
`SOURCES.json`. Патчи уже применены к исходникам в этом репозитории.

Основные изменения:

1. Исправлено размещение `.bss.rtic` и обработка packed-типа GSI в genksyms.
2. Перенесён полный stable 4.19 патч
   [net: fix __dst_negative_advice() race](https://github.com/gregkh/linux/commit/051c0bde9f0450a2ec3d62a86d2a0d2fad117f13),
   включая callbacks IPv4/IPv6/XFRM. Этот интерфейс совпадает со штатным
   ядром, что подтверждено встроенным архивом IKHEADERS и CRC модулей.
3. Восстановлен пятиаргументный экспорт multimedia feedback для штатного
   аудио-vendor; новый внутренний API сохранён под именем `_v2`.
4. Удалён пустой конструктор ION cache: обнуление через zalloc сохранено.
5. Исключение HIGH_ATOMIC_ZRAM включено внутрь WARN_ON_ONCE; поведение
   флагов выделения памяти сохранено.
6. При LCD-before-touch resume IRQ, освобождённый в tp_resume, больше
   не включается до повторной регистрации в resume work. Если resume
   пропущен, ранее отключённый IRQ включается как прежде.

MODVERSIONS и проверка подписей модулей включены. CRC не подменяются.

## Сборка

Linux x86-64. Проверенный компилятор — Android Clang **11.0.1 / r383902**
(build 6443078), GNU binutils **2.36.1** с aarch64 и arm32 assemblers.
Также нужны make, Python 3.11+, bison, flex, bc, OpenSSL development headers,
perl, gzip, xz, cpio. Для старых host-утилит при наличии OpenSSL 4 скрипт
выбирает установленную `libcrypto.so.3`.

Положите toolchains в `toolchains/clang-r383902/bin` и
`toolchains/proton-clang/bin` либо задайте пути явно:

```bash
CLANG_BIN=/path/to/clang-r383902/bin \
BINUTILS_BIN=/path/to/binutils/bin \
JOBS=6 bash build.sh
```

Доступны режимы `configure`, `probe`, `build` (по умолчанию). Можно задать
`OUT_DIR` и `ARTIFACTS_DIR`. Включённые параметры штатного конфига проверяются
после olddefconfig. Суффикс `-perf+` сохраняет vermagic штатных модулей.
Имя GolfCore отражается в метаданных сборки `golfcore@balanced-v0.2-rc1`.

Сборка завершится успешно только после проверки всех **2087 импортов
33 модулей**, включая зависимости модулей друг от друга. Результаты —
`artifacts/Image.gz`, `Module.symvers`, `vendor-abi.json`, `config-diff.txt`.
Частный ключ модульной подписи создаётся локально в out, в Git его нет.
Процедура воспроизводима по исходникам и конфигу; timestamp и новый ключ
означают, что байтовая идентичность релизному образу не обещается.

## Boot и отключённый FBE

Релизный boot создан из рабочего патченного boot этого RMX3491.
Повторная распаковка подтвердила точное сохранение ramdisk, DTB, header,
fstab, отключённого FBE и `checkpoint=fs`. Это образ для указанной рабочей
базы, а не универсальный boot для любых прошивок.

Для упаковки новой сборки используйте собственную проверенную рабочую копию
DFE boot и официальный MagiskBoot:

```bash
python3 tools/package_boot.py \
  --base-boot /path/to/current-working-dfe-boot.img \
  --magiskboot /path/to/magiskboot
```

Скрипт проверяет ABI, соответствие Image.gz отчёту, сохраняет компоненты
рабочего boot и повторно распаковывает результат для проверки. Никаких
команд прошивки или взаимодействия с телефоном он не выполняет.

## Состояние

На v0.1.0-abi-v2 проверены первичная загрузка и основные функции.
GolfCore v0.2.0-rc1 содержит исправления трёх найденных предупреждений;
проверка исправлений на телефоне ещё не выполнена. Предупреждение device links
остаётся предметом отдельного анализа. Длительная стабильность, глубокий
сон и расход батареи новой версии пока не проверены.

Лицензии и уведомления исходных kernel/vendor-компонентов сохранены в их
каталогах. Основная лицензия Linux kernel — GPL-2.0-only с указанными
в исходниках исключениями.
