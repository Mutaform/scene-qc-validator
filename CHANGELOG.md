# Changelog

## 1.19.0

### Added

- **Four collision checks.** A mesh must have a collision mesh, it must be
  named exactly `UCX_<mesh>` or `UCX_<mesh>_NN`, each one must be a closed
  convex hull, and each one must carry the same material as its mesh (with an
  autofix for the material). They live on the mesh, not on the collider: the
  `UCX_*` objects are excluded from validation project-wide, so nobody could
  speak for them - now the mesh finds its own colliders by name and answers
  for them.
  - The name is the only link between a mesh and its collision, so Blender's
    `.001` suffix is a finding, not a cosmetic detail: in the engine that
    object stops being collision and becomes ordinary geometry.
  - Convexity is judged on triangles, the way the engine will see it, and from
    the dihedral angle of each edge rather than every vertex against every
    face. For a closed manifold surface local convexity at all edges is enough
    for the whole, and it costs O(edges) instead of O(faces x vertices) - the
    difference between instant and minutes on a collision somebody made by
    copying the mesh. An open shell is reported separately from a dent, since
    the two are fixed differently. Default tolerance 1 mm, in world units.
  - Settings per check: the collision prefix regex, a regex of meshes that
    need no collision, and the dent tolerance.
  - Clicking such a finding selects the collider itself: `element_ref` now
    understands `obj:<name>`.
- Checked on synthetic cases - a correct pair of colliders, no collision at
  all, a `.001` name, dents of 200 mm, 5 mm and 0.4 mm against a 1 mm
  tolerance, an open shell, a foreign material with its autofix, and a mesh
  excluded by regex - and on the live bed asset, whose single collider passes
  all four. Kept as Dev/verify/t_collision.py.

### Changed

- **ARDENA: the padding measurement is yellow, not red.** It estimates the
  figure the artist typed into the packer, and an estimate should not fail a
  delivery. Enabled at 03_MP_UVs and 05_Textures as INFO.
- **ARDENA: the collision checks are on at 05_Textures** and off earlier -
  there is nothing to collide with at blockout or during unwrapping.
- **The shell-borders row is gone from the breakdown when the stage has no
  such rule** (ARDENA never uses it). A dash with "правила нет" only raised
  the question of what the row meant.

## 1.18.8

### Changed

- **"Границы шеллов" now says what it found.** The check had no module
  docstring at all, its finding said "12 рёбер на границах шеллов завалены
  относительно осей", and the breakdown row read "по осям" - between them an
  artist could not tell what was being measured. The finding now carries the
  worst tilt it found: "границы прямоугольных шеллов завалены: 12 рёбер, до
  2.3° от горизонтали и вертикали (проверено 3 шелла)". The breakdown names
  the tolerance it judges by, and the module got a header explaining the whole
  idea: a shell meant to be straight, off by fractions of a degree, bakes as a
  staircase instead of a line.
- Verified on synthetic shells: straight - clean; tilted 0.5 and 3 degrees -
  caught with the figure; deliberately diagonal at 30 degrees - clean, that is
  past the 5 degree cutoff; a circle tilted 2 degrees - clean, it is not a
  rectilinear shell. Kept as Dev/verify/t_unaligned.py.

## 1.18.7

### Changed

- **The padding hint is one line with the number in it:** "перепаковать канал
  с отступом из нормы - 16 для 2048". The bake, the packer's Margin and the
  Show Padding button are gone from it - an artist knows all three, and in the
  hint they read as a pile of words.

## 1.18.6

### Changed

- **The padding finding no longer promises a click.** It ended with "нажмите -
  покажу худшие в UV": the text itself is not a button, and "худшие в UV"
  named nothing an artist can picture. The sentence now ends with what the
  number rests on - "замерено по 19 шеллам", declined properly for one, two
  and five. Clicking the finding still points the UV editor at those shells;
  it just no longer advertises itself in a place where there is nothing to
  press.
- **A breakdown row no longer claims a verdict nobody reached.** When a check
  is not part of the stage the row went grey and its norm column said "правила
  нет" - but the value column still read "по осям", "нет", "внутри". "Границы
  шеллов | по осям | правила нет" reads as "we looked and it is fine"; nobody
  looked. Such rows now show a dash. Affected: topology, degenerate geometry,
  shells inside 0-1, overlaps and shell borders.
- **Three "by hand" hints lost the part that explains the checker rather than
  the work.** Packing density no longer explains that coverage is what gets
  measured, the transform hint no longer talks about length and area
  thresholds shifting by 100 and 10 000 times, and the overlap hint no longer
  argues why there is deliberately no autofix - the word "руками" beside it
  already says there is none. Those explanations live in the modules' own
  headers, where the next person to touch the code will find them.

## 1.18.5

### Changed

- **Clicking a UV finding now points the UV editor at it.** The channel was
  already switched - an overlap on UV3 put UV3 into the editor - but the whole
  mesh stayed selected, so the editor showed the entire layout and finding the
  two overlapping islands in it was again work for the eyes, which is the work
  the check was supposed to take away. A click now leaves only the faces the
  finding names selected, selects them in the UV editor and frames the view on
  them. For an overlap that means the overlapping islands alone, filling the
  editor; the same goes for padding, UDIM and shells outside 0-1.
- Narrowing happens inside the open edit session: the overlap review keeps the
  mesh in Edit Mode, and leaving it the way `_select_elements` does would tear
  that session down.

## 1.18.4

### Fixed

- **A fix started from the report page left the artist out of Edit Mode.** The
  page has to leave edit for the duration: several fixes are Blender operators
  and they refuse to run under edit - `bpy.ops.object.transform_apply` fails
  its `poll()` (measured on a synthetic mesh: scale 2 becomes 1 in Object Mode,
  poll failure in Edit Mode). Leaving was already there; coming back was not,
  so pressing a button in the browser silently kicked the artist out of their
  edit session. Fixes now run inside one `_object_mode` guard that leaves edit
  once for the whole action and restores it afterwards, including which object
  was active - the same thing the panel's Fix button has always done.
- **A fix that threw was reported as "nothing to fix".** Those are different
  things, and the artist at the browser could only tell them apart by reading
  Blender's console. `_fix_one_check` and `_fix_auto` now hand the failures
  back, and the page says "не получилось: ..." with the reason.

## 1.18.3

### Fixed

- **UV and vertex colour were unreadable while the mesh was in Edit Mode** -
  which is exactly where an artist sits when working on a UV layout. Blender
  reports attribute arrays as empty for a mesh under edit: measured on Blender
  5.2 on a live asset, `len(uv_layers["UV1"].data)` is 0 against 44 908 loops,
  and stays 0 after `update_from_editmode()` returns True; colour attributes
  behave the same way, while the geometry arrays read fine. So the emptiness
  does not look like a refusal - it looks like a mesh with no UVs. On the shelf
  in Edit Mode that cost one finding out of five: `uv_single_tile` reported
  "the channel cannot be read" on a perfectly good layout, while the padding
  and packing-density measurements switched themselves off without a word.
  Every attribute read now goes through one shared reader
  (`checks/common._read_bmesh`) that takes the values from the edit BMesh.
  Verified on a real asset: the same six findings and the same breakdown rows
  in both modes, padding 32.7 px and density 68.8% either way.

## 1.18.2

### Fixed

- **Stacked shells were being measured as the padding.** Stacking is a
  legitimate trick on the texture channel - repeated pieces are laid on top of
  each other so the masks come out finer - and the distance between two such
  shells is not a gap at all. Measured on a real shelf: of its 121 shells, 108
  had their nearest neighbour sitting on top of them, and the padding came out
  as 1.8 px against a real 33. Dropping only the exact zeroes did not help -
  the outlines of two stacked shells run a pixel or two apart, and that
  difference stood in for the padding. Islands whose bounding boxes overlap are
  not neighbours and are left out.

### Added

- Clicking the padding finding **shows the shells it is complaining about** in
  the UV editor - the twenty furthest from the norm, rather than all hundred
  and something, because selecting everything says as little as selecting
  nothing.


## 1.18.1

### Fixed

- **Padding is the whole distance from one shell to the next**, and is reported
  as such. It was being halved, on the theory that a packer inflates each shell
  by the margin so two neighbours end up two margins apart. A cube packed with
  UVPackmaster at Margin 16 and a 2048 map settled it: 16.0 px between
  neighbouring islands, 8 to the tile border. The margin is the gap, and the
  halving was wrong for it.

- **Touching islands no longer drag the figure to zero.** A packer treats
  pieces lying flush against each other as one island; Blender, going by
  topology, counts them as two, and such a pair measures nothing at all. On
  that same cube four islands out of six had a neighbour at zero distance, so
  the median came out zero against a real padding of 16. Anything closer than a
  pixel is a join rather than a gap, and is left out of the figure.

  Measured after the fix: the cube reads 16 px. Meshes laid out to 4, 16 and 40
  came back as 4.0, 16.0 and 40.0, with 4 and 40 failing the 8-16 range.


## 1.18.0

### Changed

- **The measuring checks pick their UV set by number, not by name.** They were
  matched with a regex against `^UV1$`, so a mesh whose channel was still
  called `UVMap` after import got measured by nothing at all - and said so
  nowhere. What a channel is called is the naming check's business; a
  measurement should measure whatever is there. The six of them - both padding
  checks, packing density and the three UDIM ones - now take a channel number,
  1 being the first, and the setting reads "UV Set (1 = first)".

### Fixed

- **A row that could not be measured showed a green tick.** The breakdown takes
  a row's state from "the check is on and found nothing", and a check that
  cannot measure finds nothing either - so "не измерен" came with a tick beside
  it, which reads as "looked at, all good". Such a row is grey now and says why
  it could not be measured: no channel of that number, or no neighbouring
  shells to compare.


## 1.17.1

### Changed

- **Padding Between Shells estimates the number the artist typed into the
  packer**, instead of hunting the exact worst case. A shell with an awkward
  shape can pinch closer to its neighbour than the packer was told to, and that
  is the shape's doing, not a fault in the layout - but the global minimum
  reports exactly that pinch and so lies about the setting we are after. Each
  shell's distance to its nearest neighbour is taken, and the median of those
  is the answer: it survives a pinched shell and a stray one alike.

  It reports the padding, not the gap. A packer inflates every shell by the
  margin, so two neighbours end up a margin apart on each side. Measured on the
  real asset packed to 16 px at 2048: 15.99 px to the tile border, 32.9 px
  between shells - exactly double. Half the gap is the number the artist typed.

  The result is rounded to whole pixels, because it is an estimate. Outline
  points sit slightly further apart than the outlines themselves, which on that
  asset read 16.45 instead of 16 - against a hard bound a correctly packed
  asset would have failed by half a pixel.

  Bounding boxes were tried first and thrown away: measured on the same asset,
  a tightly packed layout has shells whose boxes overlap all over, and every
  gap came out as zero.

  0.29 s over 11 930 faces, of which about half is the island walk the other UV
  checks already do.


## 1.17.0

### Added

- **Padding Between Shells** measures the padding instead of reminding you of
  it. The breakdown used to print a row reading "16 px at 2048" that was not a
  measurement at all - it printed two numbers out of the check's own settings,
  and touched no UV set. The old `Padding` check could not fail either: it
  returns an empty list by design, being the Show Padding preview rather than a
  check, so its FAIL severity in ARDENA meant nothing.

  What is measured now: the smallest gap between the borders of two different
  shells, in pixels of the target map. That is what padding is - the bake
  bleeds across it, and one narrow spot is enough for one shell's texture to
  run onto its neighbour, so the minimum is the number that matters. The upper
  bound matters too: a minimum above the limit means nothing is tight anywhere,
  which is space spent on emptiness. ARDENA accepts 8 to 16 px at 2048 and
  fails anything else.

  Shells in different UDIM tiles are not compared - they are different
  textures, and the gap between them means nothing. The tile border counts as a
  neighbour, because whatever runs off the edge is painted by nobody.

  Measured on the real asset: UV1 on `S_TAR_DK_Estate_GuestRoom_Bed_01` comes
  out at 15.99 px, packed right up to the project's 16, in 0.34 s over 11 930
  faces. UV3 measures 0.00 - which is correct and is why the check is aimed at
  UV1 alone: ARDENA lays UV3 out past the square on purpose.

  Settings: UV set regex, texture size, the two bounds, and whether the tile
  border counts.


## 1.16.1

### Fixed

- The vertex colour view is flat now - no lighting, no specular, no cavity. A
  mask is a fill, not a surface: a highlight across it and you can no longer
  tell 0.3 from 0.35. The viewport keeps whatever it had and gets it all back
  on the second press, lighting mode included.

  Scene colour management is deliberately left alone. Filmic and AgX looked
  like the obvious culprit, but solid-mode vertex colour does not go through
  them: measured on a real scene set to Filmic, the pixels on screen came out
  byte for byte the same as with Standard, and both times they were exactly the
  channel value - 0.2 gave 51, 0.5 gave 128, 0.6 gave 153 out of 255. There was
  nothing to fix there, so nothing is touched.


## 1.16.0

### Added

- **A "Посмотреть" button next to the Vertex Color row** in the report, and the
  same thing in the header menu. It puts the viewport into solid shading with
  the colour attribute showing, so the mask is on screen; pressing it again
  puts the viewport back exactly as it was, shading mode and all. The numbers
  in the breakdown say the layers exist and that they follow the rules. They
  cannot say the layer was given to the part that needed it - that is only
  visible by looking.

  A row in the breakdown can now carry a button, so other rows can get one
  where looking beats reading.


## 1.15.0

### Added

- **Vertex Color Missing** and **Vertex Color IDs** - the layer mask ARDENA's
  Medium Poly pipeline is built on. The rules come from the project document
  ("General Medium Poly Pipeline", section 8): the mesh is filled pure black,
  the id goes in the **Red channel only**, in steps of 0.1 - 0.1 is layer 1 and
  on to 1.0, layer 10. Black is not a layer, it is the background. Not all ten
  need to be on one asset, but one is not a mask: a single value separates
  nothing, so at least two layers are expected.

  The same rules are already checked by the UE toolset (`FBX.VID.STEP`,
  `FBX.VID.GB_NONZERO`, `FBX.VID.LIMIT`) and the thresholds are taken from
  there rather than invented again - 0.008 of tolerance on the step, "zero" in
  Green and Blue meaning below 0.01, ten ids to an asset. The two must not
  drift: the same asset cannot pass in Blender and be rejected in Unreal.

  Split in two because the conversations differ: a mesh with no vertex colour
  at all needs it authored, a mesh that has one needs it corrected. Both carry
  their settings - attribute name, step tolerance, how few layers are too few,
  how many are too many, and whether Green and Blue must be zero.

  A value above 1.0 is reported separately. It is a clean multiple of 0.1, so
  the step test passes it, and only the count would have caught it - and only
  by accident.

- The breakdown's **Vertex Color** row now lists the ids actually found
  ("Color: ID 0.1, 0.3, 0.5") instead of the attribute name, and says plainly
  when the mesh is filled black with no layers at all.

### Fixed

- A byte colour attribute would have failed every value. Blender stores
  `BYTE_COLOR` as eight-bit sRGB and hands it back through `.color` converted
  to linear, so an authored 0.1 arrives as 0.01 and nothing is a multiple of
  the step. Byte attributes are read through `color_srgb`, which is the number
  the artist typed.


## 1.14.0

### Added

- **UV Packing Density** - what share of the texture a UV set actually occupies,
  reported as a percentage. It measures *covered* area, not the sum of island
  areas: shells stacked on purpose share one patch of texture, and summing
  would bill them twice for an economy the artist made deliberately. Coverage
  comes from rasterising each used tile on a 512x512 grid, which costs half a
  second on an 11 500-face asset; a touched texel counts as spent, because that
  is what it is. ARDENA reports it without failing on it for now - the project
  has not declared a number, and the first real asset measured 53.1%
  (1001: 64.9%, 1002: 41.4%). The per-object breakdown shows the figure
  whatever the severity.

### Changed

- **ARDENA now requires transforms to be applied.** The check and its fix have
  been there all along; the project had them switched off because a 90° turn
  and a scale of 0.01 are the signature of an FBX imported from Maya. The
  asset still has to reach the engine clean, so the rule is on.

### Fixed

- **A threshold in local units let applying a transform change the verdict**
  without the geometry changing at all. Zero-length and zero-area read the mesh
  data, so on an asset with an unapplied scale of 0.01 a local unit is a
  centimetre: the 0.1 mm threshold really meant one micron, and applying the
  transform made the same test a hundred and ten thousand times stricter. That
  is not a hypothetical - the smallest edge on the first real asset cleared the
  threshold by a factor of 1.9 after applying. Both thresholds are now measured
  in world units, which makes the verdict the same before and after, and the
  switch is a setting on each check. Measured on an edge of 5e-5 m at scale
  0.01: in local units the verdict went from clean to two findings on applying,
  in world units it stayed at two either way.
- Object matrices are refreshed once before a validation run. A fix that
  changes an object's scale leaves `matrix_world` for the dependency graph to
  recompute, and a world-unit threshold reading it would have judged by the old
  scale.


## 1.13.0

### Added

- **Four checks that tell a UDIM layout from shells shoved aside.** A channel
  allowed to use UDIMs leaves the 0-1 square legitimately, so "outside 0-1 is
  wrong" stops working for it - and moving overlapping shells to the right is
  the quickest way to make an overlap disappear from a report. From the outside
  the two look the same, so the checks read the *layout*, not the position.
  ARDENA allows UDIMs on UV1, which is why `Shells Outside 0-1 Square` now
  judges UV2 alone there.

  There are four of them rather than one because what can be proved and what
  can only be suspected must not share a severity:

  - **UDIM: Shell Inside Tile** - an island must lie inside one tile and inside
    the UDIM grid. An island on a tile border is cut between two textures, and
    tiles at negative U or V do not exist. Provable, no false positives.
  - **UDIM: Tile Set** - tiles start at 1001, run without gaps, and stay within
    the limit (0 = any, which is what ARDENA uses). Artists pack tiles in
    order; a hole in the numbering means something was flung aside.
  - **UDIM: Tile Fill** - each tile carries at least this share of its area.
    UDIMs are bought for resolution: a tile holding half a percent is somewhere
    to put shells, not a texture. This is the one guess in the set, and its
    threshold is a dial.
  - **Shell Moved By Whole Tiles** - an island that is a copy of another one,
    moved by whole tiles, is a hidden overlap. All four measurements have to
    agree at once - face count, area and both sides of the bounding box - and
    the offset has to be a whole number of tiles. A tile copied *entirely*,
    every island matching at one offset, is left alone: that is a duplicated
    layout, odd but deliberate. Shoving shows up as part of a tile moving.

  Two signals were deliberately left out. Overlap "after taking UVs modulo 1"
  is not one: in a real UDIM two tiles are two textures, and shells in them may
  sit at the same local spot. Texel density is not one either: a shoved shell
  keeps the density it had, it was only translated.

  The project has no textures in Blender, so the material cannot be asked which
  tiles exist - `image.source == 'TILED'` is the one non-heuristic signal and it
  is unavailable. Everything above is read off the geometry.

- The per-object breakdown gained a **UDIM tiles** row, and the object table
  shows how many tiles the channel uses.


## 1.12.1

### Fixed

- **The update installed itself without the button being pressed.** The offer
  window is opened from a timer, and a timer does not always have a window in
  its context; without one Blender does not show the dialog at all - it runs
  the operator's `execute` instead, which is the branch the button leads to. So
  the add-on downloaded and installed an update nobody had agreed to. It is the
  first rule of the scheme and the one worth having: the tool reports, the
  artist installs. The offer is now skipped when there is no window, and the
  install refuses to start unless the dialog was actually shown and answered.


## 1.12.0

### Added

- **The add-on updates itself from the studio folder on Yandex.Disk.** On every
  Blender start it quietly asks the release folder whether a newer version is
  out; if one is, a window opens in the middle of the screen with the two
  version numbers and what changed, and one button installs it. Nothing is
  installed without that button being pressed. Close the window and a red row
  stays at the top of the panel until the update is in, and the window comes
  back on the next start - an add-on that knows it is out of date must not be
  easy to miss.
- The updater is a module of its own, `mutaform_update/`, meant to be copied
  into the studio's other add-ons: nothing inside it names this one, the
  settings arrive through `setup()`, and operator names carry the add-on's id
  so two Mutaform add-ons can both carry it in one Blender.
- `tools/publish_update.py` cuts a release into the channel: it reads the
  version out of the built archive, hashes the file it actually wrote, and
  checks the two against each other afterwards. A manifest that disagrees with
  the archive beside it advertises an update that cannot install, and keeps
  advertising it.

The scheme is the one ARDENA Tools and QC Bake for Maya already run, and what
it costs to get wrong is written down in `maya-addon-updater.md`: only https,
the archive is checked against the sha256 in the manifest before anything is
installed, a version the updater cannot parse is a refusal rather than a guess,
and `bpy.app.online_access` being off means silence - that setting is the
artist saying no, not an obstacle.


## 1.11.1

### Fixed

- The **А** button in the viewport header always checks ARDENA now, whatever
  project the sidebar has selected. The letter on the button is that project's,
  so it has to mean that project: an artist who switched the panel to the studio
  checklist pressed А and got the wrong project's rules, with nothing saying so.
  The panel is still the general one - the project is picked there as before.


## 1.11.0

The browser report is now the same page as the one ARDENA Tools writes, and
every finding says what is wrong in Russian, with the numbers in it.

### Added

- **Every object carries a breakdown: value, state, and the rule it is judged
  against** - the table ARDENA Tools prints for a mesh, in Blender terms. Twenty
  rows per object: name, transform, pivot, size in cm, animation, triangles,
  faces and vertices, n-gons, hard edges, topology, degenerate geometry,
  modifiers, shape keys, vertex colours, UV sets, shells inside 0-1, overlaps,
  padding, shell borders, materials. Green with a tick means the stage's rule is
  met, yellow means within tolerance but worth a look, red means a finding says
  otherwise, and grey says "правила нет" - the stage does not check it, which is
  not the same as nobody having looked. The state is read from the findings and
  from the stage's enabled checks, and the rule text from the check's own
  parameters, so no threshold is written down twice. Without it a clean object
  was an empty card and the page could not say what had been measured.
- The object table carries those facts as columns - triangles, UV sets,
  materials, pivot, transform - so a set of fifty reads as a table instead of
  fifty cards, and a legend above it says what the colours mean.
- The summary page is built on the same model as `ardena_report.py` in ARDENA
  Tools, because a lead checks assets in both and should not have to learn two
  pages: studio logo and "Показывать всё" in the header, five tiles
  (принято / отклонено / ошибок / замечаний / объектов), one "Что исправить"
  card holding the fix counts and both severity blocks, an object table with a
  ПРИНЯТ / ОТКЛОНЁН verdict, and cards per object with "развернуть все /
  свернуть все". A finding reads the same way in both tools:
  **object** · **rule**: what was measured, `machine_code`, and under it the
  line saying how it gets fixed.
- Findings are fixed in one of four ways, as in ARDENA Tools - **авто**
  (a button does it), **кнопкой** (its own button, the edit is visible),
  **руками** (with a one-line hint of what to do) and **к сведению**. The kind
  comes from the registry but is checked against the finding: a rule whose fix
  is unwired, like Overlapped UV, is shown as "руками" instead of promising a
  button that is not there.
- Every check now reports its measurement as fields (`values`), and the Russian
  sentence is built from them rather than parsed back out of the English one:
  «Канал UV1: 3027 граней за квадратом 0-1, U 0.0078..1.9732, V 0.0078..0.9697»,
  «Канал UV3: 40 островов наложены друг на друга (3632 грани)», «Пивот в
  (0, 0, 1.6256), это 1.6256 от нуля сцены (допуск 0.001)». The English message
  stays, in the per-object card, because runs are compared by it. All 26 checks
  that can report were run against real geometry, broken on purpose, to make
  sure none of them falls back to English.
- `explain.py` is the registry, in the shape of `ardena_codes.py`: a short
  Russian label per check, the fix kind and hint, and the sentence builder - one
  place, so the panel, the report and the documentation name a rule the same.
- Clicking a finding's **object name** selects it in Blender and highlights the
  elements, exactly as clicking the row in the panel does. The name alone is
  the target, not the whole row: the Fix button sits in the same line and a
  row-wide target swallowed clicks meant for it.
- Missing Material has a fix: it creates a material named by the project rule
  (ARDENA: `MI_<имя ассета>`), fills the empty slots with it, and sends faces
  pointing past the slot list back to the first slot.

### Fixed

- **The report no longer collapses to one object.** Clicking a finding selects
  that object alone, and the next button re-validated off the live selection -
  so a 20-object report shrank to one, and "снято находок: 47" was the
  difference between the full list and the wreckage, with nothing actually
  fixed. Some fixes deselect on their own, so Fix All hit this after its first
  pass even without a click. The page now remembers the objects it was built
  from and re-checks those.
- **A finding from a check that crashed no longer invents a measurement.** The
  Russian sentence is built from fields the check reports, and a crash reports
  none - which arrived as zeroes and read as "0 граней с пятью и более
  вершинами" on an object marked ОТКЛОНЁН. A finding with no measurement shows
  the error instead.
- Clicking an Overlapped UV finding worked every other time: assigning the
  active result already runs the selection, and the extra call toggled the
  overlay straight back off.
- A Fix button next to a group of findings fixed every finding of that check,
  not the ones on its own line. One check reports a separate line per distinct
  measurement, so both lines' buttons did the same thing.
- "авто: N" says how many of those fixes change geometry rather than just
  cleaning data. The flag was computed for every check and never shown.
- Seven more Russian sentences disagreed with their numbers ("1 вершина стоят",
  "5 канала при допустимых 1", "1 UV на 1 лупов").
- Grouping no longer mangles a measurement when the object is named "1" or "e":
  the object's name is cut out of the sentence only where the check put it
  there itself.
- The fix kind in the registry is no longer silently upgraded when a check
  turns out to have a button, which could pair the label "авто" with the text
  "автофикса нет намеренно". A start-up check now reports any rule whose
  registry entry and definition disagree, instead of the registry being correct
  only because it was kept by hand.
- **"Исправить автоматически" no longer renames anything.** It ran Fix All,
  which applies every fix a check has, so one click in the browser renamed
  objects and materials - while the page itself called renaming a separate kind
  ("кнопкой: правка заметная, сама собой не делается"). The button now applies
  only the checks the page counts under "авто", and renaming stays on each
  finding's own Fix button.
- A report left open from an earlier Blender says so. The page used to call a
  rejected token "нет связи с Blender", which is wrong twice over: Blender is
  running, and the token is dead because another Blender took the port. It now
  reads the 403 and says "Отчёт от прошлого запуска Blender — запустите
  проверку заново".
- A forwarded report stops knocking. The page polled 127.0.0.1 every 1.5
  seconds forever, on an artist's machine where that port belongs to something
  else entirely. It gives up once the port answers 403, and backs off to 5 and
  then 15 seconds while Blender stays silent.
- Checking a stage again no longer opens a second tab. The open page tells the
  listener it is there and visible, and a page that is already watching picks
  the new version up by itself.
- The listener survives an add-on update. Its state outlives a reload by
  design, so a field added in a new version was missing from the dictionary the
  old one had left behind, and the first check after an update died on it.
  Missing fields are filled in now.
- A finding whose Russian sentence has not been written yet printed its English
  measurement twice. The machine line is shown only when it differs.
- A report written with no listener now names what fixes the "авто" findings
  instead of only counting them.
- Muted findings are declared. They are left out of the counts, as before, but
  the page says how many rules were silenced instead of quietly printing
  ПРИНЯТ.
- Writing the report could not fail silently on anything but a file error; now
  any failure leaves the previous page intact instead of taking the run with it.
- Overlapped UV no longer offers a fix. Shoving the extra islands past the first
  UDIM clears the report and hands the artist an unpacked UV set to redo, which
  is more work than laying it out right. The fix stays in the file for a future
  version that repacks instead of shoving.
- The default validation scope is Selection.


## 1.10.0

### Added

- A **button in the 3D viewport header** (the letter A), next to the studio's
  other tools, opens a menu with one button per stage of the active project:
  for ARDENA that is Blockout, MP_UVs and Textures. A click loads the stage,
  validates the current scope and opens a summary page in the browser, so an
  artist checks an asset without opening the sidebar.
- The summary page carries **Fix buttons that work from the browser**. Blender
  keeps a small listener on 127.0.0.1 - port handed out by the system, one-time
  token baked into the page, actions only from a fixed list, Host header checked
  - so the page can ask it to fix one check or everything fixable. Blender fixes,
  re-validates, rewrites the page and bumps its revision; the open tab picks the
  new version up by itself, keeping the scroll and which cards were open. The
  request thread never touches Blender data: it queues the job for a timer on the
  main thread. No listener, Blender closed or the report forwarded to an artist -
  the page stays readable with the buttons disabled and says why.
- The **summary page** is a single self-contained HTML file - styles inside, no
  external files, readable offline and forwardable to an artist as it is.
  It carries the counts, a "what to fix" list where the same finding across
  many objects is one row with their names, a per-object verdict table and a
  card per object. Written next to the projects, in the add-on's user folder,
  along with the same report as JSON for scripts to read.
- The client project **ARDENA** ships with the add-on, next to Mutaform_Default:
  stages `01_Blockout`, `03_MP_UVs`, `05_Textures`. Its values are generated from
  `make_preset.py` in the ARDENA repository (`tools/blender_validator/`) - edit
  them there and copy the JSON over.
- **Shells Outside 0-1 Square** takes a UV Set Regex, like Overlapped UV already
  did. Which sets must stay inside 0-1 is a project rule: ARDENA lays UV3 out
  beyond the square on purpose while UV1 and UV2 may not leave it. The default
  `.+` keeps judging every set, so existing projects are unaffected.
- The **UV set** field moves the whole open review: every reviewed mesh switches
  its active UV layer, so the UV Editor shows that set at once, and each running
  overlay re-aims at the same layer and rebuilds. It used to reach only Show
  Overlaps, and only when that was scoped to a material, which is why the view
  caught up solely after switching a Show button off and on.
- Show Overlaps and Show Padding fall back to reviewing the active mesh alone
  when "Check All Material Users" is on but the mesh carries no material yet,
  rather than refusing to start. Show Texel Density already behaved that way.
- A project can **ignore objects by name**: collision and proxy meshes break
  almost every rule a render mesh must keep - no UVs, no material, an origin of
  their own - so the project states the pattern once instead of muting the same
  rows on every asset. ARDENA ignores `^(UCX|UBX|USP|UCP)_`; validating its
  whole scene went from 112 issues (104 of them from collisions) to 8. The
  pattern lives in the project file, loads with it and is written back by Save
  Stage / Save Project; the field sits under the stage tabs.
- **Overlapped UV** says what is wrong instead of how much of it there is:
  "40 UV island(s) overlap another on UV set UV3 (3632 face(s))" rather than a
  face count that came out of expanding every hit to its whole island, which
  read like the check had lost its mind.
- The Show Overlaps overlay follows that switch too: it used to cut its drawn
  shapes at the bake square, so on a UV set laid out beyond 0-1 the artist saw
  the report but almost none of what it was about.
- **Overlapped UV** takes an "Only UDIM 1001" switch. It only ever judged
  overlaps touching the first UDIM square, which hides stacking in a project
  whose UV set is laid out beyond 0-1 on purpose - ARDENA's UV3 reported a
  single island inside the square while 40 were stacked across the sheet.
  The switch is on by default, so existing projects keep their behaviour.
- **Material Name** takes a Fix Name Template, so a project can name materials
  after the asset instead of after whatever the material was called. ARDENA's
  `MI_{asset}` renames the material on `S_TAR_DK_Estate_GuestRoom_Bed_01` to
  `MI_TAR_DK_Estate_GuestRoom_Bed_01`; `{object}` is the full object name and
  `{asset}` drops its leading type token. Left empty, the fix keeps deriving
  `m_...` from the material's own name as before. Checks now carry a second
  text slot (`string_param_2`); projects saved before it keep their defaults.
- **UV Set Names** takes an Expected Names list (`UV1,UV2,UV3`) and checks the
  sets against it in order; its fix renames them to match, going through
  placeholder names so that swapping two sets cannot collide into `UV1.001`.
  Left empty it behaves as before - it only rejects Blender's own `UVMap` names
  and its fix falls back to `map1, map2, ...`.

### Fixed

- A project stating its padding outright ("16 px at 2048") loaded with that
  value rescaled, because switching the texture size rescales the padding to
  keep the same relative border - a convenience meant for the artist editing the
  field, not for a preset carrying both numbers. ARDENA's 16 px arrived as 8.
- The UV review buttons (Show Overlaps / Padding / Texel Density) appeared only
  on stages named `LP_UVs`. Any stage whose name ends in `_UVs` now shows them,
  so ARDENA's `03_MP_UVs` is covered.
- The project a scene falls back to is the studio checklist rather than the
  alphabetically first one, so bundling ARDENA does not make it the default.
- Validating a mesh while its Edit Mode is open reported failures it did not
  have: checks read `obj.data`, which an open Edit Mode leaves stale - the UV
  layers of an 11930-face asset reported zero UVs against 46962 loops, so
  Shells Outside 0-1 Square flagged every set it was watching. Each object's
  edit data is now flushed into its mesh before its checks run, Edit Mode
  staying open. The same flush runs before the single-check re-validate a Fix
  triggers.

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
