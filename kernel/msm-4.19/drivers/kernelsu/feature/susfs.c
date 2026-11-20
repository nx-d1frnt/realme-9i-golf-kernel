// SPDX-License-Identifier: GPL-2.0
/* SUSFS 1.5.5 non-GKI ABI bridge for KernelSU-Next. */
#include <linux/cred.h>
#include <linux/errno.h>
#include <linux/fs.h>
#include <linux/namei.h>
#include <linux/susfs.h>
#include <linux/uaccess.h>

static u64 susfs_features(void)
{
    u64 features = 0;
#ifdef CONFIG_KSU_SUSFS_SUS_PATH
    features |= (1ULL << 0);
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
    features |= (1ULL << 1);
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_SUS_KSU_DEFAULT_MOUNT
    features |= (1ULL << 2);
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_SUS_BIND_MOUNT
    features |= (1ULL << 3);
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
    features |= (1ULL << 4);
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_OVERLAYFS
    features |= (1ULL << 5);
#endif
#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
    features |= (1ULL << 6);
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT
    features |= (1ULL << 7);
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
    features |= (1ULL << 8);
#endif
#ifdef CONFIG_KSU_SUSFS_ENABLE_LOG
    features |= (1ULL << 9);
#endif
#ifdef CONFIG_KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS
    features |= (1ULL << 10);
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG
    features |= (1ULL << 11);
#endif
#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT
    features |= (1ULL << 12);
#endif
#ifdef CONFIG_KSU_SUSFS_HAS_MAGIC_MOUNT
    features |= (1ULL << 14);
#endif
    return features;
}

int ksu_susfs_prctl(int option, unsigned long cmd, unsigned long arg,
                    unsigned long result)
{
    void __user *data = (void __user *)arg;
    int error = -EOPNOTSUPP;
    u64 features;

    /* No manager or unprivileged caller may change global SUSFS state. */
    if (option != 0xDEADBEEF || !uid_eq(current_uid(), GLOBAL_ROOT_UID))
        return -EPERM;
    if (!access_ok(VERIFY_WRITE, (void __user *)result, sizeof(error)))
        return -EFAULT;

    switch (cmd) {
#ifdef CONFIG_KSU_SUSFS_SUS_PATH
    case CMD_SUSFS_ADD_SUS_PATH:
        error = susfs_add_sus_path(data);
        break;
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
    case CMD_SUSFS_ADD_SUS_MOUNT:
        error = susfs_add_sus_mount(data);
        break;
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
    case CMD_SUSFS_ADD_SUS_KSTAT:
        error = susfs_add_sus_kstat(data);
        break;
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
    case CMD_SUSFS_ADD_SUS_KSTAT_STATICALLY:
        error = susfs_add_sus_kstat(data);
        break;
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
    case CMD_SUSFS_UPDATE_SUS_KSTAT:
        error = susfs_update_sus_kstat(data);
        break;
#endif
#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
    case CMD_SUSFS_ADD_TRY_UMOUNT:
        error = susfs_add_try_umount(data);
        break;
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
    case CMD_SUSFS_SET_UNAME:
        error = susfs_set_uname(data);
        break;
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG
    case CMD_SUSFS_SET_CMDLINE_OR_BOOTCONFIG:
        error = susfs_set_cmdline_or_bootconfig(data);
        break;
#endif
#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT
    case CMD_SUSFS_ADD_OPEN_REDIRECT:
        error = susfs_add_open_redirect(data);
        break;
#endif
#ifdef CONFIG_KSU_SUSFS_ENABLE_LOG
    case CMD_SUSFS_ENABLE_LOG:
        if (arg > 1) {
            error = -EINVAL;
            break;
        }
        susfs_set_log(arg);
        error = 0;
        break;
#endif
#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
    case CMD_SUSFS_RUN_UMOUNT_FOR_CURRENT_MNT_NS: {
        extern void susfs_run_try_umount_for_current_mnt_ns(void);
        susfs_run_try_umount_for_current_mnt_ns();
        error = 0;
        break;
    }
#endif
    case CMD_SUSFS_SHOW_VERSION:
        error = copy_to_user(data, SUSFS_VERSION, sizeof(SUSFS_VERSION)) ? -EFAULT : 0;
        break;
    case CMD_SUSFS_SHOW_VARIANT:
        error = copy_to_user(data, SUSFS_VARIANT, sizeof(SUSFS_VARIANT)) ? -EFAULT : 0;
        break;
    case CMD_SUSFS_SHOW_ENABLED_FEATURES:
        features = susfs_features();
        error = copy_to_user(data, &features, sizeof(features)) ? -EFAULT : 0;
        break;
    case CMD_SUSFS_SHOW_SUS_SU_WORKING_MODE:
    case CMD_SUSFS_IS_SUS_SU_READY: {
        int disabled = 0; /* SUS_SU is unsupported on non-GKI/manual hooks. */
        error = copy_to_user(data, &disabled, sizeof(disabled)) ? -EFAULT : 0;
        break;
    }
    }
    return copy_to_user((void __user *)result, &error, sizeof(error)) ? -EFAULT : 0;
}

void ksu_susfs_on_post_fs_data(void)
{
    struct path path;
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_SUS_BIND_MOUNT
    {
        extern bool susfs_is_auto_add_sus_bind_mount_enabled;
        if (!kern_path(DATA_ADB_NO_AUTO_ADD_SUS_BIND_MOUNT, LOOKUP_FOLLOW, &path)) {
            susfs_is_auto_add_sus_bind_mount_enabled = false;
            path_put(&path);
        }
    }
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_SUS_KSU_DEFAULT_MOUNT
    {
        extern bool susfs_is_auto_add_sus_ksu_default_mount_enabled;
        if (!kern_path(DATA_ADB_NO_AUTO_ADD_SUS_KSU_DEFAULT_MOUNT, LOOKUP_FOLLOW, &path)) {
            susfs_is_auto_add_sus_ksu_default_mount_enabled = false;
            path_put(&path);
        }
    }
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT
    {
        extern bool susfs_is_auto_add_try_umount_for_bind_mount_enabled;
        if (!kern_path(DATA_ADB_NO_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT, LOOKUP_FOLLOW, &path)) {
            susfs_is_auto_add_try_umount_for_bind_mount_enabled = false;
            path_put(&path);
        }
    }
#endif
}
