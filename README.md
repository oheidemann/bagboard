# BagBoard

A second-screen page for World of Warcraft: Forever. It shows what each of your characters carries, which
quests and professions use every item (also professions of your other characters), and lets you mark items:
keep, keep forever, auction, toss, or send to a twink. Your marks show up in the game's item tooltips, and
the game asks before you sell something you marked to keep.

It is a small program on your own computer plus a game addon. Nothing is sent anywhere: the page only
talks to the program on your computer.

## What you need

- A Mac with WoW: Forever installed. The names in the game data are expected in German (German game client).
- Python 3. If your Mac does not have it, the first start offers to install Apple's command line developer
  tools, which include it.
- Optional game addons that BagBoard reads if they are there: Questie with QuestieDB (quest uses) and
  Auctionator (auction prices).

## Install

Open the Terminal app, paste this line and press Return:

    curl -fsSL https://raw.githubusercontent.com/oheidemann/bagboard/main/install.sh | bash

It puts BagBoard into the folder `BagBoard` in your home folder and starts it. The page opens in your
browser and offers to install the addon into the game. After that: restart WoW Forever, log in, and click
the BagBoard button in game (or type `/bb sync`).

Without the Terminal: download
[BagBoard.zip](https://github.com/oheidemann/bagboard/releases/latest/download/BagBoard.zip), unpack it and
move the `BagBoard` folder where you like. The first time, macOS refuses to open the starter because it was
downloaded: right-click `Start BagBoard.command`, choose Open, and confirm (on newer macOS: System Settings,
Privacy & Security, "Open Anyway").

## Start

Double-click `Start BagBoard.command` in the BagBoard folder. A Terminal window opens and the page appears
in your browser at http://localhost:8787. Leave the window open; closing it stops BagBoard.

## Updates

BagBoard updates itself. At every start, and every few hours while it runs, it looks for a newer version
here on GitHub, installs it and updates the addon in the game. The page tells you when that happened and
whether the game needs a `/reload` or a restart. Without an internet connection it simply starts as it is.

Your notes and settings are in the `data` folder inside the BagBoard folder. Updates never touch it. Copy
that folder if you want a backup.

## In game

- `/bb` shows the status, `/bb sync` saves and reloads so that the page gets fresh data.
- Alt+click an item to change its mark, or point at it and type `/bb keep`, `/bb forever`, `/bb auction`,
  `/bb toss`, `/bb twink` or `/bb clear`.
- Selling a marked item to a merchant is undone and you are asked first. `/bb guard` switches that off.
- Items marked toss are sold by themselves when you open a merchant. `/bb autosell` switches that off.

## Remove

In the BagBoard folder: `python3 server/bagboard_server.py --uninstall` removes the addon from the game.
Then delete the BagBoard folder.

## Data sources

The list of profession recipes comes from the game client's own tables as published by
[wago.tools](https://wago.tools); each copy of BagBoard downloads it once per game build. Item tooltips and
icons on the page come from Wowhead.
