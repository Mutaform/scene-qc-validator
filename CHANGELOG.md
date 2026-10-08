# Changelog

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
