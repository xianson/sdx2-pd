"""Hull-visibility ladder: the stock ladder's rungs, minus the geometrically blind ones.

A rung is a tracking range about the MOUNT, but the threat track runs down the
lead hull's axis. A consort standing `lat` metres off that axis can never
acquire anything at a rung with band*base < lat: the range gate excludes every
torpedo that will ever exist. The stock ladder (`ladder.LADDER`, bands to 0.28
= 798 m on a 2850 m base) therefore parks ship-2 mounts (lat 1000 m) in
guaranteed-blind states for a cool+dwell cycle every descent — structural
fire-withholding inside the winning policy, invisible at 1 hull.

Fix: per-hull band lists filtered to rungs that can reach the track, i.e.
band*base >= lat + margin. Lead keeps all rungs; nothing else changes; fire is
never ceased. At 1 hull this IS the incumbent (bit-identical bands).

LEGALITY: needs only the mount's own hull lateral offset from the threat axis —
own-formation constants over IGC plus the launch-bearing dead-reckoning that
already justifies ctx['nearest']. No torpedo state, no identity.
"""
from ladder import LADDER, _conflicts


def _hull_bands(m, ctx, bands, spacing, margin, min_rungs):
    """Bands visible from this mount's hull; computed once per mount."""
    key = getattr(m, '_vb_key', None)
    if key == (spacing, margin):
        return m._vb_bands
    lat = m._ship * spacing                     # lateral offset from threat track
    vis = tuple(f for f in bands if f * m._base_range >= lat + margin)
    if len(vis) < min_rungs:
        vis = tuple(bands[:min_rungs])
    m._vb_key = (spacing, margin)
    m._vb_bands = vis
    return vis


def vis_ladder(bands=LADDER, tol=40.0, burst=14, cool_frac=0.20, dwell=0.35,
               demote_on_conflict=True, spacing=500.0, margin=60.0,
               min_rungs=2):
    """ladder.ladder_deconflict with per-hull visibility-filtered bands.

    Everything else is kept bit-comparable with the incumbent: same rung state
    machine, same burst counter, same conflict tie-break, same cool/dwell cycle.
    """
    def pol(m, ctx):
        my_bands = _hull_bands(m, ctx, bands, spacing, margin, min_rungs)
        n = len(my_bands)
        st = getattr(m, '_vl', None)
        if st is None:
            st = m._vl = {'rung': m._idx % n, 'base': m.shots_fired,
                          'since': ctx['t'], 'bottom_at': None}
        rung = st['rung']

        demoted = False
        if demote_on_conflict:
            me = (m._ship, m._idx)
            for A, B in _conflicts(ctx, tol):
                if A != me and B != me:
                    continue
                other = B if A == me else A
                mine = m._in_flight
                theirs = ctx.get('_infl_by_key', {}).get(other, 0)
                if mine < theirs or (mine == theirs and me > other):
                    if rung < n - 1:
                        rung += 1
                        demoted = True
                    break

        if not demoted and m.shots_fired - st['base'] >= burst:
            if rung < n - 1:
                rung += 1
                demoted = True
            st['base'] = m.shots_fired

        if demoted:
            st['base'] = m.shots_fired
            st['since'] = ctx['t']
            st['bottom_at'] = ctx['t'] if rung == n - 1 else None

        if rung == n - 1:
            if st['bottom_at'] is None:
                st['bottom_at'] = ctx['t']
            hot = (m.heat / m.max_heat) if m.max_heat else 0.0
            if hot <= cool_frac and ctx['t'] - st['bottom_at'] >= dwell:
                rung = 0
                st['base'] = m.shots_fired
                st['since'] = ctx['t']
                st['bottom_at'] = None

        st['rung'] = rung
        return True, m._base_range * my_bands[rung]
    return pol


def vis_burst_only(bands=LADDER, burst=14, spacing=500.0, margin=60.0,
                   min_rungs=2):
    """Visibility-filtered counterpart of ladder.burst_ladder_only."""
    return vis_ladder(bands=bands, burst=burst, demote_on_conflict=False,
                      spacing=spacing, margin=margin, min_rungs=min_rungs)
