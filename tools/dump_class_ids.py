#!/usr/bin/env python3
"""
Dump CharaInitParam class IDs from GameParam.parambnd.dcx
Outputs CLASS_IDS dict for use in random-weapon.py
"""

import sys
import struct
sys.path.insert(0, 'DarkSoulsItemRandomizer-master')

import dcx_handler
import bnd_rebuilder
import chr_init_param as cip

GAMEPARAM_PATH = (
    r"C:\Program Files (x86)\Steam\steamapps\common"
    r"\DARK SOULS REMASTERED\param\GameParam\GameParam.parambnd.dcx"
)

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

try:
    print(f"Loading {GAMEPARAM_PATH}")
    with open(GAMEPARAM_PATH, 'rb') as f:
        content = f.read()
    
    print("Decompressing DCX...")
    content = dcx_handler.uncompress_dcx_content(content)
    
    print("Unpacking BND...")
    content_list = bnd_rebuilder.unpack_bnd(content)
    
    print("Finding CharaInitParam.param...")
    chr_init_data = None
    for file_id, filepath, file_content in content_list:
        if "CharaInitParam" in filepath:
            chr_init_data = file_content
            print(f"  Found at: {filepath}")
            break
    
    if not chr_init_data:
        print("ERROR: CharaInitParam.param not found!")
        sys.exit(1)
    
    print("Parsing CharaInitParam...")
    char_init_param = cip.ChrInitParam.load_from_file_content(chr_init_data)
    
    print("\n" + "="*60)
    print("CLASS IDs (for use in random-weapon.py):")
    print("="*60)
    
    # Map descriptions to class names for lookup
    # Check for both 2000-2009 (female?) and 3000-3009 (male?) ranges
    class_id_dict = {}
    
    for chr_init in char_init_param.chr_inits:
        chr_id = chr_init.chr_init_id
        description = chr_init.description
        
        # Check for 2000-2009 range (initial characters)
        if 2000 <= chr_id <= 2009:
            offset = chr_id - 2000
            if offset < len(CLASS_NAMES):
                class_name = CLASS_NAMES[offset]
                class_id_dict[f"{class_name}_2000"] = chr_id
                print(f"{class_name:15} (2000 range) = {chr_id:5}  | {description}")
        
        # Check for 3000-3009 range (alternate/male versions?)
        if 3000 <= chr_id <= 3009:
            offset = chr_id - 3000
            if offset < len(CLASS_NAMES):
                class_name = CLASS_NAMES[offset]
                class_id_dict[f"{class_name}_3000"] = chr_id
                print(f"{class_name:15} (3000 range) = {chr_id:5}  | {description}")
    
    
    print("\nPython dict format (2000 range):")
    print("-" * 60)
    print(f"CLASS_IDS_2000 = {{")
    for class_name in CLASS_NAMES:
        key = f"{class_name}_2000"
        if key in class_id_dict:
            print(f'    "{class_name}": {class_id_dict[key]},')
        else:
            print(f'    "{class_name}": None,  # NOT FOUND')
    print(f"}}")
    
    print("\nPython dict format (3000 range):")
    print("-" * 60)
    print(f"CLASS_IDS_3000 = {{")
    for class_name in CLASS_NAMES:
        key = f"{class_name}_3000"
        if key in class_id_dict:
            print(f'    "{class_name}": {class_id_dict[key]},')
        else:
            print(f'    "{class_name}": None,  # NOT FOUND')
    print(f"}}")
    
    print("\n" + "="*60)
    print("ALL CharaInitParam entries:")
    print("="*60)
    for chr_init in char_init_param.chr_inits:
        print(f"ID: {chr_init.chr_init_id:5} | {chr_init.description}")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
