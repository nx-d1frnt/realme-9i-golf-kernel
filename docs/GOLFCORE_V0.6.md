# GolfCore v0.6 (Realme 9i 4G / RMX3491 / khaje / bengal)

Дата сборки и проверки: **2026-11-15**

## Основные изменения относительно v0.5

1. **Память / ZRAM / MGLRU**
   - `CONFIG_CRYPTO_ZSTD=y`, `CONFIG_ZRAM_DEDUP=y`
   - `CONFIG_LRU_GEN=y`, `CONFIG_LRU_GEN_ENABLED=y`, `CONFIG_LRU_GEN_STATS=y`
   - Примечание: `CONFIG_ZRAM_WRITEBACK` не включался из-за конфликта структуры `struct zram` с `CONFIG_HYBRIDSWAP_CORE` в Oplus `drivers/block/zram/zram_drv.h`. В `vendor/oplus/kernel/oplus_performance/healthinfo/main/healthinfo.c` добавлена проверка `&& defined(CONFIG_HYBRIDSWAP_SWAPD)` вокруг `create_swappiness_para_proc()`.

2. **Планировщик и таймер ядра**
   - `CONFIG_UCLAMP_TASK=y`, `CONFIG_UCLAMP_TASK_GROUP=y` (замена `CONFIG_SCHED_TUNE`)
   - `CONFIG_HZ_300=y` (`CONFIG_HZ=300` вместо `250`)

3. **Сеть и оптимизация сокетов**
   - Бэкпорт **TCP BBRv2** (`CONFIG_TCP_CONG_BBR2=y`, `CONFIG_DEFAULT_BBR2=y`, `CONFIG_DEFAULT_TCP_CONG="bbr2"`):
     - добавлены `net/ipv4/tcp_bbr2.c`, `net/ipv4/tcp_dctcp.h` и изменения в `net/ipv4/*` / `include/net/*`;
     - `bbr_packets_in_net_at_edt()` адаптирована под таймстампы ядра 4.19 (без `tcp_wstamp_ns` / `tcp_clock_cache`);
     - включён внутренний TCP pacing при `CONFIG_DEFAULT_BBR2` без `FQ`.
   - `CONFIG_NET_SCH_CAKE=y` (в дополнение к `NET_SCH_FQ_CODEL` и `WIREGUARD`).
   - Инлайн `struct sk_security_struct` в `struct sock` (`include/net/sock.h`, `net/core/sock.c`, `security/selinux/*`) для исключения частых `kzalloc`/`kfree` на сокетах; неиспользуемый `CONFIG_SECURITY_SMACK` отключён.

4. **Сборка вендорных модулей**
   - В `build_vendor_modules.sh` добавлена автоматическая очистка устаревших `.o`, `.ko`, `.mod.c`, `.cmd`, `Module.symvers` и `modules.order` перед Pass 1, чтобы исключить рассинхронизацию CRC символов при смене конфигурации ядра.

## Проверка на устройстве (`RMX3491`, `afa6d59`)

- `uname -a`: `Linux localhost 4.19.157-GolfCore-v0.6 #6 SMP PREEMPT Sun Nov 15 12:33:01 EET 2026 aarch64`
- `sys.boot_completed`: `1`
- `/proc/sys/net/ipv4/tcp_congestion_control`: `bbr2` (доступны `reno bbr bbr2 cubic`)
- `/sys/kernel/mm/lru_gen/enabled`: `0x0001`
- `/sys/block/zram0/comp_algorithm`: `lzo [lz4] zstd`
- `/proc/swaps`: `/dev/block/zram0 partition 4194300 84624 -2`
- `/proc/asound/cards`: `0 [bengalqrdsndcar]: bengal-qrd-snd-card`
- `lsmod`: загружены все 31 модуль из `/vendor/lib/modules`
- `dumpsys wifi`: `Wi-Fi is enabled`
