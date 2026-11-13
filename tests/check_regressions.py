#!/usr/bin/env python3
"""Exercise actual source fragments with mocked IRQ ownership and allocator WARN.

These host checks cover control flow, not hardware or kernel concurrency.
Pass --source-root to a layout containing kernel/msm-4.19 and vendor.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument('--check', choices=['all', 'touch', 'allocator'], default='all')
args = parser.parse_args()


def function(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    # Inner blocks are indented; conditional compilation has alternative opens.
    end = text.index('\n}', opening) + 2
    return text[start:end]


touch = (args.source_root / 'vendor/oplus/kernel/touchpanel/oplus_touchscreen/'
         'touchpanel_common_driver.c').read_text()
resume = function(touch, 'static bool tp_resume(' if 'static bool tp_resume(' in touch
                  else 'static void tp_resume(')
# The first occurrence is a prototype; search after the resume definition.
callback = function(touch[touch.index(resume) + len(resume):],
                    'static int fb_notifier_callback(')
prefix = r'''
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#define CONFIG_DRM_MSM 1
#define CONFIG_FB 1
#define HZ 100
#define TP_LCD_SUSPEND 0
#define LCD_TP_SUSPEND 1
#define TP_LCD_RESUME 0
#define LCD_TP_RESUME 1
#define TP_RESUME_COMPLETE 2
#define TP_SPEEDUP_RESUME_COMPLETE 3
#define TP_SUSPEND_EARLY_EVENT 4
#define TP_RESUME_EARLY_EVENT 5
#define UNBANNABLE 1
#define MSM_DRM_EARLY_EVENT_BLANK 2
#define MSM_DRM_EVENT_BLANK 1
#define MSM_DRM_BLANK_POWERDOWN 4
#define MSM_DRM_BLANK_UNBLANK 0
#define TPD_INFO(...) ((void)0)
#define container_of(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
struct completion { int done; };
struct notifier_block { int unused; };
struct fb_event { void *data; };
struct device { void *data; };
struct ops {
    void (*reinit_device)(void *);
    void (*resume_prepare)(void *);
};
struct touchpanel_data {
    struct device *dev;
    struct notifier_block fb_notif;
    struct completion pm_complete;
    struct { int monitor_down, monitor_up; } monitor_data;
    struct ops *ts_ops;
    void *chip_data, *grip_info, *prEntry_tp, *speedup_resume_wq;
    int speed_up_work, mutex, irq, int_mode, suspend_state, resume_finished;
    bool is_suspended, loading_fw, disable_gesture_ctrl, hall_status;
    bool irq_trigger_hdl_support, lcd_wait_tp_resume_finished_support;
    bool kernel_grip_support, esd_handle_support, is_incell_panel, gesture_enable;
    int tp_suspend_order, tp_resume_order, esd_info;
};
static int owned, depth, bad, freed, queued, enabled;
static void *dev_get_drvdata(struct device *dev) { return dev->data; }
static void mutex_lock(int *m) { (void)m; }
static void mutex_unlock(int *m) { (void)m; }
static void complete(struct completion *c) { c->done++; }
static int wait_for_completion_timeout(struct completion *c, int t) { return 1; }
static void free_irq(int irq, void *data) {
    if (!owned) bad++;
    owned = 0; depth = 1; freed++;
}
static void disable_irq_nosync(int irq) { if (!owned) bad++; depth++; }
static void enable_irq(int irq) {
    if (!owned || depth == 0) bad++;
    depth--; enabled++;
}
static void queue_work(void *wq, int *work) { queued++; }
static void kernel_grip_reset(void *p) {}
static void *kernel_grip_init(struct device *d) { return NULL; }
static void init_kernel_grip_proc(void *p, void *g) {}
static void esd_handle_switch(int *e, bool enabled) {}
static int tp_suspend(struct device *d) { return 0; }
'''
suffix = r'''
int main(void) {
    int cases = 0;
    for (int order = 0; order < 2; order++)
    for (int suspended = 0; suspended < 2; suspended++)
    for (int loading = 0; loading < 2; loading++)
    for (int trigger = 0; trigger < 2; trigger++)
    for (int mode = 0; mode < 2; mode++) {
        struct ops ops = {0};
        struct touchpanel_data ts = {0};
        struct device dev = { .data = &ts };
        ts.dev = &dev; ts.chip_data = &ts; ts.ts_ops = &ops;
        ts.is_suspended = suspended; ts.loading_fw = loading;
        ts.irq_trigger_hdl_support = trigger; ts.int_mode = mode;
        ts.tp_resume_order = order;
        int blank = MSM_DRM_BLANK_UNBLANK;
        struct fb_event event = { .data = &blank };
        owned = 1; depth = bad = freed = queued = enabled = 0;
        fb_notifier_callback(&ts.fb_notif, MSM_DRM_EARLY_EVENT_BLANK, &event);
        fb_notifier_callback(&ts.fb_notif, MSM_DRM_EVENT_BLANK, &event);
        int expect_free = suspended && !loading && !trigger;
        int expect_queue = suspended && !loading;
        if (bad || freed != expect_free || queued != expect_queue ||
            owned != !expect_free || (!expect_free && depth != 0)) {
            fprintf(stderr, "IRQ lifetime failure: order=%d suspended=%d "
                    "loading=%d trigger=%d mode=%d bad=%d depth=%d\n",
                    order, suspended, loading, trigger, mode, bad, depth);
            return 1;
        }
        cases++;
    }
    printf("Touch resume: %d cases passed\n", cases);
    return 0;
}
'''

allocator = (args.source_root / 'kernel/msm-4.19/mm/page_alloc.c').read_text()
start = allocator.index('\tif (WARN_ON_ONCE((gfp_mask & (__GFP_ATOMIC|__GFP_DIRECT_RECLAIM))')
block = allocator[start:allocator.index('retry_cpuset:', start)]
allocator_test = r'''
#include <stdio.h>
#define __GFP_ATOMIC (1U << 19)
#define __GFP_DIRECT_RECLAIM (1U << 21)
#define ___GFP_HIGH_ATOMIC_ZRAM (1U << 25)
static int warned;
#define WARN_ON_ONCE(x) ((x) ? (warned++, 1) : 0)
static unsigned checked(unsigned gfp_mask) {
''' + block + r'''
    return gfp_mask;
}
int main(void) {
    for (int bits = 0; bits < 8; bits++) {
        unsigned mask = (bits & 1 ? __GFP_ATOMIC : 0) |
                        (bits & 2 ? __GFP_DIRECT_RECLAIM : 0) |
                        (bits & 4 ? ___GFP_HIGH_ATOMIC_ZRAM : 0);
        int invalid = (bits & 3) == 3;
#ifdef VENDOR_EDIT
        invalid = invalid && !(bits & 4);
#endif
        unsigned expected = invalid ? mask & ~__GFP_ATOMIC : mask;
        warned = 0;
        unsigned actual = checked(mask);
        if (actual != expected || warned != invalid) {
            fprintf(stderr, "Allocator flag failure: bits=%d warned=%d\n", bits, warned);
            return 1;
        }
    }
    puts("Allocator flags: 8 cases passed");
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix='golfcore-regression-') as directory:
    temp = Path(directory)
    cases = [('touch', prefix + resume + '\n' + callback + suffix, []),
             ('allocator-vendor', allocator_test, ['-DVENDOR_EDIT']),
             ('allocator-upstream', allocator_test, [])]
    for name, code, flags in cases:
        if args.check == 'touch' and name != 'touch':
            continue
        if args.check == 'allocator' and name == 'touch':
            continue
        source, executable = temp / (name + '.c'), temp / name
        source.write_text(code)
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Werror', '-Wno-unused-parameter',
                        *flags, str(source), '-o', str(executable)], check=True)
        subprocess.run([str(executable)], check=True)
