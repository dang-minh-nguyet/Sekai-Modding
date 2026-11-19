
import UnityPy
from UnityPy.enums import ClassIDType
import os
import io

# Configuration
ORIGINAL_BUNDLE_PATH = "common.bak"
OUTPUT_BUNDLE_NAME = "common" # Output will be common (no extension)

# Argument handling for Drag and Drop
import sys
if len(sys.argv) > 1:
    NEW_BUNDLE_PATH = sys.argv[1]
    print(f"Input bundle provided: {NEW_BUNDLE_PATH}")
else:
    NEW_BUNDLE_PATH = "font_replacement"
    print(f"No input provided, using default: {NEW_BUNDLE_PATH}")

OUTPUT_BUNDLE_PATH = OUTPUT_BUNDLE_NAME

# Helper for Encryption
def decrypt_header_inplace(header: bytearray):
    assert len(header) == 128
    for i in range(0, 128, 8):
        for j in range(5):
            header[i + j] = ~header[i + j] & 0xFF
    return header

def load_encrypted_bundle(path):
    with open(path, "rb") as f:
        header = f.read(4)
        if header == b"\x10\x00\x00\x00":
            print(f"Decrypting header for {os.path.basename(path)}...")
            header_data = bytearray(f.read(128))
            decrypt_header_inplace(header_data)
            rest = f.read()
            return io.BytesIO(header_data + rest)
        else:
            f.seek(0)
            return f.read()

def main():
    if not os.path.exists(NEW_BUNDLE_PATH):
        print(f"Error: New bundle not found at {NEW_BUNDLE_PATH}")
        return

    # Load Bundles
    print("Loading Original Bundle...")
    UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.62f2" 
    decrypted_data = load_encrypted_bundle(ORIGINAL_BUNDLE_PATH)
    env_old = UnityPy.load(decrypted_data)
    
    print("Loading New Bundle...")
    env_new = UnityPy.load(NEW_BUNDLE_PATH)

    # Map name -> Object for New Bundle
    # Include Materials now!
    new_assets = {}
    for obj in env_new.objects:
        try:
            if obj.type in [ClassIDType.MonoBehaviour, ClassIDType.Texture2D, ClassIDType.Material]:
                data = obj.read()
                name = getattr(data, "name", getattr(data, "m_Name", "Unknown"))
                new_assets[name] = obj
        except:
            pass
    
    # Track PathIDs for fixing references in OLD bundle
    old_script_path_id = None
    old_material_path_ids = {} # Name -> PathID
    old_texture_path_ids = {}  # Name -> PathID

    # First pass: Collect IDs
    for obj in env_old.objects:
        if obj.type == ClassIDType.MonoScript:
            data = obj.read()
            if getattr(data, "m_ClassName", "") == "TMP_FontAsset":
                old_script_path_id = obj.path_id
        elif obj.type == ClassIDType.Material:
            data = obj.read()
            name = getattr(data, "name", getattr(data, "m_Name", "Unknown"))
            old_material_path_ids[name] = obj.path_id
        elif obj.type == ClassIDType.Texture2D:
            data = obj.read()
            name = getattr(data, "name", getattr(data, "m_Name", "Unknown"))
            old_texture_path_ids[name] = obj.path_id

    # Dynamic Finding of Target Font Asset PathIDs in Old Bundle
    target_font_assets = {} # Name -> PathID
    for obj in env_old.objects:
        if obj.type == ClassIDType.MonoBehaviour:
            try:
                data = obj.read()
                if hasattr(data, "m_Script") and data.m_Script.path_id == old_script_path_id:
                    name = getattr(data, "name", getattr(data, "m_Name", "Unknown"))
                    target_font_assets[name] = obj.path_id
            except:
                pass

    # Replacement Loop
    for name, new_obj in new_assets.items():
        if "RodinNTLG" not in name: continue 
        
        # 1. Texture Replacement
        if new_obj.type == ClassIDType.Texture2D:
             if name in old_texture_path_ids:
                 target_id = old_texture_path_ids[name]
                 if target_id in env_old.assets[0].objects:
                     print(f"Replacing Texture: {name}")
                     old_tex = env_old.assets[0].objects[target_id]
                     new_tex = new_obj.read()
                     
                     # Check if we have data
                     new_data_blob = new_tex.image_data
                     new_data_len = len(new_data_blob)
                     print(f"  New Image Data Len: {new_data_len}")
                     
                     if new_data_len == 0:
                         if new_tex.m_StreamData and new_tex.m_StreamData.path:
                             spath = new_tex.m_StreamData.path
                             print(f"  Checking StreamData: {spath}")
                             if spath.startswith("archive:/"):
                                 fname = os.path.basename(spath)
                                 # Try to find in env_new files
                                 # env_new.file might be BundleFile or WebFile
                                 # Access internal files
                                 found_file = None
                                 if hasattr(env_new.file, "files"):
                                     # Might be dict or list? Script debug showed it printed items, so dict-like or iterable
                                     files = env_new.file.files
                                     if isinstance(files, dict):
                                         found_file = files.get(fname)
                                     else:
                                         # Try simple attribute access if verify script failed on list
                                         pass
                                 
                                 if found_file:
                                    print(f"  Found internal resource: {fname}")
                                    # It might be a file-like object or bytes?
                                    # UnityPy usually File objects have read() or are bytes
                                    try:
                                        print(f"  Internal File Type: {type(found_file)}")
                                        print(f"  Dir: {[d for d in dir(found_file) if not d.startswith('__')]}")
                                        
                                        # attributes might include 'Length', 'BaseStream', 'view', 'read_bytes'
                                        
                                        if hasattr(found_file, "view"):
                                            # Memoryview
                                            full_blob = bytes(found_file.view)
                                        elif hasattr(found_file, "Length") and hasattr(found_file, "read_bytes"):
                                            # Reader - extract full file
                                            length = found_file.Length
                                            if hasattr(found_file, "Position"): found_file.Position = 0
                                            full_blob = found_file.read_bytes(length)
                                        elif hasattr(found_file, "read"):
                                            # Try reading all?
                                            full_blob = found_file.read()
                                        
                                        # Now slice it!
                                        offset = new_tex.m_StreamData.offset
                                        size = new_tex.m_StreamData.size
                                        print(f"  Internal Resource Size: {len(full_blob)}")
                                        print(f"  Slicing from {offset} to {offset+size}")
                                        
                                        if offset + size <= len(full_blob):
                                            new_data_blob = full_blob[offset : offset + size]
                                        else:
                                            print("  Slice out of bounds! Using full blob as fallback.")
                                            new_data_blob = full_blob
                                            
                                        print(f"  Final Image Data Len: {len(new_data_blob)}")
                                    except Exception as e:
                                        print(f"  Failed to read internal resource: {e}")

                     if len(new_data_blob) == 0:
                         print("  WARNING: New Texture has NO data! (Missing .resS file?)")
                     
                     # Write data
                     data = old_tex.read()
                     data.m_Width = new_tex.m_Width
                     data.m_Height = new_tex.m_Height
                     data.image_data = new_data_blob
                     data.m_CompleteImageSize = new_tex.m_CompleteImageSize
                     
                     # CRITICAL FIX: Clear m_StreamData so Unity uses the blobs we just wrote
                     # instead of looking for the old .resS file
                     if hasattr(data, "m_StreamData") and data.m_StreamData:
                         print("  Clearing old m_StreamData reference")
                         data.m_StreamData.offset = 0
                         data.m_StreamData.size = 0
                         data.m_StreamData.path = ""
                         
                     data.save()
        
        # 2. Material Replacement (NEW)
        elif new_obj.type == ClassIDType.Material:
             if name in old_material_path_ids:
                 target_id = old_material_path_ids[name]
                 if target_id in env_old.assets[0].objects:
                     print(f"Replacing Material: {name}")
                     old_mat = env_old.assets[0].objects[target_id]
                     
                     # Read Old Material to get Shader PPtr
                     old_mat_data = old_mat.read_typetree()
                     
                     # Read New Material as TypeTree
                     new_mat_data = new_obj.read_typetree()
                     
                     # Fix Shader Reference (Vital for Pink Rectangles fix)
                     if 'm_Shader' in old_mat_data:
                         new_mat_data['m_Shader'] = old_mat_data['m_Shader']

                     # Fix Texture References
                     expected_atlas_name = name.replace(" Material", " Atlas")
                     
                     if expected_atlas_name in old_texture_path_ids:
                         target_tex_id = old_texture_path_ids[expected_atlas_name]
                         
                         if 'm_SavedProperties' in new_mat_data:
                             tex_envs = new_mat_data['m_SavedProperties'].get('m_TexEnvs', [])
                             for i, prop in enumerate(tex_envs):
                                 # property "first" / "second" might be dict or tuple
                                 prop_name = None
                                 prop_val = None
                                 
                                 if isinstance(prop, dict):
                                     prop_name = prop.get('first')
                                     prop_val = prop.get('second')
                                 elif isinstance(prop, (list, tuple)) and len(prop) >= 2:
                                     prop_name = prop[0]
                                     prop_val = prop[1]
                                 
                                 if prop_name in ["_MainTex", "_FaceTex", "_OutlineTex"]:
                                     print(f"  Updating texture ref for {prop_name}")
                                     if isinstance(prop_val['m_Texture'], dict):
                                          prop_val['m_Texture']['m_PathID'] = target_tex_id
                                     else:
                                          pass 
                     
                     # Save
                     old_mat.save_typetree(new_mat_data, new_obj.type_tree)

        # 3. Font Asset Replacement
        elif new_obj.type == ClassIDType.MonoBehaviour:
             target_target_id = target_font_assets.get(name, 0)
             if target_target_id != 0 and target_target_id in env_old.assets[0].objects:
                 print(f"Replacing FontAsset: {name}")
                 old_font = env_old.assets[0].objects[target_target_id]
                 
                 # CRITICAL FIX: Ensure we read the NEW data fully 
                 new_data = new_obj.read_typetree()
                 
                 # Debug: Check glyph count
                 # m_GlyphTable is list of Glyph struct
                 # m_CharacterTable is list of TMP_Character struct
                 glyph_count = len(new_data.get('m_GlyphTable', []))
                 char_count = len(new_data.get('m_CharacterTable', []))
                 print(f"  New Data: {glyph_count} Glyphs, {char_count} Characters")
                 
                 # Fix References (Pointer Patching)
                 if old_script_path_id and 'm_Script' in new_data:
                     new_data['m_Script']['m_PathID'] = old_script_path_id
                 
                 expected_atlas_name = name + " Atlas"
                 if expected_atlas_name in old_texture_path_ids and 'm_AtlasTexture' in new_data:
                     new_data['m_AtlasTexture']['m_PathID'] = old_texture_path_ids[expected_atlas_name]
                     
                 expected_mat_name = name + " Material"
                 if expected_mat_name in old_material_path_ids and 'material' in new_data:
                     new_data['material']['m_PathID'] = old_material_path_ids[expected_mat_name]
                 
                 # Force Save: Overwrite OLD object with NEW data structure
                 # UnityPy logic: old_obj.save_typetree(data) writes data to the object's body.
                 # The TypeTree definition comes from the SOURCE bundle (new_obj.type_tree).
                 try:
                    old_font.save_typetree(new_data, new_obj.type_tree)
                    print(f"  Successfully saved {name}")
                 except Exception as e:
                    print(f"  Failed to save font data: {e}")

    print("Saving modified bundle (LZ4 Compressed)...")
    with open(OUTPUT_BUNDLE_PATH + ".decrypted", "wb") as f:
        f.write(env_old.file.save(packer="lz4"))
    
    # Encrypt
    print("Encrypting...")
    with open(OUTPUT_BUNDLE_PATH + ".decrypted", "rb") as f:
        data = bytearray(f.read())
    
    header = data[:128]
    if len(header) < 128:
        print("Warning: Bundle too small")
    
    decrypt_header_inplace(header) 
    final_data = b"\x10\x00\x00\x00" + header + data[128:]
    
    with open(OUTPUT_BUNDLE_PATH, "wb") as f:
        f.write(final_data)
        
    print(f"Done! Saved to {OUTPUT_BUNDLE_PATH}")

if __name__ == "__main__":
    main()
