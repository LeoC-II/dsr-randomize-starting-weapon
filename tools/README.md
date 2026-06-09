# tools/

Scripts for extracting and regenerating `game_constants.py` from the game files. You only need these if you want to regenerate the constants (e.g. after a game update).

All scripts require `DarkSoulsItemRandomizer-master` to be present in the repo root (not included, gitignored).

---

## generate_game_constants.py

Combines data from all three dump scripts into a single `game_constants.py` at the repo root.

```
python tools/generate_game_constants.py
```

This is the only script you need to run. It calls the underlying parsers internally and writes the output file directly.

---

## dump_weapon_data.py

Parses `EquipParamWeapon.param` from `GameParam.parambnd.dcx` and extracts per-weapon stat requirements (`properStrength`, `properAgility`, `properMagic`, `properFaith`) and type flags (`enableMagic`, `enableSorcery`, `enableMiracle`).

Weapon types are mapped as:
| Flag | Type |
|---|---|
| `enableSorcery` | `pyro_flame` |
| `enableMiracle` | `talisman` |
| `enableMagic` | `catalyst` |
| _(none)_ | `weapon` |

Field offsets were verified against `EQUIP_PARAM_WEAPON_ST.paramdef` from the ds1r ParamVessel paramdefbnd.

---

## dump_class_ids.py

Parses `CharaInitParam.param` and extracts the row IDs for all ten starting classes across both ID ranges (2000–2009 and 3000–3009).

Both ranges are patched at runtime because DSR uses two separate CharaInitParam entries — one for the character creation preview and one for the actual playable character.

---

## dump_spell_data.py

Parses `Magic.param` and finds the row IDs for the three spells used by the randomizer: Soul Arrow, Combustion, and Lightning Spear. Names are matched against a keyword list to handle the Japanese strings in the param file.