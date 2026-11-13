[ "$BOOTMODE" = true ] || abort 'Install from the Magisk app only'
[ "$(getprop ro.product.model)" = RMX3491 ] || abort 'Only RMX3491 is supported'
grep -Eq '^Linux version 4[.]19[.]157-(perf[+]|GolfCore-v[0-9][^ ]*) [(]golfcore@' /proc/version || abort 'GolfCore kernel required'
ui_print 'GolfCore Profiles: Balanced / Battery / Gaming'
ui_print 'Memory: stock / experimental balanced; restore is available'
mkdir -p "$MODPATH/state"
set_perm_recursive "$MODPATH" 0 0 0755 0644
for script in profile.sh service.sh action.sh uninstall.sh; do
    set_perm "$MODPATH/$script" 0 0 0755
done
set_perm "$MODPATH/state" 0 0 0700
