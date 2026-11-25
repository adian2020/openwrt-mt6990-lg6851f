// SPDX-License-Identifier: GPL-2.0-only
/* Decode the shared CPU PLL on LG6851F using the MediaTek F370 format. */
#include <linux/bitfield.h>
#include <linux/io.h>
#include <linux/math64.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/slab.h>

struct lg6851f_cpu_clock {
	void __iomem *pll;
	void __iomem *divider;
};

static ssize_t cpu_pll_cur_freq_show(struct device *dev,
				     struct device_attribute *attr, char *buf)
{
	const struct lg6851f_cpu_clock *clk = dev_get_drvdata(dev);
	u32 pll = readl(clk->pll);
	u32 divider = readl(clk->divider);
	u32 postdiv = FIELD_GET(GENMASK(26, 24), pll);
	u32 div = FIELD_GET(GENMASK(21, 17), divider);
	u64 khz;

	if (pll != readl(clk->pll) || divider != readl(clk->divider))
		return -EAGAIN;

	if (postdiv > 4)
		return -ENODATA;

	khz = div_u64((u64)FIELD_GET(GENMASK(21, 0), pll) * 26000,
		      16384U << postdiv);
	if (div >= 9 && div <= 11)
		khz = div_u64(khz * (12 - div), 4);
	else if (div >= 17 && div <= 20)
		khz = div_u64(khz * (21 - div), 5);
	else if (div >= 25 && div <= 29)
		khz = div_u64(khz * (30 - div), 6);
	else if (div != 0 && div != 8 && div != 16 && div != 24)
		return -ENODATA;

	if (!khz)
		return -ENODATA;

	return sysfs_emit(buf, "%llu\n", khz);
}
static DEVICE_ATTR_RO(cpu_pll_cur_freq);

static struct attribute *lg6851f_cpu_clock_attrs[] = {
	&dev_attr_cpu_pll_cur_freq.attr,
	NULL,
};
ATTRIBUTE_GROUPS(lg6851f_cpu_clock);

static int lg6851f_cpu_clock_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	const struct resource *pll, *divider;
	struct lg6851f_cpu_clock *clk;

	if (!of_machine_is_compatible("fiberhome,lg6851f"))
		return -ENODEV;

	pll = platform_get_resource(pdev, IORESOURCE_MEM, 0);
	divider = platform_get_resource(pdev, IORESOURCE_MEM, 1);
	if (!pll || !divider || pll->start != 0x100102f4 ||
	    divider->start != 0x0c53a2a0 ||
	    resource_size(pll) != 4 || resource_size(divider) != 4)
		return -EINVAL;

	clk = devm_kzalloc(dev, sizeof(*clk), GFP_KERNEL);
	if (!clk)
		return -ENOMEM;

	/* These registers are shared with the existing clock providers. */
	clk->pll = devm_ioremap(dev, pll->start, resource_size(pll));
	clk->divider = devm_ioremap(dev, divider->start, resource_size(divider));
	if (!clk->pll || !clk->divider)
		return -ENOMEM;

	platform_set_drvdata(pdev, clk);
	return 0;
}

static const struct of_device_id lg6851f_cpu_clock_of_match[] = {
	{ .compatible = "fiberhome,lg6851f-cpu-frequency" },
	{ }
};
MODULE_DEVICE_TABLE(of, lg6851f_cpu_clock_of_match);

static struct platform_driver lg6851f_cpu_clock_driver = {
	.probe = lg6851f_cpu_clock_probe,
	.driver = {
		.name = "lg6851f-cpu-frequency",
		.of_match_table = lg6851f_cpu_clock_of_match,
		.dev_groups = lg6851f_cpu_clock_groups,
	},
};
module_platform_driver(lg6851f_cpu_clock_driver);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Read-only LG6851F shared CPU PLL frequency");
