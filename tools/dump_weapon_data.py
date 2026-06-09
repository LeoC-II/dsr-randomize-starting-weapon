#!/usr/bin/env python3
"""
Dump weapon data (requirements and types) from EquipParamWeapon.param

Known test weapons for format verification:
- Manus (Staff): 14 STR, 13 INT
- Tin Crystallization Catalyst: 7 STR, 32 INT
- Crystal Catalyst: ? STR, ? INT

Requirements to track: STR, DEX, INT, FTH (4 bytes each as shorts)
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
    
    print("Finding EquipParamWeapon.param...")
    equip_param_weapon_data = None
    for file_id, filepath, file_content in content_list:
        if "EquipParamWeapon" in filepath:
            equip_param_weapon_data = file_content
            print(f"  Found at: {filepath}")
            print(f"  File size: {len(file_content)} bytes")
            break
    
    if not equip_param_weapon_data:
        print("ERROR: EquipParamWeapon.param not found!")
        sys.exit(1)
    
    print("\nParsing EquipParamWeapon header...")
    
    # Parse header
    master_offset = 0
    (strings_offset, data_offset, unk, record_count) = struct.unpack_from("<IIHH", equip_param_weapon_data, offset=master_offset)
    print(f"  Strings offset: 0x{strings_offset:x}")
    print(f"  Data offset: 0x{data_offset:x}")
    print(f"  Record count: {record_count}")
    
    # Calculate record size
    if record_count > 1:
        first_record_offset = 0x30
        (val1, data_offset_1, str_offset_1) = struct.unpack_from("<III", equip_param_weapon_data, offset=first_record_offset)
        (val2, data_offset_2, str_offset_2) = struct.unpack_from("<III", equip_param_weapon_data, offset=first_record_offset + 12)
        record_size = data_offset_2 - data_offset_1
    else:
        record_size = data_offset - 0x30
    
    print(f"  Record size: {record_size} bytes")
    
    print("\n" + "="*80)
    print("Sampling weapons to find stat requirement offsets...")
    print("="*80)
    print("Looking for exact known weapon IDs:")
    print("  - Manus Catalyst: 9017000 (expect 14 STR, 13 INT)")
    print("  - Tin Crystallization Catalyst: 1306000 (expect 7 STR, 32 INT)")
    print("  - Crystal Catalyst: 1304000")
    print("="*80)
    
    known_ids = {
        9017000: "Manus Catalyst",
        1306000: "Tin Crystallization Catalyst",
        1304000: "Crystal Catalyst",
    }
    
    # Find and inspect known weapons by ID
    found_known = []
    for i in range(record_count):
        record_offset = 0x30 + i * 12
        (weapon_id, data_offset_rec, string_offset) = struct.unpack_from("<III", equip_param_weapon_data, offset=record_offset)
        
        if weapon_id not in known_ids:
            continue
        
        try:
            weapon_name = extract_shift_jisz(equip_param_weapon_data, string_offset)
        except:
            weapon_name = "(unknown)"
        
        weapon_data = equip_param_weapon_data[data_offset_rec:data_offset_rec + record_size]
        found_known.append((weapon_id, known_ids[weapon_id], weapon_name, weapon_data))
    
    for weapon_id, label, weapon_name, weapon_data in found_known:
        expected = None
        if weapon_id == 9017000:
            expected = (14, 0, 13, 0)
        elif weapon_id == 1306000:
            expected = (7, 0, 32, 0)
        
        print(f"\nID: {weapon_id:6} | {label} | {weapon_name}")
        if expected:
            print(f"  Expected STR,DEX,INT,FTH: {expected}")

        # Search for patterns across the record data
        matches = []
        for offset in range(0, record_size - 8, 2):
            try:
                vals_s = struct.unpack_from("<hhhh", weapon_data, offset=offset)
                vals_us = struct.unpack_from("<HHHH", weapon_data, offset=offset)
                vals_i = struct.unpack_from("<iiii", weapon_data, offset=offset)
            except Exception:
                continue
            
            if expected and vals_s == expected:
                matches.append((offset, "short", vals_s))
            elif expected and vals_i == expected:
                matches.append((offset, "int", vals_i))
            elif expected and vals_us == expected:
                matches.append((offset, "ushort", vals_us))
        
        if matches:
            for offset, dtype, vals in matches:
                print(f"  EXACT MATCH {dtype} at offset 0x{offset:02x}: {vals}")
        else:
            # Print best candidates where values are in a plausible weapon requirement range
            print("  No exact expected match found. Showing plausible 4-short candidates:")
            for offset in range(0, record_size - 8, 2):
                vals_s = struct.unpack_from("<hhhh", weapon_data, offset=offset)
                if all(-5 <= v <= 50 for v in vals_s):
                    print(f"    Offset 0x{offset:02x}: {vals_s}")
                    if len([x for x in vals_s if x not in (0, -1)]) >= 2:
                        break
    
    if not found_known:
        print("No known weapons found by exact ID in EquipParamWeapon.param.")
    
    # Also show first 20 for reference
    print("\n" + "="*80)
    print("First 20 weapons (for reference):")
    print("="*80)
    
    for i in range(min(record_count, 20)):
        record_offset = 0x30 + i * 12
        (weapon_id, data_offset_rec, string_offset) = struct.unpack_from("<III", equip_param_weapon_data, offset=record_offset)
        
        try:
            weapon_name = extract_shift_jisz(equip_param_weapon_data, string_offset)
        except:
            weapon_name = "(unknown)"
        
        weapon_data = equip_param_weapon_data[data_offset_rec:data_offset_rec + record_size]
        
        try:
            # Try offset 0x20 (32 bytes) which is common for requirement fields
            vals = struct.unpack_from("<hhhh", weapon_data, offset=0x20)
            print(f"ID: {weapon_id:6} | {weapon_name:40} | Offset 0x20: {vals[0]:3},{vals[1]:3},{vals[2]:3},{vals[3]:3}")
        except:
            print(f"ID: {weapon_id:6} | {weapon_name:40} | (parse error)")
    
    print("\n" + "="*80)
    print("ANALYSIS COMPLETE")
    print("="*80)
    print("Look at MANUS and TIN CRYSTALLIZATION output above.")
    print("Find which offset shows: 14,0,13,0 and 7,0,32,0")
    print("That will be the STR,DEX,INT,FTH offset for all weapons.")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
