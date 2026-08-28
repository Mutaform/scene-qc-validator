# Changelog

## 1.9.2

Every UV review is now scoped to one material, because one material is one
texture set. Covers the changes since 1.8.7.

### Added

- Review Scene: clicking a material name selects every object in the scene that
  uses it and makes it their active material slot.
- Review Scene: the UV button next to a material isolates its faces in Edit
  Mode, so the UV Editor holds that material's UVs alone. Clicking it again
  restores the selection, mode, UV sync setting and edit-mode selection that
  were there before.
- The material list keeps describing the objects that were in scope when a
  review started, so an artist can hop from material to material without a
  'Selection' scope collapsing onto the one under review.
- Show Overlaps, Show Padding and Show Texel Density follow the active material
  slot: picking another slot in the Properties editor (or another material in
  the Review Scene list) re-aims the running review at it, without leaving Edit
  Mode when the same meshes carry that material.
- A line under the three overlay toggles names the material being reviewed, and
  the operator reports name it too.
- The bundled Mutaform_Default project ships the studio checklist for all five
  stages, instead of a stale copy that was missing four checks entirely.

### Fixed

- Overlaps between two materials on one mesh are no longer reported or drawn as
  overlapping: a second material is a second texture set, free to sit anywhere
  in UV space.
- The padding band follows the reviewed material's footprint. The edge where its
  faces meet another material's counts as an island border, and other
  materials' islands are no longer wrapped in a band of their own.
- Texel density is measured against the average of the reviewed material's faces
  only, so a second material at another scale no longer shifts every colour.
- The UV Editor no longer shows every material's UVs during a review, which is
  what made a multi-material mesh unreadable there.
- Reviews opened from a validation result still cover the whole mesh, matching
  what the checker reported.
- `tools/build_release.ps1` produced an archive with "\" path separators and no
  top-level folder, which only Windows could unpack. It now writes a normal
  `scene_qc_validator/` archive plus a version-stamped copy beside it.

## 1.1.1

- Fixed repeated UV checker restore on objects that originally had no materials.
- Rebuilt the line checker texture as a 1024x1024 asset.
- Added the add-on version label to the main panel header.

## 1.1.0

- Packaged as a Blender Extension.
- Added scene and mesh validation checklist workflow.
- Added preset import/export support.
- Added UV checker assets and controls.
- Added FBX export workflow with Mutaform preset.
