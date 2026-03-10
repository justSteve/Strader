package ui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

// renderDashboard renders a comprehensive Position Dashboard with styled panels,
// P&L gauge, and DTE countdown.
func (m Model) renderDashboard(w, h int) string {
	// Find current P&L from underlying price
	currentPnL := findCurrentPnL(m)

	if w > 56 {
		return m.renderDashboardTwoCol(w, h, currentPnL)
	}
	return m.renderDashboardOneCol(w, h, currentPnL)
}

func (m Model) renderDashboardTwoCol(w, h int, currentPnL float64) string {
	strat := m.data.Strategy
	agg := strat.Aggregate
	und := m.data.Underlying

	halfW := (w - 4) / 2

	left := lipgloss.JoinVertical(lipgloss.Left,
		dashPanel("Underlying", halfW, []dashRow{
			{und.Symbol, fmt.Sprintf("%.2f", und.Price), ColorText},
			{"Change", fmt.Sprintf("%+.2f (%+.2f%%)", und.Change, und.ChangePct), ValueColor(und.Change)},
			{"IV 30/60", fmt.Sprintf("%.1f%% / %.1f%%", und.IV30, und.IV60), ColorYellow},
		}),
		dashPanel("Net Greeks", halfW, []dashRow{
			{"\u0394 Delta", fmt.Sprintf("%+.4f", agg.Delta), ValueColor(agg.Delta)},
			{"\u0393 Gamma", fmt.Sprintf("%+.4f", agg.Gamma), ValueColor(agg.Gamma)},
			{"\u0398 Theta", fmt.Sprintf("%+.4f", agg.Theta), ValueColor(agg.Theta)},
			{"V Vega", fmt.Sprintf("%+.4f", agg.Vega), ValueColor(agg.Vega)},
		}),
	)

	right := lipgloss.JoinVertical(lipgloss.Left,
		dashPanel("Strategy", halfW, []dashRow{
			{"Type", strat.Name, ColorBlue},
			{"Variant", strat.Variant, ColorText},
			{"Expires", strat.Expiration, ColorText},
			{"DTE", fmt.Sprintf("%d days", strat.DTE), dteColor(strat.DTE)},
		}),
		dashPanel("P&L Metrics", halfW, []dashRow{
			{"Debit", fmt.Sprintf("$%.2f", strat.NetDebit), ColorRed},
			{"Max Profit", fmt.Sprintf("$%.2f", strat.MaxProfit), ColorGreen},
			{"Max Loss", fmt.Sprintf("$%.2f", strat.MaxLoss), ColorRed},
			{"Risk:Reward", fmt.Sprintf("%.1f:1", strat.MaxProfit/strat.MaxLoss), ColorYellow},
			{"B/E Low", fmt.Sprintf("%.2f", strat.Breakevens[0]), ColorText},
			{"B/E High", fmt.Sprintf("%.2f", strat.Breakevens[1]), ColorText},
		}),
	)

	content := lipgloss.JoinHorizontal(lipgloss.Top, left, "  ", right)

	var resultLines []string
	resultLines = append(resultLines, content)
	resultLines = append(resultLines, "")

	// P&L gauge
	gaugeW := w - 8
	if gaugeW < 20 {
		gaugeW = 20
	}
	resultLines = append(resultLines, renderPnLGauge(currentPnL, strat.MaxLoss, strat.MaxProfit, gaugeW))

	// DTE countdown bar
	resultLines = append(resultLines, renderDTEBar(strat.DTE, 30, w-8))

	return padLines(strings.Join(resultLines, "\n"), h)
}

func (m Model) renderDashboardOneCol(w, h int, currentPnL float64) string {
	strat := m.data.Strategy
	agg := strat.Aggregate
	und := m.data.Underlying

	sections := []string{
		dashPanel("Underlying", w-4, []dashRow{
			{und.Symbol, fmt.Sprintf("%.2f", und.Price), ColorText},
			{"Change", fmt.Sprintf("%+.2f (%.2f%%)", und.Change, und.ChangePct), ValueColor(und.Change)},
			{"IV30", fmt.Sprintf("%.1f%%", und.IV30), ColorYellow},
		}),
		dashPanel("Strategy", w-4, []dashRow{
			{"Type", strat.Name, ColorBlue},
			{"DTE", fmt.Sprintf("%d days", strat.DTE), dteColor(strat.DTE)},
		}),
		dashPanel("Greeks", w-4, []dashRow{
			{"\u0394", fmt.Sprintf("%+.4f", agg.Delta), ValueColor(agg.Delta)},
			{"\u0393", fmt.Sprintf("%+.4f", agg.Gamma), ValueColor(agg.Gamma)},
			{"\u0398", fmt.Sprintf("%+.4f", agg.Theta), ValueColor(agg.Theta)},
			{"V", fmt.Sprintf("%+.4f", agg.Vega), ValueColor(agg.Vega)},
		}),
		dashPanel("P&L", w-4, []dashRow{
			{"Debit", fmt.Sprintf("$%.2f", strat.NetDebit), ColorRed},
			{"MaxP", fmt.Sprintf("$%.2f", strat.MaxProfit), ColorGreen},
			{"MaxL", fmt.Sprintf("$%.2f", strat.MaxLoss), ColorRed},
		}),
	}

	result := strings.Join(sections, "\n")
	gaugeW := w - 8
	if gaugeW < 20 {
		gaugeW = 20
	}
	result += "\n" + renderPnLGauge(currentPnL, strat.MaxLoss, strat.MaxProfit, gaugeW)
	result += "\n" + renderDTEBar(strat.DTE, 30, w-8)

	return padLines(result, h)
}

type dashRow struct {
	label string
	value string
	color lipgloss.Color
}

func dashPanel(title string, w int, rows []dashRow) string {
	var lines []string

	titleStr := lipgloss.NewStyle().Foreground(ColorBlue).Bold(true).
		Render("  " + title)
	lines = append(lines, titleStr)

	sep := DimStyle.Render("  " + strings.Repeat("─", w-4))
	lines = append(lines, sep)

	for _, r := range rows {
		pad := w - lipgloss.Width(r.label) - lipgloss.Width(r.value) - 6
		if pad < 1 {
			pad = 1
		}
		valStyled := lipgloss.NewStyle().Foreground(r.color).Render(r.value)
		lines = append(lines, "  "+SubtitleStyle.Render(r.label)+strings.Repeat(" ", pad)+valStyled)
	}
	lines = append(lines, "")
	return strings.Join(lines, "\n")
}

// renderPnLGauge renders a horizontal P&L bar gauge with current position marked.
func renderPnLGauge(current, minV, maxV float64, w int) string {
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
	if filled > w {
		filled = w
	}

	var color lipgloss.Color
	if current > 0 {
		color = ColorGreen
	} else {
		color = ColorRed
	}

	bar := lipgloss.NewStyle().Foreground(color).Render(strings.Repeat("█", filled))
	bar += DimStyle.Render(strings.Repeat("░", w-filled))

	pctDisplay := (current - minV) / rangeV * 100
	label := fmt.Sprintf("  P&L: %s  %s",
		ValueStyle(current).Render(fmt.Sprintf("%+.2f", current)),
		SubtitleStyle.Render(fmt.Sprintf("(%.0f%% of range)", pctDisplay)),
	)

	return label + "\n  " + bar
}

// renderDTEBar renders a DTE countdown progress bar.
func renderDTEBar(dte, maxDTE, w int) string {
	if w < 10 {
		w = 10
	}
	dtePct := float64(dte) / float64(maxDTE)
	if dtePct > 1 {
		dtePct = 1
	}
	filled := int(dtePct * float64(w))

	color := dteColor(dte)
	bar := lipgloss.NewStyle().Foreground(color).Render(strings.Repeat("█", filled))
	bar += DimStyle.Render(strings.Repeat("░", w-filled))

	label := fmt.Sprintf("  DTE: %s/%d  ",
		lipgloss.NewStyle().Foreground(color).Bold(true).Render(fmt.Sprintf("%d", dte)),
		maxDTE,
	)
	return label + bar
}

func findCurrentPnL(m Model) float64 {
	undPrice := m.data.Underlying.Price
	closestDist := 999999.0
	currentPnL := 0.0
	for _, p := range m.data.PayoffCurve.Points {
		dist := p.Price - undPrice
		if dist < 0 {
			dist = -dist
		}
		if dist < closestDist {
			closestDist = dist
			currentPnL = p.PnL
		}
	}
	return currentPnL
}

func dteColor(dte int) lipgloss.Color {
	if dte <= 3 {
		return ColorRed
	} else if dte <= 7 {
		return ColorYellow
	}
	return ColorGreen
}
