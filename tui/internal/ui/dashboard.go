package ui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

// renderDashboard renders the Position Dashboard with styled panels.
func (m Model) renderDashboard(w, h int) string {
	strat := m.data.Strategy
	agg := strat.Aggregate
	und := m.data.Underlying

	// Underlying info
	undPanel := m.dashPanel("Underlying", w-4, []dashRow{
		{und.Symbol, fmt.Sprintf("%.2f", und.Price), ColorText},
		{"Change", fmt.Sprintf("%+.2f (%.2f%%)", und.Change, und.ChangePct), colorForValue(und.Change)},
		{"IV30", fmt.Sprintf("%.1f%%", und.IV30), ColorYellow},
		{"IV60", fmt.Sprintf("%.1f%%", und.IV60), ColorYellow},
	})

	// Strategy info
	stratPanel := m.dashPanel("Strategy", w-4, []dashRow{
		{"Name", strat.Name, ColorBlue},
		{"Variant", strat.Variant, ColorText},
		{"Expiration", strat.Expiration, ColorText},
		{"DTE", fmt.Sprintf("%d days", strat.DTE), dteColor(strat.DTE)},
	})

	// Greeks panel
	greeksPanel := m.dashPanel("Net Greeks", w-4, []dashRow{
		{"Delta (D)", fmt.Sprintf("%+.4f", agg.Delta), colorForValue(agg.Delta)},
		{"Gamma (G)", fmt.Sprintf("%+.4f", agg.Gamma), colorForValue(agg.Gamma)},
		{"Theta (T)", fmt.Sprintf("%+.4f", agg.Theta), colorForValue(agg.Theta)},
		{"Vega  (V)", fmt.Sprintf("%+.4f", agg.Vega), colorForValue(agg.Vega)},
	})

	// P&L panel
	pnlPanel := m.dashPanel("P&L Metrics", w-4, []dashRow{
		{"Net Debit", fmt.Sprintf("$%.2f", strat.NetDebit), ColorRed},
		{"Max Profit", fmt.Sprintf("$%.2f", strat.MaxProfit), ColorGreen},
		{"Max Loss", fmt.Sprintf("$%.2f", strat.MaxLoss), ColorRed},
		{"Risk/Reward", fmt.Sprintf("%.1f:1", strat.MaxProfit/strat.MaxLoss), ColorYellow},
		{"B/E Low", fmt.Sprintf("%.2f", strat.Breakevens[0]), ColorText},
		{"B/E High", fmt.Sprintf("%.2f", strat.Breakevens[1]), ColorText},
	})

	// P&L gauge: current P&L as percentage of max profit
	currentPnL := 0.0 // at-the-money approximation
	for _, p := range m.data.PayoffCurve.Points {
		if p.Price == m.data.Underlying.Price {
			currentPnL = p.PnL
			break
		}
	}
	// Find closest point
	if currentPnL == 0 {
		closestDist := 999999.0
		for _, p := range m.data.PayoffCurve.Points {
			dist := p.Price - m.data.Underlying.Price
			if dist < 0 {
				dist = -dist
			}
			if dist < closestDist {
				closestDist = dist
				currentPnL = p.PnL
			}
		}
	}

	gaugeW := w - 8
	if gaugeW < 20 {
		gaugeW = 20
	}
	gauge := renderGauge(currentPnL, strat.MaxLoss, strat.MaxProfit, gaugeW)

	// DTE countdown bar
	maxDTE := 30 // assume 30-day cycle
	dteBarW := w - 8
	dtePct := float64(strat.DTE) / float64(maxDTE)
	if dtePct > 1 {
		dtePct = 1
	}
	dteFilled := int(dtePct * float64(dteBarW))
	dteBar := lipgloss.NewStyle().Foreground(dteColor(strat.DTE)).Render(strings.Repeat("█", dteFilled))
	dteBar += lipgloss.NewStyle().Foreground(ColorOverlay).Render(strings.Repeat("░", dteBarW-dteFilled))
	dteStr := fmt.Sprintf("  DTE: %d/%d  %s", strat.DTE, maxDTE, dteBar)

	sections := []string{undPanel, stratPanel, greeksPanel, pnlPanel}

	// Arrange in two columns if width allows
	if w > 60 {
		halfW := (w - 4) / 2
		left := lipgloss.JoinVertical(lipgloss.Left,
			m.dashPanel("Underlying", halfW, []dashRow{
				{und.Symbol, fmt.Sprintf("%.2f", und.Price), ColorText},
				{"Change", fmt.Sprintf("%+.2f (%.2f%%)", und.Change, und.ChangePct), colorForValue(und.Change)},
				{"IV30/60", fmt.Sprintf("%.1f%% / %.1f%%", und.IV30, und.IV60), ColorYellow},
			}),
			m.dashPanel("Net Greeks", halfW, []dashRow{
				{"Delta", fmt.Sprintf("%+.4f", agg.Delta), colorForValue(agg.Delta)},
				{"Gamma", fmt.Sprintf("%+.4f", agg.Gamma), colorForValue(agg.Gamma)},
				{"Theta", fmt.Sprintf("%+.4f", agg.Theta), colorForValue(agg.Theta)},
				{"Vega", fmt.Sprintf("%+.4f", agg.Vega), colorForValue(agg.Vega)},
			}),
		)
		right := lipgloss.JoinVertical(lipgloss.Left,
			m.dashPanel("Strategy", halfW, []dashRow{
				{"Name", strat.Name, ColorBlue},
				{"Exp", strat.Expiration, ColorText},
				{"DTE", fmt.Sprintf("%d days", strat.DTE), dteColor(strat.DTE)},
			}),
			m.dashPanel("P&L", halfW, []dashRow{
				{"Debit", fmt.Sprintf("$%.2f", strat.NetDebit), ColorRed},
				{"MaxProfit", fmt.Sprintf("$%.2f", strat.MaxProfit), ColorGreen},
				{"MaxLoss", fmt.Sprintf("$%.2f", strat.MaxLoss), ColorRed},
				{"R:R", fmt.Sprintf("%.1f:1", strat.MaxProfit/strat.MaxLoss), ColorYellow},
				{"B/E", fmt.Sprintf("%.2f / %.2f", strat.Breakevens[0], strat.Breakevens[1]), ColorText},
			}),
		)
		content := lipgloss.JoinHorizontal(lipgloss.Top, left, "  ", right)

		var resultLines []string
		resultLines = append(resultLines, content)
		resultLines = append(resultLines, "")
		resultLines = append(resultLines, gauge)
		resultLines = append(resultLines, dteStr)

		result := strings.Join(resultLines, "\n")
		rLines := strings.Split(result, "\n")
		for len(rLines) < h {
			rLines = append(rLines, "")
		}
		return strings.Join(rLines[:h], "\n")
	}

	// Single column fallback
	result := strings.Join(sections, "\n")
	result += "\n\n" + gauge + "\n" + dteStr

	resultLines := strings.Split(result, "\n")
	for len(resultLines) < h {
		resultLines = append(resultLines, "")
	}
	return strings.Join(resultLines[:h], "\n")
}

type dashRow struct {
	label string
	value string
	color lipgloss.Color
}

func (m Model) dashPanel(title string, w int, rows []dashRow) string {
	var lines []string
	titleStr := lipgloss.NewStyle().Foreground(ColorBlue).Bold(true).
		Render("  " + title)
	lines = append(lines, titleStr)

	sep := lipgloss.NewStyle().Foreground(ColorOverlay).
		Render("  " + strings.Repeat("─", w-4))
	lines = append(lines, sep)

	for _, r := range rows {
		pad := w - len(r.label) - len(r.value) - 6
		if pad < 1 {
			pad = 1
		}
		valStyled := lipgloss.NewStyle().Foreground(r.color).Render(r.value)
		lines = append(lines, "  "+SubtitleStyle.Render(r.label)+strings.Repeat(" ", pad)+valStyled)
	}
	lines = append(lines, "")
	return strings.Join(lines, "\n")
}

func renderGauge(current, minV, maxV float64, w int) string {
	rangeV := maxV - minV
	if rangeV == 0 {
		rangeV = 1
	}
	pct := (current - minV) / rangeV
	if pct < 0 {
		pct = 0
	}
	if pct > 1 {
		pct = 1
	}

	filled := int(pct * float64(w))
	var color lipgloss.Color
	if current > 0 {
		color = ColorGreen
	} else {
		color = ColorRed
	}

	bar := lipgloss.NewStyle().Foreground(color).Render(strings.Repeat("█", filled))
	bar += lipgloss.NewStyle().Foreground(ColorOverlay).Render(strings.Repeat("░", w-filled))

	label := fmt.Sprintf("  P&L: %+.2f (%+.0f%%)", current, pct*100-50)
	return label + "\n  " + bar
}

func colorForValue(v float64) lipgloss.Color {
	if v > 0 {
		return ColorGreen
	} else if v < 0 {
		return ColorRed
	}
	return ColorText
}

func dteColor(dte int) lipgloss.Color {
	if dte <= 3 {
		return ColorRed
	} else if dte <= 7 {
		return ColorYellow
	}
	return ColorGreen
}
