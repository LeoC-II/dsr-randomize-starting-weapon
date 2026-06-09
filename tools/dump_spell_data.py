#!/usr/bin/env python3
"""
Dump spell data from Magic.param
Outputs SPELL_IDS dict for use in random-weapon.py

Targets:
- Soul Arrow
- Combustion  
- Lightning Spear
"""

import sys
import struct
sys.path.insert(0, 'DarkSoulsItemRandomizer-master')

import dcx_handler
import bnd_rebuilder

GAMEPARAM_PATH = (
    r"C:\Program Files (x86)\Steam\steamapps\common"
    r"\DARK SOULS REMASTERED\param\GameParam\GameParam.parambnd.dcx"
)

SPELL_NAMES = [
    "Soul Arrow",
    "Combustion",
    "Lightning Spear",
]

# Japanese spell names/keywords
SPELL_KEYWORDS = {
    "Soul Arrow": ["ソウルの矢", "soul arrow", "arrow"],
    "Combustion": ["ファイアボール", "火", "炎", "combustion"],  # Fireball is probably the starter pyro
    "Lightning Spear": ["雷", "稲妻", "lightning spear", "lightning"],  # 雷 = lightning
}

def extract_shift_jisz(content, offset):
    extracted = b''
    while content[offset:offset+1] != b'\x00':
        extracted = extracted + content[offset:offset+1]
        offset += 1
    return extracted.decode('shift-jis', errors='ignore')

try:
    print(f"Loading {GAMEPARAM_PATH}")
    with open(GAMEPARAM_PATH, 'rb') as f:
        content = f.read()
    
    print("Decompressing DCX...")
    content = dcx_handler.uncompress_dcx_content(content)
    
    print("Unpacking BND...")
    content_list = bnd_rebuilder.unpack_bnd(content)
    
    print("Finding Magic.param...")
    magic_param_data = None
    for file_id, filepath, file_content in content_list:
        if "Magic" in filepath and filepath.endswith(".param"):
            magic_param_data = file_content
            print(f"  Found at: {filepath}")
            break
    
    if not magic_param_data:
        print("ERROR: Magic.param not found!")
        print("\nAvailable params:")
        for file_id, filepath, file_content in content_list:
            if filepath.endswith(".param"):
                print(f"  - {filepath}")
        sys.exit(1)
    
    print("\nParsing Magic header...")
    
    # Parse header like CharaInitParam
    master_offset = 0
    (strings_offset, data_offset, unk, record_count) = struct.unpack_from("<IIHH", magic_param_data, offset=master_offset)
    print(f"  Strings offset: 0x{strings_offset:x}")
    print(f"  Data offset: 0x{data_offset:x}")
    print(f"  Record count: {record_count}")
    
    # Calculate record size
    if record_count > 1:
        first_record_offset = 0x30
        (val1, data_offset_1, str_offset_1) = struct.unpack_from("<III", magic_param_data, offset=first_record_offset)
        (val2, data_offset_2, str_offset_2) = struct.unpack_from("<III", magic_param_data, offset=first_record_offset + 12)
        record_size = data_offset_2 - data_offset_1
    else:
        record_size = data_offset - 0x30
    
    print(f"  Record size: {record_size} bytes")
    
    print("\n" + "="*60)
    print("All spells in Magic.param:")
    print("="*60)
    
    spell_ids = {}
    
    for i in range(record_count):
        record_offset = 0x30 + i * 12
        (spell_id, data_offset_rec, string_offset) = struct.unpack_from("<III", magic_param_data, offset=record_offset)
        
        try:
            spell_name = extract_shift_jisz(magic_param_data, string_offset)
        except:
            spell_name = "(unknown)"
        
        # Check if this matches one of our target spells
        marker = ""
        for target_spell in SPELL_NAMES:
            for keyword in SPELL_KEYWORDS.get(target_spell, []):
                if keyword.lower() in spell_name.lower():
                    marker = " ← TARGET"
                    # Only record the first match (avoid duplicates for multiple IDs)
                    if target_spell not in spell_ids:
                        spell_ids[target_spell] = spell_id
                    break
            if marker:
                break
        
        # Safely print with error handling for Unicode
        try:
            print(f"ID: {spell_id:6} | {spell_name:40}{marker}")
        except:
            # Fallback if terminal can't handle Japanese
            print(f"ID: {spell_id:6} | {spell_name.encode('utf-8', errors='replace').decode('utf-8', errors='replace'):40}{marker}")
    
    print("\n" + "="*60)
    print("SPELL_IDS dict for random-weapon.py:")
    print("="*60)
    print("SPELL_IDS = {")
    for spell_name in SPELL_NAMES:
        if spell_name in spell_ids:
            print(f'    "{spell_name}": {spell_ids[spell_name]},')
        else:
            print(f'    "{spell_name}": None,  # NOT FOUND - try fuzzy matching above')
    print("}")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
