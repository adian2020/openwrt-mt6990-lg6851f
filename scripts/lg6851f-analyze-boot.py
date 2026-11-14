#!/usr/bin/env python3
"""Summarize one monotonic boot trace; never guess missing stage timings."""
import argparse
import pathlib
import re

MARKER = re.compile(r'LG6851F_BOOT_STAGE uptime=([0-9]+(?:\.[0-9]+)?) phase=(\S+)([^\n]*)')

def analyze(text):
    heading = '=== 本次启动阶段（内核运行秒数，不代表上电总耗时） ==='
    if heading in text:
        text = text.split(heading, 1)[1].split('\n=== ', 1)[0]
    boot_ids = set(re.findall(r'^LG6851F_BOOT_ID=([^\s]+)', text, re.M))
    if len(boot_ids) > 1:
        raise ValueError('输入包含多个启动UUID，请先选取同一次启动，不能跨启动相减')
    events = [(float(t), phase, tail.strip()) for t, phase, tail in MARKER.findall(text)]
    if not events:
        return ['没有阶段打点，不能追溯kmodloader或首次配置脚本耗时；请保留原始启动日志。']
    events = sorted(set(events))
    result = ['计时起点：内核uptime=0，不包含上电至内核启动的引导器时间。']
    if boot_ids:
        result.append('启动UUID：' + next(iter(boot_ids)))
    def first(phase):
        return next((e for e in events if e[1] == phase), None)
    def pair(label, begin, end):
        a = first(begin)
        b = next((e for e in events if e[1] == end and (not a or e[0] >= a[0])), None)
        if a and b:
            result.append(f'{label}：{a[0]:.2f} → {b[0]:.2f} 秒，耗时 {b[0]-a[0]:.2f} 秒；{b[2] or "已记录结束"}')
        else:
            result.append(label + '：起止记录不足，未计算')
    pair('preinit已记录区间', 'preinit-begin', 'preinit-complete')
    pair('S09存储准备', 'storage-begin', 'storage-end')
    pair('WiFi EEPROM准备', 'eeprom-prepare-begin', 'eeprom-prepare-end')
    pair('S10启动区间', 's10-boot-begin', 's10-boot-end')
    pair('模块批量加载（kmodloader，不等同单个驱动）', 'kmodloader-begin', 'kmodloader-end')
    pair('S10无线配置生成', 'boot-wifi-config-begin', 'boot-wifi-config-end')
    pair('uci-defaults总区间（本次待执行项）', 'defaults-begin', 'defaults-end')
    pair('首次WiFi配置生成', 'wifi-config-begin', 'wifi-config-end')
    pair('wifi up请求返回（不代表热点已启用）', 'wifi-up-request-begin', 'wifi-up-request-end')
    scripts = []
    pending = {}
    for stamp, phase, tail in events:
        if phase == 'defaults-script-begin':
            pending[tail] = stamp
        elif phase == 'defaults-script-end':
            name = tail.split()[0] if tail else ''
            if name in pending:
                scripts.append((stamp-pending.pop(name), name, tail))
    if scripts:
        result.append('本次uci-defaults脚本耗时（从长到短）：')
        result.extend(f'  {duration:.2f} 秒  {tail}' for duration, name, tail in sorted(scripts, reverse=True))
    result.extend('  未结束：' + name for name in pending)
    phys = {}
    for event in events:
        if event[1] == 'phy-observed' and event[2]:
            phys.setdefault(event[2].split()[0], event)
    ap = first('ap-running-observed')
    for name, phy in sorted(phys.items()):
        result.append(f'{name}首次目录观测：内核运行 {phy[0]:.2f} 秒；{phy[2]}（采样上界）')
        if ap and ap[0] >= phy[0]:
            result.append(f'{name}观测到首个热点运行观测间隔：{ap[0]-phy[0]:.2f} 秒（采样点差，非精确驱动区间，未指认该PHY为首个热点）')
    if ap:
        result.append(f'首个热点运行确认：内核运行不晚于 {ap[0]:.2f} 秒；{ap[2]}（仅成功状态查询构成边界，不是上电总耗时）')
    else:
        result.append('首个热点运行确认：没有记录；不能用wifi up返回替代')
    if any(e[1] == 'phy-add-hotplug' for e in events):
        result.append('PHY hotplug是处理时间，可能受队列延迟影响，不能代替内核注册瞬间。')
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=pathlib.Path)
    args = parser.parse_args()
    print('\n'.join(analyze(args.report.read_text(errors='replace'))))

if __name__ == '__main__':
    main()
