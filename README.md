# Sekai-FModding
Tools for modding fonts in Project Sekai (Japanese Server).

## 1. Preparation (Prerequisites)
Ensure you have Python installed. You will need the following libraries:

```bash
pip install UnityPy fonttools
```

## 2. Setup (Files & Assets)
Place your files in the following structure:

- **fontMerging/**:
  - `merge_fonts.py`: Script to merge Vietnamese/Latin glyphs into Japanese fonts.
  - Place your source fonts here (e.g., `FOT-RodinNTLG Pro EB.otf`, `#9Slide05 SVNBellico.ttf`).

- **script/**:
  - `inject_font.py`: Script to inject the merged font and updated assets into the game's AssetBundle.
  - Place the original game bundle `common` here (rename it to `common.bak` to keep a backup).

## 3. Execution (How to Run)

### Step A: Merge Fonts
Combine your custom Latin/Vietnamese font with the game's Japanese font.

```bash
cd fontMerging
# Edit existing pairings in the script or run CLI command:
# python merge_fonts.py [BaseFont] [OverrideFont] [Output]
python merge_fonts.py
```

This will generate merged font files (e.g., `FOT-RodinNTLG Pro EB - Merged.otf`).

### Step B: Create Replacement Bundle (Unity)
*(Note: requires Unity Editor with AssetBundle Browser)*
1. Import the **merged** font files into Unity.
2. Create `TMP_FontAsset` objects for them using TextMeshPro.
3. Build these into a new AssetBundle named `font_replacement`.
4. Copy `font_replacement` to the `script/` folder.

### Step C: Inject into Game Bundle
Inject the new font assets and textures into the original game bundle.

```bash
cd ../script
# Usage: python inject_font.py [NewBundlePath]
python inject_font.py font_replacement
```

This will generate a `common` file (encrypted) ready to be used in the game.
