package ui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

// renderGreekProfiles renders 4 sparkline panels for delta/gamma/theta/vega
// across the strike range, with zero-crossing labels.
func (m Model) renderGreekProfiles(w, h int) string {
	greeks := m.data.GreeksByStrike
	if len(greeks.Strikes) == 0 {
		return "No Greeks data"
	}

	profiles := []struct {
		name   string
		symbol string
		data   []float64
		color  lipgloss.Color
	}{
		{"Delta", "D", greeks.Delta, ColorGreen},
		{"Gamma", "G", greeks.Gamma, ColorMauve},
		{"Theta", "T", greeks.Theta, ColorYellow},
		{"Vega", "V", greeks.Vega, ColorRed},
	}

	panelH := (h - 2) / 4
	if panelH < 3 {
		panelH = 3
	}
	sparkW := w - 16

	var sections []string

	for _, prof := range profiles {
		// Find zero crossing
		zeroCross := ""
		for i := 0; i < len(prof.data)-1; i++ {
			if (prof.data[i] >= 0 && prof.data[i+1] < 0) || (prof.data[i] <= 0 && prof.data[i+1] > 0) {
				zeroCross = fmt.Sprintf("%.0f", greeks.Strikes[i])
				break
			}
		}

		// Find min/max
		minV, maxV := prof.data[0], prof.data[0]
		for _, v := range prof.data {
			if v < minV {
				minV = v
			}
			if v > maxV {
				maxV = v
			}
		}

		// Build sparkline with block chars
		sparkline := renderSparklineChart(prof.data, sparkW, panelH-1, prof.color)

		// Header line
		header := lipgloss.NewStyle().Foreground(prof.color).Bold(true).Render(
			fmt.Sprintf(" %s %-6s", prof.symbol, prof.name))
		rangeStr := SubtitleStyle.Render(
			fmt.Sprintf("[%+.3f..%+.3f]", minV, maxV))

		crossStr := ""
		if zeroCross != "" {
			crossStr = lipgloss.NewStyle().Foreground(ColorYellow).Render(
				fmt.Sprintf(" 0@%s", zeroCross))
		}

		sections = append(sections, header+"  "+rangeStr+crossStr)
		sections = append(sections, sparkline)
		sections = append(sections, "") // spacer
	}

	// X-axis with strike labels
	xLabels := "         "
	step := sparkW / 5
	for i := 0; i <= 4; i++ {
		idx := i * (len(greeks.Strikes) - 1) / 4
		if idx >= len(greeks.Strikes) {
			idx = len(greeks.Strikes) - 1
		}
		label := fmt.Sprintf("%.0f", greeks.Strikes[idx])
		pad := step - len(label)
		if pad < 0 {
			pad = 0
		}
		xLabels += label + strings.Repeat(" ", pad)
	}
	sections = append(sections, SubtitleStyle.Render(xLabels))

	result := strings.Join(sections, "\n")
	resultLines := strings.Split(result, "\n")
	for len(resultLines) < h {
		resultLines = append(resultLines, "")
	}
	return strings.Join(resultLines[:h], "\n")
}

// renderSparklineChart renders a multi-row sparkline using block characters.
func renderSparklineChart(values []float64, w, h int, color lipgloss.Color) string {
	if len(values) == 0 || w <= 0 || h <= 0 {
		return ""
	}

	// Find min/max
	minV, maxV := values[0], values[0]
	for _, v := range values {
		if v < minV {
			minV = v
		}
		if v > maxV {
			maxV = v
		}
	}
	rangeV := maxV - minV
	if rangeV == 0 {
		rangeV = 1
	}

	// Resample values to width
	resampled := make([]float64, w)
	for i := 0; i < w; i++ {
		srcIdx := float64(i) * float64(len(values)-1) / float64(w-1)
		lo := int(srcIdx)
		hi := lo + 1
		if hi >= len(values) {
			hi = len(values) - 1
		}
		frac := srcIdx - float64(lo)
		resampled[i] = values[lo]*(1-frac) + values[hi]*frac
	}

	// Blocks per character cell: using 8 sub-levels
	blocks := []rune{' ', '\u2581', '\u2582', '\u2583', '\u2584', '\u2585', '\u2586', '\u2587', '\u2588'}
	totalLevels := h * 8

	// Normalize values to [0, totalLevels]
	normalized := make([]int, w)
	for i, v := range resampled {
		n := int(float64(totalLevels) * (v - minV) / rangeV)
		if n < 0 {
			n = 0
		}
		if n > totalLevels {
			n = totalLevels
		}
		normalized[i] = n
	}

	// Build grid bottom-up
	var rows []string
	for row := h - 1; row >= 0; row-- {
		var line strings.Builder
		line.WriteString("         ") // left margin
		for col := 0; col < w; col++ {
			level := normalized[col] - row*8
			if level <= 0 {
				line.WriteRune(' ')
			} else if level >= 8 {
				line.WriteRune(blocks[8])
			} else {
				line.WriteRune(blocks[level])
			}
		}
		rows = append([]string{lipgloss.NewStyle().Foreground(color).Render(line.String())}, rows...)
	}

	return strings.Join(rows, "\n")
}
