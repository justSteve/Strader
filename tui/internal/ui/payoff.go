package ui

import (
	"fmt"
	"math"
	"strings"
)

// renderPayoffCurve draws the butterfly payoff tent shape using braille characters.
func (m Model) renderPayoffCurve(w, h int) string {
	title := titleStyle().Render("Payoff Curve — P&L at Expiration") + "\n"

	points := m.data.PayoffCurve.Points
	if len(points) == 0 {
		return title + "No data"
	}

	// Chart area
	chartW := w - 10 // room for Y labels
	chartH := h - 4  // room for title + X labels
	if chartW < 20 || chartH < 5 {
		return title + "Terminal too small"
	}

	// Find ranges
	minP, maxP := math.MaxFloat64, -math.MaxFloat64
	minX, maxX := points[0].Price, points[len(points)-1].Price
	for _, p := range points {
		if p.PnL < minP {
			minP = p.PnL
		}
		if p.PnL > maxP {
			maxP = p.PnL
		}
	}
	// Add padding
	pRange := maxP - minP
	if pRange == 0 {
		pRange = 1
	}
	minP -= pRange * 0.1
	maxP += pRange * 0.1

	// Build character grid
	grid := make([][]rune, chartH)
	for i := range grid {
		grid[i] = make([]rune, chartW)
		for j := range grid[i] {
			grid[i][j] = ' '
		}
	}

	// Find zero line row
	zeroRow := -1
	if minP < 0 && maxP > 0 {
		zeroRow = chartH - 1 - int(float64(chartH-1)*(0-minP)/(maxP-minP))
	}

	// Draw zero line
	if zeroRow >= 0 && zeroRow < chartH {
		for x := 0; x < chartW; x++ {
			grid[zeroRow][x] = '─'
		}
	}

	// Map data points to grid positions and plot
	for i := 0; i < len(points)-1; i++ {
		x0 := int(float64(chartW-1) * (points[i].Price - minX) / (maxX - minX))
		y0 := chartH - 1 - int(float64(chartH-1)*(points[i].PnL-minP)/(maxP-minP))
		x1 := int(float64(chartW-1) * (points[i+1].Price - minX) / (maxX - minX))
		y1 := chartH - 1 - int(float64(chartH-1)*(points[i+1].PnL-minP)/(maxP-minP))

		// Bresenham line between points
		drawLine(grid, x0, y0, x1, y1, chartW, chartH)
	}

	// Build output with Y labels and coloring
	var sb strings.Builder
	sb.WriteString(title)
	for row := 0; row < chartH; row++ {
		// Y label
		yVal := maxP - float64(row)/float64(chartH-1)*(maxP-minP)
		label := fmt.Sprintf("%+6.1f ", yVal)
		sb.WriteString(subtextStyle().Render(label))

		for col := 0; col < chartW; col++ {
			ch := grid[row][col]
			s := string(ch)
			if ch == '─' {
				sb.WriteString(subtextStyle().Render(s))
			} else if ch != ' ' {
				// Color based on P/L at this position
				yVal := maxP - float64(row)/float64(chartH-1)*(maxP-minP)
				if yVal >= 0 {
					sb.WriteString(greenStyle().Render(s))
				} else {
					sb.WriteString(redStyle().Render(s))
				}
			} else {
				sb.WriteString(s)
			}
		}
		sb.WriteString("\n")
	}

	// X axis labels
	sb.WriteString("       ")
	for i := 0; i <= 4; i++ {
		x := minX + float64(i)/4.0*(maxX-minX)
		label := fmt.Sprintf("%.0f", x)
		pad := chartW/4 - len(label)
		if pad < 0 {
			pad = 0
		}
		if i == 0 {
			sb.WriteString(subtextStyle().Render(label))
		} else {
			sb.WriteString(strings.Repeat(" ", pad))
			sb.WriteString(subtextStyle().Render(label))
		}
	}

	// Breakeven + max profit annotation
	sb.WriteString("\n")
	be := m.data.Strategy.Breakevens
	if len(be) == 2 {
		sb.WriteString(subtextStyle().Render(fmt.Sprintf("       BE: %.1f / %.1f  MaxP: %.2f @ %.0f",
			be[0], be[1], m.data.Strategy.MaxProfit, m.data.Strategy.Legs[1].Strike)))
	}

	return sb.String()
}

// drawLine plots a Bresenham line on the grid.
func drawLine(grid [][]rune, x0, y0, x1, y1, w, h int) {
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
			if grid[y0][x0] == '─' {
				grid[y0][x0] = '╋'
			} else {
				grid[y0][x0] = '●'
			}
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
	if x < 0 {
		return -x
	}
	return x
}
