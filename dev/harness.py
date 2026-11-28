"""Runs BagBoard.lua in Lua 5.1 against a mocked WoW API and writes a SavedVariables-style file."""
import sys
from lupa import lua51

addon_path, out_path = sys.argv[1], sys.argv[2]
lua = lua51.LuaRuntime(unpack_returned_tuples=True)

MOCK = r'''
timers = {}
HOOKS = {}
TooltipDataProcessor = { AddTooltipPostCall = function(t, fn) HOOKS[#HOOKS+1] = fn end }
ItemRefTooltip = {}
C_Timer = { After = function(d, fn) timers[#timers+1] = fn end }
function runTimers(rounds) for _ = 1, rounds do local t = timers; timers = {}; for _, fn in ipairs(t) do fn() end end end
bit = { band = function(a, b) local r, p = 0, 1 while a > 0 and b > 0 do if a % 2 == 1 and b % 2 == 1 then r = r + p end a = math.floor(a/2); b = math.floor(b/2); p = p * 2 end return r end }
time = os.time
local frames = {}
UIParent = {}
GameTooltip = setmetatable({}, { __index = function() return function() end end })
function CreateFrame(kind, name)
  local f = { events = {}, scripts = {} }
  local known = { ADDON_LOADED=1, PLAYER_LOGIN=1, PLAYER_LOGOUT=1, BAG_UPDATE_DELAYED=1, BANKFRAME_OPENED=1, BANKFRAME_CLOSED=1,
    MERCHANT_SHOW=1, MERCHANT_UPDATE=1, MERCHANT_CLOSED=1,
    QUEST_LOG_UPDATE=1, TRADE_SKILL_SHOW=1, TRADE_SKILL_LIST_UPDATE=1, GET_ITEM_INFO_RECEIVED=1, PLAYER_MONEY=1, PLAYER_LEVEL_UP=1 }
  function f:RegisterEvent(e) if not known[e] then error("Attempt to register unknown event " .. e) end self.events[e] = true end
  function f:SetScript(n, fn) self.scripts[n] = fn end
  setmetatable(f, { __index = function() return function() end end })
  frames[#frames+1] = f
  return f
end
function fire(event, ...) for _, f in ipairs(frames) do if f.events[event] and f.scripts.OnEvent then f.scripts.OnEvent(f, event, ...) end end end
function print(...) io.write("[chat] ", table.concat({...}, " "), "\n") end
SlashCmdList = {}
MODHOOKS = {}
function HandleModifiedItemClick(link) end
function hooksecurefunc(name, fn) if name == "HandleModifiedItemClick" then MODHOOKS[#MODHOOKS+1] = fn end end
function MODCLICK(link) MODHOOKS[#MODHOOKS](link) end
-- Merchant: a buyback list that holds at most 12 sold items, and the confirm dialog.
BUYBACK, POPUPS, StaticPopupDialogs = {}, {}, {}
function sell(id, count) BUYBACK[#BUYBACK+1] = { id = id, count = count or 1 }; if #BUYBACK > 12 then table.remove(BUYBACK, 1) end; fire("MERCHANT_UPDATE") end
function GetNumBuybackItems() return #BUYBACK end
function GetBuybackItemLink(i) return BUYBACK[i] and ("|cffffffff|Hitem:" .. BUYBACK[i].id .. "::::|h[Item " .. BUYBACK[i].id .. "]|h|r") end
function GetBuybackItemInfo(i) local b = BUYBACK[i]; if b then return "Item " .. b.id, 0, 10, b.count end end
function BuybackItem(i) print("(mock) bought back item " .. BUYBACK[i].id); table.remove(BUYBACK, i); fire("MERCHANT_UPDATE") end
function StaticPopup_Show(which, a, b, data) local p = { which = which, data = data }; POPUPS[#POPUPS+1] = p; print("(mock) dialog: " .. StaticPopupDialogs[which].text:format(a, b):gsub("\n", " ")); return p end
function answer(accept) local p = table.remove(POPUPS); local d = StaticPopupDialogs[p.which]; if accept == "alt" then d.OnAlt(p, p.data) elseif accept then d.OnAccept(p, p.data) end end
function UnitName() return "Olpheer" end
function GetRealmName() return "Heathbloke" end
function UnitClass() return "Schamane", "SHAMAN", 7 end
function UnitRace() return "Tauren", "Tauren", 6 end
function UnitFactionGroup() return "Horde" end
function UnitLevel() return 26 end
function GetLocale() return "deDE" end
function GetMoney() return 184523 end
function InCombatLockdown() return false end
function ReloadUI() print("RELOAD") end
NUM_BAG_SLOTS = 4

-- id = {name, quality, ilvl, minLevel, type, subType, stack, equipLoc, sell, classID, subclassID, bind, reagent}
ITEMS = {
  [2449] = {"Erdwurzel", 1, 10, 0, "Handwerkswaren", "Kraut", 20, "", 20, 7, 9, 0, true},
  [2453] = {"Wilddornrose", 1, 20, 0, "Handwerkswaren", "Kraut", 20, "", 25, 7, 9, 0, true},
  [3820] = {"Würgetang", 1, 20, 0, "Handwerkswaren", "Kraut", 20, "", 100, 7, 9, 0, true},
  [3356] = {"Königsblut", 1, 24, 0, "Handwerkswaren", "Kraut", 20, "", 30, 7, 9, 0, true},
  [3372] = {"Bleiphiole", 1, 15, 0, "Handwerkswaren", "Sonstiges", 20, "", 10, 7, 11, 0, true},
  [4306] = {"Seidenstoff", 1, 30, 0, "Handwerkswaren", "Stoff", 20, "", 150, 7, 5, 0, true},
  [2589] = {"Leinenstoff", 1, 5, 0, "Handwerkswaren", "Stoff", 20, "", 13, 7, 5, 0, true},
  [5469] = {"Straußenfleisch", 1, 12, 0, "Handwerkswaren", "Fleisch", 10, "", 9, 7, 8, 0, true},
  [6358] = {"Öliger Schwarzmaulfisch", 1, 15, 0, "Handwerkswaren", "Fleisch", 20, "", 4, 7, 8, 0, true},
  [5075] = {"Blutsplitter", 1, 1, 0, "Quest", "Quest", 20, "", 0, 12, 0, 4, false},
  [4865] = {"Ruinierter Balg", 0, 1, 0, "Verschiedenes", "Plunder", 5, "", 5, 15, 0, 0, false},
  [6659] = {"Krummsäbel des Affen", 2, 23, 18, "Waffe", "Einhandschwerter", 1, "INVTYPE_WEAPON", 2311, 2, 7, 2, false},
  [929]  = {"Heiltrank", 1, 22, 12, "Verbrauchbar", "Trank", 5, "", 75, 0, 1, 0, false},
  [5140] = {"Blitzstrahlpulver", 1, 20, 0, "Handwerkswaren", "Sonstiges", 20, "", 6, 7, 11, 0, true},
  [4338] = {"Magiestoff", 1, 40, 0, "Handwerkswaren", "Stoff", 20, "", 250, 7, 5, 0, true},
}
PENDING = { [3820] = 1 }   -- first lookup of this id returns nothing, like an uncached item
C_Item = {
  GetItemInfo = function(id)
    if PENDING[id] then PENDING[id] = nil; return nil end
    local i = ITEMS[id]; if not i then return nil end
    return i[1], "|cffffffff|Hitem:" .. id .. "|h[" .. i[1] .. "]|h|r", i[2], i[3], i[4], i[5], i[6], i[7], i[8], 134000, i[9], i[10], i[11], i[12], 0, nil, i[13]
  end,
  RequestLoadItemDataByID = function() end,
}
BAGS = {
  [0] = { {2449, 14}, {2453, 20}, {2453, 6}, {3820, 9}, false, {5075, 7}, {4865, 3}, {6659, 1}, {929, 4}, false, false, false, false, false, false, false },
  [1] = { {3372, 12}, {4306, 20}, {4306, 3}, {5469, 8}, {6358, 17}, {2589, 20}, false, false, false, false },
  [5] = { {3356, 20}, {3356, 20}, {5140, 11}, {4338, 4}, {2589, 20}, false, false, false },
}
C_Container = {
  GetContainerNumSlots = function(bag) return BAGS[bag] and #BAGS[bag] or 0 end,
  GetContainerItemInfo = function(bag, slot)
    local s = BAGS[bag] and BAGS[bag][slot]; if not s then return nil end
    return { itemID = s[1], stackCount = s[2], isBound = (s[1] == 5075), hyperlink = "|cffffffff|Hitem:" .. s[1] .. "|h[" .. ITEMS[s[1]][1] .. "]|h|r" }
  end,
  GetContainerItemQuestInfo = function(bag, slot)
    local s = BAGS[bag] and BAGS[bag][slot]
    return { isQuestItem = s and s[1] == 5075 or false }
  end,
}
C_Bank = { FetchPurchasedBankTabIDs = function() return { 5 } end }
Enum = { TooltipDataType = { Item = 0 }, BankType = { Character = 0, Account = 2 } }

LOG = { [888] = true, [1489] = true }
DONE = { [870] = true }
C_QuestLog = {
  IsQuestFlaggedCompleted = function(id) return DONE[id] or false end,
  GetLogIndexForQuestID = function(id) return LOG[id] and 3 or nil end,
  GetNumQuestLogEntries = function() return 3 end,
  GetInfo = function(i)
    if i == 1 then return { isHeader = true, title = "Brachland" } end
    if i == 2 then return { questID = 888, title = "Gestohlene Beute", level = 16 } end
    if i == 3 then return { questID = 1489, title = "Hamuul Runentotem", level = 22 } end
  end,
  IsComplete = function(id) return false end,
  GetQuestObjectives = function(id)
    if id == 888 then return { { text = "Blutsplitter: 7/10", type = "item", numFulfilled = 7, numRequired = 10, finished = false } } end
    return {}
  end,
}
function GetNumSkillLines() return 7 end
function GetSkillLineInfo(i)
  local t = { {"Berufe", true}, {"Alchemie", false, 166, 225}, {"Kräuterkunde", false, 142, 150}, {"Sekundäre Fertigkeiten", true},
    {"Kochkunst", false, 170, 225}, {"Angeln", false, 214, 225}, {"Erste Hilfe", false, 139, 150} }
  local s = t[i]; return s[1], s[2], nil, s[3], 0, 0, s[4]
end

QUESTS = {
  [888]  = { name = "Gestohlene Beute", lvl = 16, min = 11, obj = { nil, nil, { {5075, nil, 10} } } },
  [870]  = { name = "Die vergessenen Teiche", lvl = 13, min = 10, obj = { nil, nil, { {2449, nil, 5} } } },
  [2202] = { name = "Uldaman-Reagenzien", lvl = 42, min = 36, obj = { nil, nil, { {3820, nil, 8}, {3356, nil, 12} } } },
  [4449] = { name = "Nur für Allianz", lvl = 30, min = 25, races = 77, obj = { nil, nil, { {4306, nil, 10} } } },
  [7652] = { name = "Spende: Seidenstoff", lvl = 60, min = 26, obj = { nil, nil, { {4306, nil, 60} } }, src = { 2589 } },
}
local qids = {}
for id in pairs(QUESTS) do qids[#qids+1] = id end
table.sort(qids)
LibQuestieDB = {
  Quest = {
    GetAllIds = function() return qids end,
    objectives = function(id) return QUESTS[id] and QUESTS[id].obj end,
    requiredSourceItems = function(id) return QUESTS[id] and QUESTS[id].src end,
    name = function(id) return QUESTS[id] and QUESTS[id].name end,
    questLevel = function(id) return QUESTS[id] and QUESTS[id].lvl end,
    requiredLevel = function(id) return QUESTS[id] and QUESTS[id].min end,
    requiredRaces = function(id) return QUESTS[id] and QUESTS[id].races end,
    requiredClasses = function(id) error("simulated failure inside QuestieDB") end,
  },
  Item = { startQuest = function() return nil end, relatedQuests = function(id) if id == 2449 then return { 870 } end end },
  Enum = { raceMaskById = { [6] = 32 }, classKeys = { SHAMAN = 64 } },
}

RECIPES = {
  [3447] = { name = "Heiltrank", learned = true, diff = 3, out = 929, r = { {2453, 1}, {3372, 1} } },
  [3448] = { name = "Geringer Unsichtbarkeitstrank", learned = true, diff = 2, out = 3823, r = { {3356, 1}, {3372, 1} } },
  [7837] = { name = "Feueröl", learned = true, diff = 1, out = 6371, r = { {6358, 2}, {3372, 1} } },
  [3450] = { name = "Elixier der Seelenstärke", learned = false, diff = 0, out = 3825, r = { {3820, 1}, {3356, 1}, {3372, 1} } },
}
local rids = {}
for id in pairs(RECIPES) do rids[#rids+1] = id end
table.sort(rids)
C_TradeSkillUI = {
  IsTradeSkillLinked = function() return false end,
  GetBaseProfessionInfo = function() return { professionName = "Alchemie", skillLevel = 166, maxSkillLevel = 225 } end,
  GetAllRecipeIDs = function() return rids end,
  GetRecipeInfo = function(id) local r = RECIPES[id]; return { name = r.name, learned = r.learned, relativeDifficulty = r.diff, maxTrivialLevel = ({[3447]=110,[3448]=185,[7837]=205,[3450]=230})[id], icon = 1, sub = {} } end,
  GetRecipeSchematic = function(id)
    local r = RECIPES[id]; local slots = {}
    for _, x in ipairs(r.r) do slots[#slots+1] = { quantityRequired = x[2], reagents = { { itemID = x[1] } } } end
    return { name = r.name, outputItemID = r.out, reagentSlotSchematics = slots }
  end,
}

-- Writes a table the way the WoW client writes SavedVariables.
local function ser(v, ind, buf)
  local t = type(v)
  if t == "table" then
    buf[#buf+1] = "{\n"
    local n = #v
    for i = 1, n do
      buf[#buf+1] = ind; ser(v[i], ind, buf); buf[#buf+1] = ", -- [" .. i .. "]\n"
    end
    local keys = {}
    for k in pairs(v) do if not (type(k) == "number" and k >= 1 and k <= n and k % 1 == 0) then keys[#keys+1] = k end end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    for _, k in ipairs(keys) do
      buf[#buf+1] = ind .. (type(k) == "number" and ("[" .. k .. "]") or string.format("[%q]", k)) .. " = "
      ser(v[k], ind, buf); buf[#buf+1] = ",\n"
    end
    buf[#buf+1] = ind .. "}"
  elseif t == "string" then buf[#buf+1] = string.format("%q", v):gsub("\\\n", "\\n")
  else buf[#buf+1] = tostring(v) end
end
function dump(name) local buf = { "\n" .. name .. " = " }; ser(_G[name], "", buf); buf[#buf+1] = "\n"; return table.concat(buf) end
'''
lua.execute(MOCK)
import os
notes_path = os.path.join(os.path.dirname(os.path.abspath(addon_path)), "Notes.lua")
if os.path.exists(notes_path):
    lua.execute(open(notes_path, encoding="utf-8").read())
else:
    lua.execute('BagBoardNotes = { [4306] = { d = "keep", r = "example remark" }, [4865] = { d = "vendor" }, [929] = { r = "remark only" } }')
src = open(addon_path, encoding="utf-8").read()
lua.execute("local chunk = assert(loadstring(..., 'BagBoard.lua')); chunk('BagBoard', {})", src)
lua.execute('''
fire("ADDON_LOADED", "BagBoard")
fire("PLAYER_LOGIN")
runTimers(10)
fire("BANKFRAME_OPENED"); runTimers(3)
fire("BANKFRAME_CLOSED")
fire("TRADE_SKILL_SHOW"); runTimers(3)
fire("BAG_UPDATE_DELAYED"); runTimers(5)
SlashCmdList["BAGBOARD"]("")
local lines = {}
local tip = GameTooltip
rawset(tip, "AddLine", function(self, text, r, g, b, wrap) lines[#lines+1] = text end)
for _, id in ipairs({ 4306, 4865, 929 }) do HOOKS[1](tip, { id = id }) end
HOOKS[1]({}, { id = 4306 })   -- some other tooltip: must be ignored
print("tooltip lines: " .. table.concat(lines, " || "))
-- Sell guard. Item 4306 is marked Keep for this test, 2589 is not marked.
BagBoardNotes = type(BagBoardNotes) == "table" and BagBoardNotes or {}
BagBoardNotes.chars = BagBoardNotes.chars or {}
local key = "Olpheer - Heathbloke"
BagBoardNotes.chars[key] = BagBoardNotes.chars[key] or {}
BagBoardNotes.chars[key][4306] = { d = "keep" }
BagBoardNotes.chars[key][2589] = nil
local function expect(what, ok) print("sell guard, " .. what .. ": " .. (ok and "ok" or "FAILED")); if not ok then error("sell guard: " .. what) end end
BUYBACK[1] = { id = 4306, count = 3 }       -- sold at an earlier merchant: must be left alone
fire("MERCHANT_SHOW")
expect("old buyback entry untouched", #BUYBACK == 1 and #POPUPS == 0)
sell(2589, 5)
expect("unmarked item stays sold", #BUYBACK == 2 and #POPUPS == 0)
sell(4306, 2)
expect("kept item bought back and asked", #BUYBACK == 2 and #POPUPS == 1)
answer(false)
sell(4306, 2)
expect("asked again after Keep it", #BUYBACK == 2 and #POPUPS == 1)
answer(true)
sell(4306, 2)
expect("sale goes through after Allow", #BUYBACK == 3 and #POPUPS == 0)
for i = 1, 9 do sell(2589, i) end           -- fills the list to 12
sell(2589, 9)                               -- full list: the oldest drops off
expect("full list, unmarked", #BUYBACK == 12 and #POPUPS == 0)
fire("MERCHANT_CLOSED"); fire("MERCHANT_SHOW")
sell(4306, 1)
expect("full list, kept item asked again at the next merchant", #BUYBACK == 11 and #POPUPS == 1)
answer(false)
SlashCmdList["BAGBOARD"]("guard")
sell(4306, 1)
expect("guard off: sale goes through", #BUYBACK == 12 and #POPUPS == 0)
SlashCmdList["BAGBOARD"]("guard")
fire("MERCHANT_CLOSED")
-- Selling from a bag slot, as the addon does after "Sell it". The stack leaves the bag; a buyback does not put it back in this mock.
C_Container.UseContainerItem = function(bag, slot) local s = BAGS[bag][slot]; USED = bag .. "/" .. slot; BAGS[bag][slot] = false; sell(s[1], s[2]) end
-- "Sell it" sells the bought-back stack again by itself; "Sell and unmark" also removes the decision.
fire("MERCHANT_SHOW"); local n = #BUYBACK
sell(4306, 3)
expect("stack of 3 bought back and asked", #BUYBACK == n - 1 and #POPUPS == 1)
USED = nil; answer(true)
expect("Sell it sells the stack of 3 again", USED == "1/3" and #BUYBACK == n and #POPUPS == 0)
fire("MERCHANT_CLOSED"); fire("MERCHANT_SHOW"); n = #BUYBACK
sell(4306, 20)
expect("asked again at the next merchant", #POPUPS == 1)
USED = nil; answer("alt")
expect("Sell and unmark sells and clears the decision", USED == "1/2" and #POPUPS == 0 and BagBoardDB.edits[key][4306].d == "")
fire("MERCHANT_CLOSED"); fire("MERCHANT_SHOW"); n = #BUYBACK
sell(4306, 1)
expect("unmarked item sells without a question", BUYBACK[#BUYBACK].id == 4306 and BUYBACK[#BUYBACK].count == 1 and #POPUPS == 0)
fire("MERCHANT_CLOSED")
BagBoardDB.edits[key][4306] = nil
-- Twink and Auction are guarded too.
BagBoardNotes.chars[key][2589] = { d = "auction" }
fire("MERCHANT_SHOW")
local before = #BUYBACK
sell(2589, 1)
expect("auction item bought back and asked", #BUYBACK == before - 1 and #POPUPS == 1)     -- the list was full: one dropped off, one bought back
answer(false)
fire("MERCHANT_CLOSED")
-- Decisions changed in game: by command with a link, by command for the item under the mouse, by Alt+click menu.
local link = "|cffffffff|Hitem:2589::::|h[Leinenstoff]|h|r"
SlashCmdList["BAGBOARD"]("toss " .. link)
local edits = BagBoardDB.edits[key]
expect("/bb toss [link] stored", edits[2589] and edits[2589].d == "toss" and type(edits[2589].at) == "number")
-- Items marked Toss are sold when a merchant opens; /bb autosell switches that off.
USED = nil; fire("MERCHANT_SHOW")
expect("item changed to Toss in game is sold when the merchant opens", USED == "1/6" and BAGS[1][6] == false and BUYBACK[#BUYBACK].id == 2589 and BUYBACK[#BUYBACK].count == 20 and #POPUPS == 0)
fire("MERCHANT_CLOSED")
BAGS[1][6] = {2589, 20}
SlashCmdList["BAGBOARD"]("autosell")
USED = nil; fire("MERCHANT_SHOW")
expect("autosell off: nothing is sold by itself", USED == nil and BAGS[1][6] ~= false)
sell(2589, 1)
expect("item marked Toss sells by hand without a question", BUYBACK[#BUYBACK].id == 2589 and BUYBACK[#BUYBACK].count == 1 and #POPUPS == 0)
fire("MERCHANT_CLOSED")
SlashCmdList["BAGBOARD"]("autosell")
-- More stacks than one step sells, and one without a sell price, which stays.
local keepBags = BAGS[0]
BAGS[0] = {}
for i = 1, 8 do BAGS[0][i] = {2589, i} end
BAGS[0][9] = {5075, 7}
BagBoardNotes.chars[key][5075] = { d = "toss" }
BAGS[1][6] = false
fire("MERCHANT_SHOW")
local left = 0
for i = 1, 8 do if BAGS[0][i] then left = left + 1 end end
expect("first step sells six stacks", left == 2)
runTimers(1)
left = 0
for i = 1, 8 do if BAGS[0][i] then left = left + 1 end end
expect("second step sells the rest, the one without a price stays", left == 0 and BAGS[0][9] ~= false)
fire("MERCHANT_CLOSED")
BagBoardNotes.chars[key][5075] = nil
BAGS[0] = keepBags; BAGS[1][6] = {2589, 20}
TooltipUtil = { GetDisplayedItem = function() return "Item 4306", "|cffffffff|Hitem:4306::::|h[Item 4306]|h|r" end }
SlashCmdList["BAGBOARD"]("clear")
expect("/bb clear for the item under the mouse", edits[4306] and edits[4306].d == "")
lines = {}
HOOKS[1](tip, { id = 4306 }); HOOKS[1](tip, { id = 2589 })
print("tooltip lines after changes: " .. table.concat(lines, " || "))
expect("tooltips follow the changes", #lines == 1 and lines[1] == "BagBoard: Toss")
MENU = nil
MenuUtil = { CreateContextMenu = function(owner, build)
  MENU = {}
  build(owner, { CreateTitle = function(self, text) end,
    CreateRadio = function(self, text, isSelected, setSelected, data) MENU[#MENU+1] = { text = text, on = isSelected(data), pick = function() setSelected(data) end } end })
end }
function IsAltKeyDown() return true end
MODCLICK(link)
expect("Alt+click opens the menu with Toss selected", MENU and #MENU == 6 and MENU[4].text == "Toss" and MENU[4].on and not MENU[1].on)
MENU[5].pick()
expect("menu sets Twink", edits[2589].d == "twink")
function IsAltKeyDown() return false end
MENU = nil; MODCLICK(link)
expect("no menu without Alt", MENU == nil)
SlashCmdList["BAGBOARD"]("")
-- The helper took them over: at the next login they are dropped.
BagBoardNotes.applied = { [key] = time() }
fire("PLAYER_LOGIN")
expect("taken-over changes dropped at login", next(BagBoardDB.edits[key]) == nil)
BagBoardDB.edits[key][2589] = { d = "toss", at = time() + 100 }     -- for the helper test: one change left in the saved file
fire("PLAYER_LOGOUT")
''')
open(out_path, "w", encoding="utf-8").write(lua.eval('dump("BagBoardDB")'))
print("wrote", out_path)
