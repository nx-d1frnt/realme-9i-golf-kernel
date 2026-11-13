#!/system/bin/sh
# Six whitelisted nodes; one-shot changes, readback, per-boot backup and rollback.
set -u
umask 077
MODDIR=${0%/*}
[ "$MODDIR" != "$0" ] || MODDIR=.
STATE=$MODDIR/state
ROOT=${GOLFCORE_TEST_ROOT:-}
KEYS='boost_ms up_little up_big swappiness direct_swappiness watermark'
LOCKED=0

die() { echo "GolfCore: $*" >&2; exit 1; }
numeric() { case "$1" in ''|*[!0-9]*) return 1;; esac; }
node() {
    case "$1" in
        boost_ms) echo "$ROOT/sys/devices/system/cpu/cpu_boost/input_boost_ms";;
        up_little) echo "$ROOT/sys/devices/system/cpu/cpufreq/policy0/schedutil/up_rate_limit_us";;
        up_big) echo "$ROOT/sys/devices/system/cpu/cpufreq/policy4/schedutil/up_rate_limit_us";;
        swappiness) echo "$ROOT/proc/sys/vm/swappiness";;
        direct_swappiness) echo "$ROOT/proc/sys/vm/direct_swappiness";;
        watermark) echo "$ROOT/proc/sys/vm/watermark_scale_factor";;
        *) return 1;;
    esac
}
read_node() {
    rn_path=$(node "$1") || return 1
    rn_value=$(cat "$rn_path") || return 1
    numeric "$rn_value" || return 1
    echo "$rn_value"
}
write_node() {
    wn_path=$(node "$1") || return 1
    numeric "$2" || return 1
    [ -w "$wn_path" ] || return 1
    printf '%s\n' "$2" > "$wn_path" || return 1
    [ "$(read_node "$1")" = "$2" ]
}
field() { awk -F= -v key="$2" '$1 == key { print $2; exit }' "$1" 2>/dev/null; }
boot_id() { cat "$ROOT/proc/sys/kernel/random/boot_id"; }
guard() {
    case "$ROOT" in '')
        [ "$(id -u)" = 0 ] || die 'Root is required'
        [ "$(getprop ro.product.model)" = RMX3491 ] || die 'Only RMX3491 is supported'
        ;; *) [ -d "$ROOT/proc" ] || die 'Invalid test root';;
    esac
    grep -q '4.19.157-perf+ (golfcore@' "$ROOT/proc/version" || die 'GolfCore kernel required'
    BOOT=$(boot_id) || die 'Cannot read boot ID'
    case "$BOOT" in ''|*[!a-fA-F0-9-]*) die 'Invalid boot ID';; esac
}
valid_selection() {
    case "$1" in balanced|battery|gaming) ;; *) return 1;; esac
    case "$2" in stock|balanced) ;; *) return 1;; esac
}
selection() {
    CPU=balanced; MEMORY=balanced; AUTO=1
    if [ -f "$STATE/selection" ]; then
        CPU=$(field "$STATE/selection" cpu)
        MEMORY=$(field "$STATE/selection" memory)
        AUTO=$(field "$STATE/selection" autostart)
    fi
    valid_selection "$CPU" "$MEMORY" || die 'Invalid saved selection'
    case "$AUTO" in 0|1) ;; *) die 'Invalid autostart value';; esac
}
save_selection() {
    printf 'cpu=%s\nmemory=%s\nautostart=%s\n' "$CPU" "$MEMORY" "$AUTO" > "$STATE/selection.new" || return 1
    mv "$STATE/selection.new" "$STATE/selection"
}
rollback_pending() {
    [ -f "$STATE/pending" ] || return 0
    if [ "$(field "$STATE/pending" boot)" != "$BOOT" ]; then
        mv "$STATE/pending" "$STATE/previous-boot-pending"
        return
    fi
    # Restore only values still equal to this transaction's desired write.
    while IFS=' ' read -r rp_key rp_old rp_new; do
        case "$rp_key" in boot=*) continue;; esac
        node "$rp_key" >/dev/null || continue
        numeric "$rp_old" && numeric "$rp_new" || continue
        rp_current=$(read_node "$rp_key") || continue
        if [ "$rp_current" = "$rp_new" ] && [ "$rp_current" != "$rp_old" ]; then
            write_node "$rp_key" "$rp_old" || echo "Rollback failed: $rp_key" >&2
        fi
    done < "$STATE/pending"
    mv "$STATE/pending" "$STATE/last-rolled-back"
}
cleanup() {
    if [ "$LOCKED" = 1 ]; then
        rollback_pending
        rm -f "$STATE/lock/owner"
        rmdir "$STATE/lock" 2>/dev/null || :
    fi
}
lock() {
    mkdir -p "$STATE" || die 'Cannot create state directory'
    chmod 700 "$STATE" || die 'Cannot protect state directory'
    if ! mkdir "$STATE/lock" 2>/dev/null; then
        [ -f "$STATE/lock/owner" ] || die 'Another operation is starting'
        read -r lock_boot lock_pid < "$STATE/lock/owner" || die 'Invalid lock'
        numeric "$lock_pid" || die 'Invalid lock owner'
        if [ "$lock_boot" = "$BOOT" ] && kill -0 "$lock_pid" 2>/dev/null; then
            die 'Another operation is running'
        fi
        rm -f "$STATE/lock/owner"
        rmdir "$STATE/lock" || die 'Cannot clear stale lock'
        mkdir "$STATE/lock" || die 'Cannot acquire lock'
    fi
    LOCKED=1
    trap cleanup 0
    trap 'exit 1' 1 2 15
    printf '%s %s\n' "$BOOT" "$$" > "$STATE/lock/owner" || die 'Cannot save lock owner'
    rollback_pending
}
baseline() {
    if [ ! -f "$STATE/baseline" ] || [ "$(field "$STATE/baseline" boot)" != "$BOOT" ]; then
        printf 'boot=%s\n' "$BOOT" > "$STATE/baseline.new" || die 'Cannot save baseline'
        for base_key in $KEYS; do
            base_value=$(read_node "$base_key") || die "Cannot read $base_key"
            printf '%s=%s\n' "$base_key" "$base_value" >> "$STATE/baseline.new" || die 'Cannot save baseline'
        done
        mv "$STATE/baseline.new" "$STATE/baseline" || die 'Cannot commit baseline'
    fi
    for base_key in $KEYS; do
        numeric "$(field "$STATE/baseline" "$base_key")" || die 'Corrupt baseline'
    done
}
target() {
    target_value=$(field "$STATE/baseline" "$1")
    case "$CPU:$1" in
        battery:boost_ms) target_value=40;;
        battery:up_little|battery:up_big) target_value=2000;;
        gaming:boost_ms) target_value=120;;
    esac
    if [ "$MEMORY" = balanced ]; then
        case "$1" in direct_swappiness) target_value=40;; watermark) target_value=30;; esac
    fi
    numeric "$target_value" || return 1
    echo "$target_value"
}
apply() {
    baseline
    printf 'boot=%s\n' "$BOOT" > "$STATE/plan" || die 'Cannot create transaction'
    for ap_key in $KEYS; do
        ap_old=$(read_node "$ap_key") || die "Cannot read $ap_key"
        ap_new=$(target "$ap_key") || die "Invalid target for $ap_key"
        printf '%s %s %s\n' "$ap_key" "$ap_old" "$ap_new" >> "$STATE/plan" || die 'Cannot plan transaction'
    done
    mv "$STATE/plan" "$STATE/pending" || die 'Cannot begin transaction'
    while IFS=' ' read -r ap_key ap_old ap_new; do
        case "$ap_key" in boot=*) continue;; esac
        if [ "$ap_old" != "$ap_new" ]; then
            write_node "$ap_key" "$ap_new" || die "Write failed: $ap_key; rolling back"
        fi
    done < "$STATE/pending"
    for ap_key in $KEYS; do
        [ "$(read_node "$ap_key")" = "$(target "$ap_key")" ] || die "Readback conflict: $ap_key; rolling back"
    done
    mv "$STATE/pending" "$STATE/last-applied" || die 'Cannot commit transaction'
    save_selection || die 'Values applied, but saving selection failed'
    printf '%s cpu=%s memory=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$CPU" "$MEMORY" >> "$STATE/changes.log"
    echo "GolfCore: CPU=$CPU memory=$MEMORY autostart=$AUTO"
}
status() {
    echo "GolfCore Profiles: CPU=$CPU memory=$MEMORY autostart=$AUTO"
    printf '%-20s %-10s %-10s %s\n' NODE BASELINE CURRENT SELECTED
    if [ -f "$STATE/baseline" ] && [ "$(field "$STATE/baseline" boot)" = "$BOOT" ]; then
        for st_key in $KEYS; do
            printf '%-20s %-10s %-10s %s\n' "$st_key" "$(field "$STATE/baseline" "$st_key")" "$(read_node "$st_key")" "$(target "$st_key")"
        done
    else
        echo 'No baseline captured in this boot; no settings applied yet.'
    fi
}

guard
case "${1:-status}" in
    status) selection; status;;
    apply)
        [ "$#" -ge 2 ] && [ "$#" -le 3 ] || die 'Usage: profile.sh apply balanced|battery|gaming [stock|balanced]'
        valid_selection "$2" "${3:-balanced}" || die 'Invalid profile'
        lock; selection; CPU=$2; MEMORY=${3:-$MEMORY}; apply; status;;
    memory)
        [ "$#" = 2 ] || die 'Usage: profile.sh memory stock|balanced'
        valid_selection balanced "$2" || die 'Invalid memory mode'
        lock; selection; MEMORY=$2; apply; status;;
    restore)
        lock; selection; CPU=balanced; MEMORY=stock; AUTO=0
        if [ -f "$STATE/baseline" ] && [ "$(field "$STATE/baseline" boot)" = "$BOOT" ]; then
            apply
        else
            save_selection || die 'Cannot disable autostart'
            echo 'No baseline from this boot; autostart disabled without sysfs writes.'
        fi;;
    autostart)
        [ "$#" = 2 ] || die 'Usage: profile.sh autostart on|off'
        case "$2" in on|off) ;; *) die 'Invalid autostart mode';; esac
        lock; selection; [ "$2" = on ] && AUTO=1 || AUTO=0
        save_selection || die 'Cannot save autostart'; status;;
    cycle)
        lock; selection
        case "$CPU" in balanced) CPU=battery;; battery) CPU=gaming;; gaming) CPU=balanced;; esac
        apply; status;;
    boot)
        [ ! -e "$MODDIR/disable" ] && [ ! -e "$MODDIR/remove" ] || exit 0
        lock; selection
        [ "$AUTO" = 1 ] || exit 0
        apply;;
    *) die 'Commands: status, apply, memory, restore, autostart, cycle';;
esac
