package ui

import (
	"fmt"
	"math"
	"strings"

	"github.com/NimbleMarkets/ntcharts/sparkline"
	"github.com/charmbracelet/lipgloss"
)

// renderGreekProfiles renders 4 sparklines (Delta, Gamma, Theta, Vega) across
// the strike range using ntcharts sparkline. Each shows the zero-crossing zone
// and min/max values.
func (m Model) renderGreekProfiles(w, h int) string {
	gs := m.data.GreeksByStrike
	if len(gs.Strikes) == 0 {
		return "No Greek data available"
	}

	sparkW := w - 18
	sparkH := (h - 8) / 4
	if sparkH < 2 {
		sparkH = 2
	}
	if sparkH > 4 {
		sparkH = 4
	}
	if sparkW < 10 {
		return "Terminal too narrow for Greek profiles"
	}

	type greekProfile struct {
		symbol string
		name   string
		values []float64
		color  lipgloss.Color
	}

	profiles := []greekProfile{
		{"\u0394", "Delta", gs.Delta, ColorGreen},
		{"\u0393", "Gamma", gs.Gamma, ColorMauve},
		{"\u0398", "Theta", gs.Theta, ColorYellow},
		{"V", "Vega", gs.Vega, ColorBlue},
	}

	var sb strings.Builder

	// Title
	sb.WriteString(TitleStyle.Render("  Greek Profiles \u2014 Net Position Across Strike Range"))
	sb.WriteString("\n")

	for _, prof := range profiles {
		// Scale values to non-negative range for ntcharts
		minV, maxV := greekMinMax(prof.values)
		offset := 0.0
		if minV < 0 {
			offset = -minV
		}
		scaled := make([]float64, len(prof.values))
		for i, v := range prof.values {
			scaled[i] = v + offset
		}

		sl := sparkline.New(sparkW, sparkH,
			sparkline.WithMaxValue(maxV+offset),
			sparkline.WithStyle(lipgloss.NewStyle().Foreground(prof.color)),
		)
		sl.PushAll(scaled)
		sl.Draw()

		// Label column: symbol + name
		label := lipgloss.NewStyle().
			Width(14).
			Foreground(prof.color).
			Bold(true).
			Render(fmt.Sprintf(" %s %s", prof.symbol, prof.name))

		sb.WriteString(label + sl.View())
		sb.WriteString("\n")

		// Stats line: min, max, zero-crossing, current value at underlying price
		zeroCross := findZeroCrossing(prof.values, gs.Strikes)
		statsLine := fmt.Sprintf("               min:%s  max:%s",
			formatGreekValue(minV, prof.color),
			formatGreekValue(maxV, prof.color),
		)
		if zeroCross != "" {
			statsLine += "  " + DimStyle.Render("0\u2192") + SubtitleStyle.Render(zeroCross)
		}
		sb.WriteString(SubtitleStyle.Render(statsLine))
		sb.WriteString("\n")
	}

	// Strike axis with range labels
	sb.WriteString("\n")
	axisLabel := fmt.Sprintf("              %s%s%s",
		SubtitleStyle.Render(fmt.Sprintf("%.0f", gs.Strikes[0])),
		strings.Repeat(" ", sparkW-10),
		SubtitleStyle.Render(fmt.Sprintf("%.0f", gs.Strikes[len(gs.Strikes)-1])),
	)
	sb.WriteString(axisLabel)

	// Underlying price marker
	sb.WriteString("\n")
	undPrice := m.data.Underlying.Price
	if undPrice >= gs.Strikes[0] && undPrice <= gs.Strikes[len(gs.Strikes)-1] {
		pct := (undPrice - gs.Strikes[0]) / (gs.Strikes[len(gs.Strikes)-1] - gs.Strikes[0])
		markerPos := 14 + int(pct*float64(sparkW))
		marker := strings.Repeat(" ", markerPos) + HighlightStyle.Render("\u25b2") // ▲
		sb.WriteString(marker)
		sb.WriteString(" " + HighlightStyle.Render(fmt.Sprintf("SPX %.0f", undPrice)))
	}

	return sb.String()
}

func greekMinMax(vals []float64) (float64, float64) {
	mn, mx := math.MaxFloat64, -math.MaxFloat64
	for _, v := range vals {
		if v < mn {
			mn = v
		}
		if v > mx {
			mx = v
		}
	}
	return mn, mx
}

func findZeroCrossing(vals []float64, strikes []float64) string {
	var crossings []string
	for i := 1; i < len(vals); i++ {
		if (vals[i-1] > 0 && vals[i] < 0) || (vals[i-1] < 0 && vals[i] > 0) {
			frac := vals[i-1] / (vals[i-1] - vals[i])
			cross := strikes[i-1] + frac*(strikes[i]-strikes[i-1])
			crossings = append(crossings, fmt.Sprintf("~%.0f", cross))
		}
	}
	if len(crossings) == 0 {
		return ""
	}
	return strings.Join(crossings, ", ")
}

func formatGreekValue(v float64, color lipgloss.Color) string {
	s := fmt.Sprintf("%+.4f", v)
	return lipgloss.NewStyle().Foreground(color).Render(s)
}
