package ui

import (
	"fmt"
	"math"
	"sort"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/gastown/strader-flytui/internal/data"
)

// renderHeatmap renders a profit heatmap: strike on X-axis, DTE on Y-axis, color = P&L.
func (m Model) renderHeatmap(w, h int) string {
	title := titleStyle().Render("Profit Heatmap — Strike x DTE") + "\n"

	curves := m.data.PayoffByDTE.Curves
	if len(curves) == 0 {
		return title + "No data"
	}

	chartW := w - 12
	chartH := h - 6
	if chartW < 10 || chartH < 4 {
		return title + "Terminal too small"
	}

	// Collect DTE keys sorted descending (30, 15, 7, 1)
	var dteKeys []string
	for k := range curves {
		dteKeys = append(dteKeys, k)
	}
	sort.Slice(dteKeys, func(i, j int) bool {
		var a, b int
		fmt.Sscanf(dteKeys[i], "%d", &a)
		fmt.Sscanf(dteKeys[j], "%d", &b)
		return a > b
	})

	// Find global min/max PnL for color scaling
	globalMin, globalMax := math.MaxFloat64, -math.MaxFloat64
	for _, pts := range curves {
		for _, p := range pts {
			if p.PnL < globalMin {
				globalMin = p.PnL
			}
			if p.PnL > globalMax {
				globalMax = p.PnL
			}
		}
	}

	// Get price range from first curve
	firstKey := dteKeys[0]
	prices := curves[firstKey]
	minPrice := prices[0].Price
	maxPrice := prices[len(prices)-1].Price

	var sb strings.Builder
	sb.WriteString(title)

	// Header with strikes
	sb.WriteString("      DTE  ")
	step := chartW / 5
	if step < 1 {
		step = 1
	}
	for col := 0; col < chartW; col += step {
		price := minPrice + float64(col)/float64(chartW-1)*(maxPrice-minPrice)
		label := fmt.Sprintf("%-8.0f", price)
		sb.WriteString(subtextStyle().Render(label))
	}
	sb.WriteString("\n")

	// Each DTE gets rows proportional to available space
	rowsPerDTE := chartH / len(dteKeys)
	if rowsPerDTE < 1 {
		rowsPerDTE = 1
	}

	for _, dteKey := range dteKeys {
		pts := curves[dteKey]

		// Interpolate to chartW points
		interpolated := interpolateCurve(pts, chartW, minPrice, maxPrice)

		for row := 0; row < rowsPerDTE; row++ {
			if row == 0 {
				label := fmt.Sprintf("    %3s    ", dteKey)
				sb.WriteString(subtextStyle().Render(label))
			} else {
				sb.WriteString("           ")
			}

			for col := 0; col < chartW; col++ {
				pnl := interpolated[col]
				ch, style := heatmapCell(pnl, globalMin, globalMax)
				sb.WriteString(style.Render(string(ch)))
			}
			sb.WriteString("\n")
		}
	}

	// Legend
	sb.WriteString("\n")
	legend := "  " + redStyle().Render("█ Loss") + "  " +
		subtextStyle().Render("░ Break-even") + "  " +
		greenStyle().Render("█ Profit")
	sb.WriteString(legend)
	sb.WriteString(subtextStyle().Render(fmt.Sprintf("    Range: %.1f to +%.1f", globalMin, globalMax)))

	return sb.String()
}

func interpolateCurve(pts []data.PayoffPoint, n int, minP, maxP float64) []float64 {
	result := make([]float64, n)
	for i := 0; i < n; i++ {
		price := minP + float64(i)/float64(n-1)*(maxP-minP)
		result[i] = interpolateAt(pts, price)
	}
	return result
}

func interpolateAt(pts []data.PayoffPoint, price float64) float64 {
	if len(pts) == 0 {
		return 0
	}
	if price <= pts[0].Price {
		return pts[0].PnL
	}
	if price >= pts[len(pts)-1].Price {
		return pts[len(pts)-1].PnL
	}
	for i := 1; i < len(pts); i++ {
		if price <= pts[i].Price {
			frac := (price - pts[i-1].Price) / (pts[i].Price - pts[i-1].Price)
			return pts[i-1].PnL + frac*(pts[i].PnL-pts[i-1].PnL)
		}
	}
	return pts[len(pts)-1].PnL
}

func heatmapCell(pnl, minPnl, maxPnl float64) (rune, lipgloss.Style) {
	var norm float64
	if pnl >= 0 {
		if maxPnl > 0 {
			norm = pnl / maxPnl
		}
	} else {
		if minPnl < 0 {
			norm = -pnl / (-minPnl)
		}
	}

	blocks := []rune{' ', '░', '▒', '▓', '█'}
	idx := int(math.Abs(norm) * float64(len(blocks)-1))
	if idx >= len(blocks) {
		idx = len(blocks) - 1
	}

	if pnl >= 0 {
		return blocks[idx], greenStyle()
	}
	return blocks[idx], redStyle()
}
