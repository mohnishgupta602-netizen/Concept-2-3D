import bpy
import sys

# Get output filepath from command line args
# command: blender -b file.blend --python export_glb.py -- output.glb
argv = sys.argv
argv = argv[argv.index("--") + 1:]  # get all args after "--"
out_filepath = argv[0]

# Ensure all objects are selected (optional, default export includes all)
bpy.ops.object.select_all(action='SELECT')

# Export to GLB with all textures baked/included
bpy.ops.export_scene.gltf(
    filepath=out_filepath,
    export_format='GLB',
    use_selection=False,
    export_apply=True,    # Apply modifiers
    export_materials='EXPORT'
)

print(f"Successfully exported {out_filepath}")
