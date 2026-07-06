# Scene QC Validator by Mutaform Studio

Scene QC Validator is a Blender Extension for production scene and mesh validation before export.

It provides a checklist-driven review workflow for common production issues such as unapplied transforms, missing materials, mesh topology problems, UV issues, naming rules, pivots, and FBX export readiness.

## Compatibility

- Blender 4.5 or newer
- Packaged for Blender Extensions, including Blender 5.1

## Install

1. Download the release ZIP from GitHub Releases.
2. In Blender, open `Edit > Preferences > Extensions`.
3. Use `Install from Disk`.
4. Select `scene_qc_validator_by_mutaform_studio.zip`.
5. Enable `Scene QC Validator by Mutaform Studio`.

## Usage

Open Blender's 3D Viewport sidebar and use the `Scene QC` panels to configure checks, run validation, inspect results, apply supported fixes, and export with the Mutaform FBX preset.

## Build Release ZIP

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File tools/build_release.ps1
```

The release archive will be written to `dist/scene_qc_validator_by_mutaform_studio.zip`.

## Repository Layout

```text
scene_qc_validator/
  blender_manifest.toml
  __init__.py
  checks/
  operators/
  ui/
  assets/
tools/
  build_release.ps1
```

## License

This project is licensed under GPL-3.0-or-later, matching the Blender Extension manifest.
