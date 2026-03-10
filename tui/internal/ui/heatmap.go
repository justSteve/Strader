package ui

import (
	"fmt"
	"math"
	"sort"
	"strconv"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/gastown/strader-flytui/internal/data"
)

// renderProfitHeatmap renders strike (X) vs DTE (Y) with color intensity = P&L.
// Uses half-block characters with graduated color intensity for a smooth heatmap.
func (m Model) renderProfitHeatmap(w, h int) string {
	curves := m.data.PayoffByDTE.Curves
	if len(curves) == 0 {
		return "No heatmap data"
	}

	// Sort DTE keys descending (high DTE at top)
	var dteKeys []int
	for k := range curves {
		d, _ := strconv.Atoi(k)
		dteKeys = append(dteKeys, d)
	}
	sort.Sort(sort.Reverse(sort.IntSlice(dteKeys)))

	// Interpolate additional DTE rows for smoother gradient
	allDTEs := interpolateDTEs(dteKeys)

	prices := m.data.PayoffCurve.Points
	if len(prices) == 0 {
		return "No price data"
	}

	labelW := 6
	hmW := w - labelW - 2
	hmH := h - 6
	if hmW < 10 {
		hmW = 10
	}
	if hmH < 4 {
		hmH = 4
	}

	// Global P&L range
	minPnL, maxPnL := 0.0, 0.0
	for _, curve := range curves {
		for _, p := range curve {
			if p.PnL < minPnL {
				minPnL = p.PnL
			}
			if p.PnL > maxPnL {
				maxPnL = p.PnL
			}
		}
	}

	minPrice := prices[0].Price
	maxPrice := prices[len(prices)-1].Price
	priceRange := maxPrice - minPrice
	if priceRange == 0 {
		priceRange = 1
	}

	var lines []string

	// Column headers — price labels
	headerLine := strings.Repeat(" ", labelW+1)
	headerStep := hmW / 5
	if headerStep < 1 {
		headerStep = 1
	}
	for i := 0; i <= 4; i++ {
		x := i * headerStep
		price := minPrice + float64(x)*priceRange/float64(hmW-1)
		label := fmt.Sprintf("%.0f", price)
		pad := headerStep - len(label)
		if pad < 0 {
			pad = 0
		}
		headerLine += label + strings.Repeat(" ", pad)
	}
	lines = append(lines, SubtitleStyle.Render(headerLine))

	// Breakeven markers on a separator line
	beLine := strings.Repeat(" ", labelW+1)
	beChars := make([]rune, hmW)
	for i := range beChars {
		beChars[i] = '─'
	}
	for _, be := range m.data.Strategy.Breakevens {
		bx := int(float64(hmW-1) * (be - minPrice) / priceRange)
		if bx >= 0 && bx < hmW {
			beChars[bx] = '╋'
		}
	}
	// Mark center strike
	center := m.data.Strategy.Legs[1].Strike // middle leg
	cx := int(float64(hmW-1) * (center - minPrice) / priceRange)
	if cx >= 0 && cx < hmW {
		beChars[cx] = '▼'
	}
	beLine += DimStyle.Render(string(beChars))
	lines = append(lines, beLine)

	// Heatmap rows
	for _, dte := range allDTEs {
		if len(lines) >= hmH+2 {
			break
		}

		row := interpolateRow(curves, dteKeys, dte, hmW, minPrice, priceRange)

		label := fmt.Sprintf("%3dd ", dte)
		var rowStr strings.Builder
		rowStr.WriteString(SubtitleStyle.Render(label) + " ")

		for _, pnl := range row {
			ch, style := heatmapCellStyled(pnl, minPnL, maxPnL)
			rowStr.WriteString(style.Render(string(ch)))
		}
		lines = append(lines, rowStr.String())
	}

	// Legend
	lines = append(lines, "")
	legend := "  " +
		lipgloss.NewStyle().Background(lipgloss.Color("#2a1520")).Foreground(ColorRed).Render("░") +
		NegativeStyle.Render(" Loss") + "  " +
		DimStyle.Render("·") + SubtitleStyle.Render(" Break-even") + "  " +
		lipgloss.NewStyle().Background(lipgloss.Color("#1a2a1a")).Foreground(ColorGreen).Render("░") +
		PositiveStyle.Render(" Profit") + "  " +
		HighlightStyle.Render("▼") + SubtitleStyle.Render(" Center") + "  " +
		DimStyle.Render("╋") + SubtitleStyle.Render(" B/E")
	lines = append(lines, legend)

	return padLines(strings.Join(lines, "\n"), h)
}

// heatmapCellStyled returns a character and style for a heatmap cell.
// Uses background color with graduated intensity for a proper heatmap effect.
func heatmapCellStyled(pnl, minPnL, maxPnL float64) (rune, lipgloss.Style) {
	if maxPnL == minPnL {
		return ' ', lipgloss.NewStyle()
	}

	if pnl > 0.1 {
		intensity := math.Min(pnl/maxPnL, 1.0)
		// Graduated green: darker bg for low intensity, brighter for high
		var bg, fg lipgloss.Color
		if intensity > 0.8 {
			bg = lipgloss.Color("#1a3a1a")
			fg = ColorGreen
			return '\u2588', lipgloss.NewStyle().Foreground(fg).Background(bg) // █
		} else if intensity > 0.5 {
			bg = lipgloss.Color("#1a2a1a")
			fg = ColorGreen
			return '\u2593', lipgloss.NewStyle().Foreground(fg).Background(bg) // ▓
		} else if intensity > 0.2 {
			bg = lipgloss.Color("#1a2518")
			fg = lipgloss.Color("#6aaa6a")
			return '\u2592', lipgloss.NewStyle().Foreground(fg).Background(bg) // ▒
		}
		return '\u2591', lipgloss.NewStyle().Foreground(lipgloss.Color("#4a8a4a")) // ░
	} else if pnl < -0.1 {
		intensity := math.Min(math.Abs(pnl)/math.Abs(minPnL), 1.0)
		var bg, fg lipgloss.Color
		if intensity > 0.8 {
			bg = lipgloss.Color("#3a1520")
			fg = ColorRed
			return '\u2588', lipgloss.NewStyle().Foreground(fg).Background(bg)
		} else if intensity > 0.5 {
			bg = lipgloss.Color("#2a1520")
			fg = ColorRed
			return '\u2593', lipgloss.NewStyle().Foreground(fg).Background(bg)
		} else if intensity > 0.2 {
			bg = lipgloss.Color("#251518")
			fg = lipgloss.Color("#aa5a5a")
			return '\u2592', lipgloss.NewStyle().Foreground(fg).Background(bg)
		}
		return '\u2591', lipgloss.NewStyle().Foreground(lipgloss.Color("#8a4a4a"))
	}

	return '\u00B7', lipgloss.NewStyle().Foreground(ColorSubtext0) // near-zero: middle dot
}

// interpolateDTEs adds midpoint DTEs between existing keys for smoother heatmap.
func interpolateDTEs(keys []int) []int {
	if len(keys) < 2 {
		return keys
	}
	var result []int
	for i := 0; i < len(keys)-1; i++ {
		result = append(result, keys[i])
		// Add 2 intermediate points for smoother gradient
		gap := keys[i] - keys[i+1]
		if gap > 2 {
			result = append(result, keys[i]-gap/3)
			result = append(result, keys[i]-2*gap/3)
		} else if gap > 1 {
			result = append(result, keys[i]-gap/2)
		}
	}
	result = append(result, keys[len(keys)-1])
	return result
}

// interpolateRow generates a row of P&L values for a specific DTE by linear
// interpolation between known DTE curves.
func interpolateRow(curves map[string][]data.PayoffPoint, dteKeys []int, dte, w int, minPrice, priceRange float64) []float64 {
	loDTE := dteKeys[len(dteKeys)-1]
	hiDTE := dteKeys[0]
	for _, d := range dteKeys {
		if d >= dte {
			hiDTE = d
		}
		if d <= dte && d >= loDTE {
			loDTE = d
		}
	}

	loKey := strconv.Itoa(loDTE)
	hiKey := strconv.Itoa(hiDTE)

	loCurve := curves[loKey]
	hiCurve := curves[hiKey]
	if loCurve == nil {
		loCurve = hiCurve
	}
	if hiCurve == nil {
		hiCurve = loCurve
	}

	frac := 0.0
	if hiDTE != loDTE {
		frac = float64(dte-loDTE) / float64(hiDTE-loDTE)
	}

	row := make([]float64, w)
	for i := 0; i < w; i++ {
		price := minPrice + float64(i)*priceRange/float64(w-1)
		loPnL := lookupPnL(loCurve, price)
		hiPnL := lookupPnL(hiCurve, price)
		row[i] = loPnL*(1-frac) + hiPnL*frac
	}
	return row
}

// lookupPnL finds the P&L at a specific price by linear interpolation on a curve.
func lookupPnL(curve []data.PayoffPoint, price float64) float64 {
	if len(curve) == 0 {
		return 0
	}
	for i := 0; i < len(curve)-1; i++ {
		if price >= curve[i].Price && price <= curve[i+1].Price {
			frac := (price - curve[i].Price) / (curve[i+1].Price - curve[i].Price)
			return curve[i].PnL*(1-frac) + curve[i+1].PnL*frac
		}
	}
	if price <= curve[0].Price {
		return curve[0].PnL
	}
	return curve[len(curve)-1].PnL
}
