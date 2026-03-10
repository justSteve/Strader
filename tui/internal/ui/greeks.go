package ui

import (
	"fmt"
	"math"
	"strings"

	"github.com/NimbleMarkets/ntcharts/sparkline"
	"github.com/charmbracelet/lipgloss"
)

// renderGreekProfiles renders 4 sparklines (delta, gamma, theta, vega) across strike range
// using ntcharts sparkline with configurable height.
func (m Model) renderGreekProfiles(w, h int) string {
	title := TitleStyle.Render("Greek Profiles \u2014 Across Strike Range") + "\n"

	gs := m.data.GreeksByStrike
	if len(gs.Strikes) == 0 {
		return title + "No data"
	}

	sparkW := w - 16
	sparkH := (h - 6) / 4
	if sparkH < 2 {
		sparkH = 2
	}
	if sparkW < 10 {
		return title + "Terminal too small"
	}

	type greekProfile struct {
		name   string
		values []float64
		color  lipgloss.Color
	}
	profiles := []greekProfile{
		{"\u0394 Delta", gs.Delta, ColorGreen},
		{"\u0393 Gamma", gs.Gamma, ColorMauve},
		{"\u0398 Theta", gs.Theta, ColorYellow},
		{"V Vega", gs.Vega, ColorBlue},
	}

	var sb strings.Builder
	sb.WriteString(title)

	for _, prof := range profiles {
		// Scale values to positive range for sparkline (ntcharts requires non-negative)
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

		label := lipgloss.NewStyle().
			Width(12).
			Foreground(prof.color).
			Bold(true).
			Render(prof.name)

		zeroCross := findZeroCrossing(prof.values, gs.Strikes)

		sb.WriteString(label + sl.View() + "\n")
		info := fmt.Sprintf("             min:%+.4f  max:%+.4f", minV, maxV)
		if zeroCross != "" {
			info += "  zero:" + zeroCross
		}
		sb.WriteString(SubtitleStyle.Render(info) + "\n")
	}

	// Strike axis labels
	sb.WriteString("\n")
	sb.WriteString(SubtitleStyle.Render(fmt.Sprintf("             %.0f", gs.Strikes[0])))
	padding := sparkW - 10
	if padding > 0 {
		sb.WriteString(strings.Repeat(" ", padding))
	}
	sb.WriteString(SubtitleStyle.Render(fmt.Sprintf("%.0f", gs.Strikes[len(gs.Strikes)-1])))

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
	for i := 1; i < len(vals); i++ {
		if (vals[i-1] > 0 && vals[i] < 0) || (vals[i-1] < 0 && vals[i] > 0) {
			frac := vals[i-1] / (vals[i-1] - vals[i])
			cross := strikes[i-1] + frac*(strikes[i]-strikes[i-1])
			return fmt.Sprintf("~%.0f", cross)
		}
	}
	return ""
}
