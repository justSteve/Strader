package ui

import (
	"fmt"
	"math"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

// renderGEXMatrix renders the Gamma Exposure table with color-coded values.
func (m Model) renderGEXMatrix(w, h int) string {
	gex := m.data.GEXMatrix
	if len(gex.Strikes) == 0 {
		return "No GEX data"
	}

	// Find max magnitude for intensity scaling
	maxMag := 0.0
	for _, v := range gex.CallGEX {
		if math.Abs(v) > maxMag {
			maxMag = math.Abs(v)
		}
	}
	for _, v := range gex.PutGEX {
		if math.Abs(v) > maxMag {
			maxMag = math.Abs(v)
		}
	}
	if maxMag == 0 {
		maxMag = 1
	}

	// Column widths
	strikeW := 8
	gexW := 10

	// Header
	header := fmt.Sprintf("%-*s %*s %*s %*s",
		strikeW, "Strike",
		gexW, "Call GEX",
		gexW, "Put GEX",
		gexW, "Net GEX")
	headerStyled := lipgloss.NewStyle().
		Foreground(ColorBlue).
		Bold(true).
		Render(header)

	sep := lipgloss.NewStyle().
		Foreground(ColorOverlay).
		Render(strings.Repeat("─", strikeW+gexW*3+3))

	var lines []string
	lines = append(lines, headerStyled)
	lines = append(lines, sep)

	for i, strike := range gex.Strikes {
		callV := gex.CallGEX[i]
		putV := gex.PutGEX[i]
		netV := gex.NetGEX[i]

		strikeStr := fmt.Sprintf("%-*s", strikeW, fmt.Sprintf("%.0f", strike))

		callStr := gexValueStyled(callV, maxMag, gexW)
		putStr := gexValueStyled(putV, maxMag, gexW)
		netStr := gexValueStyled(netV, maxMag, gexW)

		// Highlight the ATM strike
		if strike == 5840 {
			strikeStr = HighlightStyle.Render(strikeStr)
		} else {
			strikeStr = lipgloss.NewStyle().Foreground(ColorText).Render(strikeStr)
		}

		line := strikeStr + " " + callStr + " " + putStr + " " + netStr
		lines = append(lines, line)
	}

	// Bar visualization
	lines = append(lines, "")
	lines = append(lines, TitleStyle.Render("Net GEX Distribution"))
	maxNet := 0.0
	for _, v := range gex.NetGEX {
		if v > maxNet {
			maxNet = v
		}
	}
	barW := w - 14
	if barW < 10 {
		barW = 10
	}
	for i, strike := range gex.Strikes {
		barLen := int(float64(barW) * gex.NetGEX[i] / maxNet)
		if barLen < 0 {
			barLen = 0
		}
		bar := strings.Repeat("█", barLen)
		label := fmt.Sprintf("%.0f ", strike)

		intensity := gex.NetGEX[i] / maxNet
		var barColor lipgloss.Color
		if intensity > 0.7 {
			barColor = ColorGreen
		} else if intensity > 0.3 {
			barColor = ColorYellow
		} else {
			barColor = ColorOverlay
		}

		lines = append(lines, SubtitleStyle.Render(label)+lipgloss.NewStyle().Foreground(barColor).Render(bar))
	}

	result := strings.Join(lines, "\n")
	resultLines := strings.Split(result, "\n")
	for len(resultLines) < h {
		resultLines = append(resultLines, "")
	}
	return strings.Join(resultLines[:h], "\n")
}

func gexValueStyled(v, maxMag float64, width int) string {
	str := fmt.Sprintf("%*s", width, fmt.Sprintf("%+.0f", v))
	intensity := math.Abs(v) / maxMag

	if v > 0 {
		if intensity > 0.5 {
			return lipgloss.NewStyle().Foreground(ColorGreen).Bold(true).Render(str)
		}
		return lipgloss.NewStyle().Foreground(ColorGreen).Render(str)
	} else if v < 0 {
		if intensity > 0.5 {
			return lipgloss.NewStyle().Foreground(ColorRed).Bold(true).Render(str)
		}
		return lipgloss.NewStyle().Foreground(ColorRed).Render(str)
	}
	return lipgloss.NewStyle().Foreground(ColorText).Render(str)
}
