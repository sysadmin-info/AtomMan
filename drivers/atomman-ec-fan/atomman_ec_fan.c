// SPDX-License-Identifier: GPL-2.0-only
/* AtomMan X7 Ti EC fan RPM proof of concept (disabled by default).
 *
 * Tested on AtomMan X Series / MTBAC with Linux 7.0.0-42-generic:
 * repeated EC readings approx. 1906-1911 RPM. Temperature/load
 * correlation and long-term reliability are not yet established.
 * Enabling EC reads remains experimental.
 */
#include <linux/acpi.h>
#include <linux/dmi.h>
#include <linux/err.h>
#include <linux/hwmon.h>
#include <linux/jiffies.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/platform_device.h>
#include <linux/string.h>

#define DRIVER_NAME "atomman_ec_fan"
#define ACPI_READ_METHOD "\\_SB.PC00.LPCB.H_EC.EC2R"
#define EC_CMD_READ 0xD5
#define EC_RPM_LOW  0x18
#define EC_RPM_HIGH 0x19
#define EC_RPM_CEILING 4000

/* No hardware access unless explicitly opted in at module load. */
static bool enable_ec_reads;
module_param(enable_ec_reads, bool, 0400);
MODULE_PARM_DESC(enable_ec_reads,
                 "EXPERIMENTAL: permit EC2R hardware reads (default false)");

struct atomman_fan {
    struct mutex lock;
    acpi_handle method;
    unsigned long last_read;
    long rpm;
    bool cached;
};

static struct platform_device *fan_pdev;

static bool atomman_dmi_matches(void)
{
    const char *vendor = dmi_get_system_info(DMI_SYS_VENDOR);
    const char *product = dmi_get_system_info(DMI_PRODUCT_NAME);
    const char *board = dmi_get_system_info(DMI_BOARD_NAME);

    return vendor && product && board &&
           !strcmp(vendor, "Micro Computer (HK) Tech Limited") &&
           !strcmp(product, "AtomMan X Series") &&
           !strcmp(board, "MTBAC");
}

/* Calling ACPI method may issue EC I/O even though it returns only a byte. */
static int atomman_ec_read_byte(struct atomman_fan *fan, u8 address, u8 *result)
{
    struct acpi_object_list args;
    union acpi_object values[2];
    unsigned long long value;
    acpi_status status;

    values[0].type = ACPI_TYPE_INTEGER;
    values[0].integer.value = EC_CMD_READ;
    values[1].type = ACPI_TYPE_INTEGER;
    values[1].integer.value = address;
    args.count = ARRAY_SIZE(values);
    args.pointer = values;

    status = acpi_evaluate_integer(fan->method, NULL, &args, &value);
    if (ACPI_FAILURE(status))
        return -EIO;
    if (value > 0xff)
        return -ERANGE;

    *result = (u8)value;
    return 0;
}

static int atomman_read_rpm(struct atomman_fan *fan, long *out_rpm)
{
    u8 low, high;
    long rpm;
    int ret;

    /* This method is explicitly experimental; do not auto-probe the EC. */
    if (!enable_ec_reads)
        return -EOPNOTSUPP;

    mutex_lock(&fan->lock);
    if (fan->cached && time_before(jiffies, fan->last_read + HZ)) {
        *out_rpm = fan->rpm;
        mutex_unlock(&fan->lock);
        return 0;
    }

    ret = atomman_ec_read_byte(fan, EC_RPM_LOW, &low);
    if (ret)
        goto out;
    ret = atomman_ec_read_byte(fan, EC_RPM_HIGH, &high);
    if (ret)
        goto out;

    rpm = ((long)high << 8) | low;
    if (rpm >= EC_RPM_CEILING) {
        ret = -ERANGE; /* never silently publish an unverified value */
        goto out;
    }

    fan->rpm = rpm;
    fan->last_read = jiffies;
    fan->cached = true;
    *out_rpm = rpm;
out:
    mutex_unlock(&fan->lock);
    return ret;
}

static umode_t atomman_is_visible(const void *data,
                                 enum hwmon_sensor_types type,
                                 u32 attr, int channel)
{
    if (type == hwmon_fan && attr == hwmon_fan_input && channel == 0)
        return 0444;
    return 0;
}

static int atomman_hwmon_read(struct device *dev, enum hwmon_sensor_types type,
                             u32 attr, int channel, long *val)
{
    struct atomman_fan *fan = dev_get_drvdata(dev);

    if (type != hwmon_fan || attr != hwmon_fan_input || channel != 0)
        return -EOPNOTSUPP;
    return atomman_read_rpm(fan, val);
}

static const struct hwmon_ops atomman_hwmon_ops = {
    .is_visible = atomman_is_visible,
    .read = atomman_hwmon_read,
};

static const struct hwmon_channel_info * const atomman_hwmon_info[] = {
    HWMON_CHANNEL_INFO(fan, HWMON_F_INPUT),
    NULL,
};

static const struct hwmon_chip_info atomman_chip_info = {
    .ops = &atomman_hwmon_ops,
    .info = atomman_hwmon_info,
};

static int __init atomman_init(void)
{
    struct atomman_fan *fan;
    struct device *hwmon;
    acpi_status status;
    int ret;

    if (!atomman_dmi_matches()) {
        pr_err(DRIVER_NAME ": DMI mismatch; refusing to load\n");
        return -ENODEV;
    }

    fan_pdev = platform_device_register_simple(DRIVER_NAME, PLATFORM_DEVID_NONE,
                                               NULL, 0);
    if (IS_ERR(fan_pdev))
        return PTR_ERR(fan_pdev);

    fan = devm_kzalloc(&fan_pdev->dev, sizeof(*fan), GFP_KERNEL);
    if (!fan) {
        ret = -ENOMEM;
        goto unregister;
    }
    mutex_init(&fan->lock);

    status = acpi_get_handle(NULL, ACPI_READ_METHOD, &fan->method);
    if (ACPI_FAILURE(status)) {
        pr_err(DRIVER_NAME ": BIOS ACPI method EC2R not found\n");
        ret = -ENODEV;
        goto unregister;
    }

    hwmon = devm_hwmon_device_register_with_info(&fan_pdev->dev, DRIVER_NAME,
                                                 fan, &atomman_chip_info, NULL);
    if (IS_ERR(hwmon)) {
        ret = PTR_ERR(hwmon);
        goto unregister;
    }

    pr_info(DRIVER_NAME ": loaded; EC hardware reads are %s\n",
            enable_ec_reads ? "EXPERIMENTALLY ENABLED" : "DISABLED");
    return 0;

unregister:
    platform_device_unregister(fan_pdev);
    return ret;
}

static void __exit atomman_exit(void)
{
    platform_device_unregister(fan_pdev);
    pr_info(DRIVER_NAME ": unloaded\n");
}

module_init(atomman_init);
module_exit(atomman_exit);
MODULE_DESCRIPTION("AtomMan X7 Ti read-only EC fan RPM PoC - hardware access disabled by default");
MODULE_AUTHOR("Community proof of concept");
MODULE_LICENSE("GPL");
MODULE_VERSION("0.2.0-experimental");
