```
██╗  ██╗ ██████╗ ██╗    ██╗███████╗███████╗ █████╗ ████████╗
██║  ██║██╔═══██╗██║    ██║╚══███╔╝╚══███╔╝██╔══██╗╚══██╔══╝
███████║██║   ██║██║ █╗ ██║  ███╔╝   ███╔╝ ███████║   ██║
██╔══██║██║   ██║██║███╗██║ ███╔╝   ███╔╝  ██╔══██║   ██║
██║  ██║╚██████╔╝╚███╔███╔╝███████╗███████╗██║  ██║   ██║
╚═╝  ╚═╝ ╚═════╝  ╚══╝╚══╝ ╚══════╝╚══════╝╚═╝  ╚═╝   ╚═╝
                                                        CLI
        Live cricket scores. Right in your terminal.
```

---

> **Howzzat!** — the appeal that stops the game. This CLI does the same to your productivity.

`howzzat-cli` is a terminal-based live cricket score ticker. No browser, no app, no noise — just the match, line by line, the way cricket was meant to be followed.

---

## Features

- **Live Scoreboard** — current innings score, wickets, overs at a glance
- **Both Batsmen** — on-strike and non-striker scores, balls faced, strike rate
- **Current Partnership** — runs and balls for the active stand
- **Bowler Stats** — current bowler's figures (O-M-R-W) updated live
- **Over-by-Over** — current over ball sequence with run/wicket markers
- **Live Commentary** — latest ball-by-ball commentary feed
- **Chase Stats** — runs required, balls remaining, required run rate (only when chasing)
- **Run Rate** — current CRR vs RRR side by side
- **Match Situation** — venue, toss result, match type, series name

---

## Demo

```
┌─────────────────────────────────────────────────────────────┐
│  IND vs AUS  •  2nd Test  •  Day 3  •  Wankhede, Mumbai    │
├─────────────────────────────────────────────────────────────┤
│  AUSTRALIA 2nd INNINGS                                      │
│  187 / 4   (52.3 ov)                                       │
├──────────────────────────┬──────────────────────────────────┤
│  BATTING                 │  BOWLING                        │
│  *SPD Smith   63 (98)    │  R Jadeja                       │
│   TM Head     41 (55)    │  12-3-38-2                      │
├──────────────────────────┴──────────────────────────────────┤
│  PARTNERSHIP  82 runs  (103 balls)                          │
├─────────────────────────────────────────────────────────────┤
│  THIS OVER   • 1 • W • 4 • • 1                             │
├───────────────────────────┬─────────────────────────────────┤
│  TARGET  312              │  CRR   3.56                    │
│  NEED    125 off 284      │  RRR   2.64                    │
└───────────────────────────┴─────────────────────────────────┘
  💬  Jadeja beats Smith outside off, sharp turn, just misses
      the edge. Beauty of a delivery.
```

---

## Installation

```bash
# clone the repo
git clone https://github.com/yourusername/howzzat-cli.git
cd howzzat-cli

# install dependencies
npm install

# run it
npm start
```

### Requirements

- Node.js `v18+`
- A terminal that supports UTF-8 and ANSI colors (most do)
- An active internet connection

---

## Usage

```bash
# Show live matches and pick one
howzzat

# Jump straight into a specific match (by match ID)
howzzat --match <match-id>

# Refresh interval in seconds (default: 10)
howzzat --refresh 5

# Compact single-line ticker mode
howzzat --ticker

# Show scorecard view
howzzat --scorecard

# Help
howzzat --help
```

---

## Options

| Flag | Alias | Description | Default |
|---|---|---|---|
| `--match <id>` | `-m` | Jump to a specific match by ID | — |
| `--refresh <s>` | `-r` | Polling interval in seconds | `10` |
| `--ticker` | `-t` | Single-line ticker mode for tmux/status bars | `false` |
| `--scorecard` | `-s` | Full scorecard instead of live view | `false` |
| `--no-color` | | Disable ANSI colors | `false` |
| `--help` | `-h` | Show help | — |

---

## Keybindings (Interactive Mode)

| Key | Action |
|---|---|
| `r` | Force refresh |
| `m` | Switch match |
| `s` | Toggle scorecard |
| `t` | Toggle ticker mode |
| `q` / `Ctrl+C` | Quit |

---

## Build

> 🚧 **WIP**

---

## Data Source

`howzzat-cli` pulls data from [Cricbuzz](https://www.cricbuzz.com) / a supported cricket API. You may need an API key depending on the data provider configured.

Set your key in a `.env` file:

```env
CRICKET_API_KEY=your_key_here
```

---

## Roadmap

- [ ] Match selection from live matches list
- [ ] Ball-by-ball ticker mode for tmux status bars
- [ ] Full scorecard (FOW, all batsmen, bowling figures)
- [ ] Notifications on wickets / milestones
- [ ] T20 wagon wheel in ASCII
- [ ] Multi-match split view
- [ ] Historical match lookup

---

## Contributing

Pull requests are welcome. For major changes, open an issue first. If you find a bug mid-match, please wait for the over to finish before filing it.

---

## License

MIT © [Your Name]

---

*"Cricket is not just a sport. It's a reason to have a terminal open."*
