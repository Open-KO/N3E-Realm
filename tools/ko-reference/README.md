# KO client-version importers

Importers for later Knight Online client releases (1097 installers, 2145/2233 packs
and tables) that the asset cooker uses for specific zones and item visuals. The
inputs are the player's own installer executables, never committed: place them under
`ref/ko-bin/installer/` (git-ignored) and run
`python3 -I tools/ko-reference/unpack_installer.py <installer.exe>`; outputs land in
ignored `build/ko-reference/`. Tests that need an install SKIP without it.

The Moradon realm package (`make realm-assets`) needs **none** of this — only the
pinned client asset tree from `tools/fetch-ko-assets.sh`. Whether other zones that do
need an install become realm content is `specs/QUESTIONS.md` Q27.

`inspect_db.py` restores the operator's own KO SQL Server backup into a disposable,
offline container and exports allow-listed definition tables (`--table K_MONSTER`,
`START_POSITION`, `MAGIC_TYPE2`, …) as JSON under ignored `build/`; the KO zone,
NPC and glow cooks read those exports and SKIP without them. Account, user and
credential tables are never exported.
