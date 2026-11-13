#!/system/bin/sh
MODDIR=${0%/*}
# Restore the baseline from this boot before Magisk removes the module's state.
sh "$MODDIR/profile.sh" restore
