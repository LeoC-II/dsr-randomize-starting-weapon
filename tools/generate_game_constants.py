#!/usr/bin/env python3
from pathlib import Path
import csv
import json
import sys
import struct

sys.path.insert(0, "DarkSoulsItemRandomizer-master")

import dcx_handler
import bnd_rebuilder
import chr_init_param as cip

ROOT = Path(__file__).parent
DS120INFO_PATH = ROOT / "DS120INFO.md"
GAMEPARAM_PATH = (
    r"C:\Program Files (x86)\Steam\steamapps\common"
    r"\DARK SOULS REMASTERED\param\GameParam\GameParam.parambnd.dcx"
)
OUTPUT_PATH = ROOT / "game_constants.py"

CLASS_NAMES = [
    "Warrior",
    "Knight",
    "Wanderer",
    "Thief",
    "Bandit",
    "Hunter",
    "Sorcerer",
    "Pyromancer",
    "Cleric",
    "Deprived",
]

SPELL_NAMES = [
    "Soul Arrow",
    "Combustion",
    "Lightning Spear",
]

SPELL_KEYWORDS = {
    "Soul Arrow": ["ソウルの矢", "soul arrow", "arrow"],
    "Combustion": ["ファイアボール", "火", "炎", "combustion", "fireball"],
    "Lightning Spear": ["雷", "稲妻", "lightning spear", "lightning"],
}

# Field offsets within each EquipParamWeapon record (verified against
# EQUIP_PARAM_WEAPON_ST.paramdef from ds1r_paramdef-paramdefbnd):
#   properStrength  u8  @ 0x0ED  → "str"
#   properAgility   u8  @ 0x0EE  → "dex"  (agility == dexterity in DS1)
#   properMagic     u8  @ 0x0EF  → "int"
#   properFaith     u8  @ 0x0F0  → "fth"
#   enableGuard     1-bit  @ byte 0x100 bit 5
#   enableParry     1-bit  @ byte 0x100 bit 6
#   enableMagic     1-bit  @ byte 0x100 bit 7
#   enableSorcery   1-bit  @ byte 0x101 bit 0
#   enableMiracle   1-bit  @ byte 0x101 bit 1
#   enableVowMagic  1-bit  @ byte 0x101 bit 2
_OFF_STR      = 0x0ED
_OFF_AGI      = 0x0EE
_OFF_MAG      = 0x0EF
_OFF_FTH      = 0x0F0
_OFF_FLAGS0   = 0x100   # bits: 5=enableGuard, 6=enableParry, 7=enableMagic
_OFF_FLAGS1   = 0x101   # bits: 0=enableSorcery, 1=enableMiracle, 2=enableVowMagic


def extract_shift_jisz(content, offset):
    result = b""
    while offset < len(content) and content[offset:offset+1] != b"\x00":
        result += content[offset:offset+1]
        offset += 1
    return result.decode("shift-jis", errors="ignore")


def parse_ds120info():
    with DS120INFO_PATH.open("r", encoding="utf-8") as f:
        lines = [line.rstrip("\n") for line in f if "|" in line]

    if not lines:
        raise RuntimeError("DS120INFO.md looks empty or has no table rows")

    headers = [h.strip() for h in next(csv.reader([lines[0]], delimiter="|"))]
    weapons = []

    for line in lines[2:]:
        values = [v.strip() for v in next(csv.reader([line], delimiter="|"))]
        if len(values) != len(headers):
            values += [""] * (len(headers) - len(values))
        weapon = dict(zip(headers, values))
        weapons.append(weapon)

    return weapons


def find_bnd_entry(content_list, term, endswith=None):
    for file_id, filepath, file_content in content_list:
        if term in filepath and (endswith is None or filepath.endswith(endswith)):
            return file_id, filepath, file_content
    return None


def parse_weapon_record(record):
    """Extract requirements and type flags from a raw EquipParamWeapon record."""
    if len(record) < 0x102:
        return None

    str_req = record[_OFF_STR]
    dex_req = record[_OFF_AGI]
    mag_req = record[_OFF_MAG]
    fth_req = record[_OFF_FTH]

    flags0 = record[_OFF_FLAGS0]
    flags1 = record[_OFF_FLAGS1]

    enable_magic    = bool(flags0 & (1 << 7))
    enable_sorcery  = bool(flags1 & (1 << 0))
    enable_miracle  = bool(flags1 & (1 << 1))

    if enable_sorcery:
        weapon_type = "pyro_flame"
    elif enable_miracle:
        weapon_type = "talisman"
    elif enable_magic:
        weapon_type = "catalyst"
    else:
        weapon_type = "weapon"

    return {
        "requirements": {
            "str": str_req,
            "dex": dex_req,
            "int": mag_req,
            "fth": fth_req,
        },
        "weapon_type": weapon_type,
    }


def parse_weapon_param(weapon_data):
    """Parse EquipParamWeapon.param and return (requirements_dict, types_dict)."""
    # Param header layout (DS1 / DSR):
    #   0x00: u32 strings_offset
    #   0x04: u16 data_start_offset
    #   0x06: s16 unk1
    #   0x08: s16 unk2
    #   0x0A: u16 row_count
    #   0x0C: char[32] param_id (shift-jis, padded)
    #   0x2C: s32 format_version
    #   0x30: row headers start (12 bytes each: s32 id, u32 data_offset, u32 name_offset)
    (strings_offset,) = struct.unpack_from("<I", weapon_data, 0)
    (data_start,)     = struct.unpack_from("<H", weapon_data, 4)
    (row_count,)      = struct.unpack_from("<H", weapon_data, 10)

    if row_count < 2:
        entry_size = strings_offset - data_start
    else:
        (_, off1, _) = struct.unpack_from("<III", weapon_data, 0x30)
        (_, off2, _) = struct.unpack_from("<III", weapon_data, 0x30 + 12)
        entry_size = off2 - off1

    requirements = {}
    types = {}

    for i in range(row_count):
        hdr_off = 0x30 + i * 12
        row_id, data_off, _ = struct.unpack_from("<III", weapon_data, hdr_off)
        record = weapon_data[data_off:data_off + entry_size]
        parsed = parse_weapon_record(record)
        if parsed is not None:
            requirements[row_id] = parsed["requirements"]
            types[row_id]        = parsed["weapon_type"]

    return requirements, types


def parse_gameparam():
    with open(GAMEPARAM_PATH, "rb") as f:
        content = f.read()

    content = dcx_handler.uncompress_dcx_content(content)
    content_list = bnd_rebuilder.unpack_bnd(content)

    # --- CharaInitParam ---
    entry = find_bnd_entry(content_list, "CharaInitParam")
    if entry is None:
        raise RuntimeError("CharaInitParam.param not found in GameParam.parambnd.dcx")
    _, chr_path, chr_data = entry
    char_init_param = cip.ChrInitParam.load_from_file_content(chr_data)

    class_ids_2000 = {}
    class_ids_3000 = {}
    for chr_init in char_init_param.chr_inits:
        chr_id = chr_init.chr_init_id
        if 2000 <= chr_id <= 2009:
            class_ids_2000[CLASS_NAMES[chr_id - 2000]] = chr_id
        if 3000 <= chr_id <= 3009:
            class_ids_3000[CLASS_NAMES[chr_id - 3000]] = chr_id

    # --- Magic.param ---
    entry = find_bnd_entry(content_list, "Magic", endswith=".param")
    if entry is None:
        raise RuntimeError("Magic.param not found in GameParam.parambnd.dcx")
    _, magic_path, magic_data = entry

    (strings_offset, data_offset, unk, record_count) = struct.unpack_from("<IIHH", magic_data, offset=0)
    if record_count > 1:
        first_record_offset = 0x30
        (_, data_offset_1, _) = struct.unpack_from("<III", magic_data, offset=first_record_offset)
        (_, data_offset_2, _) = struct.unpack_from("<III", magic_data, offset=first_record_offset + 12)
        record_size = data_offset_2 - data_offset_1
    else:
        record_size = data_offset - 0x30

    spell_ids = {}
    for i in range(record_count):
        record_offset = 0x30 + i * 12
        spell_id, _, string_offset = struct.unpack_from("<III", magic_data, offset=record_offset)
        spell_name = extract_shift_jisz(magic_data, string_offset)
        for target_spell in SPELL_NAMES:
            if target_spell in spell_ids:
                continue
            for keyword in SPELL_KEYWORDS[target_spell]:
                if keyword.lower() in spell_name.lower():
                    spell_ids[target_spell] = spell_id
                    break

    # --- EquipParamWeapon ---
    entry = find_bnd_entry(content_list, "EquipParamWeapon", endswith=".param")
    if entry is None:
        raise RuntimeError("EquipParamWeapon.param not found in GameParam.parambnd.dcx")
    _, weapon_path, weapon_data = entry
    weapon_requirements, weapon_types = parse_weapon_param(weapon_data)

    return class_ids_2000, class_ids_3000, spell_ids, weapon_requirements, weapon_types


def write_constants(class_ids_2000, class_ids_3000, spell_ids,
                    weapon_requirements, weapon_types, weapons):
    weapon_metadata = {weapon["ID"]: weapon for weapon in weapons}

    lines = [
        "# Auto-generated game constants file",
        "# Generated by generate_game_constants.py",
        "from typing import Dict, Any",
        "",
        "CLASS_IDS_2000 = {",
    ]

    for name in CLASS_NAMES:
        value = class_ids_2000.get(name)
        lines.append(f'    "{name}": {value if value is not None else "None"},')
    lines.append("}")
    lines.append("")
    lines.append("CLASS_IDS_3000 = {")
    for name in CLASS_NAMES:
        value = class_ids_3000.get(name)
        lines.append(f'    "{name}": {value if value is not None else "None"},')
    lines.append("}")
    lines.append("")
    lines.append("SPELL_IDS = {")
    for name in SPELL_NAMES:
        value = spell_ids.get(name)
        lines.append(f'    "{name}": {value if value is not None else "None"},')
    lines.append("}")
    lines.append("")

    # WEAPONS: one entry per param ID, merging requirements, type, and DS120INFO metadata.
    # Keys per entry:
    #   "name"     str  — display name
    #   "type"     str  — "weapon" | "catalyst" | "talisman" | "pyro_flame"
    #   "req_str"  int  — properStrength
    #   "req_dex"  int  — properAgility (dexterity)
    #   "req_int"  int  — properMagic
    #   "req_fth"  int  — properFaith
    #   + all remaining DS120INFO columns as strings
    # Only include weapons present in DS120INFO; skip param-only entries (shields, etc.)
    all_ids = sorted(int(k) for k in weapon_metadata.keys())
    lines.append("WEAPONS = {")
    for wid in all_ids:
        if wid not in weapon_requirements:
            continue
        req  = weapon_requirements[wid]
        wtyp = weapon_types.get(wid, "weapon")
        meta = weapon_metadata.get(str(wid), {})
        name = meta.get("Name", "")

        lines.append(f"    {wid}: {{")
        lines.append(f'        "name": "{name}",')
        lines.append(f'        "type": "{wtyp}",')
        lines.append(f'        "req_str": {req["str"]},')
        lines.append(f'        "req_dex": {req["dex"]},')
        lines.append(f'        "req_int": {req["int"]},')
        lines.append(f'        "req_fth": {req["fth"]},')
        for key, value in meta.items():
            if key == "Name":
                continue
            escaped = value.replace('"', '\"') if isinstance(value, str) else value
            lines.append(f'        "{key}": "{escaped}",')
        lines.append(f"    }},")
    lines.append("}")
    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    weapons = parse_ds120info()
    class_ids_2000, class_ids_3000, spell_ids, weapon_requirements, weapon_types = parse_gameparam()
    write_constants(class_ids_2000, class_ids_3000, spell_ids,
                    weapon_requirements, weapon_types, weapons)