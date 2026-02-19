# Sekai-FModding
Tools for modding fonts in a certain Miku tap tap game (native: JP Server, might work on EN).

## 1. Preparation
Ensure you have Python installed. You will need the following libraries:

```bash
pip install UnityPy fonttools
```

## 2. Setup (Files & Assets)
Place your files in the following structure:

- **fontMerging/**:
  - `merge_fonts.py`: Script to merge Vietnamese/Latin glyphs into Japanese fonts.
  - Source font included. Add your own here and modify the script.
- **script/**:
  - `inject_font.py`: Script to inject the merged font and updated assets into the game's AssetBundle.
  - Original file included.

## 3.  How to Run

### Step A: Merge Fonts
Combine your custom Latin/Vietnamese font with the game's Japanese font.

```bash
cd fontMerging
# Edit existing pairings in the script or run CLI command:
# python merge_fonts.py [BaseFont] [OverrideFont] [Output]
python merge_fonts.py
```

This will generate merged font files.

### Step B: Create Replacement Bundle (Unity)
*(Note: requires Unity Editor with AssetBundle Browser, Unity version 2022.3.31f1, with Android Build Support.)*
1. Import the **merged** font files into Unity.
2. Inside Unity Editor, go to Window -> TextMesh Pro -> Font Asset Creator
3. Config
Sampling Point Size, choose Custom then 42
Padding 5
Atlas Res: 4096 x 2048 (Native)
Character Set: Custom or Character from file. Refer to the txt files inside unityMisc for the characters.
Render Mode: SFDAA
4. Generate the Atlas, then Save.
Name should be
FOT-RodinNTLGPro-EB-OnDemand (In story, EB is the character name)
FOT-RodinNTLGPro-DB-OnDemand (In story, DB is the text)
5. Build the font.
Copy BuildAssetBundles.cs into /Assets/Editor
In Unity Editor, Assets -> Build Font AssetBundle (Android)
6. Copy the font_replacement file into the script folder.

### Step C: Inject into Game Bundle
Inject the new font assets and textures into the original game bundle.

```bash
cd ../script
# Usage: python inject_font.py [NewBundlePath]
python inject_font.py font_replacement
```

This will generate a `common` file (encrypted) ready to be used in the game.

### Finalizing and testing
Rename the common file into 4ad9182d51b21d790af3f73d72ddc193.  
Navigate to Android/data/com.sega.pjsekai/files/data/47a2 and replace the file inside.  
Open the game. The font should appear in Rank and Level if done correctly.
