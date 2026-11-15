#!/usr/bin/env python3
"""Hash-pinned, host-only replay of user-provided LG6851F preloader evidence.

Requires Python unicorn. Executes original Thumb code with in-memory storage,
registers, PMIC and reset boundaries. No device I/O or firmware modification.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R4, UC_ARM_REG_R5,
    UC_ARM_REG_LR, UC_ARM_REG_SP,
)

EXPECTED = '728178fd02c36979c3433ae39d89e5be29f628c1c40ebbbe03f42c1fb4441e97'
BIAS, STACK, STOP = 0x200690, 0x30000000, 0x10000000


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def control(pa=14, pb=15, ra=0, rb=0, sa=1, sb=1):
    result = bytearray(34)
    result[4:10] = b'BCAB\x01\x02'
    result[12:17] = bytes([pa, ra, sa, 1, 0])
    result[17:22] = bytes([pb, rb, sb, 1, 0])
    return result


class Replay:
    def __init__(self, image, record=None, bootpart=2, status=0x40000000,
                 bypass=True, pmic_reset=False, abnormal=False,
                 read_error=False, write_error=False):
        self.u = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        for address, size in [(0x200000, 0x110000), (0x100000, 0x20000),
                              (0x12007000, 0x1000), (STACK, 0x10000),
                              (STOP, 0x1000)]:
            self.u.mem_map(address, size)
        self.u.mem_write(BIAS, image)
        # Execute BX LR at mocked boundaries instead of assigning PC inside
        # a code hook. The instruction consumes Thumb IT state correctly even
        # when a caller reached this translation block after an IT sequence.
        boundaries = [0xf2c, 0x16b4a, 0x15498, 0xb440, 0xb494, 0x1558c]
        if abnormal is not None:
            boundaries.append(0x17090)
        for offset in boundaries:
            self.u.mem_write(BIAS + offset, b'\x70\x47')
        self.record = bytearray(control() if record is None else record)
        self.bootpart, self.pmic_reset, self.abnormal = bootpart, pmic_reset, abnormal
        self.read_error, self.write_error = read_error, write_error
        self.writes, self.logs, self.switched, self.resets = [], [], [], []
        self.ended, self.reason = False, None
        self.word(0x1200700c, status)
        self.word(0x1149f4, 0x2000 if bypass else 0)
        self.setup_ram()
        self.u.hook_add(UC_HOOK_CODE, self.hook)
        self.u.hook_add(UC_HOOK_MEM_WRITE, self.write_hook)

    def word(self, address, value):
        self.u.mem_write(address, struct.pack('<I', value))

    def setup_ram(self, status=2, step=0, valid_type=True):
        # Synthetic RAM_CONSOLE header and previous-stage records.
        self.word(0x111894, 0x110000)
        self.word(0x111898, 0x1000)
        self.word(0x110004, 0x40)
        self.word(0x11002c, 0x80)
        self.word(0x110040, status)
        self.word(0x110080, step)
        self.word(0x110084, 0xaeedead1 if valid_type else 0)

    def ret(self, value=None):
        if value is not None:
            self.u.reg_write(UC_ARM_REG_R0, value & 0xffffffff)

    def stop(self):
        self.ended = True
        self.u.emu_stop()

    def write_hook(self, machine, access, address, size, value, data):
        allowed = any(start <= address and address + size <= end for start, end in [
            (STACK, STACK + 0x10000), (0x100000, 0x120000),
            (0x12007000, 0x12008000), (0x25fb78, 0x25fb79),
        ])
        require(allowed, f'unexpected emulated memory write: {address:#x}')

    def hook(self, machine, pc, size, data):
        if pc == STOP:
            self.stop()
            return
        offset = pc - BIAS
        if offset == 0xf2c:
            pointer = machine.reg_read(UC_ARM_REG_R0)
            mode = machine.reg_read(UC_ARM_REG_R1)
            require(mode in (0, 1), 'unexpected record I/O mode')
            if mode == 0:
                if not self.read_error:
                    machine.mem_write(pointer, bytes(self.record))
                self.ret(-1 if self.read_error else 0)
            else:
                value = bytes(machine.mem_read(pointer, 34))
                self.writes.append(value.hex())
                if not self.write_error:
                    self.record[:] = value
                self.ret(-1 if self.write_error else 0)
        elif offset == 0x16b4a:
            pointer = machine.reg_read(UC_ARM_REG_R0)
            self.logs.append(bytes(machine.mem_read(pointer, 180)).split(b'\0')[0]
                             .decode('ascii', errors='replace'))
            self.ret()
        elif offset == 0x15498:
            self.ret(int(self.pmic_reset))
        elif offset == 0xb440:
            self.word(machine.reg_read(UC_ARM_REG_R0), self.bootpart)
            self.ret(0)
        elif offset == 0xb494:
            self.switched.append(machine.reg_read(UC_ARM_REG_R0))
            self.ret(0)
        elif offset == 0x17090 and self.abnormal is not None:
            self.ret(int(self.abnormal))
        elif offset == 0x1558c:
            self.ret(0)
        elif offset == 0x44b1c:
            self.resets.append(machine.reg_read(UC_ARM_REG_R0))
            self.stop()
        elif offset == 0x14410:
            raise RuntimeError('preloader assertion reached')
        elif offset == 0x14002:
            self.reason = machine.reg_read(UC_ARM_REG_R5)
            self.stop()
        elif offset == 0x14338:
            # Other boot-reason paths are outside this selected WDT slice.
            self.stop()

    def run(self, offset):
        self.ended = False
        self.u.reg_write(UC_ARM_REG_SP, STACK + 0xff00)
        self.u.reg_write(UC_ARM_REG_LR, STOP | 1)
        self.u.reg_write(UC_ARM_REG_R4, 0x110200)
        self.u.reg_write(UC_ARM_REG_R5, 0)
        self.u.emu_start((BIAS + offset) | 1, STOP + 2, count=10000)
        require(self.ended, 'instruction budget exhausted')
        return self.u.reg_read(UC_ARM_REG_R0)

    def flag(self):
        return bytes(self.u.mem_read(0x25fb78, 1))[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path, help='mmcblk0boot0/1.prefix.img')
    args = parser.parse_args()
    require(args.image.is_file(), 'input must be a regular evidence file')
    image = args.image.read_bytes()
    require(len(image) == 1048576 and hashlib.sha256(image).hexdigest() == EXPECTED,
            'unknown image: fixed offsets require the documented evidence hash')
    require(image[:9] == b'EMMC_BOOT', 'unexpected eMMC boot header')
    # Main calls platform preinit (which calls the boot check) BEFORE the
    # boot-reason function containing the increment. Do not reverse phases.
    require(image[0x9642:0x9646] == bytes.fromhex('0af0f1fa') and
            image[0x96f0:0x96f4] == bytes.fromhex('0af0dcfb') and
            image[0x13dc6:0x13dca] == bytes.fromhex('edf71dff'),
            'unexpected call sites for boot-check-before-increment order')
    counts = dict(counter=0, reset_classification=0, boot_check=0,
                  ram_console=0, combined_boots=0)
    for pa, pb in [(15, 14), (14, 15), (15, 15)]:
        for retry in [0, 1, 2, 3, 4, 254, 255]:
            for sa in [0, 1]:
                for sb in [0, 1]:
                    before = control(pa, pb, retry, retry, sa, sb)
                    expected = before.copy()
                    chosen = 13 if pa >= pb else 18
                    expected[chosen] = (retry + 1) & 255
                    m = Replay(image, before)
                    require(m.run(0x10a4) == 0 and m.record == expected,
                            'counter did not change only the chosen TRY byte')
                    require(len(m.writes) == 1, 'unexpected counter write count')
                    counts['counter'] += 1
    for read_error, write_error in [(True, False), (False, True)]:
        before = control(rb=2)
        m = Replay(image, before, read_error=read_error, write_error=write_error)
        require(m.run(0x10a4) == 0xffffffff and m.record == before,
                'counter I/O failure was not reported')
        require(len(m.writes) == int(write_error), 'write after failed read')
        counts['counter'] += 1
    for status in [0, 0x40000000, 0x80000000, 0x20000, 0x10,
                   0x40040000, 0x40000010, 0x04000000]:
        for bypass in [False, True]:
            for pmic_reset in [False, True]:
                normalized = status & ~0x20010
                significant = normalized & ~0x2fc0ff00
                flag = 1
                if significant:
                    classification = 2 if bypass else 1
                    if bypass and normalized & 0x40010:
                        flag = 0
                else:
                    classification = 2 if pmic_reset else 0
                    if pmic_reset:
                        flag = 0
                m = Replay(image, status=status, bypass=bypass, pmic_reset=pmic_reset)
                require((m.run(0x44ad4), m.flag()) == (classification, flag),
                        'reset classification/flag mismatch')
                n = Replay(image, control(rb=2), status=status,
                           bypass=bypass, pmic_reset=pmic_reset)
                n.run(0x142f6)
                require(n.record[18] == 2 + int(classification == 2 and flag == 1),
                        'WDT route increment mismatch')
                require(n.reason == {0: None, 1: 3, 2: 4}[classification],
                        'selected WDT boot-reason mismatch')
                counts['reset_classification'] += 1
    for selected in [1, 2]:
        for bootpart in [1, 2]:
            for retry in [0, 1, 3, 4, 5, 255]:
                for other in [0, 3, 4]:
                    for abnormal in [False, True]:
                        for success in [0, 1]:
                            before = control(15, 14, retry, other, success, success) \
                                if selected == 1 else control(14, 15, other, retry, success, success)
                            m = Replay(image, before, bootpart=bootpart, abnormal=abnormal)
                            m.run(0x1c04)
                            target = None
                            if not abnormal:
                                if bootpart != selected:
                                    target = selected
                                elif retry > 3 and other <= 3:
                                    target = 3 - selected
                            require(m.switched == ([] if target is None else [target]),
                                    f'boot-check target mismatch: selected={selected}, '
                                    f'bootpart={bootpart}, retry={retry}, other={other}, '
                                    f'abnormal={abnormal}, success={success}, '
                                    f'actual={m.switched}, logs={m.logs}')
                            expected = before.copy()
                            if target is not None:
                                expected[12], expected[17] = (15, 14) if target == 1 else (14, 15)
                            require(m.record == expected, 'boot-check changed unexpected fields')
                            require(m.resets == ([] if target is None else [1]),
                                    'boot-check reset request mismatch')
                            counts['boot_check'] += 1
    for status, step, valid_type, expected in [
        (0, 0, True, 0), (2, 0, True, 0), (0x800, 0, True, 0),
        (1, 0, True, 1), (2, 1, True, 1), (2, 1, False, 0),
        (0x200, 0, True, 0), (0x2000, 0, True, 0),
    ]:
        m = Replay(image, abnormal=None)
        m.setup_ram(status, step, valid_type)
        require(m.run(0x17090) == expected, 'actual RAM_CONSOLE abnormal check mismatch')
        counts['ram_console'] += 1
    record, chain = control(), []
    for attempt in range(1, 6):
        m = Replay(image, record, abnormal=None)
        m.run(0x1c04)
        require(m.switched == ([1] if attempt == 5 else []),
                'combined normal-RAM-console boot-check mismatch')
        if not m.switched:
            m.run(0x142f6)
            require(m.reason == 4 and m.record[18] == attempt,
                    'combined counter route mismatch')
        else:
            require(m.record[18] == 4 and m.reason is None,
                    'switch must happen before this stage could increment')
        record = m.record
        chain.append(dict(b_boot_check=attempt, boot_reason=m.reason, retry_b=record[18],
                          priority_a=record[12], priority_b=record[17],
                          bootpart_request=m.switched))
        counts['combined_boots'] += 1
    m = Replay(image, record, bootpart=1, abnormal=None)
    m.run(0x1c04)
    require(not m.switched, 'new preferred A slot should not switch back to B')
    m.run(0x142f6)
    require(m.record[13] == 1 and m.record[18] == 4,
            'new A boot must retain the previous B retry until Linux handles it')
    counts['combined_boots'] += 1
    print(json.dumps(dict(
        prefix_sha256=EXPECTED, cases=counts, total_cases=sum(counts.values()),
        combined_example=chain,
        subsequent_a_before_linux=dict(retry_a=m.record[13], retry_b=m.record[18],
                                       priority_a=m.record[12], priority_b=m.record[17]),
        order='main 0x9642 -> platform preinit -> boot check 0x13dc6; '
              'later main 0x96f0 -> boot-reason function -> possible increment',
        scope='Original selected preloader Thumb functions; synthetic valid BCAB, '
              'RAM_CONSOLE, MMIO and PMIC; storage/set-bootpart/reset boundaries '
              'stubbed; no real I/O, power cycle, signature validation or Linux clone',
    ), indent=2))


if __name__ == '__main__':
    main()
