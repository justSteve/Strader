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
func (m Model) renderProfitHeatmap(w, h int) string {
	curves := m.data.PayoffByDTE.Curves
	if len(curves) == 0 {
		return "No heatmap data"
	}

	// Sort DTE keys descending
	var dteKeys []int
	for k := range curves {
		d, _ := strconv.Atoi(k)
		dteKeys = append(dteKeys, d)
	}
	sort.Sort(sort.Reverse(sort.IntSlice(dteKeys)))

	// Interpolate additional DTE rows
	allDTEs := interpolateDTEs(dteKeys)

	prices := m.data.PayoffCurve.Points
	if len(prices) == 0 {
		return "No price data"
	}

	labelW := 6
	hmW := w - labelW - 2
	hmH := h - 4
	if hmW < 10 {
		hmW = 10
	}
	if hmH < 4 {
		hmH = 4
	}

	// Find global P&L range
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

	// Title row
	lines = append(lines, TitleStyle.Render("  DTE")+"  "+SubtitleStyle.Render(
		fmt.Sprintf("%.0f%s%.0f", minPrice, strings.Repeat(" ", hmW-8), maxPrice)))

	for _, dte := range allDTEs {
		if len(lines) >= hmH+1 {
			break
		}

		row := interpolateRow(curves, dteKeys, dte, hmW, minPrice, priceRange)

		label := fmt.Sprintf("%3dd ", dte)
		var rowStr strings.Builder
		rowStr.WriteString(SubtitleStyle.Render(label))

		for _, pnl := range row {
			ch, fg, bg := heatmapCell(pnl, minPnL, maxPnL)
			style := lipgloss.NewStyle()
			if fg != "" {
				style = style.Foreground(fg)
			}
			if bg != "" {
				style = style.Background(bg)
			}
			rowStr.WriteString(style.Render(string(ch)))
		}
		lines = append(lines, rowStr.String())
	}

	// Legend
	lines = append(lines, "")
	legend := fmt.Sprintf("  %s Loss  %s Break-even  %s Profit",
		NegativeStyle.Render("##"),
		SubtitleStyle.Render(".."),
		PositiveStyle.Render("##"))
	lines = append(lines, legend)

	result := strings.Join(lines, "\n")
	resultLines := strings.Split(result, "\n")
	for len(resultLines) < h {
		resultLines = append(resultLines, "")
	}
	return strings.Join(resultLines[:h], "\n")
}

func interpolateDTEs(keys []int) []int {
	if len(keys) < 2 {
		return keys
	}
	var result []int
	for i := 0; i < len(keys)-1; i++ {
		result = append(result, keys[i])
		mid := (keys[i] + keys[i+1]) / 2
		if mid != keys[i] && mid != keys[i+1] {
			result = append(result, mid)
		}
	}
	result = append(result, keys[len(keys)-1])
	return result
}

func interpolateRow(curves map[string][]data.PayoffPoint, dteKeys []int, dte, w int, minPrice, priceRange float64) []float64 {
	// Find bracketing DTEs
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

func heatmapCell(pnl, minPnL, maxPnL float64) (rune, lipgloss.Color, lipgloss.Color) {
	if maxPnL == minPnL {
		return ' ', ColorSubtext, ""
	}

	if pnl > 0 {
		intensity := math.Min(pnl/maxPnL, 1.0)
		if intensity > 0.7 {
			return '\u2588', ColorGreen, "" // full block
		} else if intensity > 0.3 {
			return '\u2593', ColorGreen, "" // dark shade
		}
		return '\u2591', ColorGreen, "" // light shade
	} else if pnl < 0 {
		intensity := math.Min(math.Abs(pnl)/math.Abs(minPnL), 1.0)
		if intensity > 0.7 {
			return '\u2588', ColorRed, ""
		} else if intensity > 0.3 {
			return '\u2593', ColorRed, ""
		}
		return '\u2591', ColorRed, ""
	}
	return '\u00B7', ColorSubtext, "" // middle dot
}
