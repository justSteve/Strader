package ui

import (
	"fmt"
	"strings"

	"github.com/NimbleMarkets/ntcharts/sparkline"
	"github.com/charmbracelet/lipgloss"
	"github.com/gastown/strader-flytui/internal/graphics"
)

// View renders the complete TUI frame.
func (m Model) View() string {
	if !m.ready {
		return "\n  Loading Strader Fly TUI..."
	}

	// Minimum viable terminal size
	if m.width < 60 || m.height < 20 {
		return lipgloss.Place(m.width, m.height, lipgloss.Center, lipgloss.Center,
			NegativeStyle.Render("Terminal too small\nNeed at least 60x20"))
	}

	if m.showHelp {
		return m.renderHelp()
	}

	mainW := m.mainPanelWidth()
	bodyH := m.bodyHeight()

	// Build sidebar
	sidebar := m.renderSidebar(bodyH)

	// Build main panel
	main := m.renderMainPanel(mainW, bodyH)

	// Join sidebar + main horizontally
	body := lipgloss.JoinHorizontal(lipgloss.Top, sidebar, main)

	// Bottom strip
	strip := m.renderBottomStrip()

	return lipgloss.JoinVertical(lipgloss.Left, body, strip)
}

// renderSidebar builds the three stacked left panels: Legs, Position, Strategy.
func (m Model) renderSidebar(totalH int) string {
	innerW := sidebarWidth - 4 // inside border + padding

	// Proportional distribution — legs gets less, position more
	legsH := totalH * 30 / 100
	posH := totalH * 40 / 100
	stratH := totalH - legsH - posH

	// Minimum heights
	if legsH < 6 {
		legsH = 6
	}
	if posH < 8 {
		posH = 8
	}
	if stratH < 6 {
		stratH = 6
	}

	legs := m.renderLegsPanel(innerW, legsH-2)
	pos := m.renderPositionPanel(innerW, posH-2)
	strat := m.renderStrategyPanel(innerW, stratH-2)

	return lipgloss.JoinVertical(lipgloss.Left, legs, pos, strat)
}

// renderLegsPanel shows butterfly legs with selection indicators.
func (m Model) renderLegsPanel(w, h int) string {
	var lines []string
	for i, leg := range m.data.Strategy.Legs {
		prefix := "  "
		if i == m.selectedLeg && m.focusPanel == PanelLegs {
			prefix = HighlightStyle.Render("\u25b6 ") // ▶ focused
		} else if i == m.selectedLeg {
			prefix = MauveStyle.Render("\u25cf ") // ● selected unfocused
		}

		sign := "+"
		if leg.Side == "sell" {
			sign = "-"
		}
		strike := fmt.Sprintf("%.0f", leg.Strike)
		optType := strings.ToUpper(leg.Type[:1])
		delta := fmt.Sprintf("\u0394%+.2f", leg.Greeks.Delta)

		left := fmt.Sprintf("%s%s%d %s%s", prefix, sign, leg.Qty, strike, optType)
		deltaRendered := ValueStyle(leg.Greeks.Delta).Render(delta)

		pad := w - lipgloss.Width(left) - lipgloss.Width(delta) - 1
		if pad < 1 {
			pad = 1
		}
		lines = append(lines, left+strings.Repeat(" ", pad)+deltaRendered)
	}

	content := padLines(strings.Join(lines, "\n"), h)
	style := m.panelStyle(PanelLegs, sidebarWidth-2, h)
	return style.Render(TitleStyle.Render(" Legs ") + "\n" + content)
}

// renderPositionPanel shows aggregate Greeks and P&L metrics.
func (m Model) renderPositionPanel(w, h int) string {
	agg := m.data.Strategy.Aggregate
	strat := m.data.Strategy

	rows := []struct{ label, value string }{
		{"Net \u0394", fmt.Sprintf("%+.2f", agg.Delta)},
		{"Net \u0393", fmt.Sprintf("%+.4f", agg.Gamma)},
		{"Net \u0398", fmt.Sprintf("%+.2f", agg.Theta)},
		{"Net V", fmt.Sprintf("%+.2f", agg.Vega)},
		{"", ""}, // separator
		{"Debit", fmt.Sprintf("%.2f", strat.NetDebit)},
		{"MaxP", fmt.Sprintf("%.2f", strat.MaxProfit)},
		{"MaxL", fmt.Sprintf("%.2f", strat.MaxLoss)},
		{"B/E", fmt.Sprintf("%.0f/%.0f", strat.Breakevens[0], strat.Breakevens[1])},
	}

	var lines []string
	for _, r := range rows {
		if r.label == "" {
			lines = append(lines, DimStyle.Render(strings.Repeat("─", w-2)))
			continue
		}

		pad := w - len(r.label) - len(r.value) - 2
		if pad < 1 {
			pad = 1
		}
		val := r.value
		switch r.label {
		case "Net \u0394":
			val = ValueStyle(agg.Delta).Render(r.value)
		case "Net \u0393":
			val = ValueStyle(agg.Gamma).Render(r.value)
		case "Net \u0398":
			val = ValueStyle(agg.Theta).Render(r.value)
		case "Net V":
			val = ValueStyle(agg.Vega).Render(r.value)
		case "MaxP":
			val = PositiveStyle.Render(r.value)
		case "MaxL":
			val = NegativeStyle.Render(r.value)
		}
		lines = append(lines, SubtitleStyle.Render(r.label)+strings.Repeat(" ", pad)+val)
	}

	content := padLines(strings.Join(lines, "\n"), h)
	style := m.panelStyle(PanelPosition, sidebarWidth-2, h)
	return style.Render(TitleStyle.Render(" Position ") + "\n" + content)
}

// renderStrategyPanel shows strategy type selector with DTE info.
func (m Model) renderStrategyPanel(w, h int) string {
	var lines []string
	for i, name := range m.strategies {
		prefix := "  "
		style := SubtitleStyle
		if i == m.strategyIdx && m.focusPanel == PanelStrategy {
			prefix = HighlightStyle.Render("\u25b6 ") // ▶
			style = HighlightStyle
		} else if i == m.strategyIdx {
			prefix = MauveStyle.Render("\u25cf ") // ●
			style = MauveStyle
		}
		lines = append(lines, prefix+style.Render(name))
	}

	lines = append(lines, "")
	dte := m.data.Strategy.DTE
	dteStyle := PositiveStyle
	if dte <= 3 {
		dteStyle = NegativeStyle
	} else if dte <= 7 {
		dteStyle = HighlightStyle
	}
	lines = append(lines, SubtitleStyle.Render("DTE: ")+dteStyle.Render(fmt.Sprintf("%d", dte))+
		SubtitleStyle.Render("  "+m.data.Strategy.Expiration))

	content := padLines(strings.Join(lines, "\n"), h)
	style := m.panelStyle(PanelStrategy, sidebarWidth-2, h)
	return style.Render(TitleStyle.Render(" Strategy ") + "\n" + content)
}

// renderMainPanel renders the large right panel based on active view or bitmap mode.
func (m Model) renderMainPanel(w, h int) string {
	var content string
	var title string

	if m.bitmapMode {
		title = "TV Screenshot"
		img, err := graphics.RenderImage(m.imagePath, w-4, h-3)
		if err != nil {
			content = NegativeStyle.Render(fmt.Sprintf("Image error: %v", err))
		} else {
			content = img
		}
	} else {
		switch m.activeView {
		case ViewPayoff:
			title = "Payoff Curve [1]"
			content = m.renderPayoffCurve(w-4, h-3)
		case ViewGEX:
			title = "GEX Matrix [2]"
			content = m.renderGEXMatrix(w-4, h-3)
		case ViewGreeks:
			title = "Greek Profiles [3]"
			content = m.renderGreekProfiles(w-4, h-3)
		case ViewHeatmap:
			title = "Profit Heatmap [4]"
			content = m.renderProfitHeatmap(w-4, h-3)
		case ViewDashboard:
			title = "Position Dashboard [5]"
			content = m.renderDashboard(w-4, h-3)
		}
	}

	style := m.panelStyle(PanelMain, w-2, h)
	titleStr := TitleStyle.Render(" " + title + " ")
	return style.Render(titleStr + "\n" + content)
}

// renderBottomStrip renders mini Greek sparklines (ntcharts), view selector, and status.
func (m Model) renderBottomStrip() string {
	gs := m.data.GreeksByStrike
	stripW := m.width - 4

	sparkW := (stripW - 48) / 4
	if sparkW < 5 {
		sparkW = 5
	}
	if sparkW > 20 {
		sparkW = 20
	}

	type miniGreek struct {
		label  string
		values []float64
		color  lipgloss.Color
	}
	greeks := []miniGreek{
		{"\u0394", gs.Delta, ColorGreen},
		{"\u0393", gs.Gamma, ColorMauve},
		{"\u0398", gs.Theta, ColorYellow},
		{"V", gs.Vega, ColorBlue},
	}

	var parts []string
	for _, g := range greeks {
		if len(g.values) == 0 {
			continue
		}
		minV, _ := greekMinMax(g.values)
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

	// View selector with active highlight
	viewSel := "["
	views := []struct {
		key  string
		mode ViewMode
	}{
		{"1:Payoff", ViewPayoff},
		{"2:GEX", ViewGEX},
		{"3:Greeks", ViewGreeks},
		{"4:Heat", ViewHeatmap},
		{"5:Dash", ViewDashboard},
	}
	for i, v := range views {
		if v.mode == m.activeView && !m.bitmapMode {
			viewSel += MauveStyle.Render(v.key)
		} else {
			viewSel += SubtitleStyle.Render(v.key)
		}
		if i < len(views)-1 {
			viewSel += " "
		}
	}
	viewSel += "]"

	bm := ""
	if m.bitmapMode {
		bm = HighlightStyle.Render(" BITMAP")
	}

	// Focus indicator
	focusNames := map[Panel]string{
		PanelLegs:     "Legs",
		PanelPosition: "Pos",
		PanelStrategy: "Strat",
		PanelMain:     "Main",
	}
	focus := lipgloss.NewStyle().Foreground(ColorBlue).Bold(true).
		Render("\u25c6" + focusNames[m.focusPanel]) // ◆

	status := viewSel + bm + " " + focus + SubtitleStyle.Render(" ?=help q=quit")

	strip := strings.Join(parts, "\u2502") + "  " + status

	borderStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(ColorOverlay0).
		Width(m.width - 2)

	return borderStyle.Render(strip)
}

// renderHelp shows the keyboard reference overlay.
func (m Model) renderHelp() string {
	title := TitleStyle.Render("  Strader Fly TUI \u2014 Keyboard Reference")

	sections := []string{
		title,
		"",
		HighlightStyle.Render("  Navigation"),
		DimStyle.Render("  " + strings.Repeat("─", 40)),
		fmt.Sprintf("  %s  %s", lipgloss.NewStyle().Foreground(ColorTeal).Width(20).Render("Tab / Shift+Tab"), "Cycle panel focus"),
		fmt.Sprintf("  %s  %s", lipgloss.NewStyle().Foreground(ColorTeal).Width(20).Render("j / k / ↑ / ↓"), "Move within panel"),
		"",
		HighlightStyle.Render("  Views"),
		DimStyle.Render("  " + strings.Repeat("─", 40)),
		fmt.Sprintf("  %s  %s", lipgloss.NewStyle().Foreground(ColorTeal).Width(20).Render("1"), "Payoff Curve"),
		fmt.Sprintf("  %s  %s", lipgloss.NewStyle().Foreground(ColorTeal).Width(20).Render("2"), "GEX Matrix"),
		fmt.Sprintf("  %s  %s", lipgloss.NewStyle().Foreground(ColorTeal).Width(20).Render("3"), "Greek Profiles"),
		fmt.Sprintf("  %s  %s", lipgloss.NewStyle().Foreground(ColorTeal).Width(20).Render("4"), "Profit Heatmap"),
		fmt.Sprintf("  %s  %s", lipgloss.NewStyle().Foreground(ColorTeal).Width(20).Render("5"), "Position Dashboard"),
		fmt.Sprintf("  %s  %s", lipgloss.NewStyle().Foreground(ColorTeal).Width(20).Render("v"), "Toggle bitmap mode"),
		"",
		HighlightStyle.Render("  General"),
		DimStyle.Render("  " + strings.Repeat("─", 40)),
		fmt.Sprintf("  %s  %s", lipgloss.NewStyle().Foreground(ColorTeal).Width(20).Render("?"), "Toggle this help"),
		fmt.Sprintf("  %s  %s", lipgloss.NewStyle().Foreground(ColorTeal).Width(20).Render("q"), "Quit"),
	}

	helpText := strings.Join(sections, "\n")

	style := lipgloss.NewStyle().
		Border(lipgloss.DoubleBorder()).
		BorderForeground(ColorBlue).
		Padding(1, 2).
		Width(52).
		Foreground(ColorText)

	return lipgloss.Place(m.width, m.height, lipgloss.Center, lipgloss.Center,
		style.Render(helpText))
}

// panelStyle returns the appropriate border style for a panel based on focus state.
func (m Model) panelStyle(p Panel, w, h int) lipgloss.Style {
	if p == m.focusPanel {
		return ActiveBorderStyle.Width(w).Height(h)
	}
	return InactiveBorderStyle.Width(w).Height(h)
}

// padLines pads content to fill h lines.
func padLines(content string, h int) string {
	lines := strings.Split(content, "\n")
	for len(lines) < h {
		lines = append(lines, "")
	}
	if len(lines) > h {
		lines = lines[:h]
	}
	return strings.Join(lines, "\n")
}
