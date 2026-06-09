# DSR Random Starting Weapon

Randomizes the starting weapon for Dark Souls Remastered. Each run picks a random weapon, finds the best-fitting starting class, adjusts its stats to meet requirements, and patches the game files directly.

## Requirements

- Python 3.10+
- Dark Souls Remastered (Steam)
- No third-party Python packages needed

## Setup

Run the following command (this is on windows):
```bash
cp .\config.json.example config.json
```

Edit `config.json` to point to your game installation (default Steam value is already in `config.json.example`):

```json
{
    "gameparam_path": "C:/Program Files (x86)/Steam/steamapps/common/DARK SOULS REMASTERED/param/GameParam/GameParam.parambnd.dcx",
    "backup_path": "C:/Program Files (x86)/Steam/steamapps/common/DARK SOULS REMASTERED/param/GameParam/GameParam.parambnd.dcx.bak"
}
```

`backup_path` defaults to next to the game file. Change it if you want the backup stored elsewhere.

## Usage

```
python random_weapon.py [--seed SEED]
```

| Argument | Description |
|---|---|
| `--seed` | Integer seed for reproducible results. Omit for a random seed. |

```
Seed: 2847163054

============================================================
RANDOMIZATION RESULT
============================================================
Weapon : Zweihänder (ID: 300000)
Spell  : None
Class  : Bandit  (+2 levels → 6)
Stats  : STR 16  DEX 9  INT 8  FTH 10

Restoring from backup → GameParam.parambnd.dcx.bak
Patched 2 class record(s) (IDs [2004, 3004]).
GameParam.parambnd.dcx updated.

Re-run with --seed 2847163054 to reproduce this result.
```

## Backup behaviour

- **First run:** the original `GameParam.parambnd.dcx` is backed up automatically.
- **Subsequent runs:** the backup is restored first, then the new patch is applied. Every run starts from the clean original.
- **To restore manually:** copy `GameParam.parambnd.dcx.bak` back over `GameParam.parambnd.dcx`.

## How it works

1. A weapon is picked at random from the pool (arrows, bolts, bows, crossbows, shields, and greatshields excluded).
2. Catalysts get Soul Arrow, pyromancy flames get Combustion, talismans get Lightning Spear.
3. All ten starting classes are scored by levels needed to meet the weapon's stat requirements. Ties are broken randomly using the same seed.
4. The winning class's STR/DEX/INT/FTH are raised to exactly meet requirements.
5. Both class ID ranges (2000 and 3000) are patched in `CharaInitParam.param` inside `GameParam.parambnd.dcx`.

## Credits
Credits to the (Dark Souls Randomizer)[https://github.com/HotPocketRemix/DarkSoulsItemRandomizer] without which the inlined param reading and editing logic would not have been possible. It is also what is used in the tools folder.