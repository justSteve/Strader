package ui

import (
	"fmt"
	"math"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/gastown/strader-flytui/internal/data"
)

// renderPayoffCurve draws the butterfly tent shape using braille characters.
// Overlays multiple DTE curves showing tent sharpening.
func (m Model) renderPayoffCurve(w, h int) string {
	if w < 10 || h < 5 {
		return "Panel too small"
	}

	points := m.data.PayoffCurve.Points
	if len(points) == 0 {
		return "No payoff data"
	}

	// Reserve space for axes labels
	chartW := w - 8
	chartH := h - 3
	if chartW < 10 {
		chartW = 10
	}
	if chartH < 4 {
		chartH = 4
	}

	// Find data range
	minPrice, maxPrice := points[0].Price, points[len(points)-1].Price
	minPnL, maxPnL := points[0].PnL, points[0].PnL
	for _, p := range points {
		if p.PnL < minPnL {
			minPnL = p.PnL
		}
		if p.PnL > maxPnL {
			maxPnL = p.PnL
		}
	}
	// Also check DTE curves for range
	for _, curve := range m.data.PayoffByDTE.Curves {
		for _, p := range curve {
			if p.PnL < minPnL {
				minPnL = p.PnL
			}
			if p.PnL > maxPnL {
				maxPnL = p.PnL
			}
		}
	}

	pnlRange := maxPnL - minPnL
	if pnlRange == 0 {
		pnlRange = 1
	}
	priceRange := maxPrice - minPrice
	if priceRange == 0 {
		priceRange = 1
	}

	// Create character grid
	grid := make([][]rune, chartH)
	colorGrid := make([][]lipgloss.Color, chartH)
	for i := range grid {
		grid[i] = make([]rune, chartW)
		colorGrid[i] = make([]lipgloss.Color, chartW)
		for j := range grid[i] {
			grid[i][j] = ' '
		}
	}

	// Find zero line
	zeroY := chartH - 1 - int(float64(chartH-1)*(0-minPnL)/pnlRange)
	if zeroY < 0 {
		zeroY = 0
	}
	if zeroY >= chartH {
		zeroY = chartH - 1
	}

	// Draw zero line
	for x := 0; x < chartW; x++ {
		if grid[zeroY][x] == ' ' {
			grid[zeroY][x] = '─'
			colorGrid[zeroY][x] = ColorOverlay
		}
	}

	// Plot DTE curves (dimmer) first
	dteOrder := []string{"30", "15", "7", "1"}
	dteColors := []lipgloss.Color{
		lipgloss.Color("#585b70"),
		lipgloss.Color("#7f849c"),
		lipgloss.Color("#9399b2"),
		ColorYellow,
	}

	for ci, dte := range dteOrder {
		curve, ok := m.data.PayoffByDTE.Curves[dte]
		if !ok {
			continue
		}
		plotPoints(grid, colorGrid, curve, chartW, chartH, minPrice, priceRange, minPnL, pnlRange, dteColors[ci])
	}

	// Plot expiration curve (main) on top
	plotPoints(grid, colorGrid, points, chartW, chartH, minPrice, priceRange, minPnL, pnlRange, ColorText)

	// Color profit green, loss red for expiration curve
	for _, p := range points {
		x := int(float64(chartW-1) * (p.Price - minPrice) / priceRange)
		y := chartH - 1 - int(float64(chartH-1)*(p.PnL-minPnL)/pnlRange)
		if x >= 0 && x < chartW && y >= 0 && y < chartH {
			if p.PnL > 0 {
				colorGrid[y][x] = ColorGreen
			} else if p.PnL < 0 {
				colorGrid[y][x] = ColorRed
			}
		}
	}

	// Render grid to string
	var lines []string

	// Y-axis labels
	for row := 0; row < chartH; row++ {
		pnl := maxPnL - float64(row)*(pnlRange)/float64(chartH-1)
		label := fmt.Sprintf("%+5.1f", pnl)
		if len(label) > 6 {
			label = label[:6]
		}

		var rowStr strings.Builder
		rowStr.WriteString(SubtitleStyle.Render(label) + " ")
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
	xAxis := strings.Repeat(" ", 7)
	step := chartW / 5
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

	// Legend
	legend := fmt.Sprintf("  %s Exp  %s 1D  %s 7D  %s 15D  %s 30D",
		lipgloss.NewStyle().Foreground(ColorText).Render("*"),
		lipgloss.NewStyle().Foreground(dteColors[3]).Render("*"),
		lipgloss.NewStyle().Foreground(dteColors[2]).Render("*"),
		lipgloss.NewStyle().Foreground(dteColors[1]).Render("*"),
		lipgloss.NewStyle().Foreground(dteColors[0]).Render("*"),
	)
	lines = append(lines, legend)

	result := strings.Join(lines, "\n")

	// Pad to fill height
	resultLines := strings.Split(result, "\n")
	for len(resultLines) < h {
		resultLines = append(resultLines, "")
	}

	return strings.Join(resultLines[:h], "\n")
}

func plotPoints(grid [][]rune, colorGrid [][]lipgloss.Color, points []data.PayoffPoint, w, h int, minPrice, priceRange, minPnL, pnlRange float64, color lipgloss.Color) {
	for i := 0; i < len(points)-1; i++ {
		x0 := int(float64(w-1) * (points[i].Price - minPrice) / priceRange)
		y0 := h - 1 - int(float64(h-1)*(points[i].PnL-minPnL)/pnlRange)
		x1 := int(float64(w-1) * (points[i+1].Price - minPrice) / priceRange)
		y1 := h - 1 - int(float64(h-1)*(points[i+1].PnL-minPnL)/pnlRange)

		drawLine(grid, colorGrid, x0, y0, x1, y1, w, h, color)
	}
}

func drawLine(grid [][]rune, colorGrid [][]lipgloss.Color, x0, y0, x1, y1, w, h int, color lipgloss.Color) {
	dx := abs(x1 - x0)
	dy := abs(y1 - y0)
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
			if grid[y0][x0] == ' ' || grid[y0][x0] == '─' {
				grid[y0][x0] = '*'
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

func abs(x int) int {
	return int(math.Abs(float64(x)))
}
