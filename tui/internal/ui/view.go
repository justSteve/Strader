package ui

import (
	"fmt"
	"strings"

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

	// Bottom strip
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
	for _, leg := range m.data.Strategy.Legs {
		sign := "+"
		if leg.Side == "sell" {
			sign = "-"
		}
		qty := leg.Qty
		strike := fmt.Sprintf("%.0f", leg.Strike)
		optType := strings.ToUpper(leg.Type[:1])
		delta := fmt.Sprintf("%.2f", leg.Greeks.Delta)

		line := fmt.Sprintf("%s%d %s%s", sign, qty, strike, optType)
		deltaStr := ValueStyle(leg.Greeks.Delta).Render(fmt.Sprintf("D%s", delta))
		pad := w - lipgloss.Width(line) - lipgloss.Width(delta) - 3
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

	rows := []struct{ label, value string }{
		{"Net D", fmt.Sprintf("%+.2f", agg.Delta)},
		{"Net G", fmt.Sprintf("%+.4f", agg.Gamma)},
		{"Net T", fmt.Sprintf("%+.2f", agg.Theta)},
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
		// Color-code the Greek values
		switch r.label {
		case "Net D", "Net G", "Net T", "Net V":
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
	variants := []string{"Standard Fly", "Iron Fly", "Broken Wing"}
	var lines []string
	for i, v := range variants {
		prefix := "  "
		if i == m.strategyIdx {
			prefix = HighlightStyle.Render("> ")
			v = HighlightStyle.Render(v)
		} else {
			v = SubtitleStyle.Render(v)
		}
		lines = append(lines, prefix+v)
	}

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

func (m Model) renderBottomStrip() string {
	greekLabels := []string{"D", "G", "T", "V"}
	greekData := [][]float64{
		m.data.GreeksByStrike.Delta,
		m.data.GreeksByStrike.Gamma,
		m.data.GreeksByStrike.Theta,
		m.data.GreeksByStrike.Vega,
	}
	greekColors := []lipgloss.Color{ColorGreen, ColorMauve, ColorYellow, ColorRed}

	sparkWidth := (m.width - 8) / 4
	if sparkWidth < 8 {
		sparkWidth = 8
	}

	var sparks []string
	for i, label := range greekLabels {
		spark := renderMiniSparkline(greekData[i], sparkWidth, greekColors[i])
		sparks = append(sparks, lipgloss.NewStyle().Foreground(greekColors[i]).Render(label)+" "+spark)
	}

	strip := lipgloss.JoinHorizontal(lipgloss.Center, sparks[0], "  ", sparks[1], "  ", sparks[2], "  ", sparks[3])

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

// renderMiniSparkline renders a small sparkline using block characters.
func renderMiniSparkline(values []float64, width int, color lipgloss.Color) string {
	if len(values) == 0 {
		return ""
	}

	// Normalize values to 0-7 range for block characters
	minV, maxV := values[0], values[0]
	for _, v := range values {
		if v < minV {
			minV = v
		}
		if v > maxV {
			maxV = v
		}
	}

	blocks := []rune{' ', '\u2581', '\u2582', '\u2583', '\u2584', '\u2585', '\u2586', '\u2587', '\u2588'}
	rangeV := maxV - minV
	if rangeV == 0 {
		rangeV = 1
	}

	// Resample to fit width
	result := make([]rune, width)
	for i := 0; i < width; i++ {
		idx := i * (len(values) - 1) / (width - 1)
		if idx >= len(values) {
			idx = len(values) - 1
		}
		normalized := (values[idx] - minV) / rangeV
		blockIdx := int(normalized * 8)
		if blockIdx > 8 {
			blockIdx = 8
		}
		result[i] = blocks[blockIdx]
	}

	return lipgloss.NewStyle().Foreground(color).Render(string(result))
}
