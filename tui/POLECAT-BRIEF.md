# Strader Fly TUI — Polecat Build Brief

**Bead:** (assigned at sling time)
**Domain:** SPX butterfly spread trading cockpit
**Framework:** Go + Bubble Tea + Bubbles ecosystem
**Layout model:** lazygit-style — left sidebar panels, large main panel, bottom strip
**Data:** `tui/data/butterfly-sample.json` (pre-loaded, do not fetch live data)

---

## What You're Building

A terminal UI for visualizing and interacting with SPX butterfly spreads. The layout follows lazygit's proven pattern: stacked sidebar panels on the left, a large main panel on the right (the "Diff" equivalent), and an optional bottom strip. All keyboard-navigable.

```
┌─ Legs ────────────┬─ Main Panel ──────────────────────────────┐
│ +1 5830C  Δ+0.62  │                                           │
│ -2 5840C  Δ-1.04  │  (content changes based on sidebar focus  │
│ +1 5850C  Δ+0.42  │   and active view mode)                   │
│                   │                                           │
├─ Position ────────┤  Views toggled by keystroke:              │
│ Net Δ:    0.00    │   1 = Payoff Curve (tent shape)           │
│ Net Γ:   -0.0007  │   2 = GEX Matrix (table)                 │
│ Net Θ:   +0.19    │   3 = Greek Profiles (sparklines)         │
│ Net V:   -0.39    │   4 = Profit Heatmap (strike × DTE)      │
│ Debit:    3.40    │   v = Bitmap toggle (TV screencap)        │
│ MaxP:     6.60    │                                           │
│ MaxL:     3.40    │                                           │
├─ Strategy ────────┤                                           │
│ ▶ Standard Fly    │                                           │
│   Iron Fly        │                                           │
│   Broken Wing     │                                           │
│                   │                                           │
└───────────────────┴───────────────────────────────────────────┘
┌─ Greeks Strip ────────────────────────────────────────────────┐
│ Δ ⣀⣠⣤⣶⣿⣶⣤⣠⣀  Γ ⣿⣶⣤⣀⣀⣤⣶⣿  θ ⣀⣤⣶⣿⣿⣶⣤⣀  ν ⣿⣤⣀⣀⣀⣀⣤⣿ │
│   +  0  -          -  0  +       -  0  +       +  0  -       │
└───────────────────────────────────────────────────────────────┘
```

---

## Visualization Targets (build at least 4 of 6)

### 1. Payoff Curve
The butterfly tent shape. Render using ntcharts or braille characters.
- X-axis: underlying price (5810–5870)
- Y-axis: P&L
- Color: green above zero, red below zero
- Bonus: overlay multiple DTE curves (30/15/7/1) showing tent sharpening

Data: `payoffCurve.points` and `payoffByDTE.curves` in the sample JSON.

### 2. GEX Matrix
Gamma Exposure table — dealer positioning by strike.
- Columns: Strike | Call GEX | Put GEX | Net GEX
- Color-code: positive green, negative red, magnitude = intensity
- Sortable by any column

Data: `gexMatrix` in the sample JSON.

### 3. Greek Profiles
Row of 4 sparklines showing delta/gamma/theta/vega across the strike range.
- Each sparkline shows the sign-flip zone (where the Greek crosses zero)
- Label the zero-crossing point
- Use ntcharts sparkline component

Data: `greeksByStrike` in the sample JSON.

### 4. Profit Heatmap
Strike on X-axis, DTE on Y-axis, color intensity = P&L.
- The butterfly's profit zone appears as a bright band narrowing toward expiration
- Use half-block characters (▀▄) with color gradients
- Green = profit, red = loss, bright = high magnitude

Data: `payoffByDTE.curves` in the sample JSON (interpolate for more DTE rows).

### 5. Position Dashboard
Styled panels showing aggregate position data.
- Net Greeks (Δ, Γ, Θ, V) with color-coded sign
- Debit paid, max profit, max loss, breakeven prices
- DTE countdown (use bubbles/timer)
- P&L as percentage of max profit (use bubbles/progress as gauge)

Data: `strategy.aggregate` and `strategy` top-level fields.

### 6. Strategy Builder
Interactive strike selection.
- Three text inputs for lower/middle/upper strike
- As strikes change, payoff curve updates live
- Toggle between Standard / Iron / Broken Wing
- Broken Wing: allow asymmetric wing widths

Data: compute payoff from strike inputs (basic Black-Scholes not required — linear interpolation of intrinsic value at expiration is sufficient).

---

## Component Menu

These are pre-approved dependencies. Use what you need.

### Layout
| Package | Import | Use |
|---------|--------|-----|
| FlexBox | `github.com/76creates/stickers` | Responsive grid layout (lazygit-style panels) |
| Lip Gloss | `github.com/charmbracelet/lipgloss` | Styling, borders, colors, JoinHorizontal/Vertical |
| Viewport | `github.com/charmbracelet/bubbles/viewport` | Scrollable panels |

### Data Display
| Package | Import | Use |
|---------|--------|-----|
| bubble-table | `github.com/evertras/bubble-table/table` | Interactive sortable tables (GEX, legs) |
| ntcharts | `github.com/NimbleMarkets/ntcharts` | Sparklines, candlestick, time series, streamline |
| bubbles/table | `github.com/charmbracelet/bubbles/table` | Simple tables (position summary) |

### Interaction
| Package | Import | Use |
|---------|--------|-----|
| bubbles/textinput | `github.com/charmbracelet/bubbles/textinput` | Strike entry |
| bubbles/list | `github.com/charmbracelet/bubbles/list` | Strategy type selection |
| bubbles/help | `github.com/charmbracelet/bubbles/help` | Keybinding help bar |
| bubbles/timer | `github.com/charmbracelet/bubbles/timer` | DTE countdown |
| bubbles/progress | `github.com/charmbracelet/bubbles/progress` | P&L gauge |
| BubbleZone | `github.com/lrstanley/bubblezone` | Mouse click-to-select |

### Animation
| Package | Import | Use |
|---------|--------|-----|
| Harmonica | `github.com/charmbracelet/harmonica` | Spring-animated value transitions |
| bubbles/spinner | `github.com/charmbracelet/bubbles/spinner` | Loading indicators |

---

## Keyboard Navigation (lazygit pattern)

Follow lazygit's navigation model:

| Key | Action |
|-----|--------|
| `Tab` / `Shift+Tab` | Cycle focus between sidebar panels and main panel |
| `j` / `k` | Move within focused panel (select legs, scroll data) |
| `h` / `l` | Collapse/expand sidebar or switch sub-views |
| `1` `2` `3` `4` | Switch main panel view (payoff / GEX / Greeks / heatmap) |
| `v` | Toggle bitmap mode in main panel (see Bitmap Toggle section) |
| `Enter` | Select / confirm in focused panel |
| `?` | Toggle help overlay |
| `q` | Quit |

Focused panel should have a visually distinct border (accent color). Unfocused panels dim slightly.

---

## Color Palette

Use a cohesive palette. Recommended (Catppuccin Mocha-adjacent):

```go
var (
    colorBg       = lipgloss.Color("#1e1e2e") // base
    colorSurface  = lipgloss.Color("#313244") // panel backgrounds
    colorOverlay  = lipgloss.Color("#45475a") // borders, separators
    colorText     = lipgloss.Color("#cdd6f4") // primary text
    colorSubtext  = lipgloss.Color("#a6adc8") // secondary text
    colorGreen    = lipgloss.Color("#a6e3a1") // profit, positive Greeks
    colorRed      = lipgloss.Color("#f38ba8") // loss, negative Greeks
    colorBlue     = lipgloss.Color("#89b4fa") // accent, active borders
    colorYellow   = lipgloss.Color("#f9e2af") // warnings, highlights
    colorMauve    = lipgloss.Color("#cba6f7") // special emphasis
)
```

---

## Bitmap Toggle — Technical Implementation

The main panel supports two render modes toggled by `v`:
- **TUI mode**: character-based content (GEX matrix, payoff curve, etc.)
- **Bitmap mode**: renders a PNG image in the same panel region

A test image is provided at `tui/data/tv-screenshot.png`. In production this would be a TradingView screencap with LuxAlgo indicators.

### How It Works

The bitmap toggle has three implementation tiers. Build Tier 1 (guaranteed to work). Attempt Tier 2 or 3 if time allows.

### Tier 1: chafa (works everywhere, no special terminal required)

`chafa` converts a PNG to Unicode half-block characters with color. It runs as an external process and returns a string you paste directly into your `View()`.

```go
package graphics

import (
    "fmt"
    "os/exec"
    "strings"
)

// RenderImageChafa renders a PNG as colored character art.
// cols/rows should match the main panel dimensions.
func RenderImageChafa(imagePath string, cols, rows int) (string, error) {
    args := []string{
        imagePath,
        fmt.Sprintf("--size=%dx%d", cols, rows),
        "--format=symbols",     // Unicode output
        "--color-space=din99d", // perceptual color matching
        "--dither=diffusion",   // Floyd-Steinberg dithering
        "--symbols=block+border+space+extra", // character set
    }
    cmd := exec.Command("chafa", args...)
    out, err := cmd.Output()
    if err != nil {
        return "", fmt.Errorf("chafa: %w", err)
    }
    return strings.TrimRight(string(out), "\n"), nil
}
```

Usage in your model:

```go
func (m model) viewMainPanel() string {
    panelW, panelH := m.mainPanelWidth, m.mainPanelHeight

    if m.bitmapMode {
        img, err := graphics.RenderImageChafa("tui/data/tv-screenshot.png", panelW, panelH-2)
        if err != nil {
            return fmt.Sprintf("Image error: %v", err)
        }
        return img
    }

    // Normal TUI rendering
    switch m.activeView {
    case viewPayoff:
        return m.renderPayoffCurve()
    case viewGEX:
        return m.renderGEXMatrix()
    // ...
    }
}
```

The `v` key handler:

```go
case "v":
    m.bitmapMode = !m.bitmapMode
    return m, nil
```

That's it. chafa outputs characters — Bubble Tea renders them like any other string. No graphics protocol, no terminal detection, no passthrough. Works in Windows Terminal, any tmux version, any terminal.

**Quality:** ~160x96 effective resolution in a full-screen pane. Recognizable charts and price action. Not crisp, but legible.

### Tier 2: Kitty Graphics Protocol (high-res, needs WezTerm/Kitty/Ghostty)

For operators with a Kitty-protocol-capable terminal, render the image at native pixel resolution.

```go
package graphics

import (
    "encoding/base64"
    "fmt"
    "os"
    "strings"
)

// RenderImageKitty emits Kitty graphics protocol escape sequences.
// The image renders at native resolution in the terminal,
// occupying cols×rows character cells.
func RenderImageKitty(imagePath string, cols, rows int) (string, error) {
    data, err := os.ReadFile(imagePath)
    if err != nil {
        return "", err
    }
    encoded := base64.StdEncoding.EncodeToString(data)

    // Kitty protocol: transmit + display in one command
    // f=100 = PNG format
    // a=T   = transmit and display
    // c/r   = columns/rows to occupy
    // q=2   = suppress response from terminal
    var sb strings.Builder

    // Wrap in tmux passthrough if inside tmux
    inTmux := os.Getenv("TMUX") != ""

    // Kitty sends in 4096-byte chunks
    chunks := splitString(encoded, 4096)
    for i, chunk := range chunks {
        more := 1
        if i == len(chunks)-1 {
            more = 0
        }
        payload := fmt.Sprintf("\x1b_Gf=100,a=T,c=%d,r=%d,q=2,m=%d;%s\x1b\\",
            cols, rows, more, chunk)
        // Only set f,a,c,r on first chunk
        if i > 0 {
            payload = fmt.Sprintf("\x1b_Gm=%d;%s\x1b\\", more, chunk)
        }

        if inTmux {
            // DCS passthrough wrapping for tmux
            payload = fmt.Sprintf("\x1bPtmux;%s\x1b\\",
                strings.ReplaceAll(payload, "\x1b", "\x1b\x1b"))
        }
        sb.WriteString(payload)
    }
    return sb.String(), nil
}

// DeleteImageKitty removes the displayed image. Characters underneath reappear.
func DeleteImageKitty() string {
    cmd := "\x1b_Ga=d,q=2;\x1b\\"
    if os.Getenv("TMUX") != "" {
        cmd = fmt.Sprintf("\x1bPtmux;%s\x1b\\",
            strings.ReplaceAll(cmd, "\x1b", "\x1b\x1b"))
    }
    return cmd
}

func splitString(s string, chunkSize int) []string {
    var chunks []string
    for len(s) > 0 {
        if len(s) < chunkSize {
            chunkSize = len(s)
        }
        chunks = append(chunks, s[:chunkSize])
        s = s[chunkSize:]
    }
    return chunks
}
```

**Prerequisite:** Operator must run `tmux set -g allow-passthrough on` (one-time).

**Terminal detection** — pick the right renderer automatically:

```go
package graphics

import "os"

type Renderer int

const (
    RendererChafa Renderer = iota
    RendererKitty
)

// DetectRenderer checks terminal capabilities.
func DetectRenderer() Renderer {
    term := os.Getenv("TERM_PROGRAM")
    // Kitty, WezTerm, Ghostty all support Kitty graphics protocol
    switch term {
    case "WezTerm", "kitty", "ghostty":
        return RendererKitty
    }
    // Also check KITTY_WINDOW_ID (set inside Kitty terminal)
    if os.Getenv("KITTY_WINDOW_ID") != "" {
        return RendererKitty
    }
    return RendererChafa
}

// RenderImage picks the best available renderer.
func RenderImage(path string, cols, rows int) (string, error) {
    switch DetectRenderer() {
    case RendererKitty:
        return RenderImageKitty(path, cols, rows)
    default:
        return RenderImageChafa(path, cols, rows)
    }
}

// ClearImage removes a Kitty image (no-op for chafa since it's just characters).
func ClearImage() string {
    if DetectRenderer() == RendererKitty {
        return DeleteImageKitty()
    }
    return "" // chafa: just re-render TUI, characters replace characters
}
```

### Tier 3: Live Screenshot Pipeline (bonus, not required)

For operators who want the TV screencap to auto-refresh:

```bash
#!/usr/bin/env bash
# tui/scripts/tv-capture.sh
# Run in a separate tmux pane. Captures TradingView browser tab every 5 seconds.
# Requires: scrot or maim (Linux), or PowerShell (WSL→Windows screenshot)

OUTFILE="tui/data/tv-screenshot.png"

while true; do
    # WSL: capture Windows screen region via PowerShell
    powershell.exe -Command "
        Add-Type -AssemblyName System.Windows.Forms
        \$bounds = [System.Drawing.Rectangle]::FromLTRB(100, 100, 1920, 1080)
        \$bitmap = New-Object System.Drawing.Bitmap(\$bounds.Width, \$bounds.Height)
        \$graphics = [System.Drawing.Graphics]::FromImage(\$bitmap)
        \$graphics.CopyFromScreen(\$bounds.Location, [System.Drawing.Point]::Empty, \$bounds.Size)
        \$bitmap.Save('C:\temp\tv-screenshot.png')
    " 2>/dev/null

    # Copy from Windows to WSL
    cp /mnt/c/temp/tv-screenshot.png "$OUTFILE" 2>/dev/null

    sleep 5
done
```

The TUI watches the file's mtime and re-renders on change:

```go
// In your Update loop, send a tick every 2 seconds
case tickMsg:
    info, _ := os.Stat("tui/data/tv-screenshot.png")
    if info != nil && info.ModTime().After(m.lastImageMod) {
        m.lastImageMod = info.ModTime()
        m.imageCache = "" // force re-render
    }
    return m, tick()
```

---

## Project Structure

```
tui/
├── cmd/flytui/main.go          # Entry point (scaffold provided)
├── internal/
│   ├── ui/                     # Bubble Tea models, views, components
│   ├── data/                   # JSON loader, data types
│   └── graphics/               # Bitmap toggle (chafa + kitty)
├── data/
│   ├── butterfly-sample.json   # Pre-loaded position data
│   └── tv-screenshot.png       # Test image for bitmap mode
├── go.mod                      # Dependencies (pre-configured)
└── POLECAT-BRIEF.md            # This file
```

## Running

```bash
cd tui
go mod tidy    # resolve dependencies
go run ./cmd/flytui
```

## Evaluation Criteria

| Criterion | Weight | What We're Looking For |
|-----------|--------|----------------------|
| Visual quality | 30% | Cohesive palette, spacing, borders. Does it look finished? |
| Component range | 25% | How many Bubbles components used effectively? |
| Butterfly accuracy | 20% | Payoff math correct. Greeks make sense. Zones colored right. |
| Keyboard navigation | 15% | lazygit-feel: Tab between panels, j/k within, number keys switch views |
| Bitmap toggle | 10% | v key swaps TUI↔image cleanly. Tier 1 minimum, Tier 2+ is bonus. |
