### AnyKernel3 Ramdisk Mod Script
## osm0sis @ xda-developers

### AnyKernel setup
# global properties
properties() { '
kernel.string=GolfCore v0.6 + SUSFS (KernelSU-Next) for Realme 9i 4G (RMX3491)
do.devicecheck=0
do.modules=0
do.systemless=1
do.cleanup=1
do.cleanuponabort=0
device.name1=RMX3491
device.name2=bengal
device.name3=khaje
device.name4=qssi
device.name5=gsi_arm64
supported.versions=
supported.patchlevels=
supported.vendorpatchlevels=
'; } # end properties

### AnyKernel install
# boot shell variables
BLOCK=/dev/block/bootdevice/by-name/boot;
IS_SLOT_DEVICE=0;
RAMDISK_COMPRESSION=auto;
PATCH_VBMETA_FLAG=auto;

# import functions/variables and setup patching - see for reference (DO NOT REMOVE)
. tools/ak3-core.sh;

# boot install (kernel-only: preserves existing DFE ramdisk and DTB)
split_boot;
flash_boot;
## end boot install

# vendor install (rebuilt EROFS vendor with matching ThinLTO modules)
if [ -f vendor.img ]; then
  VENDOR_BLK="";
  for b in /dev/block/mapper/vendor /dev/block/bootdevice/by-name/vendor; do
    if [ -b "$b" ]; then
      VENDOR_BLK="$b";
      break;
    fi;
  done;
  if [ -z "$VENDOR_BLK" ]; then
    abort "Vendor block device not found!";
  fi;
  ui_print "- Flashing GolfCore vendor (33 ThinLTO modules)...";
  umount /vendor 2>/dev/null || true;
  blockdev --setrw "$VENDOR_BLK" 2>/dev/null || true;
  dd if=vendor.img of="$VENDOR_BLK" bs=4194304 || abort "Failed to flash vendor.img";
  sync;
  rm -f vendor.img;
fi;
