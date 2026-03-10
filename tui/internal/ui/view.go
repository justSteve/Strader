package ui

import (
	"fmt"
	"strings"

	"github.com/NimbleMarkets/ntcharts/sparkline"
	"github.com/charmbracelet/lipgloss"
	"github.com/gastown/strader-flytui/internal/graphics"
)

const sidebarWidth = 24

func (m Model) View() string {
	if !m.ready {
		return "Loading Strader Fly TUI..."
	}

	if m.showHelp {
		return m.renderHelp()
	}

	mainW := m.width - sidebarWidth - 4 // borders
	if mainW < 20 {
		mainW = 20
	}
	bodyH := m.height - 6 // bottom strip + margins

	// Sidebar panels
	sidebar := m.renderSidebar(bodyH)

	// Main panel
	main := m.renderMainPanel(mainW, bodyH)

	// Join sidebar + main horizontally
	body := lipgloss.JoinHorizontal(lipgloss.Top, sidebar, main)

	// Bottom strip with view selector
	strip := m.renderBottomStrip()

	return lipgloss.JoinVertical(lipgloss.Left, body, strip)
}

func (m Model) renderSidebar(totalH int) string {
	legsH := totalH * 35 / 100
	posH := totalH * 40 / 100
	stratH := totalH - legsH - posH

	legs := m.renderLegsPanel(sidebarWidth-2, legsH-2)
	pos := m.renderPositionPanel(sidebarWidth-2, posH-2)
	strat := m.renderStrategyPanel(sidebarWidth-2, stratH-2)

	return lipgloss.JoinVertical(lipgloss.Left, legs, pos, strat)
}

func (m Model) renderLegsPanel(w, h int) string {
	var lines []string
	for i, leg := range m.data.Strategy.Legs {
		// Selection indicator from slit
		prefix := "  "
		if i == m.selectedLeg && m.focusPanel == PanelLegs {
			prefix = "\u25b6 " // ▶ when focused
		} else if i == m.selectedLeg {
			prefix = "\u25cf " // ● when selected but unfocused
		}

		sign := "+"
		if leg.Side == "sell" {
			sign = "-"
		}
		qty := leg.Qty
		strike := fmt.Sprintf("%.0f", leg.Strike)
		optType := strings.ToUpper(leg.Type[:1])
		delta := fmt.Sprintf("\u0394%+.2f", leg.Greeks.Delta) // Δ prefix

		line := fmt.Sprintf("%s%s%d %s%s", prefix, sign, qty, strike, optType)
		deltaStr := ValueStyle(leg.Greeks.Delta).Render(delta)
		pad := w - lipgloss.Width(line) - lipgloss.Width(delta) - 1
		if pad < 1 {
			pad = 1
		}
		lines = append(lines, line+strings.Repeat(" ", pad)+deltaStr)
	}

	content := strings.Join(lines, "\n")
	for len(strings.Split(content, "\n")) < h {
		content += "\n"
	}

	style := m.panelStyle(PanelLegs, w, h)
	title := TitleStyle.Render(" Legs ")
	return style.Render(title + "\n" + content)
}

func (m Model) renderPositionPanel(w, h int) string {
	agg := m.data.Strategy.Aggregate
	strat := m.data.Strategy

	// Unicode Greek symbols from slit
	rows := []struct{ label, value string }{
		{"Net \u0394", fmt.Sprintf("%+.2f", agg.Delta)},
		{"Net \u0393", fmt.Sprintf("%+.4f", agg.Gamma)},
		{"Net \u0398", fmt.Sprintf("%+.2f", agg.Theta)},
		{"Net V", fmt.Sprintf("%+.2f", agg.Vega)},
		{"Debit", fmt.Sprintf("%.2f", strat.NetDebit)},
		{"MaxP", fmt.Sprintf("%.2f", strat.MaxProfit)},
		{"MaxL", fmt.Sprintf("%.2f", strat.MaxLoss)},
		{"B/E", fmt.Sprintf("%.0f/%.0f", strat.Breakevens[0], strat.Breakevens[1])},
	}

	var lines []string
	for _, r := range rows {
		pad := w - len(r.label) - len(r.value) - 2
		if pad < 1 {
			pad = 1
		}
		val := r.value
		switch r.label {
		case "Net \u0394", "Net \u0393", "Net \u0398", "Net V":
			var v float64
			fmt.Sscanf(r.value, "%f", &v)
			val = ValueStyle(v).Render(r.value)
		case "MaxP":
			val = PositiveStyle.Render(r.value)
		case "MaxL":
			val = NegativeStyle.Render(r.value)
		}
		lines = append(lines, SubtitleStyle.Render(r.label)+strings.Repeat(" ", pad)+val)
	}

	content := strings.Join(lines, "\n")
	for len(strings.Split(content, "\n")) < h {
		content += "\n"
	}

	style := m.panelStyle(PanelPosition, w, h)
	title := TitleStyle.Render(" Position ")
	return style.Render(title + "\n" + content)
}

func (m Model) renderStrategyPanel(w, h int) string {
	var lines []string
	for i, v := range m.strategies {
		prefix := "  "
		if i == m.strategyIdx && m.focusPanel == PanelStrategy {
			prefix = HighlightStyle.Render("\u25b6 ") // ▶
			v = HighlightStyle.Render(v)
		} else if i == m.strategyIdx {
			prefix = HighlightStyle.Render("\u25cf ") // ●
			v = HighlightStyle.Render(v)
		} else {
			v = SubtitleStyle.Render(v)
		}
		lines = append(lines, prefix+v)
	}

	// DTE and expiration from slit
	lines = append(lines, "")
	lines = append(lines, SubtitleStyle.Render(
		fmt.Sprintf("DTE: %d  Exp: %s", m.data.Strategy.DTE, m.data.Strategy.Expiration)))

	content := strings.Join(lines, "\n")
	for len(strings.Split(content, "\n")) < h {
		content += "\n"
	}

	style := m.panelStyle(PanelStrategy, w, h)
	title := TitleStyle.Render(" Strategy ")
	return style.Render(title + "\n" + content)
}

func (m Model) renderMainPanel(w, h int) string {
	var content string
	var title string

	if m.bitmapMode {
		title = "TV Screenshot"
		img, err := graphics.RenderImage(m.imagePath, w-2, h-2)
		if err != nil {
			content = NegativeStyle.Render(fmt.Sprintf("Image error: %v", err))
		} else {
			content = img
		}
	} else {
		switch m.activeView {
		case ViewPayoff:
			title = "Payoff Curve [1]"
			content = m.renderPayoffCurve(w-2, h-2)
		case ViewGEX:
			title = "GEX Matrix [2]"
			content = m.renderGEXMatrix(w-2, h-2)
		case ViewGreeks:
			title = "Greek Profiles [3]"
			content = m.renderGreekProfiles(w-2, h-2)
		case ViewHeatmap:
			title = "Profit Heatmap [4]"
			content = m.renderProfitHeatmap(w-2, h-2)
		case ViewDashboard:
			title = "Position Dashboard [5]"
			content = m.renderDashboard(w-2, h-2)
		}
	}

	style := m.panelStyle(PanelMain, w, h)
	titleRendered := TitleStyle.Render(" " + title + " ")
	return style.Render(titleRendered + "\n" + content)
}

// renderBottomStrip renders the bottom bar with mini Greek sparklines (ntcharts),
// a view selector showing the active view, and a BITMAP indicator.
func (m Model) renderBottomStrip() string {
	gs := m.data.GreeksByStrike
	stripW := m.width - 4

	sparkW := (stripW - 40) / 4
	if sparkW < 5 {
		sparkW = 5
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

	// View selector bar from slit
	viewName := "["
	views := []struct {
		key  string
		mode ViewMode
	}{
		{"1:Payoff", ViewPayoff},
		{"2:GEX", ViewGEX},
		{"3:Greeks", ViewGreeks},
		{"4:Heatmap", ViewHeatmap},
		{"5:Dash", ViewDashboard},
	}
	for i, v := range views {
		if v.mode == m.activeView {
			viewName += MauveStyle.Render(v.key)
		} else {
			viewName += SubtitleStyle.Render(v.key)
		}
		if i < len(views)-1 {
			viewName += " "
		}
	}
	viewName += "]"

	bm := ""
	if m.bitmapMode {
		bm = HighlightStyle.Render(" [BITMAP]")
	}
	status := viewName + bm + SubtitleStyle.Render(" ?=help q=quit")

	strip := strings.Join(parts, "\u2502") + "  " + status

	borderStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(ColorOverlay).
		Width(m.width - 2)

	return borderStyle.Render(strip)
}

func (m Model) renderHelp() string {
	help := `
  Strader Fly TUI - Keyboard Reference

  Navigation
  ----------
  Tab / Shift+Tab   Cycle panel focus
  j / k             Move within panel
  1                 Payoff Curve
  2                 GEX Matrix
  3                 Greek Profiles
  4                 Profit Heatmap
  5                 Position Dashboard
  v                 Toggle bitmap mode
  ?                 Toggle this help
  q                 Quit
`
	style := lipgloss.NewStyle().
		Border(lipgloss.DoubleBorder()).
		BorderForeground(ColorBlue).
		Padding(1, 2).
		Width(50).
		Foreground(ColorText)

	centered := lipgloss.Place(m.width, m.height, lipgloss.Center, lipgloss.Center,
		style.Render(help))
	return centered
}

func (m Model) panelStyle(p Panel, w, h int) lipgloss.Style {
	if p == m.focusPanel {
		return ActiveBorderStyle.Width(w).Height(h)
	}
	return InactiveBorderStyle.Width(w).Height(h)
}
