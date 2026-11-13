#!/system/bin/sh
MODDIR=${0%/*}
# Non-blocking late_start script. Apply once after Android/vendor initialization.
attempt=0
while [ "$(getprop sys.boot_completed)" != 1 ]; do
    attempt=$((attempt + 1))
    [ "$attempt" -lt 60 ] || exit 0
    sleep 3
done
sleep 30
[ ! -e "$MODDIR/disable" ] && [ ! -e "$MODDIR/remove" ] || exit 0
mkdir -p "$MODDIR/state" || exit 1
chmod 700 "$MODDIR/state" || exit 1
sh "$MODDIR/profile.sh" boot >> "$MODDIR/state/boot.log" 2>&1
