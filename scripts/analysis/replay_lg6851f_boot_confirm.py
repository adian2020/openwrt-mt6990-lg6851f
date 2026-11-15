#!/usr/bin/env python3
"""Replay pinned preloader code plus the real boot worker using ordinary files.

Host-only: all storage, register and reset boundaries use the existing replay
and shell fixtures. Never opens a device, contacts a router or resets hardware.
Requires unicorn and the separately supplied, hash-checked preloader evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from replay_lg6851f_preloader import EXPECTED, Replay, control, require

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tests'))
from test_lg6851f_boot_confirm import BootConfirmTest


def confirm(record, slot, healthy, shutdown=False):
    fixture = BootConfirmTest('test_zero_retry_records_health_without_any_misc_write')
    fixture.setUp()
    try:
        fixture.set_record(record[:32])
        part = 26 if slot == 'a' else 39
        (fixture.root/'proc/cmdline').write_text(f'bootslot={slot} root={fixture.root}/dev/mmcblk0p{part}\n')
        (fixture.root/'proc/uptime').write_text('45.0 0.0\n')
        if not healthy:
            fixture.ready.unlink()
        elif shutdown:
            fixture.ready.rename(str(fixture.ready)+'.shutdown')
            fixture.binary('ps', "#!/bin/sh\necho '12 root /etc/init.d/rcS K shutdown'\n")
        result = fixture.run_confirm(*(['--shutdown'] if shutdown else []))
        require(result.returncode == (0 if healthy else 75), result.stderr)
        after = fixture.record() + record[32:]
        if healthy:
            require(fixture.current_status()['uptime'] == 45, 'healthy boot waited for a fixed timer')
        return bytearray(after)
    finally:
        fixture.doCleanups()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    args = parser.parse_args()
    require(args.image.is_file(), 'regular evidence file required')
    image = args.image.read_bytes()
    require(len(image) == 1048576 and hashlib.sha256(image).hexdigest() == EXPECTED,
            'unknown preloader image; fixed offsets must not be guessed')
    results = []
    for slot, index, bootpart, other in [('a', 13, 1, 2), ('b', 18, 2, 1)]:
        initial = control(pa=15, pb=14, ra=3) if slot == 'a' else control(rb=3)
        for healthy, shutdown in [(True, False), (True, True), (False, False)]:
            stage = Replay(image, initial, bootpart=bootpart, abnormal=None)
            stage.run(0x1c04)
            require(not stage.switched, 'TRY=3 unexpectedly switched before increment')
            stage.run(0x142f6)
            require(stage.record[index] == 4, 'expected classified WDT increment to 4')
            after = confirm(stage.record, slot, healthy, shutdown)
            expected = bytearray(stage.record)
            if healthy:
                expected[index] = 0
            require(after == expected, 'worker changed bytes beyond current TRY')
            following = Replay(image, after, bootpart=bootpart, abnormal=None)
            following.run(0x1c04)
            require(following.switched == ([] if healthy else [other]),
                    'healthy acknowledgment or failed-boot fallback changed')
            results.append(dict(slot=slot, healthy=healthy, shutdown=shutdown,
                                uptime=45, try_after_worker=after[index],
                                next_bootpart_requests=following.switched))
        # Four quick but completed boots must keep the selected slot. The real
        # boot-reason slice is deliberately the one that increments each time.
        record = control(pa=15, pb=14) if slot == 'a' else control()
        for _ in range(4):
            stage = Replay(image, record, bootpart=bootpart, abnormal=None)
            stage.run(0x1c04)
            require(not stage.switched, 'completed rapid boots unexpectedly switched')
            stage.run(0x142f6)
            record = confirm(stage.record, slot, True)
            require(record[index] == 0, 'completed boot left accumulated retry')
        results.append(dict(slot=slot, completed_rapid_boots=4, final_retry=record[index]))
    print(json.dumps(dict(scope='offline original Thumb code + actual shell; all I/O uses fixtures',
                          scenarios=results), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
