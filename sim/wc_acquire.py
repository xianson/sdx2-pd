"""Line-faithful port of WeaponCore 3.0 target acquisition.

Source of truth (workshop 3154371364, Data/Scripts/CoreSystems):
    Support/Utils.cs:57-249        XorShiftRandomStruct
    Ai/AiSupport.cs:225-252        GetDeck
    Ai/AiTargeting.cs:526-869      AcquireProjectile
    Ai/AiTargeting.cs:1248-1289    AcquireBlock (SubSystems priority walk)
    Ai/AiTargeting.cs:1291-1610    FindRandomBlock
    Ai/AiTargeting.cs:1612+        GetClosestHitableBlockOfType

Everything here reproduces the C# integer sequence and control flow exactly,
including the arithmetic quirks (truncated remainder, int32 wrap, the
Range(1,n)-can-return-0 bug, the CycleTargets > numOfTargets subtraction).
Nothing is "improved".
"""

MASK64 = 0xFFFFFFFFFFFFFFFF
MASK32 = 0xFFFFFFFF


def _i32(v):
    """C# unchecked (int) cast of an integer."""
    v &= MASK32
    return v - 0x100000000 if v & 0x80000000 else v


def _crem(a, b):
    """C# '%': remainder truncated toward zero (Python's % is floored)."""
    r = abs(a) % abs(b)
    return -r if a < 0 else r


# ---------------------------------------------------------------------------
# Support/Utils.cs:57  public struct XorShiftRandomStruct
# ---------------------------------------------------------------------------
class XorShiftRandomStruct:

    # Utils.cs:60  private const double DoubleUnit = 1.0 / (int.MaxValue + 1.0);
    DoubleUnit = 1.0 / (2147483647 + 1.0)

    # Utils.cs:78  public XorShiftRandomStruct(ulong seed)
    def __init__(self, seed):
        self.reinit(seed)

    # Utils.cs:95  public void Reinit(ulong seed)   -- identical body to the ctor
    def reinit(self, seed):
        seed &= MASK64
        self._x = (seed << 3) & MASK64
        self._y = seed >> 3
        self._buffer = 0
        self._bufferMask = 0

        # Utils.cs:105
        temp1 = self._y
        self._x ^= (self._x << 23) & MASK64
        temp2 = self._x ^ self._y ^ (self._x >> 17) ^ (self._y >> 26)
        self._x = temp1
        self._y = temp2

        # Utils.cs:107
        tempX = self._y
        self._x ^= (self._x << 23) & MASK64
        tempY = self._x ^ self._y ^ (self._x >> 17) ^ (self._y >> 26)
        newSeed = (tempY + self._y) & MASK64
        self._x = tempX
        self._y = tempY

        # Utils.cs:109
        self._x = (newSeed << 3) & MASK64
        self._y = newSeed >> 3

    # Utils.cs:112  GetSeedVaues  [sic]
    def get_seed_values(self):
        return (self._x, self._y)

    # Utils.cs:117  SyncSeed
    def sync_seed(self, x, y):
        self._x = x & MASK64
        self._y = y & MASK64

    # Utils.cs:129  public bool NextBoolean()
    def next_boolean(self):
        if self._bufferMask > 0:
            v = (self._buffer & self._bufferMask) == 0
            self._bufferMask >>= 1
            return v

        tempX = self._y
        self._x ^= (self._x << 23) & MASK64
        tempY = self._x ^ self._y ^ (self._x >> 17) ^ (self._y >> 26)

        self._buffer = (tempY + self._y) & MASK64
        self._x = tempX
        self._y = tempY

        self._bufferMask = 0x8000000000000000
        return (self._buffer & 0xF000000000000000) == 0

    # Utils.cs:156  public ushort NextUInt16()
    def next_uint16(self):
        tempX = self._y
        self._x ^= (self._x << 23) & MASK64
        tempY = self._x ^ self._y ^ (self._x >> 17) ^ (self._y >> 26)
        v = (tempY + self._y) & 0xFFFF
        self._x = tempX
        self._y = tempY
        return v

    # Utils.cs:174  public ulong NextUInt64()
    def next_uint64(self):
        tempX = self._y
        self._x ^= (self._x << 23) & MASK64
        tempY = self._x ^ self._y ^ (self._x >> 17) ^ (self._y >> 26)
        v = (tempY + self._y) & MASK64
        self._x = tempX
        self._y = tempY
        return v

    # Utils.cs:193  public double NextDouble()
    def next_double(self):
        tempX = self._y
        self._x ^= (self._x << 23) & MASK64
        tempY = self._x ^ self._y ^ (self._x >> 17) ^ (self._y >> 26)
        tempZ = (tempY + self._y) & MASK64
        v = self.DoubleUnit * (0x7FFFFFFF & tempZ)
        self._x = tempX
        self._y = tempY
        return v

    # Utils.cs:207  public int Range(int aMin, int aMax)
    #
    # NOTE the two quirks, both load-bearing and both reproduced:
    #   * (int)NextUInt64() keeps only the low 32 bits, SIGNED -> rndInt is
    #     negative half the time, so `value` can fall below aMin.
    #   * the guard compares against aMax INCLUSIVE while the modulo is
    #     exclusive, and "fixes" an out-of-range value by negating it. When
    #     value == 0 and aMin == 1, `0 * -1 == 0` is still out of range and is
    #     returned anyway. Range(1, n) therefore returns 0 about 1/(n-1) of the
    #     time. GetDeck's startChunk depends on this.
    def range_int(self, aMin, aMax):
        rndInt = _i32(self.next_uint64())
        value = aMin + _crem(rndInt, aMax - aMin)
        if value < aMin or value > aMax:
            value *= -1
        return value

    # Utils.cs:217  public double Range(double aMin, double aMax)
    def range_double(self, aMin, aMax):
        value = aMin + self.next_double() * (aMax - aMin)
        if value < aMin or value > aMax:
            value *= -1
        return value

    # Utils.cs:236  public ulong FairRange(ulong aRange)
    def fair_range(self, aRange):
        dif = MASK64 % aRange
        if dif == 0 or MASK64 // (aRange // 4) < 2:
            return self.next_uint64() % aRange
        v = self.next_uint64()
        while MASK64 - v < dif:
            v = self.next_uint64()
        return v % aRange


# Definitions/SerializedConfigs/Misc.cs:76-85  WeaponRandomGenerator.Init
#   CurrentSeed = int.MaxValue - w.UniquePartId;
#   AcquireRandom = new XorShiftRandomStruct((ulong)CurrentSeed);
#   AcquireRandom.NextBoolean();      <-- one burn-in draw, servers only
def new_acquire_random(unique_part_id):
    seed = (2147483647 - unique_part_id) & MASK64
    r = XorShiftRandomStruct(seed)
    r.next_boolean()                                   # Misc.cs:85
    return r


# ---------------------------------------------------------------------------
# Ai/AiSupport.cs:225
#   private static int[] GetDeck(ref int[] deck, int firstCard, int cardsToSort,
#                                int cardsToShuffle, ref XorShiftRandomStruct rng)
#
# `deck` is a PERSISTENT session buffer (Session.TargetDeck / Session.BlockDeck)
# shared by every weapon; it is only reallocated when it is too small, and the
# reallocation DISCARDS the old contents (C# `new int[n]` is zero-filled).
# Callers must consume it before anyone else calls GetDeck. DeckBuffer models
# that lifetime rather than returning a fresh list.
# ---------------------------------------------------------------------------
class DeckBuffer:
    def __init__(self, size=0):
        self.deck = [0] * size

    def get_deck(self, first_card, cards_to_sort, cards_to_shuffle, rng):
        deck = self.deck
        if len(deck) < cards_to_sort:                            # AiSupport.cs:227
            deck = self.deck = [0] * (cards_to_sort * 2)         # AiSupport.cs:228

        shuffle = cards_to_shuffle > 0                           # AiSupport.cs:230

        # AiSupport.cs:232
        split_size = (cards_to_sort // cards_to_shuffle
                      if shuffle and cards_to_shuffle <= cards_to_sort else 0)
        # AiSupport.cs:233
        start_chunk = rng.range_int(1, split_size + 1) if (shuffle and split_size > 0) else 0

        # AiSupport.cs:235-236
        end = start_chunk * cards_to_shuffle if start_chunk > 0 else cards_to_shuffle
        start = (end - cards_to_shuffle) if start_chunk > 0 else 0

        for i in range(cards_to_sort):                           # AiSupport.cs:237
            if shuffle and i >= start and i < end:               # AiSupport.cs:240
                j = rng.range_int(0, i + 1)                      # AiSupport.cs:242
            else:
                j = i                                            # AiSupport.cs:246

            deck[i] = deck[j]                                    # AiSupport.cs:249
            deck[j] = i + first_card                             # AiSupport.cs:250
        return deck


# ---------------------------------------------------------------------------
# The chunk/checkSize arithmetic, shared verbatim by every acquisition path
# (AiTargeting.cs:176, 429, 620, 950, 1340, 2082 are the same five lines).
# ---------------------------------------------------------------------------
def cycle_window(cycle, num_of_targets, acquire_attempts):
    """Returns (chunk, check_size).  AiTargeting.cs:612-622."""
    if cycle <= 0:                                               # AiTargeting.cs:613
        check_size = num_of_targets
    elif cycle > num_of_targets:                                 # AiTargeting.cs:615
        # NOT a clamp -- it SUBTRACTS. With CycleTargets=4 and 3 candidates in
        # the cache the weapon examines exactly 1 of them.
        check_size = cycle - num_of_targets                      # AiTargeting.cs:616
    else:
        check_size = cycle                                       # AiTargeting.cs:618

    # AiTargeting.cs:620   int32 multiply wraps; '%' truncates toward zero
    if num_of_targets > 0:
        chunk = _crem(_i32(check_size * acquire_attempts), num_of_targets)
    else:
        chunk = 0

    if chunk + check_size >= num_of_targets:                     # AiTargeting.cs:622
        check_size = num_of_targets - chunk                      # AiTargeting.cs:623
    return chunk, check_size


# ---------------------------------------------------------------------------
# Ai/AiTargeting.cs:583-600 -- the in-place shellsort of the SHARED projectile
# cache done when ClosestFirst is on. It mutates ai's cache for every other
# weapon that reads it later in the same tick; that is the real behaviour.
# ---------------------------------------------------------------------------
def sort_closest_in_place(collection, weapon_pos, dist_sq):
    length = len(collection)                                     # AiTargeting.cs:584
    h = length // 2
    while h > 0:                                                 # AiTargeting.cs:585
        for i in range(h, length):                               # AiTargeting.cs:587
            temp_value = collection[i]
            temp = dist_sq(collection[i], weapon_pos)            # AiTargeting.cs:591
            j = i
            while j >= h and dist_sq(collection[j - h], weapon_pos) > temp:
                collection[j] = collection[j - h]                # AiTargeting.cs:595
                j -= h
            collection[j] = temp_value                           # AiTargeting.cs:597
        h //= 2


# ---------------------------------------------------------------------------
# Ai/AiTargeting.cs:526  AcquireProjectile
#
# Reduced to its selection skeleton: everything between the deck and the
# `return true` in the C# is a chain of `continue` filters, supplied here as
# `accept(candidate) -> bool`. The ORDER in which candidates are offered, and
# how many are offered, is what this reproduces exactly.
# ---------------------------------------------------------------------------
def acquire_projectile(w, collection, accept, weapon_pos=None, dist_sq=None,
                       index=None):
    """w: object with .closest_first .top_targets .cycle_targets
                      .acquire_attempts .acquire_random .target_deck
    Returns the accepted candidate, or None.
    Does NOT increment acquire_attempts -- see bump_acquire_attempts().
    """
    if index is None:
        index = -2147483648                                      # int.MinValue

    target_closest = w.closest_first                             # AiTargeting.cs:579

    if target_closest:                                           # AiTargeting.cs:583
        sort_closest_in_place(collection, weapon_pos, dist_sq)

    # AiTargeting.cs:602
    num_of_targets = len(collection) if index < -1 else (0 if index < 0 else 1)

    deck = None
    check_size = num_of_targets                                  # AiTargeting.cs:605

    if index < -1:                                               # AiTargeting.cs:607
        # AiTargeting.cs:609 -- with ClosestFirst=false this is the WHOLE cache
        # count, not TopTargets. cardsToShuffle > cardsToSort then makes GetDeck
        # take the "no split" branch and fully shuffle the window.
        num_to_randomize = w.top_targets if target_closest else num_of_targets

        chunk, check_size = cycle_window(w.cycle_targets, num_of_targets,
                                         w.acquire_attempts)
        # AiTargeting.cs:625
        deck = w.target_deck.get_deck(chunk, check_size, num_to_randomize,
                                      w.acquire_random)

    for x in range(check_size):                                  # AiTargeting.cs:628
        card = deck[x] if index < -1 else index                  # AiTargeting.cs:640
        lp = collection[card]                                    # AiTargeting.cs:641
        if accept(lp):
            return lp                                            # AiTargeting.cs:855-856
    return None                                                  # AiTargeting.cs:867


def bump_acquire_attempts(w):
    """AiTargeting.cs:98  ++w.AcquireAttempts;

    Runs at the very END of AcquireTarget, unconditionally -- success, failure,
    projectile path, grid path, fake-target path, all of them. It is an int and
    is never reset (grep: the only write in the codebase is this ++).
    So it is a per-weapon count of acquisition ATTEMPTS, and it is what walks
    the CycleTargets window forward.
    """
    w.acquire_attempts = _i32(w.acquire_attempts + 1)


# ---------------------------------------------------------------------------
# Ai/AiTargeting.cs:1291  FindRandomBlock
# ---------------------------------------------------------------------------
def find_random_block(w, sub_system_list, accept, dist_to_ent,
                      total_blocks=None, is_priority=False,
                      weapon_check=True):
    """Returns the accepted block, or None.

    `accept(block) -> bool` stands in for the MarkedForClose / checkPower /
    modApi-filter / distance / CanShootTarget / water / raycast chain.
    `weapon_check` is `p == null && (!SkipAimChecks || RotorTurretTracking)`
    (AiTargeting.cs:1315); it gates the blocksChecked budget.
    """
    if total_blocks is None:
        total_blocks = len(sub_system_list)                      # AiTargeting.cs:1295

    top_blocks = w.top_blocks                                    # AiTargeting.cs:1317
    # AiTargeting.cs:1318 -- "last 10" unless the target is close AND TopBlocks
    # is generous. Note distToEnt is surface distance to the target's sphere.
    last_blocks = top_blocks if (top_blocks > 10 and dist_to_ent < 1000) else 10

    if last_blocks < 250:                                        # AiTargeting.cs:1321
        if is_priority:                                          # AiTargeting.cs:1325
            last_blocks = total_blocks if total_blocks < 250 else 250

    if total_blocks < last_blocks:                               # AiTargeting.cs:1330
        last_blocks = total_blocks

    # AiTargeting.cs:1332-1336 -- NOTE this differs from the projectile path:
    # the >= branch clamps to totalBlocks instead of subtracting.
    if w.cycle_blocks <= 0 or w.cycle_blocks >= total_blocks:
        check_size = total_blocks
    else:
        check_size = w.cycle_blocks

    # AiTargeting.cs:1340
    chunk = _crem(_i32(check_size * w.acquire_attempts), total_blocks) if total_blocks > 0 else 0
    if chunk + check_size >= total_blocks:                       # AiTargeting.cs:1342
        check_size = total_blocks - chunk                        # AiTargeting.cs:1343

    # AiTargeting.cs:1345 -- cardsToShuffle is TopBlocks here, NOT lastBlocks
    deck = w.block_deck.get_deck(chunk, check_size, top_blocks, w.acquire_random)

    blocks_checked = 0                                           # AiTargeting.cs:1354
    blocks_sighted = 0                                           # AiTargeting.cs:1355

    for i in range(check_size):                                  # AiTargeting.cs:1359
        # AiTargeting.cs:1361 -- '>' not '>=', so the budget is lastBlocks+1
        if weapon_check and (blocks_checked > last_blocks or
                             (is_priority and blocks_sighted > 100)):
            break

        card = deck[i]                                           # AiTargeting.cs:1364
        block = sub_system_list[card]                            # AiTargeting.cs:1365

        ok, checked, sighted = accept(block)
        blocks_checked += checked                                # AiTargeting.cs:1391
        blocks_sighted += sighted                                # AiTargeting.cs:1400
        if ok:
            return block
    return None


# ---------------------------------------------------------------------------
# Ai/AiTargeting.cs:1612  GetClosestHitableBlockOfType
#
# Keeps five running minima (newEntity..newEntity3) and walks Top5 first, so it
# is a true nearest-block search over the whole list -- no deck, no RNG, and
# NO CycleBlocks budget. Turning ClosestFirst on therefore also removes the
# per-attempt work cap on the block path.
# ---------------------------------------------------------------------------
def get_closest_hitable_block_of_type(w, cubes, weapon_pos, dist_sq, accept):
    top5 = getattr(w, 'top5', [])
    top5_count = len(top5)                                       # AiTargeting.cs:1645
    best = None
    best_val = float('inf')
    for i in range(len(cubes) + top5_count):                     # AiTargeting.cs:1651
        index = i if i < top5_count else i - top5_count          # AiTargeting.cs:1654
        cube = top5[index] if i < top5_count else cubes[index]   # AiTargeting.cs:1655
        test = dist_sq(cube, weapon_pos)                         # AiTargeting.cs:1681
        if test < best_val and accept(cube):                     # AiTargeting.cs:1688
            best_val = test
            best = cube
    return best


# ---------------------------------------------------------------------------
# Ai/AiTargeting.cs:1248  AcquireBlock -- the SubSystems priority walk.
# ---------------------------------------------------------------------------
# Definitions/CoreDefinitions.cs:285  enum BlockTypes
ANY, OFFENSE, UTILITY, POWER, PRODUCTION, THRUST, JUMPING, STEERING = range(8)
BLOCK_TYPE_NAMES = ['Any', 'Offense', 'Utility', 'Power', 'Production',
                    'Thrust', 'Jumping', 'Steering']


def acquire_block(w, block_type_map, find_random, find_closest,
                  focus_sub_system=False, forced_sub_system=ANY,
                  any_list=None):
    """AiTargeting.cs:1248-1289.

    block_type_map: {BlockTypes -> list}
    find_random(bt, lst) / find_closest(bt, lst) -> block or None
    Returns the block, or None.
    """
    if w.target_sub_systems:                                     # AiTargeting.cs:1254
        for block_type in w.sub_systems:                         # AiTargeting.cs:1259
            bt = forced_sub_system if focus_sub_system else block_type  # :1261
            lst = block_type_map.get(bt)
            # AiTargeting.cs:1265 -- 'Any' in the SubSystems array is SKIPPED
            # here; it only ever falls through to the whole-grid list below.
            if bt != ANY and lst is not None and len(lst) > 0:
                if w.closest_first:                              # AiTargeting.cs:1269
                    # AiTargeting.cs:1273-1275: Top5 is invalidated whenever the
                    # subsystem type OR the target grid changes. The grid half
                    # (`w.Top5[0].CubeGrid != subSystemList[0].CubeGrid`) has no
                    # analogue here -- there is one grid -- so only the type
                    # test is reproduced.
                    if getattr(w, 'top5', None) and (bt != getattr(w, 'last_top5_block_type', None)):
                        w.top5 = []
                    w.last_top5_block_type = bt                  # AiTargeting.cs:1275
                    hit = find_closest(bt, lst)                  # AiTargeting.cs:1276
                else:
                    hit = find_random(bt, lst)                   # AiTargeting.cs:1279
                if hit is not None:
                    return hit

            if focus_sub_system:                                 # AiTargeting.cs:1282
                break

        # AiTargeting.cs:1285
        if w.only_sub_systems or (focus_sub_system and forced_sub_system != ANY):
            return None

    # AiTargeting.cs:1288 -- fallback: FindRandomBlock over EVERY block, and
    # note it is FindRandomBlock even when ClosestFirst is on.
    if any_list:
        return find_random(ANY, any_list)
    return None


# ---------------------------------------------------------------------------
# SDX2 (workshop 3580645761) definition values -- READ, not assumed.
# ---------------------------------------------------------------------------
class WcWeaponParams:
    """Mirrors the WeaponSystem fields the acquisition paths actually read."""

    def __init__(self, name, top_targets, cycle_targets, top_blocks, cycle_blocks,
                 closest_first, locked_smart_only, ignore_dumb_projectiles,
                 max_target_distance, sub_systems=None, only_sub_systems=False,
                 target_sub_systems=True, unique_part_id=0):
        self.name = name
        self.top_targets = top_targets
        self.cycle_targets = cycle_targets
        self.top_blocks = top_blocks
        self.cycle_blocks = cycle_blocks
        self.closest_first = closest_first
        self.locked_smart_only = locked_smart_only
        self.ignore_dumb_projectiles = ignore_dumb_projectiles
        self.max_target_distance = max_target_distance
        self.sub_systems = sub_systems or [POWER, UTILITY, OFFENSE, THRUST,
                                           PRODUCTION, ANY]
        self.only_sub_systems = only_sub_systems
        self.target_sub_systems = target_sub_systems
        self.unique_part_id = unique_part_id
        self.reset_state()

    def reset_state(self):
        self.acquire_attempts = 0
        self.acquire_random = new_acquire_random(self.unique_part_id)
        self.target_deck = DeckBuffer()
        self.block_deck = DeckBuffer()
        self.top5 = []
        self.last_top5_block_type = None

    def clone(self, unique_part_id):
        c = WcWeaponParams(self.name, self.top_targets, self.cycle_targets,
                           self.top_blocks, self.cycle_blocks, self.closest_first,
                           self.locked_smart_only, self.ignore_dumb_projectiles,
                           self.max_target_distance, list(self.sub_systems),
                           self.only_sub_systems, self.target_sub_systems,
                           unique_part_id)
        return c


# PDC/BasePDCDefinition.cs:27-48, with the per-weapon overrides that follow.
#   BasePDCDefinition: TopTargets 32, CycleTargets 4, TopBlocks 16, CycleBlocks 4,
#                      ClosestFirst false, IgnoreDumbProjectiles false,
#                      LockedSmartOnly false, MaxTargetDistance 3000.
#   Every shipped PDC except pdcPgenAdv overrides TopTargets/TopBlocks to 12
#   (sdx_weapon_pdcMcrn.cs:47-48, pdcUnn.cs:47-48, pdcOpa.cs:49-50,
#    pdcImprovised.cs:27-28, pdcMcrnAdv.cs:61-62, pdcUnnAdv.cs:60-61,
#    pdcOpaAdv.cs:31-32). CycleTargets/CycleBlocks stay at 4.
#   pdcPgenAdv.cs:27-30 is the outlier: TopTargets 8, TopBlocks 4,
#   CycleTargets 0, CycleBlocks 0  -> it scans the WHOLE cache every attempt.
#   pdcOpaAdv.cs:29 raises MaxTargetDistance to 4000 for one variant
#   (and pdcOpaAdv.cs:84 sets 3000 for the other).
def sdx2_pdc(name='PdcMcrn', unique_part_id=0):
    if name in ('PdcPgenAdv', 'pdcPgenAdv'):
        return WcWeaponParams(name, 8, 0, 4, 0, False, False, False, 3000.0,
                              unique_part_id=unique_part_id)
    rng = 4000.0 if name in ('PdcOpaAdv', 'pdcOpaAdv') else 3000.0
    return WcWeaponParams(name, 12, 4, 12, 4, False, False, False, rng,
                          unique_part_id=unique_part_id)


# Railguns/BaseRailgunDefinition.cs:26-45
#   TopTargets 12, CycleTargets 0, TopBlocks 24, CycleBlocks 0,
#   ClosestFirst false, IgnoreDumbProjectiles false, LockedSmartOnly false,
#   MaxTargetDistance 10000, Threats = { Grids } only.
#   sdx_weapon_railgunUnnLightFixed.cs:25-26 overrides TopTargets/TopBlocks to 0
#   (= no randomisation at all: GetDeck's `shuffle` is false, deck stays in
#    internal list order).
def sdx2_railgun(name='RailgunMcrnMediumTurreted', unique_part_id=0):
    if 'UnnLightFixed' in name:
        return WcWeaponParams(name, 0, 0, 0, 0, False, False, False, 10000.0,
                              unique_part_id=unique_part_id)
    return WcWeaponParams(name, 12, 0, 24, 0, False, False, False, 10000.0,
                          unique_part_id=unique_part_id)


# ---------------------------------------------------------------------------
# Acquisition CADENCE -- SessionUpdate.cs.
# A weapon only calls AcquireTarget when it is queued into Session.AcquireTargets.
# ---------------------------------------------------------------------------
AWAKE_BUCKETS = 60           # SessionFields.cs:51
ASLEEP_BUCKETS = 180         # SessionFields.cs:52
SHORT_LOAD_BUCKETS = 15      # SessionSupport.cs:70 (QCount 0..14),
                             # SessionSupport.cs:414-419 (ShortLoadAssigner 0..14)


def projectiles_near(tick, short_load_id, target_changed):
    """SessionUpdate.cs:736 (the QCount term only).

    QCount cycles 0..14, so a weapon that is not mid-target-change gets one
    projectile-seek window every 15 ticks = 0.25 s.
    """
    return target_changed or (tick % SHORT_LOAD_BUCKETS) == short_load_id


def weapon_may_seek(tick, slot_id, short_load_id, has_target, target_changed):
    """SessionUpdate.cs:746-757, reduced to the terms that matter here.

        weaponReady = ... && (!w.Target.HasTarget || focus reset)
        acquireReady = ... && myTimeSlot            (AwakeCount == SlotId)
        seek = weaponReady && (acquireReady || w.ProjectilesNear)

    So: a weapon that already holds a target never re-seeks, and a weapon
    without one seeks on its 1-in-60 awake slot OR its 1-in-15 projectile
    window.
    """
    if has_target:
        return False                                             # SessionUpdate.cs:755
    my_time_slot = (tick % AWAKE_BUCKETS) == slot_id             # SessionUpdate.cs:748
    return my_time_slot or projectiles_near(tick, short_load_id, target_changed)
