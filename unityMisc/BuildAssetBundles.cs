using UnityEditor;
using UnityEngine;
using System.IO;

public class BuildFontBundle
{
    [MenuItem("Assets/Build Font AssetBundle (Android)")]
    static void BuildBundle()
    {
        string outputPath = "Assets/AssetBundles";
        if (!Directory.Exists(outputPath))
            Directory.CreateDirectory(outputPath);

        AssetBundleBuild[] builds = new AssetBundleBuild[1];
        builds[0].assetBundleName = "font_replacement"; 
        
        string[] fontGuids = AssetDatabase.FindAssets("t:TMP_FontAsset", new[] { "Assets/Fonts" });
        
        if (fontGuids.Length == 0)
        {
            Debug.LogError("No TMP Font Assets found in Assets/Fonts/. Create them first!");
            return;
        }

        string[] assetPaths = new string[fontGuids.Length];
        for (int i = 0; i < fontGuids.Length; i++)
        {
            assetPaths[i] = AssetDatabase.GUIDToAssetPath(fontGuids[i]);
            Debug.Log($"Including: {assetPaths[i]}");
        }
        builds[0].assetNames = assetPaths;

        BuildPipeline.BuildAssetBundles(
            outputPath,
            builds,
            BuildAssetBundleOptions.None,
            BuildTarget.Android
        );

        Debug.Log($"SUCCESS! Bundle built at: {Path.Combine(outputPath, "font_replacement")}");
    }

    [MenuItem("Assets/Build Font AssetBundle (Windows)")]
    static void BuildBundleWindows()
    {
        string outputPath = "Assets/AssetBundles";
        if (!Directory.Exists(outputPath))
            Directory.CreateDirectory(outputPath);
        AssetBundleBuild[] builds = new AssetBundleBuild[1];
        builds[0].assetBundleName = "font_replacement"; 
        
        string[] fontGuids = AssetDatabase.FindAssets("t:TMP_FontAsset", new[] { "Assets/Fonts" });
        
        if (fontGuids.Length == 0)
        {
            Debug.LogError("No TMP Font Assets found in Assets/Fonts/. Create them first!");
            return;
        }

        string[] assetPaths = new string[fontGuids.Length];
        for (int i = 0; i < fontGuids.Length; i++)
        {
            assetPaths[i] = AssetDatabase.GUIDToAssetPath(fontGuids[i]);
            Debug.Log($"Including: {assetPaths[i]}");
        }
        builds[0].assetNames = assetPaths;

        BuildPipeline.BuildAssetBundles(
            outputPath,
            builds,
            BuildAssetBundleOptions.None,
            BuildTarget.StandaloneWindows64
        );
        Debug.Log($"SUCCESS! Windows Bundle built at: {Path.Combine(outputPath, "font_replacement")}");
    }
}