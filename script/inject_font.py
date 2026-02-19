import UnityPy
from UnityPy.enums import ClassIDType
import os
import io

ORIGINAL_BUNDLE_PATH = "common.bak"
OUTPUT_BUNDLE_NAME = "common"

import sys
if len(sys.argv) > 1:
    NEW_BUNDLE_PATH = sys.argv[1]
    print(f"Input bundle provided: {NEW_BUNDLE_PATH}")
else:
    NEW_BUNDLE_PATH = "font_replacement"
    print(f"No input provided, using default: {NEW_BUNDLE_PATH}")

OUTPUT_BUNDLE_PATH = OUTPUT_BUNDLE_NAME

def decrypt(header: bytearray):
    assert len(header) == 128
    for i in range(0, 128, 8):
        for j in range(5):
            header[i + j] = ~header[i + j] & 0xFF
    return header

def load_encrypted_bundle(path):
    with open(path, "rb") as f:
        header = f.read(4)
        if header == b"\x10\x00\x00\x00":
            header_data = bytearray(f.read(128))
            decrypt(header_data)
            rest = f.read()
            return io.BytesIO(header_data + rest)
        else:
            f.seek(0)
            return f.read()

def main():
    if not os.path.exists(NEW_BUNDLE_PATH):
        print(f"Error: New bundle not found at {NEW_BUNDLE_PATH}")
        return

    UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.31f1" 
    decrypted_data = load_encrypted_bundle(ORIGINAL_BUNDLE_PATH)
    env_old = UnityPy.load(decrypted_data)
    
    env_new = UnityPy.load(NEW_BUNDLE_PATH)

    new_assets = {}
    for obj in env_new.objects:
        try:
            if obj.type in [ClassIDType.MonoBehaviour, ClassIDType.Texture2D, ClassIDType.Material]:
                data = obj.read()
                name = getattr(data, "name", getattr(data, "m_Name", "Unknown"))
                new_assets[name] = obj
        except:
            pass
    
    old_script_path_id = None
    old_material_path_ids = {}
    old_texture_path_ids = {}
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

    target_font_assets = {}
    for obj in env_old.objects:
        if obj.type == ClassIDType.MonoBehaviour:
            try:
                data = obj.read()
                if hasattr(data, "m_Script") and data.m_Script.path_id == old_script_path_id:
                    name = getattr(data, "name", getattr(data, "m_Name", "Unknown"))
                    target_font_assets[name] = obj.path_id
            except:
                pass

    for name, new_obj in new_assets.items():
        if "RodinNTLG" not in name: continue 
        
        if new_obj.type == ClassIDType.Texture2D:
             if name in old_texture_path_ids:
                 target_id = old_texture_path_ids[name]
                 if target_id in env_old.assets[0].objects:
                     print(f"Replacing Texture: {name}")
                     old_tex = env_old.assets[0].objects[target_id]
                     new_tex = new_obj.read()
                     
                     new_data_blob = new_tex.image_data
                     new_data_len = len(new_data_blob)
                     print(f"  New Image Data Len: {new_data_len}")
                     
                     if new_data_len == 0:
                         if new_tex.m_StreamData and new_tex.m_StreamData.path:
                             spath = new_tex.m_StreamData.path
                             print(f"  Checking StreamData: {spath}")
                             if spath.startswith("archive:/"):
                                 fname = os.path.basename(spath)
                                 found_file = None
                                 if hasattr(env_new.file, "files"):
                                     files = env_new.file.files
                                     if isinstance(files, dict):
                                         found_file = files.get(fname)
                                     else:
                                         pass
                                 
                                 if found_file:
                                    try:
                                        if hasattr(found_file, "view"):
                                            full_blob = bytes(found_file.view)
                                        elif hasattr(found_file, "Length") and hasattr(found_file, "read_bytes"):
                                            length = found_file.Length
                                            if hasattr(found_file, "Position"): found_file.Position = 0
                                            full_blob = found_file.read_bytes(length)
                                        elif hasattr(found_file, "read"):
                                            full_blob = found_file.read()
                                        
                                        offset = new_tex.m_StreamData.offset
                                        size = new_tex.m_StreamData.size
                                        
                                        if offset + size <= len(full_blob):
                                            new_data_blob = full_blob[offset : offset + size]
                                        else:
                                            new_data_blob = full_blob
                                            
                                    except Exception as e:
                                        print(f"  Failed to read internal resource: {e}")

                     if len(new_data_blob) == 0:
                         print("  WARNING: New Texture has NO data! (Missing .resS file?)")
                     
                     data = old_tex.read()
                     data.m_Width = new_tex.m_Width
                     data.m_Height = new_tex.m_Height
                     data.image_data = new_data_blob
                     data.m_CompleteImageSize = new_tex.m_CompleteImageSize
                     
                     if hasattr(data, "m_StreamData") and data.m_StreamData:
                         data.m_StreamData.offset = 0
                         data.m_StreamData.size = 0
                         data.m_StreamData.path = ""
                         
                     data.save()
        
        elif new_obj.type == ClassIDType.Material:
             if name in old_material_path_ids:
                 target_id = old_material_path_ids[name]
                 if target_id in env_old.assets[0].objects:
                     print(f"Replacing Material: {name}")
                     old_mat = env_old.assets[0].objects[target_id]
                     
                     old_mat_data = old_mat.read_typetree()
                     
                     new_mat_data = new_obj.read_typetree()
                     
                     if 'm_Shader' in old_mat_data:
                         new_mat_data['m_Shader'] = old_mat_data['m_Shader']

                     expected_atlas_name = name.replace(" Material", " Atlas")
                     
                     if expected_atlas_name in old_texture_path_ids:
                         target_tex_id = old_texture_path_ids[expected_atlas_name]
                         
                         if 'm_SavedProperties' in new_mat_data:
                             tex_envs = new_mat_data['m_SavedProperties'].get('m_TexEnvs', [])
                             for i, prop in enumerate(tex_envs):
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
                     
                     old_mat.save_typetree(new_mat_data, new_obj.type_tree)

        elif new_obj.type == ClassIDType.MonoBehaviour:
             target_target_id = target_font_assets.get(name, 0)
             if target_target_id != 0 and target_target_id in env_old.assets[0].objects:
                 print(f"Replacing FontAsset: {name}")
                 old_font = env_old.assets[0].objects[target_target_id]
                 
                 new_data = new_obj.read_typetree()
                 
                 glyph_count = len(new_data.get('m_GlyphTable', []))
                 char_count = len(new_data.get('m_CharacterTable', []))
                 print(f"  New Data: {glyph_count} Glyphs, {char_count} Characters")
                 
                 if old_script_path_id and 'm_Script' in new_data:
                     new_data['m_Script']['m_PathID'] = old_script_path_id
                 
                 expected_atlas_name = name + " Atlas"
                 if expected_atlas_name in old_texture_path_ids and 'm_AtlasTexture' in new_data:
                     new_data['m_AtlasTexture']['m_PathID'] = old_texture_path_ids[expected_atlas_name]
                     
                 expected_mat_name = name + " Material"
                 if expected_mat_name in old_material_path_ids and 'material' in new_data:
                     new_data['material']['m_PathID'] = old_material_path_ids[expected_mat_name]
                 
                 try:
                    old_font.save_typetree(new_data, new_obj.type_tree)
                 except Exception as e:
                    print(f"  Failed to save font data: {e}")

    with open(OUTPUT_BUNDLE_PATH + ".decrypted", "wb") as f:
        f.write(env_old.file.save(packer="lz4"))
    
    #Encrypt
    with open(OUTPUT_BUNDLE_PATH + ".decrypted", "rb") as f:
        data = bytearray(f.read())
    
    header = data[:128]
    if len(header) < 128:
        print("Warning: Bundle too small")
    
    decrypt(header) 
    final_data = b"\x10\x00\x00\x00" + header + data[128:]
    
    with open(OUTPUT_BUNDLE_PATH, "wb") as f:
        f.write(final_data)
        

if __name__ == "__main__":
    main()