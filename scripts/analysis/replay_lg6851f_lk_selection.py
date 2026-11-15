#!/usr/bin/env python3
"""Offline evidence replay; requires host-only `unicorn`, never device access.

Execute get_suffix from the hash-pinned, user-supplied LK, replacing only the
partition-read and logging boundaries. This is not a whole boot-chain test.
The private image is deliberately not included in the repository.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_PC, UC_ARM_REG_LR, UC_ARM_REG_SP,
)

EXPECTED = '5ce5ff892ca7dc2d443647dd27e05d3b4067743029f2603d6b2331b9d3a5091d'
SEGMENTS = [
    dict(name='lk', payload=0x200, size=0x56ae4, base=0xda200000,
         entry=0xa410, read=0xa4ac, log=0x25180),
    dict(name='aee_lk', payload=0x57da0, size=0x74780, base=0xdc600000,
         entry=0x668d0, read=0x6696c, log=0x7cef8),
]
STACK, STOP = 0x20000000, 0x10000000


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def replay(image, segment, pa, pb, ra, rb, sa, sb, read_rc=34, magic=True):
    record = bytearray(34)
    record[4:8] = b'BCAB' if magic else b'BAD!'
    record[8:10] = b'\x01\x02'
    record[12:16] = bytes([pa, ra, sa, 1])
    record[17:21] = bytes([pb, rb, sb, 1])
    base, payload = segment['base'], segment['payload']
    address = lambda offset: base + offset - payload
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    uc.mem_map(base, 0x80000)
    uc.mem_write(base, image[payload:payload + segment['size']])
    uc.mem_map(STACK, 0x10000)
    uc.mem_map(STOP, 0x1000)
    reads = []

    def code_hook(machine, pc, size, data):
        if pc == STOP:
            machine.emu_stop()
        elif pc == address(segment['read']):
            require(machine.reg_read(UC_ARM_REG_R1) == 0,
                    'get_suffix attempted a partition write')
            reads.append(True)
            machine.mem_write(machine.reg_read(UC_ARM_REG_R0), bytes(record))
            machine.reg_write(UC_ARM_REG_R0, read_rc & 0xffffffff)
            machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))
        elif pc == address(segment['log']):
            machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))

    def write_hook(machine, access, location, size, value, data):
        require(STACK <= location and location + size <= STACK + 0x10000,
                'unexpected non-stack write')

    uc.hook_add(UC_HOOK_CODE, code_hook)
    uc.hook_add(UC_HOOK_MEM_WRITE, write_hook)
    uc.reg_write(UC_ARM_REG_SP, STACK + 0xff00)
    uc.reg_write(UC_ARM_REG_LR, STOP | 1)
    uc.emu_start(address(segment['entry']) | 1, STOP + 2, count=300)
    require(uc.reg_read(UC_ARM_REG_PC) == STOP and len(reads) == 1,
            'function did not return after exactly one partition read')
    pointer = uc.reg_read(UC_ARM_REG_R0)
    return bytes(uc.mem_read(pointer, 8)).split(b'\0')[0].decode('ascii')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path, help='user-provided lk_a.img or lk_b.img')
    args = parser.parse_args()
    image = args.image.read_bytes()
    require(len(image) == 1048576 and hashlib.sha256(image).hexdigest() == EXPECTED,
            'unrecognized image: offsets apply only to the documented evidence hash')
    require(struct.unpack_from('<I', image)[0] == 0x58881688,
            'unexpected MTK partition image header')
    results = []
    for segment in SEGMENTS:
        cases = 0
        for pa, pb, expected in [(15, 14, '_a'), (14, 15, '_b'),
                                 (15, 15, '_a'), (0, 0, '_a'),
                                 (0, 15, '_b'), (15, 0, '_a')]:
            for ra in [0, 1, 3, 4, 255]:
                for rb in [0, 1, 3, 4, 255]:
                    for sa in [0, 1]:
                        for sb in [0, 1]:
                            actual = replay(image, segment, pa, pb, ra, rb, sa, sb)
                            require(actual == expected,
                                    f'unexpected selection: {segment["name"]}, '
                                    f'{pa,pb,ra,rb,sa,sb}, {actual!r}')
                            cases += 1
        for read_rc, magic in [(-1, True), (0, False), (34, False)]:
            require(replay(image, segment, 14, 15, 0, 0, 1, 1,
                           read_rc=read_rc, magic=magic) == '',
                    'read/magic failure did not return an empty suffix')
            cases += 1
        results.append(dict(segment=segment['name'], cases=cases,
                            get_suffix_file_offset=hex(segment['entry'])))
    print(json.dumps(dict(
        image_sha256=EXPECTED, results=results,
        confirmed='Higher unsigned priority wins; ties return _a; read/magic '
                  'failure returns empty suffix; retry/success do not affect get_suffix',
        scope='Actual normal/AEE LK Thumb functions with synthetic partition reads '
              'and logging stubs; excludes preloader, real I/O, signature validation, '
              'reset handling, and Linux execution',
    ), indent=2))


if __name__ == '__main__':
    main()
