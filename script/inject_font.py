import io
import os
import sys
import UnityPy
from UnityPy.enums import ClassIDType

ORIGINAL_BUNDLE_PATH = "common.bak"
OUTPUT_BUNDLE_PATH = "common"

def decrypt(header: bytearray) -> bytearray:
    assert len(header) == 128
    for i in range(0, 128, 8):
        for j in range(5):
            header[i + j] = ~header[i + j] & 0xFF
    return header

def load_encrypted_bundle(path: str) -> io.BytesIO | bytes:
    with open(path, "rb") as f:
        if f.read(4) == b"\x10\x00\x00\x00":
            return io.BytesIO(decrypt(bytearray(f.read(128))) + f.read())
        f.seek(0)
        return f.read()

def process_texture(name: str, new_obj, old_tex, env_new) -> None:
    new_tex = new_obj.read()
    new_data_blob = new_tex.image_data
    
    if not new_data_blob and new_tex.m_StreamData and new_tex.m_StreamData.path.startswith("archive:/"):
        found_file = getattr(env_new.file, "files", {}).get(os.path.basename(new_tex.m_StreamData.path))
        if found_file:
            try:
                full_blob = bytes(found_file.view) if hasattr(found_file, "view") else (
                    found_file.read_bytes(found_file.Length) if hasattr(found_file, "Length") else found_file.read()
                )
                offset, size = new_tex.m_StreamData.offset, new_tex.m_StreamData.size
                new_data_blob = full_blob[offset:offset+size] if offset + size <= len(full_blob) else full_blob
            except Exception as e:
                print(f"  Failed to read internal resource: {e}")

    data = old_tex.read()
    data.m_Width, data.m_Height = new_tex.m_Width, new_tex.m_Height
    data.image_data, data.m_CompleteImageSize = new_data_blob, new_tex.m_CompleteImageSize
    if hasattr(data, "m_StreamData") and data.m_StreamData:
        data.m_StreamData.offset = data.m_StreamData.size = 0
        data.m_StreamData.path = ""
    data.save()

def process_material(new_obj, old_mat, expected_atlas_name: str, old_texture_path_ids: dict) -> None:
    old_mat_data, new_mat_data = old_mat.read_typetree(), new_obj.read_typetree()
    if 'm_Shader' in old_mat_data:
        new_mat_data['m_Shader'] = old_mat_data['m_Shader']

    if expected_atlas_name in old_texture_path_ids and 'm_SavedProperties' in new_mat_data:
        for prop in new_mat_data['m_SavedProperties'].get('m_TexEnvs', []):
            prop_name, prop_val = (prop.get('first'), prop.get('second')) if isinstance(prop, dict) else (prop[0], prop[1])
            if prop_name in ["_MainTex", "_FaceTex", "_OutlineTex"] and isinstance(prop_val.get('m_Texture'), dict):
                prop_val['m_Texture']['m_PathID'] = old_texture_path_ids[expected_atlas_name]
                
    old_mat.save_typetree(new_mat_data, new_obj.type_tree)

def process_font_asset(name: str, new_obj, old_font, old_script_path_id, old_texture_path_ids, old_material_path_ids) -> None:
    new_data = new_obj.read_typetree()
    if old_script_path_id and 'm_Script' in new_data:
        new_data['m_Script']['m_PathID'] = old_script_path_id
        
    if (atlas := f"{name} Atlas") in old_texture_path_ids and 'm_AtlasTexture' in new_data:
        new_data['m_AtlasTexture']['m_PathID'] = old_texture_path_ids[atlas]
        
    if (mat := f"{name} Material") in old_material_path_ids and 'material' in new_data:
        new_data['material']['m_PathID'] = old_material_path_ids[mat]
        
    old_font.save_typetree(new_data, new_obj.type_tree)

def main():
    new_bundle_path = sys.argv[1] if len(sys.argv) > 1 else "font_replacement"
    if not os.path.exists(new_bundle_path):
        return print(f"Error: New bundle not found at {new_bundle_path}")

    UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.62f2"
    env_old, env_new = UnityPy.load(load_encrypted_bundle(ORIGINAL_BUNDLE_PATH)), UnityPy.load(new_bundle_path)

    new_assets = {
        getattr(data := obj.read(), "name", getattr(data, "m_Name", "Unknown")): obj
        for obj in env_new.objects if obj.type in (ClassIDType.MonoBehaviour, ClassIDType.Texture2D, ClassIDType.Material)
    }

    old_script_path_id = next((obj.path_id for obj in env_old.objects if obj.type == ClassIDType.MonoScript and getattr(obj.read(), "m_ClassName", "") == "TMP_FontAsset"), None)
    old_material_path_ids = {getattr(data := obj.read(), "name", getattr(data, "m_Name", "Unknown")): obj.path_id for obj in env_old.objects if obj.type == ClassIDType.Material}
    old_texture_path_ids = {getattr(data := obj.read(), "name", getattr(data, "m_Name", "Unknown")): obj.path_id for obj in env_old.objects if obj.type == ClassIDType.Texture2D}
    
    target_font_assets = {
        getattr(data := obj.read(), "name", getattr(data, "m_Name", "Unknown")): obj.path_id
        for obj in env_old.objects if obj.type == ClassIDType.MonoBehaviour and getattr(data, "m_Script", None) and data.m_Script.path_id == old_script_path_id
    }

    for name, new_obj in new_assets.items():
        if "RodinNTLG" not in name: continue
        
        if new_obj.type == ClassIDType.Texture2D and name in old_texture_path_ids and old_texture_path_ids[name] in env_old.assets[0].objects:
            print(f"Replacing Texture: {name}")
            process_texture(name, new_obj, env_old.assets[0].objects[old_texture_path_ids[name]], env_new)
            
        elif new_obj.type == ClassIDType.Material and name in old_material_path_ids and old_material_path_ids[name] in env_old.assets[0].objects:
            print(f"Replacing Material: {name}")
            process_material(new_obj, env_old.assets[0].objects[old_material_path_ids[name]], name.replace(" Material", " Atlas"), old_texture_path_ids)

        elif new_obj.type == ClassIDType.MonoBehaviour and (target_id := target_font_assets.get(name, 0)) in env_old.assets[0].objects:
            print(f"Replacing FontAsset: {name}")
            process_font_asset(name, new_obj, env_old.assets[0].objects[target_id], old_script_path_id, old_texture_path_ids, old_material_path_ids)

    decrypted_path = f"{OUTPUT_BUNDLE_PATH}.decrypted"
    with open(decrypted_path, "wb") as f:
        f.write(env_old.file.save(packer="lz4"))
        
    with open(decrypted_path, "rb") as f:
        data = bytearray(f.read())
        
    with open(OUTPUT_BUNDLE_PATH, "wb") as f:
        f.write(b"\x10\x00\x00\x00" + decrypt(data[:128]) + data[128:])

if __name__ == "__main__":
    main()