-- BagBoard: collects what you carry and what it is used for, for the BagBoard page.
-- An addon cannot send data out of the game. Everything here lands in
-- WTF/Account/<ACCOUNT>/SavedVariables/BagBoard.lua when you /reload or log out.

local ADDON = ...

local MAX_QUESTS_PER_ITEM = 15
local INDEX_BATCH = 120          -- quests read per frame while the quest index builds

local frame = CreateFrame("Frame")
local DB, C                      -- saved table, this character's table
local charKey                    -- this character's key in DB.chars and in BagBoardNotes.chars

-- BagBoardNotes comes from Notes.lua: { chars = { [character] = { [itemID] = { d = decision, r = remark } } } }.
-- Decisions and remarks are per character. Returns this character's notes, or nil.
local function myNotes()
  local all = _G.BagBoardNotes
  local chars = type(all) == "table" and all.chars
  local mine = type(chars) == "table" and charKey and chars[charKey]
  return type(mine) == "table" and mine or nil
end
-- Decisions changed in game: BagBoardDB.edits[character][itemID] = { d = decision or "", at = time }. They count
-- at once in game. The helper reads them from the saved file after the next /reload or logout, puts them into
-- the notes and names the newest one it took over in Notes.lua (applied); those are dropped at the next login.
local function myEdits(create)
  if not (DB and charKey) then return nil end
  if type(DB.edits) ~= "table" then
    if not create then return nil end
    DB.edits = {}
  end
  if type(DB.edits[charKey]) ~= "table" then
    if not create then return nil end
    DB.edits[charKey] = {}
  end
  return DB.edits[charKey]
end
-- The note of an item as it counts now: the one from the page, with a decision changed in game on top.
local function noteFor(itemID)
  local notes = myNotes()
  local note = notes and notes[itemID]
  if type(note) ~= "table" then note = nil end
  local edits = myEdits()
  local edit = edits and edits[itemID]
  if type(edit) ~= "table" then return note end
  local d = edit.d ~= "" and edit.d or nil
  return { d = d, r = note and note.r, t = d == "twink" and note and note.d == "twink" and note.t or nil }
end
local bankOpen = false
local scanQueued = false
local questIndex = {}            -- itemID -> { {q = questID, need = n, role = "objective"|"source"}, ... }
local indexState = "none"        -- none | building | ready | missing
local playerRaceMask, playerClassMask

local function out(msg)
  print("|cff66ccffBagBoard|r: " .. tostring(msg))
end

-- Call a game function that may be missing or may fail on this client.
local function try(fn, ...)
  if type(fn) ~= "function" then return nil end
  local ok, a, b, c, d, e, f2, g, h, i, j, k, l, m, n, o, p, q = pcall(fn, ...)
  if ok then return a, b, c, d, e, f2, g, h, i, j, k, l, m, n, o, p, q end
  return nil
end

local function plain(v)
  -- Midnight-style "secret" values must not be stored or compared.
  if issecretvalue and issecretvalue(v) then return nil end
  return v
end

---------------------------------------------------------------------------
-- Containers
---------------------------------------------------------------------------

local function bagIDs()
  local ids = {}
  for bag = 0, (NUM_TOTAL_EQUIPPED_BAG_SLOTS or NUM_BAG_SLOTS or 4) do ids[#ids + 1] = bag end
  return ids
end

local function bankIDs()
  local ids = {}
  local bankType = Enum and Enum.BankType and Enum.BankType.Character
  if bankType ~= nil and C_Bank then
    local tabs = try(C_Bank.FetchPurchasedBankTabIDs, bankType)
    if type(tabs) == "table" then
      for _, id in ipairs(tabs) do ids[#ids + 1] = id end
    end
  end
  if #ids == 0 then
    -- Classic-style bank: main container plus bank bags.
    ids[1] = BANK_CONTAINER or -1
    local first = (NUM_TOTAL_EQUIPPED_BAG_SLOTS or NUM_BAG_SLOTS or 4) + 1
    for bag = first, first + (NUM_BANKBAGSLOTS or 7) - 1 do ids[#ids + 1] = bag end
  end
  return ids
end

-- Returns counts per itemID, plus slot totals, and remembers per-slot facts in `seen`.
local function countContainers(ids, seen)
  local counts, total, free = {}, 0, 0
  if not C_Container then return counts, total, free end
  for _, bag in ipairs(ids) do
    local slots = try(C_Container.GetContainerNumSlots, bag) or 0
    total = total + slots
    for slot = 1, slots do
      local info = try(C_Container.GetContainerItemInfo, bag, slot)
      local id = info and plain(info.itemID)
      if id then
        counts[id] = (counts[id] or 0) + (plain(info.stackCount) or 1)
        local s = seen[id]
        if not s then s = {}; seen[id] = s end
        if plain(info.isBound) then s.bound = true end
        if not s.link then s.link = plain(info.hyperlink) end
        local q = try(C_Container.GetContainerItemQuestInfo, bag, slot)
        if type(q) == "table" then
          if plain(q.isQuestItem) then s.questItem = true end
          local startID = plain(q.questID)
          if type(startID) == "number" and startID > 0 then s.startsQuest = startID end
        end
      else
        free = free + 1
      end
    end
  end
  return counts, total, free
end

-- What the character wears: equipment slots 1 to 19, plus 0 for ammunition where the client has it.
-- The bags themselves (slots 20 and up) are not counted.
local function scanEquipped(seen)
  local counts = {}
  if not GetInventoryItemID then return counts end
  for slot = 0, 19 do
    local id = plain(try(GetInventoryItemID, "player", slot))
    if type(id) == "number" and id > 0 then
      local n = GetInventoryItemCount and plain(try(GetInventoryItemCount, "player", slot))
      counts[id] = (counts[id] or 0) + ((type(n) == "number" and n > 0) and n or 1)
      local s = seen[id]
      if not s then s = {}; seen[id] = s end
      if not s.link and GetInventoryItemLink then s.link = plain(try(GetInventoryItemLink, "player", slot)) end
    end
  end
  return counts
end

---------------------------------------------------------------------------
-- Questie database (optional)
---------------------------------------------------------------------------

local function questieDB()
  local lib = _G.LibQuestieDB
  if type(lib) == "table" and type(lib.Quest) == "table" and type(lib.Item) == "table" then return lib end
end

local function addIndex(itemID, questID, need, role)
  if type(itemID) ~= "number" then return end
  local list = questIndex[itemID]
  if not list then list = {}; questIndex[itemID] = list end
  for _, e in ipairs(list) do
    if e.q == questID then return end
  end
  list[#list + 1] = { q = questID, need = need, role = role }
end

local requestScan -- forward declaration

local function buildQuestIndex()
  local lib = questieDB()
  if not lib then indexState = "missing"; return end
  if indexState ~= "none" then return end
  local ids = try(lib.Quest.GetAllIds)
  if type(ids) ~= "table" then indexState = "missing"; return end
  indexState = "building"
  local pos, count = 1, #ids
  local function step()
    local stop = math.min(pos + INDEX_BATCH - 1, count)
    for i = pos, stop do
      local questID = ids[i]
      local obj = try(lib.Quest.objectives, questID)
      local items = type(obj) == "table" and obj[3]
      if type(items) == "table" then
        for _, it in ipairs(items) do
          if type(it) == "table" then
            addIndex(it[1], questID, (type(it[3]) == "number" and it[3] > 0) and it[3] or nil, "objective")
          end
        end
      end
      local src = try(lib.Quest.requiredSourceItems, questID)
      if type(src) == "table" then
        for _, itemID in ipairs(src) do addIndex(itemID, questID, nil, "source") end
      end
      -- The item a quest hands you when you accept it (a report to deliver, a banner to plant).
      local given = try(lib.Quest.sourceItemId, questID)
      if type(given) == "number" and given > 0 then addIndex(given, questID, nil, "given") end
    end
    pos = stop + 1
    if pos <= count then
      C_Timer.After(0, step)
    else
      indexState = "ready"
      requestScan()
    end
  end
  step()
end

local function playerMasks()
  if playerRaceMask ~= nil then return end
  playerRaceMask, playerClassMask = false, false
  local lib = questieDB()
  if not (lib and type(lib.Enum) == "table") then return end
  local _, _, raceID = UnitRace("player")
  if type(lib.Enum.raceMaskById) == "table" and raceID then
    playerRaceMask = lib.Enum.raceMaskById[raceID] or false
  end
  local _, classFile = UnitClass("player")
  if type(lib.Enum.classKeys) == "table" and classFile then
    local v = lib.Enum.classKeys[classFile]
    if type(v) == "number" then playerClassMask = v end
  end
end

local function questState(lib, questID)
  if C_QuestLog then
    if try(C_QuestLog.IsQuestFlaggedCompleted, questID) then return "done" end
    if try(C_QuestLog.GetLogIndexForQuestID, questID) then return "log" end
  end
  playerMasks()
  local band = bit and bit.band
  if band then
    local races = try(lib.Quest.requiredRaces, questID)
    if playerRaceMask and type(races) == "number" and races ~= 0 and band(races, playerRaceMask) == 0 then
      return "other"            -- other faction or race
    end
    local classes = try(lib.Quest.requiredClasses, questID)
    if playerClassMask and type(classes) == "number" and classes ~= 0 and band(classes, playerClassMask) == 0 then
      return "other"
    end
  end
  return "open"
end

-- Questie marks quests that can be handed in again and again (special flag 1) and files reputation
-- hand-ins under their own category (sort key -367). The page can hide both kinds.
local REPUTATION_SORT = -367

local function questKind(lib, questID)
  local repeatable, reputation
  local flags = try(lib.Quest.specialFlags, questID)
  local band = bit and bit.band
  if type(flags) == "number" and band and band(flags, 1) ~= 0 then repeatable = true end
  if try(lib.Quest.zoneOrSort, questID) == REPUTATION_SORT then reputation = true end
  return repeatable, reputation
end

local function questsForItem(itemID, startsQuest)
  local lib = questieDB()
  if not lib then return nil end
  local found, order = {}, {}
  local function add(questID, need, role)
    if type(questID) ~= "number" or questID <= 0 or found[questID] then return end
    found[questID] = { need = need, role = role }
    order[#order + 1] = questID
  end
  add(startsQuest, nil, "starts")
  add(try(lib.Item.startQuest, itemID), nil, "starts")
  for _, e in ipairs(questIndex[itemID] or {}) do add(e.q, e.need, e.role) end
  local related = try(lib.Item.relatedQuests, itemID)
  if type(related) == "table" then
    for _, questID in ipairs(related) do add(questID, nil, "related") end
  end
  if #order == 0 then return nil end
  local list = {}
  for _, questID in ipairs(order) do
    if #list >= MAX_QUESTS_PER_ITEM then break end
    local e = found[questID]
    local repeatable, reputation = questKind(lib, questID)
    list[#list + 1] = {
      repeatable = repeatable,
      reputation = reputation,
      id = questID,
      name = try(lib.Quest.name, questID) or ("Quest " .. questID),
      level = try(lib.Quest.questLevel, questID),
      min = try(lib.Quest.requiredLevel, questID),
      need = e.need,
      role = e.role,
      state = questState(lib, questID),
    }
  end
  return list
end

---------------------------------------------------------------------------
-- Items
---------------------------------------------------------------------------

local pendingItems = false

-- Auction prices come from Auctionator, if it is installed, through the functions it offers to other
-- addons (Auctionator.API.v1). Returns the price of one item in copper and the days since it was
-- last seen at the auction house; nil where Auctionator has nothing.
local function auctionatorAPI()
  local a = _G.Auctionator
  local api = type(a) == "table" and type(a.API) == "table" and a.API.v1
  return type(api) == "table" and api or nil
end

local function auctionPrice(itemID, link)
  local api = auctionatorAPI()
  if not api then return nil end
  local price, age
  if type(link) == "string" then      -- the link tells apart versions of the same gear ("of the Monkey")
    price = plain(try(api.GetAuctionPriceByItemLink, ADDON, link))
    age = plain(try(api.GetAuctionAgeByItemLink, ADDON, link))
  end
  if type(price) ~= "number" then
    price = plain(try(api.GetAuctionPriceByItemID, ADDON, itemID))
    age = plain(try(api.GetAuctionAgeByItemID, ADDON, itemID))
  end
  if type(price) ~= "number" or price <= 0 then return nil end
  return price, type(age) == "number" and age or nil
end

local function describeItem(itemID, seen)
  local getInfo = C_Item and C_Item.GetItemInfo
  local name, _, quality, itemLevel, minLevel, itemType, subType, stack, equipLoc, _, sellPrice,
        classID, subclassID, bindType, _, _, isReagent = try(getInfo, itemID)
  local s = seen or {}
  local item = {
    id = itemID,
    link = s.link,
    bound = s.bound or nil,
    questItem = s.questItem or nil,
  }
  if name then
    item.name = name
    item.quality = quality
    item.ilvl = itemLevel
    item.minLevel = minLevel
    item.type = itemType
    item.subType = subType
    item.stack = stack
    item.equipLoc = (equipLoc and equipLoc ~= "" and not equipLoc:find("NON_EQUIP")) and equipLoc or nil
    item.sell = sellPrice
    item.classID = classID
    item.subclassID = subclassID
    item.bind = bindType
    item.reagent = isReagent or nil
  else
    pendingItems = true
    if C_Item and C_Item.RequestLoadItemDataByID then try(C_Item.RequestLoadItemDataByID, itemID) end
    local linkName = s.link and s.link:match("%[(.-)%]")
    item.name = linkName or ("Item " .. itemID)
    item.pending = true
  end
  item.quests = questsForItem(itemID, s.startsQuest)
  item.auction, item.auctionAge = auctionPrice(itemID, s.link)
  return item
end

---------------------------------------------------------------------------
-- Quest log and skills
---------------------------------------------------------------------------

local function scanQuestLog()
  local log = {}
  if not (C_QuestLog and C_QuestLog.GetNumQuestLogEntries) then return log end
  local entries = try(C_QuestLog.GetNumQuestLogEntries) or 0
  for i = 1, entries do
    local info = try(C_QuestLog.GetInfo, i)
    if type(info) == "table" and not info.isHeader and info.questID then
      local q = { id = info.questID, title = plain(info.title), level = plain(info.level), obj = {} }
      q.complete = try(C_QuestLog.IsComplete, info.questID) and true or nil
      local objectives = try(C_QuestLog.GetQuestObjectives, info.questID)
      if type(objectives) == "table" then
        for _, o in ipairs(objectives) do
          if type(o) == "table" then
            q.obj[#q.obj + 1] = {
              text = plain(o.text), type = plain(o.type),
              have = plain(o.numFulfilled), need = plain(o.numRequired),
              done = plain(o.finished) and true or nil,
            }
          end
        end
      end
      log[#log + 1] = q
    end
  end
  return log
end

local function scanSkills()
  local skills = {}
  if GetNumSkillLines and GetSkillLineInfo then
    local header
    for i = 1, (try(GetNumSkillLines) or 0) do
      local name, isHeader, _, rank, _, _, maxRank = try(GetSkillLineInfo, i)
      if name then
        if isHeader then
          header = name
        else
          skills[#skills + 1] = { name = name, rank = rank, max = maxRank, group = header }
        end
      end
    end
  end
  if #skills == 0 and GetProfessions and GetProfessionInfo then
    local list = { try(GetProfessions) }
    for i = 1, 6 do
      local index = list[i]
      if index then
        local name, _, rank, maxRank = try(GetProfessionInfo, index)
        if name then skills[#skills + 1] = { name = name, rank = rank, max = maxRank } end
      end
    end
  end
  return skills
end

---------------------------------------------------------------------------
-- Recipes (read while a profession window is open)
---------------------------------------------------------------------------

local recipeQueued = false

-- Stores "Optimal", "Medium", "Easy" or "Trivial" so the page does not depend on enum numbers.
local function difficultyName(value)
  local enum = Enum and Enum.TradeskillRelativeDifficulty
  if value ~= nil and type(enum) == "table" then
    for name, v in pairs(enum) do
      if v == value then return name end
    end
  end
  return value
end

local function scanRecipes()
  recipeQueued = false
  if not (C and C_TradeSkillUI and C_TradeSkillUI.GetAllRecipeIDs) then return end
  if try(C_TradeSkillUI.IsTradeSkillLinked) or try(C_TradeSkillUI.IsTradeSkillGuild) then return end
  local base = try(C_TradeSkillUI.GetBaseProfessionInfo)
  local profName = type(base) == "table" and plain(base.professionName)
  if not profName or profName == "" then return end
  local ids = try(C_TradeSkillUI.GetAllRecipeIDs)
  if type(ids) ~= "table" or #ids == 0 then return end
  local list = {}
  local sample
  for _, recipeID in ipairs(ids) do
    local info = try(C_TradeSkillUI.GetRecipeInfo, recipeID)
    local schematic = try(C_TradeSkillUI.GetRecipeSchematic, recipeID, false)
    if type(schematic) == "table" and type(schematic.reagentSlotSchematics) == "table" then
      local reagents, any = {}, false
      for _, slot in ipairs(schematic.reagentSlotSchematics) do
        local first = type(slot) == "table" and type(slot.reagents) == "table" and slot.reagents[1]
        if type(first) == "table" and first.itemID then
          reagents[first.itemID] = (reagents[first.itemID] or 0) + (slot.quantityRequired or 1)
          any = true
        end
      end
      if any then
        local r = {
          id = recipeID,
          name = (type(info) == "table" and plain(info.name)) or plain(schematic.name),
          makes = plain(schematic.outputItemID),
          r = reagents,
        }
        if type(info) == "table" then
          r.learned = info.learned and true or false
          r.diff = difficultyName(plain(info.relativeDifficulty))
          -- Skill at which the recipe turns grey, when this client provides it.
          local trivial = plain(info.maxTrivialLevel)
          if type(trivial) == "number" and trivial > 0 then r.trivial = trivial end
          if not sample and info.learned then
            -- One recipe's plain fields, kept so the page can show what this client offers.
            sample = {}
            for k, v in pairs(info) do
              local kind = type(v)
              if type(k) == "string" and (kind == "number" or kind == "string" or kind == "boolean") and plain(v) ~= nil then
                sample[k] = v
              end
            end
          end
        end
        list[#list + 1] = r
      end
    end
  end
  if #list == 0 then return end
  C.recipes = C.recipes or {}
  C.recipes[profName] = {
    updated = time(),
    rank = type(base) == "table" and plain(base.skillLevel) or nil,
    max = type(base) == "table" and plain(base.maxSkillLevel) or nil,
    list = list,
    sample = sample,
  }
end

local function requestRecipeScan()
  if recipeQueued then return end
  recipeQueued = true
  C_Timer.After(1, scanRecipes)
end

---------------------------------------------------------------------------
-- Full scan
---------------------------------------------------------------------------

-- Which addon wrote the data: the version from the manifest, and the build stamp from Build.lua, which the
-- BagBoard helper writes when it installs the addon. The page compares the stamp with the installed addon to
-- tell whether a character's data is from an older addon.
local function addonVersion()
  local get = (C_AddOns and C_AddOns.GetAddOnMetadata) or GetAddOnMetadata
  local version = get and plain(try(get, ADDON, "Version")) or nil
  local build = rawget(_G, "BagBoardBuild")
  return type(version) == "string" and version or nil, type(build) == "string" and build or nil
end

local function scan()
  scanQueued = false
  if not C then return end
  pendingItems = false
  local seen = {}

  local bags, total, free = countContainers(bagIDs(), seen)
  -- The backpack always has slots. None reported means the client has no character data right now:
  -- seen at logout, where bags, money, skills and quest progress all came back empty. Keep the last scan.
  if total == 0 then return end
  C.bags, C.slots, C.free = bags, total, free

  if bankOpen then
    local bank, bankTotal, bankFree = countContainers(bankIDs(), seen)
    C.bank, C.bankSlots, C.bankFree, C.bankUpdated = bank, bankTotal, bankFree, time()
  end

  C.equipped = scanEquipped(seen)

  local old = C.items or {}
  local items = {}
  local function add(counts)
    for itemID in pairs(counts or {}) do
      if not items[itemID] then
        local s = seen[itemID]
        if not s and old[itemID] then
          -- Bank item while the bank is closed: keep what was seen at the bank.
          s = { link = old[itemID].link, bound = old[itemID].bound, questItem = old[itemID].questItem }
        end
        items[itemID] = describeItem(itemID, s)
      end
    end
  end
  add(C.bags)
  add(C.bank)
  add(C.equipped)
  -- Worn gear that binds when picked up or equipped is bound by now.
  for itemID in pairs(C.equipped) do
    local item = items[itemID]
    if item and (item.bind == 1 or item.bind == 2) then item.bound = true end
  end
  C.items = items

  C.questLog = scanQuestLog()
  C.skills = scanSkills()
  C.level = UnitLevel("player")
  C.money = plain(GetMoney and GetMoney())
  C.questie = indexState
  C.auctionator = auctionatorAPI() and true or false
  C.addonVersion, C.addonBuild = addonVersion()
  C.updated = time()

  if pendingItems then requestScan(2) end
end

function requestScan(delay)
  if scanQueued then return end
  scanQueued = true
  C_Timer.After(delay or 0.5, function()
    local ok, err = pcall(scan)
    if not ok then
      scanQueued = false
      if DB then DB.lastError = tostring(err) end
    end
  end)
end

---------------------------------------------------------------------------
-- Sync button and slash command
---------------------------------------------------------------------------

local button

local function sync()
  if InCombatLockdown and InCombatLockdown() then
    out("not in combat. Sync again after the fight.")
    return
  end
  pcall(scan)
  ReloadUI()
end

local function makeButton()
  if button then return button end
  button = CreateFrame("Button", "BagBoardSyncButton", UIParent, "UIPanelButtonTemplate")
  button:SetSize(86, 22)
  button:SetText("BagBoard")
  button:SetMovable(true)
  button:SetClampedToScreen(true)
  button:RegisterForDrag("LeftButton")
  button:RegisterForClicks("LeftButtonUp")
  button:SetScript("OnDragStart", function(self)
    if IsShiftKeyDown() then self:StartMoving() end
  end)
  button:SetScript("OnDragStop", function(self)
    self:StopMovingOrSizing()
    local point, _, relPoint, x, y = self:GetPoint(1)
    DB.button = { point = point, relPoint = relPoint, x = x, y = y }
  end)
  button:SetScript("OnClick", sync)
  button:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    GameTooltip:AddLine("BagBoard")
    GameTooltip:AddLine("Click: save and reload, the page updates.", 1, 1, 1)
    GameTooltip:AddLine("Shift-drag: move this button.", 1, 1, 1)
    GameTooltip:AddLine("/bb hide: hide this button.", 1, 1, 1)
    GameTooltip:Show()
  end)
  button:SetScript("OnLeave", function() GameTooltip:Hide() end)
  local p = DB.button
  if type(p) == "table" and p.point then
    button:SetPoint(p.point, UIParent, p.relPoint or p.point, p.x or 0, p.y or 0)
  else
    button:SetPoint("BOTTOMRIGHT", UIParent, "BOTTOMRIGHT", -260, 6)
  end
  return button
end

---------------------------------------------------------------------------
-- Tooltip: your decision and remark from the BagBoard page
---------------------------------------------------------------------------

-- BagBoardNotes comes from Notes.lua, which the BagBoard helper rewrites whenever you
-- change a note on the page. The game reads it at login and on /reload.
local DECISION = {
  keep = { "Keep", 0.49, 0.81, 0.42 },
  forever = { "Keep forever", 0.60, 0.60, 0.60 },
  auction = { "Auction", 0.94, 0.75, 0.35 },
  toss = { "Toss", 0.88, 0.41, 0.35 },
  twink = { "Twink", 0.44, 0.70, 0.88 },
}

local function addNoteLines(tooltip, itemID)
  if type(itemID) ~= "number" then return end
  local note = noteFor(itemID)
  if type(note) ~= "table" then return end
  local d = DECISION[note.d]
  if d then
    local label = d[1]
    if note.d == "twink" and type(note.t) == "string" and note.t ~= "" then label = "Send to " .. note.t end
    tooltip:AddLine("BagBoard: " .. label, d[2], d[3], d[4])
  end
  if type(note.r) == "string" and note.r ~= "" then
    tooltip:AddLine((d and "" or "BagBoard: ") .. note.r, 0.91, 0.88, 0.83, true)
  end
  if d or note.r then tooltip:Show() end
end

local function onTooltipItem(tooltip, data)
  if tooltip ~= GameTooltip and tooltip ~= ItemRefTooltip then return end
  local itemID = type(data) == "table" and plain(data.id) or nil
  if not itemID and tooltip.GetItem then
    local _, link = try(tooltip.GetItem, tooltip)
    link = plain(link)
    itemID = type(link) == "string" and tonumber(link:match("item:(%d+)")) or nil
  end
  if itemID then addNoteLines(tooltip, itemID) end
end

local function hookTooltips()
  local guarded = function(tooltip, data) pcall(onTooltipItem, tooltip, data) end
  if TooltipDataProcessor and TooltipDataProcessor.AddTooltipPostCall and Enum and Enum.TooltipDataType
     and Enum.TooltipDataType.Item then
    TooltipDataProcessor.AddTooltipPostCall(Enum.TooltipDataType.Item, guarded)
  else
    for _, tooltip in ipairs({ GameTooltip, ItemRefTooltip }) do
      if tooltip and tooltip.HookScript then pcall(tooltip.HookScript, tooltip, "OnTooltipSetItem", guarded) end
    end
  end
end

---------------------------------------------------------------------------
-- Changing a decision in game: Alt+click on an item, or /bb keep and so on
---------------------------------------------------------------------------

local DECISION_ORDER = { "keep", "forever", "auction", "toss", "twink" }

local function setDecision(itemID, link, decision)
  local edits = myEdits(true)
  if not edits or type(itemID) ~= "number" then return end
  local now = noteFor(itemID)
  if (now and now.d or "") == decision then return end
  edits[itemID] = { d = decision, at = time() }
  out((link or ("item " .. itemID)) .. ": " .. (decision == "" and "no decision" or DECISION[decision][1])
    .. ". The page gets it at the next /reload or logout.")
end

local function decisionMenu(itemID, link)
  if not (MenuUtil and MenuUtil.CreateContextMenu) then return false end
  return pcall(MenuUtil.CreateContextMenu, UIParent, function(_, root)
    root:CreateTitle("BagBoard: " .. (link or ("item " .. itemID)))
    local chosen = function(d) local note = noteFor(itemID); return (note and note.d or "") == d end
    local choose = function(d) setDecision(itemID, link, d) end
    for _, d in ipairs(DECISION_ORDER) do root:CreateRadio(DECISION[d][1], chosen, choose, d) end
    root:CreateRadio("No decision", chosen, choose, "")
  end)
end

-- The game calls this for every click on an item with a modifier key held. Alt alone is not used by the game.
local function onModifiedItemClick(link)
  if not (IsAltKeyDown and IsAltKeyDown()) or (IsShiftKeyDown and IsShiftKeyDown()) or (IsControlKeyDown and IsControlKeyDown()) then return end
  link = plain(link)
  local itemID = type(link) == "string" and tonumber(link:match("item:(%d+)")) or nil
  if itemID and not decisionMenu(itemID, link) then
    out("no menu on this client. Point at the item and type /bb keep, forever, auction, toss, twink or clear.")
  end
end

-- For /bb keep and the like: the item linked behind the command, otherwise the one under the mouse.
local function commandItem(rest)
  local id = tonumber(rest:match("item:(%d+)"))
  if id then return id, rest:match("(|c.-|h|r)") end
  local link
  if TooltipUtil and TooltipUtil.GetDisplayedItem then _, link = try(TooltipUtil.GetDisplayedItem, GameTooltip) end
  if not link and GameTooltip and GameTooltip.GetItem then _, link = try(GameTooltip.GetItem, GameTooltip) end
  link = plain(link)
  id = type(link) == "string" and tonumber(link:match("item:(%d+)")) or nil
  return id, link
end

---------------------------------------------------------------------------
-- Sell guard: selling something marked Keep is undone, then a dialog asks
---------------------------------------------------------------------------

-- An addon cannot stop a sale before it happens without breaking item clicks. So this watches the merchant's
-- buyback list: when an item marked Keep, Keep forever, Twink or Auction turns up there, it is bought back at once and a
-- dialog asks: "Sell it" sells it again and lets that item be sold until the merchant window closes, "Sell and
-- unmark" also removes the decision for good, "Keep it" leaves it in the bags. /bb guard switches it off.
local GUARDED = { keep = true, forever = true, twink = true, auction = true }
local merchantOpen = false
local buyback = nil              -- the buyback list as last seen: { "itemID:count", ... }; nil before the first look
local sellAllowed = {}           -- itemID -> true, until the merchant window closes

local function buybackList()
  local n = plain(try(GetNumBuybackItems))
  if type(n) ~= "number" then return nil end
  local sigs, ids, links, counts = {}, {}, {}, {}
  for i = 1, n do
    local link = plain(try(GetBuybackItemLink, i))
    local id = type(link) == "string" and tonumber(link:match("item:(%d+)")) or nil
    if not id and C_MerchantFrame then id = plain(try(C_MerchantFrame.GetBuybackItemID, i)) end
    local _, _, _, count = try(GetBuybackItemInfo, i)
    ids[i] = type(id) == "number" and id or 0
    links[i] = type(link) == "string" and link or false
    counts[i] = type(plain(count)) == "number" and count or false
    sigs[i] = ids[i] .. ":" .. tostring(plain(count))
  end
  return sigs, ids, links, counts
end

-- Sells the stack that was just bought back: the one of that size, or the item's only stack. When it cannot be
-- told apart or the client does not let an addon do it, the player sells it by hand; that is allowed now.
local function sellAgain(data)
  sellAllowed[data.id] = true
  local use = C_Container and C_Container.UseContainerItem
  local stacks, exact = {}, nil
  if merchantOpen and type(use) == "function" then
    for _, bag in ipairs(bagIDs()) do
      for slot = 1, try(C_Container.GetContainerNumSlots, bag) or 0 do
        local info = try(C_Container.GetContainerItemInfo, bag, slot)
        if type(info) == "table" and plain(info.itemID) == data.id and not plain(info.isLocked) then
          local stack = { bag, slot }
          stacks[#stacks + 1] = stack
          if not exact and data.count and plain(info.stackCount) == data.count then exact = stack end
        end
      end
    end
  end
  local stack = exact or (#stacks == 1 and stacks[1]) or nil
  if not (stack and pcall(use, stack[1], stack[2])) then
    out("sell " .. data.name .. " again yourself. It is allowed until you close the merchant window.")
  end
end

local function askSell(id, link, decision, undone, count)
  local label = DECISION[decision][1]
  local name = link or ("item " .. id)
  if not undone then
    out(name .. " is marked \"" .. label .. "\" but was sold. This client offers no way to buy it back from an addon; use the merchant's buyback tab.")
    return
  end
  out(name .. " is marked \"" .. label .. "\", so the sale was undone.")
  if type(StaticPopupDialogs) ~= "table" or type(StaticPopup_Show) ~= "function" then
    out("/bb guard switches this off if you do want to sell it.")
    return
  end
  -- The game puts the third button between the other two: Sell it, Sell and unmark, Keep it. Escape keeps.
  StaticPopupDialogs["BAGBOARD_SELL_KEPT"] = StaticPopupDialogs["BAGBOARD_SELL_KEPT"] or {
    text = "BagBoard: %s is marked \"%s\", so the sale was undone.\n\nSell it after all?",
    button1 = "Sell it", button2 = "Keep it", button3 = "Sell and unmark",
    OnAccept = function(_, data)
      if type(data) == "table" then sellAgain(data) end
    end,
    OnAlt = function(_, data)
      if type(data) == "table" then
        setDecision(data.id, data.link, "")
        sellAgain(data)
      end
    end,
    timeout = 0, whileDead = true, hideOnEscape = true, multiple = true, preferredIndex = 3,
  }
  local data = { id = id, link = link, name = name, count = count or nil }
  local popup = try(StaticPopup_Show, "BAGBOARD_SELL_KEPT", name, label, data)
  if type(popup) == "table" then popup.data = data end
end

local function checkSales()
  if not merchantOpen or (DB and DB.noSellGuard) then return end
  local sigs, ids, links, counts = buybackList()
  if not sigs then return end
  local old = buyback
  buyback = sigs
  if not old or #sigs < #old then return end      -- first look, or something was bought back
  -- Sold items are added at the end; once the list is full the oldest drop off the front. Find how far the
  -- old list moved up: what lies behind it is newly sold.
  local shift = 0
  while shift < #old do
    local same = true
    for i = shift + 1, #old do
      if old[i] ~= sigs[i - shift] then same = false; break end
    end
    if same then break end
    shift = shift + 1
  end
  for i = #sigs, #old - shift + 1, -1 do          -- last one first, so that the numbers below stay valid
    local id = ids[i]
    local note = noteFor(id)
    if type(note) == "table" and GUARDED[note.d] and not sellAllowed[id] then
      local can = type(BuybackItem) == "function"
      if can then pcall(BuybackItem, i) end
      askSell(id, links[i], note.d, can, counts[i])
    end
  end
end

local function guardSales()
  local ok, err = pcall(checkSales)
  if not ok and DB then DB.lastError = "sell guard: " .. tostring(err) end
end

---------------------------------------------------------------------------
-- /bb
---------------------------------------------------------------------------

SLASH_BAGBOARD1 = "/bagboard"
SLASH_BAGBOARD2 = "/bb"
SlashCmdList["BAGBOARD"] = function(msg)
  local raw = (msg or ""):match("^%s*(.-)%s*$")
  msg = raw:lower()
  local word = msg:match("^(%a+)") or ""
  if DECISION[word] or word == "clear" then
    local itemID, link = commandItem(raw)
    if itemID then
      setDecision(itemID, link, word == "clear" and "" or word)
    else
      out("point at an item, or add its link: /bb " .. word .. " [item]")
    end
  elseif msg == "sync" or msg == "reload" then
    sync()
  elseif msg == "hide" then
    DB.hideButton = true
    if button then button:Hide() end
    out("button hidden. /bb show brings it back.")
  elseif msg == "guard" then
    DB.noSellGuard = not DB.noSellGuard or nil
    out(DB.noSellGuard and "sell guard off: every item can be sold." or "sell guard on: selling an item marked Keep, Twink or Auction is undone and asked about.")
  elseif msg == "show" then
    DB.hideButton = nil
    makeButton():Show()
  else
    local n = 0
    for _ in pairs((C and C.items) or {}) do n = n + 1 end
    out(n .. " different items scanned. Quest data: " .. indexState .. ".")
    local notes = 0
    for _ in pairs(myNotes() or {}) do notes = notes + 1 end
    out(notes .. " notes for this character loaded from the page.")
    if C and not C.bankUpdated then out("open your bank once so the page can show it.") end
    if DB and DB.lastError then out("last error: " .. DB.lastError) end
    local version, build = addonVersion()
    out("version " .. (version or "?") .. (build and (", build " .. build) or ", no build stamp"))
    local changed = 0
    for _ in pairs(myEdits() or {}) do changed = changed + 1 end
    if changed > 0 then out(changed .. " decisions changed in game, the page gets them at the next /reload or logout.") end
    out("Alt+click an item to change its decision, or point at it and type /bb keep, forever, auction, toss, twink or clear.")
    out("sell guard for items marked Keep, Twink or Auction: " .. (DB and DB.noSellGuard and "off" or "on") .. ". /bb guard switches it.")
    out("/bb sync saves and reloads. /bb hide or /bb show for the button.")
  end
end

---------------------------------------------------------------------------
-- Events
---------------------------------------------------------------------------

local handlers = {}

function handlers.ADDON_LOADED(name)
  if name ~= ADDON then return end
  if type(BagBoardDB) ~= "table" then BagBoardDB = {} end
  DB = BagBoardDB
  DB.version = 1
  DB.chars = type(DB.chars) == "table" and DB.chars or {}
  DB.lastError = nil
end

function handlers.PLAYER_LOGIN()
  if not DB then handlers.ADDON_LOADED(ADDON) end
  local name = UnitName("player")
  local realm = plain(GetRealmName and GetRealmName()) or ""
  if realm == "" then realm = plain(GetNormalizedRealmName and GetNormalizedRealmName()) or "" end
  local key = realm ~= "" and (name .. " - " .. realm) or name
  -- Earlier versions stored the character under "Name - " when the realm name was empty.
  for _, oldKey in ipairs({ name .. " - ", name }) do
    if oldKey ~= key and type(DB.chars[oldKey]) == "table" then
      if type(DB.chars[key]) ~= "table" then DB.chars[key] = DB.chars[oldKey] end
      DB.chars[oldKey] = nil
    end
  end
  C = type(DB.chars[key]) == "table" and DB.chars[key] or {}
  DB.chars[key] = C
  DB.lastChar = key
  charKey = key
  C.name, C.realm = name, realm
  local className, classFile = UnitClass("player")
  C.class, C.classFile = className, classFile
  C.race = UnitRace("player")
  C.faction = UnitFactionGroup and UnitFactionGroup("player") or nil
  C.locale = GetLocale and GetLocale() or nil
  -- Decisions changed in game that the helper has put into the notes are done with.
  local all = _G.BagBoardNotes
  local applied = type(all) == "table" and type(all.applied) == "table" and all.applied[key]
  local edits = myEdits()
  if edits then
    for itemID, edit in pairs(edits) do
      if type(edit) ~= "table" or type(edit.d) ~= "string" or type(edit.at) ~= "number"
         or (type(applied) == "number" and edit.at <= applied) then
        edits[itemID] = nil
      end
    end
  end
  if not DB.hideButton then makeButton():Show() end
  pcall(hookTooltips)
  if hooksecurefunc and HandleModifiedItemClick then
    pcall(hooksecurefunc, "HandleModifiedItemClick", function(link) pcall(onModifiedItemClick, link) end)
  end
  requestScan(2)
  C_Timer.After(5, function() pcall(buildQuestIndex) end)
end

-- No scan at PLAYER_LOGOUT: the client has already dropped the character's data by then, and the scan
-- replaced a good one with empty bags. The scans after each change keep the saved data current.

function handlers.BANKFRAME_OPENED() bankOpen = true; requestScan() end
function handlers.BANKFRAME_CLOSED() bankOpen = false end
function handlers.MERCHANT_SHOW()
  merchantOpen = true
  buyback = nil
  guardSales()                   -- remembers what is in the buyback list already
end
function handlers.MERCHANT_UPDATE() guardSales() end
function handlers.MERCHANT_CLOSED()
  merchantOpen = false
  buyback = nil
  sellAllowed = {}
end
function handlers.TRADE_SKILL_SHOW() requestRecipeScan() end
function handlers.TRADE_SKILL_LIST_UPDATE() requestRecipeScan() end
function handlers.NEW_RECIPE_LEARNED() requestRecipeScan() end

for _, event in ipairs({
  "BAG_UPDATE_DELAYED", "PLAYERBANKSLOTS_CHANGED", "BANK_TABS_CHANGED", "QUEST_LOG_UPDATE",
  "SKILL_LINES_CHANGED", "PLAYER_LEVEL_UP", "GET_ITEM_INFO_RECEIVED", "PLAYER_MONEY", "PLAYER_EQUIPMENT_CHANGED",
}) do
  handlers[event] = function() requestScan() end
end
function handlers.BAG_UPDATE_DELAYED()
  requestScan()
  if merchantOpen then
    guardSales()
    C_Timer.After(0.5, guardSales)       -- in case the buyback list follows the bags a moment later
  end
end

frame:SetScript("OnEvent", function(_, event, ...)
  local h = handlers[event]
  if h then h(...) end
end)

for event in pairs(handlers) do
  -- Registering an event this client does not know raises an error, so guard each one.
  pcall(frame.RegisterEvent, frame, event)
end
