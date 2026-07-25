"""Move the tile focus with the pad, verifying against what KD reports each step.

Never assumes a press landed: the focus is read back from KD, so a dropped or
swallowed pad event fails here rather than silently launching the wrong tile.
"""

from tests.behavioral.harness import timeouts
from tests.behavioral.harness.kd_client import KDClient
from tests.behavioral.harness.virtual_pad import VirtualPad


def focus_tile(kd: KDClient, pad: VirtualPad, app_id: str) -> dict:
    """Bring the pad focus onto the tile for *app_id* and return the snapshot."""
    target = kd.tile_index(app_id)

    snap = kd.snapshot()
    if snap['focus']['zone'] != 'tiles':
        pad.down()
        snap = kd.wait_until(lambda s: s['focus']['zone'] == 'tiles',
                             timeouts.TILE_FOCUS, 'focus back on the tile bar')

    # Steered by the cursor: tile_index is None outside the app section, which is
    # the leftmost one, so a window tile would send the walk rightwards instead.
    steps_left = snap['focus']['cursor'] + len(snap['tiles']) + 2
    while snap['focus']['tile_index'] != target:
        if steps_left <= 0:
            raise TimeoutError(
                f'focus stuck at cursor {snap["focus"]["cursor"]} '
                f'({snap["focus"]["kind"]}), wanted index {target} for {app_id!r} — '
                'is KD reading the virtual pad?'
            )
        before = snap['focus']['cursor']
        pad.right() if before < target else pad.left()
        snap = kd.wait_until(
            lambda s, b=before: s['focus']['cursor'] != b, timeouts.TILE_FOCUS,
            f'tile cursor to move off {before}',
        )
        steps_left -= 1

    return snap
