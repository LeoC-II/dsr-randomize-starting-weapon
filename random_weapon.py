"""
random-weapon.py
Picks a random DS1R starting weapon, finds the best class, then patches
GameParam.parambnd.dcx in-place. A backup is written before any changes.

Dependencies: only game_constants.py (no DarkSoulsItemRandomizer needed).
"""

from pathlib import Path
import json
import random
import struct
import zlib

from game_constants import (
    CLASS_IDS_2000,
    CLASS_IDS_3000,
    SPELL_IDS,
    WEAPONS,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GAMEPARAM_PATH = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common"
    r"\DARK SOULS REMASTERED\param\GameParam\GameParam.parambnd.dcx"
)
BACKUP_PATH = Path(__file__).parent / "GameParam.parambnd.dcx.bak"

EXCLUDED_CATEGORIES = {
    "0",   # arrows & bolts
    "44",  # bows
    "46",  # crossbows
    "47",  # greatshields
    "48",  # shields
}

# ---------------------------------------------------------------------------
# DCX  (zlib DFLT, big-endian header)
# ---------------------------------------------------------------------------

def dcx_decompress(data: bytes) -> bytes:
    assert data[0:4] == b"DCX\x00"
    # skip to DCA section to find where the zlib stream starts
    dca_off = data.index(b"DCA\x00")
    zlib_off = dca_off + 8          # 4 "DCA\x00" + 4 compressedHeaderLength
    assert data[zlib_off:zlib_off+2] == b"\x78\xda", "Expected zlib magic 78 DA"
    uncompressed_size = struct.unpack_from(">i", data, 0x14)[0]  # in DCS section
    return zlib.decompress(data[zlib_off:])


def dcx_compress(raw: bytes, original_dcx: bytes) -> bytes:
    """Re-compress raw bytes into a DCX, preserving all header values from the original."""
    # Use raw deflate (wbits=-15) — DSR stores 78 DA prefix then raw deflate.
    # We write the magic bytes explicitly and compress without any zlib envelope.
    cobj = zlib.compressobj(level=6, method=zlib.DEFLATED, wbits=-15)
    compressed = cobj.compress(raw) + cobj.flush()

    # Parse original header values we need to preserve
    unk_a, unk_b = struct.unpack_from(">ii", original_dcx, 0x0C)

    dca_off      = original_dcx.index(b"DCA\x00")
    cmp_hdr_len  = struct.unpack_from(">i", original_dcx, dca_off + 4)[0]

    out = bytearray()
    def wb(fmt, *args): out.extend(struct.pack(fmt, *args))
    def ws(s):          out.extend(s if isinstance(s, bytes) else s.encode())

    ws(b"DCX\x00");        wb(">i", 0x10000)
    wb(">i", 0x18);        wb(">i", unk_a);      wb(">i", unk_b)
    wb(">i", 0x2C)
    ws(b"DCS\x00");        wb(">i", len(raw));   wb(">i", len(compressed) + 2)
    ws(b"DCP\x00");        ws(b"DFLT")
    wb(">i", 0x20);        wb(">i", 0x9000000)
    wb(">i", 0);           wb(">i", 0);           wb(">i", 0)
    wb(">i", 0x00010100)
    ws(b"DCA\x00");        wb(">i", cmp_hdr_len)
    out.extend(b"\x78\xda")
    out.extend(compressed)
    return bytes(out)


# ---------------------------------------------------------------------------
# BND3  (little-endian entries, big-endian ignored here — DSR uses LE BND3)
# ---------------------------------------------------------------------------

def bnd3_unpack(data: bytes):
    """Return (entries, fmt, big_endian, signature, unk_bytes01).
    entries = list of [id, name, data, unk_flag1] — list so entries are mutable.
    """
    assert data[0:4] == b"BND3"
    signature  = data[4:12]           # 8 bytes, may be null-padded
    fmt        = data[12]
    be         = data[13] == 1
    endian     = ">" if be else "<"
    count,     = struct.unpack_from(endian + "i", data, 16)
    unk_bytes  = data[24:32]          # UnknownBytes01 — must be preserved exactly

    has_uncomp = fmt in (0x74, 0x54, 0x2E, 0x64)
    entry_hdr  = 20 + (4 if has_uncomp else 0)

    entries = []
    cur = 32
    for i in range(count):
        unk_flag1 = data[cur]
        size,     = struct.unpack_from(endian + "i", data, cur + 4)
        data_off, = struct.unpack_from(endian + "i", data, cur + 8)
        entry_id, = struct.unpack_from(endian + "i", data, cur + 12)
        name_off, = struct.unpack_from(endian + "i", data, cur + 16)
        cur += entry_hdr

        end  = data.index(b"\x00", name_off)
        name = data[name_off:end].decode("shift-jis", errors="replace")
        entries.append([entry_id, name, data[data_off:data_off + size], unk_flag1])

    return entries, fmt, be, signature, unk_bytes


def bnd3_pack(entries, fmt, big_endian, signature, unk_bytes):
    """Rebuild a BND3 from [[id, name, data, unk_flag1], ...].
    Faithfully mirrors BND.cs Write() for BND3.
    """
    endian     = ">" if big_endian else "<"
    has_uncomp = fmt in (0x74, 0x54, 0x2E, 0x64)
    entry_hdr  = 20 + (4 if has_uncomp else 0)

    encoded_names = [e[1].encode("shift-jis") + b"\x00" for e in entries]

    # --- Pass 1: write header + entry header placeholders ---
    out = bytearray()
    def wb(f, *a): out.extend(struct.pack(f, *a))

    # BND3 header (32 bytes)
    out += b"BND3"
    sig_bytes = signature if isinstance(signature, bytes) else signature.encode()
    out += sig_bytes[:8].ljust(8, b"\x00")   # exactly 8 bytes
    out.append(fmt)
    out.append(1 if big_endian else 0)
    out.append(0)           # IsPS3
    out.append(0)           # UnkFlag01
    wb(endian + "i", len(entries))
    OFF_names_end = len(out)
    wb(endian + "i", 0)     # placeholder: namesEndOffset
    out += unk_bytes[:8].ljust(8, b"\x00")   # UnknownBytes01, preserved exactly

    # Entry headers (all offsets as placeholders for now)
    OFF_entry_hdrs = len(out)
    for e in entries:
        eid, ename, edata, unk_flag1 = e
        out.append(unk_flag1)
        out += b"\x00\x00\x00"
        wb(endian + "i", len(edata))       # CompressedFileSize (= size, not compressed)
        wb(endian + "i", 0)                # placeholder: data offset
        wb(endian + "i", eid)
        wb(endian + "i", 0)                # placeholder: name offset
        if has_uncomp:
            wb(endian + "i", len(edata))   # UncompressedFileSize

    # Names section
    name_offsets = []
    for enc in encoded_names:
        name_offsets.append(len(out))
        out += enc

    # namesEndOffset = position right after all names, BEFORE padding (matches BND.cs)
    names_end_val = len(out)
    struct.pack_into(endian + "i", out, OFF_names_end, names_end_val)

    # Pad to 0x10
    rem = len(out) % 16
    if rem:
        out += b"\x00" * (16 - rem)

    # Data section
    data_offsets = []
    for i, e in enumerate(entries):
        data_offsets.append(len(out))
        out += e[2]
        if i < len(entries) - 1:
            rem = len(out) % 16
            if rem:
                out += b"\x00" * (16 - rem)

    # --- Pass 2: fill in data and name offset placeholders ---
    cur = OFF_entry_hdrs
    for i, e in enumerate(entries):
        cur += 4                           # skip flag + 3 blank bytes
        cur += 4                           # skip CompressedFileSize
        struct.pack_into(endian + "i", out, cur, data_offsets[i])
        cur += 4                           # data offset
        cur += 4                           # skip ID
        struct.pack_into(endian + "i", out, cur, name_offsets[i])
        cur += 4                           # name offset
        if has_uncomp:
            cur += 4                       # skip UncompressedFileSize

    return bytes(out)


# ---------------------------------------------------------------------------
# CharaInitParam  —  read/write individual class records
# ---------------------------------------------------------------------------

# Field offsets within a CharaInitParam record (size 0xF0):
_CHR_RECORD_SIZE  = 0xF0
_OFF_WEP_RIGHT    = 0x010   # s32  equip_Wep_Right
_OFF_SPELL_01     = 0x060   # s32  equip_Spell_01
_OFF_SOUL_LV      = 0x0C0   # s16  soulLv
_OFF_BASE_VIT     = 0x0C2   # u8   baseVit
_OFF_BASE_WIL     = 0x0C3   # u8   baseWil  (attunement)
_OFF_BASE_END     = 0x0C4   # u8   baseEnd
_OFF_BASE_STR     = 0x0C5   # u8   baseStr
_OFF_BASE_DEX     = 0x0C6   # u8   baseDex
_OFF_BASE_MAG     = 0x0C7   # u8   baseMag  (intelligence)
_OFF_BASE_FAI     = 0x0C8   # u8   baseFai


def parse_chara_init_param(data: bytes):
    """Return list of (row_id, name, record_bytes) from a CharaInitParam.param."""
    strings_offset, = struct.unpack_from("<I", data, 0)
    data_start,     = struct.unpack_from("<H", data, 4)
    row_count,      = struct.unpack_from("<H", data, 10)

    if row_count < 2:
        entry_size = strings_offset - data_start
    else:
        _, off1, _ = struct.unpack_from("<III", data, 0x30)
        _, off2, _ = struct.unpack_from("<III", data, 0x30 + 12)
        entry_size = off2 - off1

    rows = []
    for i in range(row_count):
        hdr = 0x30 + i * 12
        row_id, data_off, name_off = struct.unpack_from("<III", data, hdr)
        record = bytearray(data[data_off:data_off + entry_size])
        end    = data.index(b"\x00", name_off)
        name   = data[name_off:end].decode("shift-jis", errors="replace")
        rows.append([row_id, name, record])

    return rows


def build_chara_init_param(rows: list, original: bytes) -> bytes:
    """Write patched records back into the original param bytes at their original offsets.
    Since we never add/remove rows or change record size, the header and all offsets
    stay identical — we only overwrite the data bytes in-place.
    """
    out = bytearray(original)
    row_count, = struct.unpack_from("<H", original, 10)
    for i in range(row_count):
        hdr = 0x30 + i * 12
        _, data_off, _ = struct.unpack_from("<III", original, hdr)
        record = rows[i][2]
        out[data_off:data_off + len(record)] = record
    return bytes(out)


def patch_class_record(record: bytearray, weapon_id: int, spell_id,
                        soul_level: int, str_: int, dex: int, int_: int, fth: int):
    struct.pack_into("<i", record, _OFF_WEP_RIGHT, weapon_id)
    struct.pack_into("<i", record, _OFF_SPELL_01,  spell_id if spell_id is not None else -1)
    struct.pack_into("<h", record, _OFF_SOUL_LV,   soul_level)
    record[_OFF_BASE_STR] = str_
    record[_OFF_BASE_DEX] = dex
    record[_OFF_BASE_MAG] = int_
    record[_OFF_BASE_FAI] = fth


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
    req = {"str": weapon["req_str"], "dex": weapon["req_dex"],
           "int": weapon["req_int"], "fth": weapon["req_fth"]}
    if spell_req:
        req["int"] = max(req["int"], spell_req.get("int", 0))
        req["fth"] = max(req["fth"], spell_req.get("fth", 0))
    return req


def levels_needed(stats, req):
    return (max(0, req["str"] - stats["str"]) + max(0, req["dex"] - stats["dex"])
          + max(0, req["int"] - stats["int"]) + max(0, req["fth"] - stats["fth"]))


def find_best_class(req):
    return min(STARTING_CLASSES.items(), key=lambda kv: levels_needed(kv[1], req))


def compute_final_stats(class_name, req):
    base = STARTING_CLASSES[class_name]
    return {k: max(base[k], req.get(k, 0)) for k in ("str", "dex", "int", "fth")}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

pool = [w for w in WEAPONS.values()
        if not w["name"].startswith("徘徊")
        and w.get("wepmotionCategory", "") not in EXCLUDED_CATEGORIES]

weapon     = random.choice(pool)
spell      = determine_spell(weapon)
req        = combine_requirements(weapon, SPELL_REQUIREMENTS.get(spell))
best_class, _ = find_best_class(req)
levels     = levels_needed(STARTING_CLASSES[best_class], req)
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
print(f"\nLoading {GAMEPARAM_PATH} ...")
raw_dcx  = GAMEPARAM_PATH.read_bytes()
bnd_data = dcx_decompress(raw_dcx)
entries, fmt, be, sig, unk_bytes = bnd3_unpack(bnd_data)

chr_idx  = next(i for i, (_, name, _, _flag) in enumerate(entries) if "CharaInitParam" in name)
chr_entry = entries[chr_idx]
chr_name, chr_data = chr_entry[1], chr_entry[2]
rows = parse_chara_init_param(chr_data)

# --- Backup before touching anything ---
if not BACKUP_PATH.exists():
    BACKUP_PATH.write_bytes(raw_dcx)
    print(f"Backup written → {BACKUP_PATH}")
else:
    print(f"Backup already exists, skipping → {BACKUP_PATH}")

# --- Patch both class ID ranges ---
target_ids = {CLASS_IDS_2000[best_class], CLASS_IDS_3000[best_class]}
patched = 0
for row in rows:
    if row[0] in target_ids:
        patch_class_record(
            row[2],
            weapon_id   = int(weapon["ID"]),
            spell_id    = spell_id,
            soul_level  = final_level,
            str_        = final_stats["str"],
            dex         = final_stats["dex"],
            int_        = final_stats["int"],
            fth         = final_stats["fth"],
        )
        patched += 1

if patched == 0:
    raise RuntimeError(f"No rows matched class IDs {target_ids} — nothing patched.")

# --- Rebuild CharaInitParam → BND → DCX → write ---
new_chr_data = build_chara_init_param(rows, chr_data)
entries[chr_idx][2] = new_chr_data  # patch in-place, preserving id/name/flag

new_bnd  = bnd3_pack(entries, fmt, be, sig, unk_bytes)
new_dcx  = dcx_compress(new_bnd, raw_dcx)
GAMEPARAM_PATH.write_bytes(new_dcx)

print(f"\nPatched {patched} class record(s) (IDs {sorted(target_ids)}).")
print(f"GameParam.parambnd.dcx updated.")
print(f"\nTo restore: copy {BACKUP_PATH.name} back over GameParam.parambnd.dcx")