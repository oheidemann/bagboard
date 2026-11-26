# BagBoard

A World of Warcraft: Forever addon plus a local web page for a second screen. The page shows what a character carries, what each item is used for, and the player's own decision and remark per item.

WoW: Forever is not Retail or Classic Era. It uses interface `16001` and the modern (Mainline 12.1.5-style) addon API. The client here is German (deDE), so item, quest and profession names in the data are German. The page's own labels are English.

## How it fits together

An addon cannot send data out of the game or read files at runtime. Everything goes through files, and the game only writes or reads them at login, `/reload` and logout.

```
game ──(/reload writes)──> <game>/WTF/Account/<account>/SavedVariables/BagBoard.lua
                                         │ read by
                              server/bagboard_server.py  (http://localhost:8787, this computer only)
                                         │ serves
                                  web/board.html ──(PATCH /notes)─> data/bagboard-notes.json
                                                                    + <game>/Interface/AddOns/BagBoard/Notes.lua
game <──(/reload reads Notes.lua)───────────────────────────────────────────┘
```

`<game>` is `/Applications/World of Warcraft/_forever_` by default. The page's Settings dialog changes it and stores the choice in `data/bagboard-config.json` (`gameDir`). `BAGBOARD_WOW_DIR` overrides both. The same dialog can name the addon's data file directly (`savedFile`, must be called `BagBoard.lua`); when empty, the helper reads the newest one under `<game>/WTF/Account/*/SavedVariables/`. The game itself always writes into its own folder, so `savedFile` is only for reading a copy from elsewhere.

## Layout

This project folder is the single source. The game folder only receives a copy of the addon.

| Path | Role |
|---|---|
| `addon/BagBoard/BagBoard.toc` | Addon manifest. Loads `Notes.lua`, `Build.lua`, then `BagBoard.lua`. Adding a file here needs a full game restart. |
| `addon/BagBoard/BagBoard.lua` | Scans bags, worn equipment (`equipped`, item ID to count), bank (only while open), quest log, skills and recipes (only while a profession window is open) into the saved variable `BagBoardDB`. Reads quest uses from Questie's `LibQuestieDB` if installed. Reads auction prices from Auctionator if installed, only through its public functions (`Auctionator.API.v1.GetAuctionPriceByItemLink` / `ByItemID` and `GetAuctionAge...`), into `item.auction` (copper per unit) and `item.auctionAge` (days). Adds the decision and remark to item tooltips. Sell guard (below). Sync button and `/bb` command. |
| `server/bagboard_server.py` | Python 3 standard library only. Endpoints: `/` page, `/mtime`, `/data`, `/notes` (GET; PATCH merges a list of changes to single notes of single characters, nothing replaces the whole file), `/install` (POST), `/settings` (GET, PUT), `/uses` (for item IDs: every profession recipe of the game that uses them, plus `made`: the items those recipes make where other recipes use them, with their recipes; from the recipe list below). Binds to 127.0.0.1 and rejects foreign Host and Origin headers. Also installs the addon: `--install` replaces `<game>/Interface/AddOns/BagBoard` with `addon/BagBoard/*` and regenerates `Notes.lua`; `--uninstall` removes it (`--purge` also removes the game's saved scan data; notes in `data/` always stay); `--write-notes` regenerates `Notes.lua` only. There are no install scripts. |
| `web/board.html` | Single-file page. Contains a parser for the SavedVariables Lua format. Polls the helper every 2 seconds. On opening, shows a dialog that offers to install the addon when the helper reports it missing. Settings dialog for the game folder and the addon's data file. |
| `data/` | Personal data, not in git: `bagboard-notes.json` (decisions `d` and remarks `r` per character and item ID: `{version: 2, chars: {character: {itemID: {d, r}}}, legacy: {...}}`; decisions are `keep` (keep for now, stays visible), `forever` (keep forever, hidden on the page unless "Kept forever" is ticked), `auction`, `toss`, `twink`; a `twink` note also has `t`, the character the item goes to, which the page pre-selects from the other characters' recipes and professions; `legacy` holds notes from before they were per character, which the page hands to every character that carries the item; `bagboard-notes.v1.json` is a copy of the file from before that change), `bagboard-config.json` (locations chosen in Settings), `bagboard-ingame.json` (see "Decisions changed in game") and `recipe-cache.json` (the recipe list, can be deleted and is downloaded again; `wowhead-cache.json` is a leftover of the removed Wowhead lookup). Never overwrite or delete the notes. |
| `Start BagBoard.command` | Double-click launcher: checks for Python 3, then runs `starter.py`. |
| `starter.py` | Updates an installed copy to the newest release, then runs the helper. Does nothing but start the helper in a development copy (a folder with `.git`) or with `BAGBOARD_NO_UPDATE` set. |
| `VERSION` | The program's version, shown in Settings. Set by `dev/release.py`; not the addon's `## Version`. |
| `install.sh`, `README.md` | For other people: the one-line install into `~/BagBoard` and the instructions shown on the GitHub page. |
| `dev/release.py` | Publishes a release (below). |
| `dev/harness.py` | Runs `BagBoard.lua` in Lua 5.1 against a mocked WoW API and writes a SavedVariables-style file. Needs `pip install lupa`. |

`Build.lua` also exists only in the installed addon: the helper writes it at install time with `BagBoardBuild`, a ten-character fingerprint of the addon's files (`addon_build()`). The addon stores it and the manifest's `## Version` with every scan (`addonBuild`, `addonVersion` per character), and `/bb` prints both. The page compares a character's `addonBuild` with the helper's and marks the status "older addon data" when they differ. Raise `## Version` by hand when the addon changes; the build stamp needs no care.

`Notes.lua` exists only in the installed addon. It is generated from the notes and defines `BagBoardNotes = { chars = { [character] = { [itemID] = { d, r } } } }`. The character key is the same one the addon uses in `BagBoardDB.chars`.

## Distribution and self-update

BagBoard is published at `github.com/oheidemann/bagboard` (public) for other people's computers. Only Macs with Python 3.9 or newer are supported; the code must keep running on 3.9, the Python of Apple's command line tools.

- A release is two files attached to a GitHub release marked latest: `BagBoard.zip` (a folder `BagBoard` with `starter.PARTS`: `addon`, `server`, `web`, the starter files, `README.md`, `VERSION`; never `data/`, `dev/` or `CLAUDE.md`) and `version.json` (`{version, file, sha256, notes}`). Both are read from `https://github.com/oheidemann/bagboard/releases/latest/download/`, which needs no login and no API.
- To release: commit everything, then `python3 dev/release.py 1.0.1 "what changed"`. It sets `VERSION`, commits, tags `v1.0.1`, pushes and creates the GitHub release. `--build-only` just writes `dist/`.
- `starter.py` at every start: reads `version.json`; if its version is newer than `VERSION`, downloads the zip, checks the SHA-256, unpacks into `.update/` and swaps the parts one by one, putting the old ones back if a step fails. `data/` is never touched. Any failure (no connection, damaged download) starts the version that is there.
- While running, the helper looks again every six hours (`watch_for_updates()`); for a newer version it replaces itself with the starter (`os.execv`), which updates and starts the helper again without opening a second page. `/mtime` carries `app: {version, updatedFrom, started}`; the page reloads itself when the version changed and shows "BagBoard was updated from X to Y".
- The addon needs nothing extra: the updated helper sees that its `addon/BagBoard` differs from the installed one and replaces it as always.
- For tests: `BAGBOARD_UPDATE_URL` (another base address, also `file://…/`), `BAGBOARD_UPDATE_EVERY` (seconds), `BAGBOARD_PORT`, `BAGBOARD_DIR` and `BAGBOARD_NO_START` for `install.sh`. Tested 26 Nov 2026 with a `file://` release folder and `/usr/bin/python3` 3.9.6.
- Whoever can push a release controls what runs on those computers; the checksum only guards against a broken download.
- Still tied to this setup: the German client (`RECIPE_LOCALE`, professions matched by their German names) and the Mac default game folder.

## Sell guard

Selling an item marked `keep`, `forever`, `twink` or `auction` at a merchant is undone and asked about. An addon cannot stop a sale beforehand without replacing the bag buttons' click code, which taints item use. So `checkSales()` watches the merchant's buyback list (`GetNumBuybackItems`, `GetBuybackItemLink`, `GetBuybackItemInfo`) on `MERCHANT_SHOW`, `MERCHANT_UPDATE` and `BAG_UPDATE_DELAYED`: an entry that is new since the last look and is marked gets `BuybackItem(index)` and a `StaticPopup` with three buttons. "Sell it" lets that item ID be sold until `MERCHANT_CLOSED` and sells the bought-back stack again (`sellAgain()`: `C_Container.UseContainerItem` on the stack of the same size, or the item's only stack; otherwise the player is told to sell it by hand). "Sell and unmark" does the same and clears the decision for good, as a decision changed in game. "Keep it" or Escape leaves it in the bags. What was in the buyback list when the merchant opened is never touched. `/bb guard` switches the guard off and on (`BagBoardDB.noSellGuard`). The notes are those of the last login or `/reload`, with decisions changed in game on top. The mock test covers the logic; in the real client it is unchecked (as of 26 Nov 2026) whether the buyback functions and the two merchant events behave as assumed.

## Decisions changed in game

The one way back from the game to the notes. Alt+click on an item opens a menu with the decisions (`hooksecurefunc("HandleModifiedItemClick")`, a post-hook, and `MenuUtil.CreateContextMenu`); `/bb keep|forever|auction|toss|twink|clear` does the same for a linked item or the one under the mouse. A remark cannot be changed in game, and `twink` set in game has no target character.

- The addon stores `BagBoardDB.edits[character][itemID] = { d = decision or "", at = time() }` and uses it at once for tooltips and the sell guard (`noteFor()`).
- After a `/reload` or logout the helper finds them in the saved file (`take_ingame_edits()`, called from `/mtime` and at start; `parse_saved()` is a small reader for the SavedVariables format), merges them into the notes like a page change and keeps, per character, the time of the newest one in `data/bagboard-ingame.json`. Older or equal times are never applied again, so a later change on the page is not undone.
- `Notes.lua` carries those times as `BagBoardNotes.applied[character]`; at login the addon drops the edits up to that time. The game loads `Notes.lua` before the helper has seen the new saved file, so an edit is dropped one `/reload` later than it was made.
- Unchecked in the real client (as of 26 Nov 2026): whether Alt+click reaches `HandleModifiedItemClick` and whether other bag addons call it.

## Working on it

- Edit files here, never in the game folder. A running helper notices within two seconds that `addon/BagBoard/*` differs from the installed copy (`addon_state()` returns `outdated`; the generated `Notes.lua` and `Build.lua` are ignored) and replaces it by itself (`update_addon()`), also once at start. The page then shows a notice to `/reload`, or to restart the game when the `.toc` or the list of files changed. It never does a first install on its own; the page asks for that. A failed update is retried every minute and shows as a problem on the Settings button. Without a running helper, `python3 server/bagboard_server.py --install` does the same by hand.
- Run the mock test: `python3 dev/harness.py addon/BagBoard/BagBoard.lua /tmp/BagBoard.lua`. It prints chat output and the tooltip lines, and fails loudly on Lua errors. The mock only proves the code runs; it does not prove the real client behaves the same.
- Run the helper: `python3 server/bagboard_server.py` (add `--no-browser` to skip opening the page). After changing it, restart it. After changing `web/board.html`, reload the browser page.
- The real saved file is the best test data for the page. It is rewritten by the game on every `/reload`, so read it, do not edit it.
- To test installing without touching the game, point `BAGBOARD_WOW_DIR` at a scratch folder that contains `Interface/AddOns`.
- In game, `/bb` prints the scan status, the number of notes loaded and the last error.

## Rules that came out of testing

- Wrap every game API call. Functions and events differ from Classic and may be missing; `try()` and `pcall` around `RegisterEvent` are there for that. Registering an unknown event raises an error.
- Never store or compare "secret" values; `plain()` filters them.
- Questie returns quest ID `0` and objective counts of `0` for "none". Filter both.
- Questie's `specialFlags` bit 1 means repeatable, and `zoneOrSort` `-367` is its reputation category. The addon stores both per quest (`repeatable`, `reputation`); the page hides such quests unless "Repeatable and reputation quests" is ticked. On the page quests have their own column: the level of the quest in the log, otherwise of the highest open quest, in the game's difficulty colours for the character's level; a click lists the quests.
- `equipLoc` can be `INVTYPE_NON_EQUIP_IGNORE` on items that are not gear.
- The profession window lists unlearned recipes too (hundreds), all reported as `Optimal`. Only learned recipes have a meaningful difficulty colour.
- Do not scan at `PLAYER_LOGOUT`. On a real logout the client has already dropped the character's data: bags, money, skills and quest progress came back empty and replaced a good scan (seen 21 Nov 2026). `scan()` also refuses to store a result with zero bag slots.
- `GetRealmName()` returned an empty string on this client; the code falls back to `GetNormalizedRealmName()`.
- Chrome refuses to open files under `/Applications` through the File System Access API. That is why the helper exists, and one reason the project lives outside the game folder.
- Other addons in `Interface/AddOns` are a good reference for which API calls exist on Forever. Their code and data are not ours to copy: Mastercraft's licence forbids it explicitly.

## The recipe list (all professions)

The page shows, per item, every profession that uses it, also professions no character has, with the number of recipes and the skill where the last one turns grey. This does not come from the game scan (which only knows the character's own professions) but from the game client's tables, which wago.tools publishes for tools.

- Source: `https://wago.tools/db2/{table}/csv?version=<build>[&locale=deDE]`, product `wowf` (WoW: Forever), newest build from `/api/builds/wowf/latest`. Its `robots.txt` and `/llms.txt` allow exactly these CSV and API routes and forbid crawling the HTML pages; they ask to reuse a download instead of repeating it. No licence or terms page was readable (the site's HTML pages refuse automated requests), so keep the use personal and do not redistribute the cache.
- `build_recipes()` joins `SkillLineAbility` (spell, skill line, `TrivialSkillLineRankLow` = yellow, `TrivialSkillLineRankHigh` = grey), `SpellReagents` (item IDs and counts), `SkillLine` and `SpellName` (both in deDE and enUS), `SpellEffect` (effect `24` is "create item", `EffectItemType` is the item a recipe makes; 2,336 of 2,521 recipes have one) and `ItemSparse` in deDE (names of the made items). Only skill lines of category 11 and 9 count (professions and secondary skills); sub-lines fold into their parent.
- `data/recipe-cache.json`: `{format, version, items: {itemID: [{id, name, en, skill, yellow, grey, qty, makes}]}, made: {itemID: German name}, skills: {skillLineID: German name}, skillsEn}`. `name` is German, `en` English, `makes` the item ID the recipe creates. `made` only names made items that are materials of other recipes. The helper asks for the newest build once a week and downloads the tables again only when the build changed. Raise `RECIPE_FORMAT` after changing the layout.
- On the page each profession that uses one of the character's items is a column of its own (icon header from Wowhead's icon host, `PROF_ICONS`). A cell shows the skill where the last recipe with that item turns grey, coloured by the best skill-up colour at the selected character's skill. If the selected character lacks the profession, the colour is the best any other character gets, struck through (muted when nobody has the profession). An asterisk means another character gets a better colour than the selected one. Clicking it opens a dialog with the recipes of that profession that use the item.
- The filter bar is one row, and the filters that belong to columns sit over those columns (`placeColTools()`, run after every render, on resize, on sideways scrolling and when a column's width changes): "Professions of …" and "Indirect uses" start where the profession columns start, "Kept forever" and the decision filter where the Decision column starts, Bank and Equipped in between, the Quest filter at the right end. The search field shrinks to make room; a group gives way to the right rather than cover its neighbour, and the decision group stops before the Quest filter. Below about 1610 px of window width there is no room for one row and the bar wraps (class `wrapped`).
- The "Professions of …" selector there (`state.profChar`, read through `profKey()`) picks the character whose skills colour the profession columns and the recipe dialog. Its default is the character shown; with another one picked, "selected character" above means that one, while the items stay those of the character shown. The choice is not stored and falls back to the default when it equals the character shown.
- Indirect uses, one step deep (`profsFor()` in `web/board.html`): if a recipe turns the item into something that recipes of a profession use, that profession's cell shows the number lighter with an arrow (`→185`), coloured by those further recipes. A direct use wins; its tooltip mentions the further ones. When a recipe one step on gives a better skill-up colour than the direct recipes, the cell gets an arrow behind the number in that colour (`70→`, `p.chain`), judged for the same character as the cell's own colour; the tooltip names the recipe. In the recipe dialog a recipe's name links to the item it makes, so that hovering shows Wowhead's tooltip of that item (the tooltip script goes by the link's address; `data-wowhead` did not override it), with a small "recipe" link to the recipe itself. Below it the dialog says which professions use the made item ("used by", with "makes X" in front only when the item is named differently from the recipe) (a click steps on to the made item, Back returns), and, only where the step in between belongs to another profession, the recipes one step on follow under a small remark (a step in the dialog's own profession is reached through its chip instead), "Next in the chain · X enables:" (with "made with <profession>" when the step in between belongs to another profession; hovering the remark gives that step's recipe, numbers and who can do it). The "Indirect uses" checkbox in the filter bar switches the cells off; the choice is kept in the browser (`bagboard-indirect`). The recipe dialog has its own "Indirect uses" checkbox (`dialogIndirect`): it is on each time the dialog opens, whatever the board has, stays as set while stepping and going back, and never changes the board.
- The tables do not say at which skill a recipe is learned (`MinSkillLineRank` is 1 everywhere) or where it comes from (trainer, vendor, drop).
- Checked 22 Nov 2026 against the in-game scan and wowforevertalent.com: Alchimie 196, Schneiderei 471, Erste Hilfe 32 match exactly; Kochkunst is 133 here against 132.
- The Wowhead lookup that used to fill this was removed. It never got the page back. If Wowhead is refusing automated requests, respect that. Do not add workarounds for it.

## Potential data sources

Found by web search on 21 Nov 2026. Descriptions are what each site says about itself; none has been checked in depth. None advertises a data feed or API, so read a site's terms or ask its owner before using its data in BagBoard. The same applies to Wowhead.

With recipe skill numbers:

| Site | URL | Notes |
|---|---|---|
| WarcraftMaps | https://warcraftmaps.com/database/recipes | 2,034 Forever recipes from client build 1.60.1.70938 with inputs, yields and skill requirements. Its quest list is Classic data (CMaNGOS Classic-DB). |
| ConquestCapped | https://conquestcapped.com/guides/wow-forever/wow-forever-recipes/ | Required skill, yellow, green and grey points, reagents and pattern source per recipe. Has a German version under `/guides/de/`. |
| Games Lantern | https://wowforever.gameslantern.com/professions | Profession pages with the ranks where a recipe turns yellow, green and grey. |
| wowforevertalent.com | https://wowforevertalent.com/professions/ | Searchable by reagent; materials, output, yellow and grey ranks. Names the client column `TrivialSkillLineRankLow` for yellow. Surveyed 22 Nov 2026: its recipe counts match our in-game scan exactly (Alchemy 196, Tailoring 471, Cooking 132, First Aid 32). Per recipe: spell ID, reagents with quantities (names, no item IDs), created item and count, orange/yellow/green/grey skills; how a recipe is learned is mostly "not recorded". Profession and item pages are English only. No API or download; one page per profession holds the full list. robots.txt allows everything, no terms page, no licence stated for profession data (CC BY 4.0 covers only its talent records). Run by one person, contact support@wowforevertalent.com. It says the profession data comes from the public client tables on wago.tools (`https://wago.tools/db2/SpellReagents/csv?build=1.60.1.70753` and similar), which would be the machine-readable source; wago.tools' terms are unchecked. |
| foreverguide.net | https://foreverguide.net/professions/cooking/ | Leveling guides per profession with green and grey numbers per craft. |

General databases (items, quests, NPCs):

| Site | URL | Notes |
|---|---|---|
| Wowhead (Forever) | https://www.wowhead.com/forever/de/ | Item pages carry a `reagent-for` list with `learnedat` and `colors`. Automated requests from the helper did not get the page. |
| WarcraftDB | https://www.warcrafttavern.com/forever/ | Warcraft Tavern's database, launched with Forever together with its Lexicon Client. |
| Warcraft Wiki | https://warcraft.wiki.gg/wiki/Category:Forever_items | Category of Forever-only items, with recipe list pages per profession. |
| Wowseer | https://wowseer.gg/database | Pages for items, NPCs, quests, spells, recipes, zones and factions; profession planner. |
| ForeverDB | https://www.foreverdb.app/en/forever | Items, quests, NPCs and spells linked to drops, vendors and quest rewards. |
| WoW Forever Friends | https://www.wowforeverfriends.org/library/ | Connects spells to recipes, reagents and created items. |
| wowforever.gg | https://wowforever.gg/en/atlas/knowledge/ | Quests, NPCs, items, recipes and locations tied to maps, five languages. |
| forevermastery.com | https://forevermastery.com/en/items | Item pages built from the Forever client's tables and Classic data; English and French. |
| TheWoWDB | https://thewowdb.com/wow-forever/item/ | Item pages plus per-realm Auction House prices from Blizzard's API. |
| RankedBoost | https://rankedboost.com/world-of-warcraft/forever/items/ | 22,102 items with a new-or-changed marker. |

Several of these sites state that the skill thresholds come from the game files: the client stores, per recipe, the skill where it turns yellow and where it turns grey, and green is usually calculated as the midpoint. Whether the addon API exposes those numbers in game is still unchecked (see `recipes[profession].sample` below).

## Not done yet

- `recipes[profession].sample` in the saved file holds one recipe's plain fields from the game. Check it for `maxTrivialLevel` to see whether the client reports skill thresholds itself.
- Skill numbers are not shown in the in-game tooltip, only decision and remark.
- Profession names for skill lines beyond the twelve classic ones are not mapped (`SKILL_NAMES` in `web/board.html`).
- Wowhead hover tooltips on the page use Wowhead's public tooltip script.
