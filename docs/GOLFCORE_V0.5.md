# GolfCore v0.5 — Снятие ABI-ограничений вендора и MGLRU

**Целевое устройство**: Realme 9i 4G (`RMX3491` / `khaje` / `bengal`, Snapdragon 680)  
**Версия ядра**: `4.19.157-GolfCore-v0.5` (`LOCALVERSION=-GolfCore-v0.5`)  
**Дата**: 2026-11-15

## Ключевые изменения

### 1. Полная пересборка всех 33 вендорных модулей из исходников
Раньше любая опция, меняющая CRC структур ядра (`CONFIG_LRU_GEN`, изменения в `mm`/`sched`), блокировалась проверкой `MODVERSIONS` стоковых модулей в `/vendor/lib/modules/`. Теперь все 33 модуля собираются, стрипаются (`llvm-strip --strip-debug`) и подписываются ключом текущей сборки (`out/certs/signing_key.pem`, `PKCS#7 SHA-512`) с сохранением `CONFIG_MODULE_SIG_FORCE=y` через [build_vendor_modules.sh](../build_vendor_modules.sh):

- **31 аудио-модуль** (`audio_*.ko`):
  - Qualcomm `audio-kernel`: `soc`, `dsp`, `ipc`, `dsp/codecs`, `asoc/codecs`, `bolero`, `wcd937x`, `rouleur`, `asoc` (`bengal`)
  - Oplus `vendor/oplus/kernel_4.19/audio/codecs`: `common` (`audio_pa_manager.ko`), `sia81xx_1.2.0` (`audio_sia81xx.ko`), `aw87xxx` (`audio_aw87xxx.ko`), `aw882xx` (`audio_aw882xx.ko`)
  - Двухпроходная сборка (`Pass 1` -> `Pass 2` с полным `KBUILD_EXTRA_SYMBOLS`) обеспечивает нулевое число `undefined` символов и точные CRC `MODVERSIONS`.
- **Wi-Fi (`qca_cld3_wlan.ko`)**:
  - Собирается с `MODNAME=wlan` (создаёт ожидаемый HAL-ом sysfs-узел `/sys/module/wlan/parameters/con_mode`) и переименовывается в `qca_cld3_wlan.ko`.
  - Использование коротких симлинков `/tmp/wl`, `/tmp/ak`, `/tmp/op_ak` устраняет ошибку `/bin/sh: Argument list too long` при линковке `qcacld-3.0`.
- **In-tree (`rdbg.ko`)**:
  - Копируется из `$OUT/drivers/char/rdbg.ko`, стрипается и подписывается тем же ключом.

### 2. Совместимость `Kbuild` с GNU Make 4.4
В 13 `Kbuild`-файлах `vendor/qcom/opensource/audio-kernel/` и `vendor/oplus/kernel_4.19/audio/codecs/` удалены голые директивы `export` внутри блоков `ifeq ($(CONFIG_ARCH_BENGAL), y)`, вызывавшие ошибку `Makefile.build:164: prerequisites cannot be defined in recipes` на GNU Make 4.4.

### 3. Включение MGLRU (`Multi-Gen LRU`)
В [build.sh](../build.sh) включены:
- `CONFIG_LRU_GEN=y`
- `CONFIG_LRU_GEN_ENABLED=y`
- Поддержан флаг `SKIP_STOCK_ABI_CHECK=1` (по умолчанию `1`), так как все вендорные модули пересобираются синхронно с ядром.

### 4. Чистый `vendor.img` (EROFS) и нативный `zram0`
Добавлен воспроизводимый инструмент [repack_vendor_erofs.py](../tools/repack_vendor_erofs.py) для перепаковки EROFS `vendor.img` с сохранением всех GSI-оверлеев, прав (`uid`/`gid`/`mode`), SELinux xattrs (включая корневую директорию `/`) и проверкой через `fsck.erofs -p`.

На тестируемом `vendor.img` дополнительно выполнена замена ручного shell-скрипта инициализации `zram0` в `/vendor/bin/init.qcom.post_boot.sh` на стандартный механизм Android (`init`/`fs_mgr`):
- `/vendor/etc/fstab.default`: `/dev/block/zram0 none swap defaults zramsize=4294967296`
- `/vendor/etc/init/hw/init.target.rc` (`on property:sys.boot_completed=1`): `write /sys/block/zram0/comp_algorithm lz4` и `swapon_all /vendor/etc/fstab.default`.

## Проверка на устройстве (`RMX3491`, `afa6d59`)
Прошиты `vendor_golfcore_v05.img` (`fastbootd`) и чистый `boot-golfcore-v0.5.0-clean-rmx3491-dfe.img` (без оверлея модулей в `ramdisk`):
- `uname -a`: `Linux localhost 4.19.157-GolfCore-v0.5 #4 SMP PREEMPT`
- MGLRU: `/sys/kernel/mm/lru_gen/enabled` = `0x0001`
- Модули: 31 модуль загружен напрямую с `/vendor/lib/modules/` (`lsmod | wc -l` = `32`)
- Звук: `0 [bengalqrdsndcar]: bengal-qrd-snd-card`
- Wi-Fi: `Wi-Fi is enabled`, `ConnectModeState`
- Swap/ZRAM: `/dev/block/zram0` (`4194300` KiB, алгоритм `lzo [lz4]`).
