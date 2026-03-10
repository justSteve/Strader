package ui

import (
	"fmt"
	"math"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/gastown/strader-flytui/internal/data"
)

// renderPayoffCurve draws the butterfly tent shape with multi-DTE overlay.
// Uses Bresenham line drawing with color-coded profit/loss regions.
func (m Model) renderPayoffCurve(w, h int) string {
	if w < 10 || h < 5 {
		return "Panel too small"
	}

	points := m.data.PayoffCurve.Points
	if len(points) == 0 {
		return "No payoff data"
	}

	// Reserve space for Y-axis labels, X-axis, and legend
	chartW := w - 8
	chartH := h - 4
	if chartW < 10 {
		chartW = 10
	}
	if chartH < 4 {
		chartH = 4
	}

	// Find unified data range across all curves
	minPrice, maxPrice := points[0].Price, points[len(points)-1].Price
	minPnL, maxPnL := findPnLRange(points)

	for _, curve := range m.data.PayoffByDTE.Curves {
		lo, hi := findPnLRange(curve)
		if lo < minPnL {
			minPnL = lo
		}
		if hi > maxPnL {
			maxPnL = hi
		}
	}

	// Add margin
	margin := (maxPnL - minPnL) * 0.05
	minPnL -= margin
	maxPnL += margin

	pnlRange := maxPnL - minPnL
	if pnlRange == 0 {
		pnlRange = 1
	}
	priceRange := maxPrice - minPrice
	if priceRange == 0 {
		priceRange = 1
	}

	// Character + color grids
	grid := make([][]rune, chartH)
	colorGrid := make([][]lipgloss.Color, chartH)
	for i := range grid {
		grid[i] = make([]rune, chartW)
		colorGrid[i] = make([]lipgloss.Color, chartW)
		for j := range grid[i] {
			grid[i][j] = ' '
		}
	}

	// Draw zero line
	zeroY := clampInt(chartH-1-int(float64(chartH-1)*(0-minPnL)/pnlRange), 0, chartH-1)
	for x := 0; x < chartW; x++ {
		if grid[zeroY][x] == ' ' {
			grid[zeroY][x] = '─'
			colorGrid[zeroY][x] = ColorOverlay0
		}
	}

	// Draw breakeven markers
	for _, be := range m.data.Strategy.Breakevens {
		bx := clampInt(int(float64(chartW-1)*(be-minPrice)/priceRange), 0, chartW-1)
		if grid[zeroY][bx] == '─' {
			grid[zeroY][bx] = '┼'
			colorGrid[zeroY][bx] = ColorYellow
		}
	}

	// Plot DTE curves (dim to bright: 30D, 15D, 7D, 1D)
	dteOrder := []string{"30", "15", "7", "1"}
	dteColors := []lipgloss.Color{ColorDTE30, ColorDTE15, ColorDTE7, ColorDTE1}
	dteChars := []rune{'·', '·', '·', '•'}

	for ci, dte := range dteOrder {
		curve, ok := m.data.PayoffByDTE.Curves[dte]
		if !ok {
			continue
		}
		plotCurve(grid, colorGrid, curve, chartW, chartH, minPrice, priceRange, minPnL, pnlRange, dteColors[ci], dteChars[ci])
	}

	// Plot expiration curve on top — the definitive tent shape
	plotCurve(grid, colorGrid, points, chartW, chartH, minPrice, priceRange, minPnL, pnlRange, ColorText, '●')

	// Color-code expiration curve: green above zero, red below
	for _, p := range points {
		x := clampInt(int(float64(chartW-1)*(p.Price-minPrice)/priceRange), 0, chartW-1)
		y := clampInt(chartH-1-int(float64(chartH-1)*(p.PnL-minPnL)/pnlRange), 0, chartH-1)
		if p.PnL > 0 {
			colorGrid[y][x] = ColorGreen
		} else if p.PnL < 0 {
			colorGrid[y][x] = ColorRed
		}
	}

	// Render grid to string
	var lines []string
	for row := 0; row < chartH; row++ {
		pnl := maxPnL - float64(row)*(pnlRange)/float64(chartH-1)
		label := fmt.Sprintf("%+5.1f", pnl)
		if len(label) > 6 {
			label = label[:6]
		}

		var rowStr strings.Builder
		rowStr.WriteString(SubtitleStyle.Render(label) + " \u2502")
		for col := 0; col < chartW; col++ {
			ch := string(grid[row][col])
			if colorGrid[row][col] != "" {
				ch = lipgloss.NewStyle().Foreground(colorGrid[row][col]).Render(ch)
			}
			rowStr.WriteString(ch)
		}
		lines = append(lines, rowStr.String())
	}

	// X-axis
	xAxis := strings.Repeat(" ", 8)
	step := chartW / 5
	if step < 1 {
		step = 1
	}
	for i := 0; i <= 4; i++ {
		x := i * step
		price := minPrice + float64(x)*priceRange/float64(chartW-1)
		label := fmt.Sprintf("%.0f", price)
		pad := step - len(label)
		if pad < 0 {
			pad = 0
		}
		xAxis += label + strings.Repeat(" ", pad)
	}
	lines = append(lines, SubtitleStyle.Render(xAxis))

	// Legend with colored markers
	legend := "  "
	legend += lipgloss.NewStyle().Foreground(ColorText).Render("● Exp") + "  "
	legend += lipgloss.NewStyle().Foreground(ColorDTE1).Render("• 1D") + "  "
	legend += lipgloss.NewStyle().Foreground(ColorDTE7).Render("· 7D") + "  "
	legend += lipgloss.NewStyle().Foreground(ColorDTE15).Render("· 15D") + "  "
	legend += lipgloss.NewStyle().Foreground(ColorDTE30).Render("· 30D") + "  "
	legend += DimStyle.Render("┼ B/E")
	lines = append(lines, legend)

	return padLines(strings.Join(lines, "\n"), h)
}

// plotCurve draws a series of payoff points onto the grid using Bresenham lines.
func plotCurve(grid [][]rune, colorGrid [][]lipgloss.Color, points []data.PayoffPoint, w, h int, minPrice, priceRange, minPnL, pnlRange float64, color lipgloss.Color, ch rune) {
	for i := 0; i < len(points)-1; i++ {
		x0 := clampInt(int(float64(w-1)*(points[i].Price-minPrice)/priceRange), 0, w-1)
		y0 := clampInt(h-1-int(float64(h-1)*(points[i].PnL-minPnL)/pnlRange), 0, h-1)
		x1 := clampInt(int(float64(w-1)*(points[i+1].Price-minPrice)/priceRange), 0, w-1)
		y1 := clampInt(h-1-int(float64(h-1)*(points[i+1].PnL-minPnL)/pnlRange), 0, h-1)
		bresenham(grid, colorGrid, x0, y0, x1, y1, w, h, color, ch)
	}
}

// bresenham draws a line between two points on the grid.
func bresenham(grid [][]rune, colorGrid [][]lipgloss.Color, x0, y0, x1, y1, w, h int, color lipgloss.Color, ch rune) {
	dx := intAbs(x1 - x0)
	dy := intAbs(y1 - y0)
	sx, sy := 1, 1
	if x0 > x1 {
		sx = -1
	}
	if y0 > y1 {
		sy = -1
	}
	err := dx - dy

	for {
		if x0 >= 0 && x0 < w && y0 >= 0 && y0 < h {
			if grid[y0][x0] == ' ' || grid[y0][x0] == '─' || grid[y0][x0] == '·' {
				grid[y0][x0] = ch
			}
			colorGrid[y0][x0] = color
		}
		if x0 == x1 && y0 == y1 {
			break
		}
		e2 := 2 * err
		if e2 > -dy {
			err -= dy
			x0 += sx
		}
		if e2 < dx {
			err += dx
			y0 += sy
		}
	}
}

func findPnLRange(points []data.PayoffPoint) (float64, float64) {
	if len(points) == 0 {
		return 0, 0
	}
	mn, mx := points[0].PnL, points[0].PnL
	for _, p := range points {
		if p.PnL < mn {
			mn = p.PnL
		}
		if p.PnL > mx {
			mx = p.PnL
		}
	}
	return mn, mx
}

func intAbs(x int) int {
	return int(math.Abs(float64(x)))
}

func clampInt(v, lo, hi int) int {
	if v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}
