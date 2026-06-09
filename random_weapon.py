"""
random-weapon.py
Picks a random DS1R starting weapon, finds the best class, then patches
GameParam.parambnd.dcx in-place. A backup is written before any changes.

Dependencies: only game_constants.py (no DarkSoulsItemRandomizer needed).
"""

import random

from game_constants import (
    CLASS_IDS_2000,
    CLASS_IDS_3000,
    SPELL_IDS,
    WEAPONS,
)

from game_patcher import (
    # CONFIG
    BACKUP_PATH,
    GAMEPARAM_PATH,

    # DCX
    dcx_decompress,
    dcx_compress,

    # BND3
    bnd3_unpack,
    bnd3_pack,

    # Params
    parse_chara_init_param,
    patch_class_record,
    build_chara_init_param
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

EXCLUDED_CATEGORIES = {
    "0",   # arrows & bolts
    "44",  # bows
    "46",  # crossbows
    "47",  # greatshields
    "48",  # shields
}

# ---------------------------------------------------------------------------
# Game logic
# ---------------------------------------------------------------------------

STARTING_CLASSES = {
    "Warrior":    {"level": 4, "vit": 11, "att":  8, "end": 12, "str": 13, "dex": 13, "res": 11, "int":  9, "fth":  9},
    "Knight":     {"level": 5, "vit": 14, "att": 10, "end": 10, "str": 11, "dex": 11, "res": 10, "int":  9, "fth": 11},
    "Wanderer":   {"level": 3, "vit": 10, "att": 11, "end": 10, "str": 10, "dex": 14, "res": 12, "int": 11, "fth":  8},
    "Thief":      {"level": 5, "vit":  9, "att": 11, "end":  9, "str":  9, "dex": 15, "res": 10, "int": 12, "fth": 11},
    "Bandit":     {"level": 4, "vit": 12, "att":  8, "end": 14, "str": 14, "dex":  9, "res": 11, "int":  8, "fth": 10},
    "Hunter":     {"level": 4, "vit": 11, "att":  9, "end": 11, "str": 12, "dex": 14, "res": 11, "int":  9, "fth":  9},
    "Sorcerer":   {"level": 3, "vit":  8, "att": 15, "end":  8, "str":  9, "dex": 11, "res":  8, "int": 15, "fth":  8},
    "Pyromancer": {"level": 1, "vit": 10, "att": 12, "end": 11, "str": 12, "dex":  9, "res": 12, "int": 10, "fth":  8},
    "Cleric":     {"level": 2, "vit": 11, "att": 11, "end":  9, "str": 12, "dex":  8, "res": 11, "int":  8, "fth": 14},
    "Deprived":   {"level": 6, "vit": 11, "att": 11, "end": 11, "str": 11, "dex": 11, "res": 11, "int": 11, "fth": 11},
}

SPELL_REQUIREMENTS = {
    "Soul Arrow":      {"int": 10, "fth":  0},
    "Combustion":      {"int":  0, "fth":  0},
    "Lightning Spear": {"int":  0, "fth": 20},
}


def determine_spell(weapon):
    t = weapon.get("type", "weapon")
    return {"catalyst": "Soul Arrow", "pyro_flame": "Combustion", "talisman": "Lightning Spear"}.get(t)


def combine_requirements(weapon, spell_req=None):
    import math
    raw_str = weapon["req_str"]
    req = {
        # Two-handing counts STR as floor(base*1.5), so the minimum base STR
        # needed to two-hand is ceil(req_str / 1.5).
        "str": math.ceil(raw_str / 1.5),
        "dex": weapon["req_dex"],
        "int": weapon["req_int"],
        "fth": weapon["req_fth"],
    }
    if spell_req:
        req["int"] = max(req["int"], spell_req.get("int", 0))
        req["fth"] = max(req["fth"], spell_req.get("fth", 0))
    return req


def levels_needed(stats, req):
    return (max(0, req["str"] - stats["str"]) + max(0, req["dex"] - stats["dex"])
          + max(0, req["int"] - stats["int"]) + max(0, req["fth"] - stats["fth"]))


def find_best_class(req, rng: random.Random):
    """Return the class requiring the fewest level-ups. Breaks ties randomly using rng."""
    best_levels = min(levels_needed(stats, req) for stats in STARTING_CLASSES.values())
    candidates  = [name for name, stats in STARTING_CLASSES.items()
                   if levels_needed(stats, req) == best_levels]
    return rng.choice(candidates), best_levels


def compute_final_stats(class_name, req):
    base = STARTING_CLASSES[class_name]
    return {k: max(base[k], req.get(k, 0)) for k in ("str", "dex", "int", "fth")}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="DSR random starting weapon randomizer")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed (omit for a random seed)")
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else random.randrange(2**32)
    rng  = random.Random(seed)
    print(f"Seed: {seed}")

    pool = [w for w in WEAPONS.values()
            if not w["name"].startswith("徘徊")
            and w.get("wepmotionCategory", "") not in EXCLUDED_CATEGORIES]

    weapon      = rng.choice(pool)
    spell       = determine_spell(weapon)
    req         = combine_requirements(weapon, SPELL_REQUIREMENTS.get(spell))
    best_class, levels = find_best_class(req, rng)
    final_stats = compute_final_stats(best_class, req)
    final_level = STARTING_CLASSES[best_class]["level"] + levels
    spell_id    = SPELL_IDS.get(spell) if spell else None

    print(f"\n{'='*60}")
    print(f"RANDOMIZATION RESULT")
    print(f"{'='*60}")
    print(f"Weapon : {weapon['name']} (ID: {weapon['ID']})")
    print(f"Spell  : {spell}")
    print(f"Class  : {best_class}  (+{levels} levels → {final_level})")
    print(f"Stats  : STR {final_stats['str']}  DEX {final_stats['dex']}  "
          f"INT {final_stats['int']}  FTH {final_stats['fth']}")

    # --- Load DCX → BND → CharaInitParam ---
    # Restore from backup first if it exists, so each run starts from clean state
    if BACKUP_PATH.exists():
        print(f"\nRestoring from backup → {BACKUP_PATH}")
        raw_dcx = BACKUP_PATH.read_bytes()
    else:
        raw_dcx = GAMEPARAM_PATH.read_bytes()
        BACKUP_PATH.write_bytes(raw_dcx)
        print(f"Backup written → {BACKUP_PATH}")

    bnd_data = dcx_decompress(raw_dcx)
    entries, fmt, be, sig, unk_bytes = bnd3_unpack(bnd_data)

    chr_idx   = next(i for i, (_, name, _, _flag) in enumerate(entries) if "CharaInitParam" in name)
    chr_entry = entries[chr_idx]
    chr_name, chr_data = chr_entry[1], chr_entry[2]
    rows = parse_chara_init_param(chr_data)

    # --- Patch both class ID ranges ---
    target_ids = {CLASS_IDS_2000[best_class], CLASS_IDS_3000[best_class]}
    patched = 0
    for row in rows:
        if row[0] in target_ids:
            patch_class_record(
                row[2],
                weapon_id  = int(weapon["ID"]),
                spell_id   = spell_id,
                soul_level = final_level,
                str_       = final_stats["str"],
                dex        = final_stats["dex"],
                int_       = final_stats["int"],
                fth        = final_stats["fth"],
            )
            patched += 1

    if patched == 0:
        raise RuntimeError(f"No rows matched class IDs {target_ids} — nothing patched.")

    # --- Rebuild CharaInitParam → BND → DCX → write ---
    new_chr_data = build_chara_init_param(rows, chr_data)
    entries[chr_idx][2] = new_chr_data

    new_bnd = bnd3_pack(entries, fmt, be, sig, unk_bytes)
    new_dcx = dcx_compress(new_bnd, raw_dcx)
    GAMEPARAM_PATH.write_bytes(new_dcx)

    print(f"\nPatched {patched} class record(s) (IDs {sorted(target_ids)}).")
    print(f"GameParam.parambnd.dcx updated.")
    print(f"\nRe-run with --seed {seed} to reproduce this result.")


if __name__ == "__main__":
    main()