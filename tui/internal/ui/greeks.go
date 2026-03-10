package ui

import (
	"fmt"
	"math"
	"strings"

	"github.com/NimbleMarkets/ntcharts/sparkline"
	"github.com/charmbracelet/lipgloss"
)

// renderGreekProfiles renders 4 sparklines (delta, gamma, theta, vega) across strike range.
func (m Model) renderGreekProfiles(w, h int) string {
	title := titleStyle().Render("Greek Profiles — Across Strike Range") + "\n"

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

	type greekData struct {
		name   string
		values []float64
		color  lipgloss.Color
	}
	greeks := []greekData{
		{"Delta (Δ)", gs.Delta, colorGreen},
		{"Gamma (Γ)", gs.Gamma, colorMauve},
		{"Theta (Θ)", gs.Theta, colorYellow},
		{"Vega  (V)", gs.Vega, colorBlue},
	}

	var sb strings.Builder
	sb.WriteString(title)

	for _, g := range greeks {
		// Scale values to positive range for sparkline
		minV, maxV := minMax(g.values)
		offset := 0.0
		if minV < 0 {
			offset = -minV
		}
		scaled := make([]float64, len(g.values))
		for i, v := range g.values {
			scaled[i] = v + offset
		}

		sl := sparkline.New(sparkW, sparkH,
			sparkline.WithMaxValue(maxV+offset),
			sparkline.WithStyle(lipgloss.NewStyle().Foreground(g.color)),
		)
		sl.PushAll(scaled)
		sl.Draw()

		label := lipgloss.NewStyle().
			Width(12).
			Foreground(g.color).
			Bold(true).
			Render(g.name)

		// Find zero crossing
		zeroCross := findZeroCrossing(g.values, gs.Strikes)

		sb.WriteString(label + sl.View() + "\n")
		info := fmt.Sprintf("             min:%+.4f  max:%+.4f", minV, maxV)
		if zeroCross != "" {
			info += "  zero:" + zeroCross
		}
		sb.WriteString(subtextStyle().Render(info) + "\n")
	}

	// Strike labels
	sb.WriteString("\n")
	sb.WriteString(subtextStyle().Render(fmt.Sprintf("             %.0f", gs.Strikes[0])))
	padding := sparkW - 10
	if padding > 0 {
		sb.WriteString(strings.Repeat(" ", padding))
	}
	sb.WriteString(subtextStyle().Render(fmt.Sprintf("%.0f", gs.Strikes[len(gs.Strikes)-1])))

	return sb.String()
}

func minMax(vals []float64) (float64, float64) {
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
			// Linear interpolation
			frac := vals[i-1] / (vals[i-1] - vals[i])
			cross := strikes[i-1] + frac*(strikes[i]-strikes[i-1])
			return fmt.Sprintf("~%.0f", cross)
		}
	}
	return ""
}

// renderGreekStrip renders the bottom strip with mini sparklines for each Greek.
func (m Model) renderGreekStrip(w int) string {
	gs := m.data.GreeksByStrike
	if len(gs.Strikes) == 0 {
		return ""
	}

	sparkW := (w - 40) / 4
	if sparkW < 5 {
		sparkW = 5
	}

	type miniGreek struct {
		label  string
		values []float64
		color  lipgloss.Color
	}
	greeks := []miniGreek{
		{"Δ", gs.Delta, colorGreen},
		{"Γ", gs.Gamma, colorMauve},
		{"Θ", gs.Theta, colorYellow},
		{"V", gs.Vega, colorBlue},
	}

	var parts []string
	for _, g := range greeks {
		minV, _ := minMax(g.values)
		offset := 0.0
		if minV < 0 {
			offset = -minV
		}
		scaled := make([]float64, len(g.values))
		for i, v := range g.values {
			scaled[i] = v + offset
		}

		sl := sparkline.New(sparkW, 1,
			sparkline.WithStyle(lipgloss.NewStyle().Foreground(g.color)),
		)
		sl.PushAll(scaled)
		sl.Draw()

		label := lipgloss.NewStyle().Foreground(g.color).Bold(true).Render(g.label)
		parts = append(parts, " "+label+" "+sl.View()+" ")
	}

	// Status bar
	viewName := "["
	views := []string{"1:Payoff", "2:GEX", "3:Greeks", "4:Heatmap"}
	for i, v := range views {
		if viewMode(i) == m.activeView {
			viewName += mauveStyle().Render(v)
		} else {
			viewName += subtextStyle().Render(v)
		}
		if i < len(views)-1 {
			viewName += " "
		}
	}
	viewName += "]"
	bm := ""
	if m.bitmapMode {
		bm = yellowStyle().Render(" [BITMAP]")
	}
	status := viewName + bm + subtextStyle().Render(" ?=help q=quit")

	return strings.Join(parts, "│") + "  " + status
}
