package ui

import (
	"fmt"

	"github.com/gastown/strader-flytui/internal/data"
	"github.com/gastown/strader-flytui/internal/graphics"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	btable "github.com/evertras/bubble-table/table"
)

// View modes for the main panel
type viewMode int

const (
	viewPayoff  viewMode = iota // 1 key
	viewGEX                     // 2 key
	viewGreeks                  // 3 key
	viewHeatmap                 // 4 key
)

// Focus panels
type panel int

const (
	panelLegs panel = iota
	panelPosition
	panelStrategy
	panelMain
)

const numPanels = 4

// Model is the top-level Bubble Tea model for the Fly TUI.
type Model struct {
	data *data.ButterflyData

	width  int
	height int
	ready  bool

	activeView  viewMode
	focusPanel  panel
	bitmapMode  bool
	imageCache  string
	showHelp    bool

	// Sidebar state
	selectedLeg      int
	selectedStrategy int
	strategies       []string

	// GEX table
	gexTable btable.Model
}

// New creates an initialized Model from loaded butterfly data.
func New(d *data.ButterflyData) Model {
	m := Model{
		data:       d,
		activeView: viewPayoff,
		focusPanel: panelMain,
		strategies: []string{"Standard Fly", "Iron Fly", "Broken Wing"},
	}
	m.gexTable = m.buildGEXTable(80)
	return m
}

func (m Model) Init() tea.Cmd {
	return nil
}

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		if m.showHelp {
			m.showHelp = false
			return m, nil
		}
		switch msg.String() {
		case "q", "ctrl+c":
			return m, tea.Quit

		// View switching
		case "1":
			m.activeView = viewPayoff
			m.bitmapMode = false
			return m, nil
		case "2":
			m.activeView = viewGEX
			m.bitmapMode = false
			return m, nil
		case "3":
			m.activeView = viewGreeks
			m.bitmapMode = false
			return m, nil
		case "4":
			m.activeView = viewHeatmap
			m.bitmapMode = false
			return m, nil

		// Bitmap toggle
		case "v":
			m.bitmapMode = !m.bitmapMode
			m.imageCache = ""
			return m, nil

		// Panel focus cycling
		case "tab":
			m.focusPanel = (m.focusPanel + 1) % numPanels
			return m, nil
		case "shift+tab":
			m.focusPanel = (m.focusPanel - 1 + numPanels) % numPanels
			return m, nil

		// Navigation within focused panel
		case "j", "down":
			m.navigateDown()
			return m, nil
		case "k", "up":
			m.navigateUp()
			return m, nil

		// Help
		case "?":
			m.showHelp = !m.showHelp
			return m, nil
		}

		// Forward to GEX table when it's focused
		if m.focusPanel == panelMain && m.activeView == viewGEX && !m.bitmapMode {
			var cmd tea.Cmd
			m.gexTable, cmd = m.gexTable.Update(msg)
			return m, cmd
		}

	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		m.ready = true
		m.imageCache = ""
		mainW := m.mainPanelWidth()
		m.gexTable = m.buildGEXTable(mainW)
	}
	return m, nil
}

func (m *Model) navigateDown() {
	switch m.focusPanel {
	case panelLegs:
		if m.selectedLeg < len(m.data.Strategy.Legs)-1 {
			m.selectedLeg++
		}
	case panelStrategy:
		if m.selectedStrategy < len(m.strategies)-1 {
			m.selectedStrategy++
		}
	case panelMain:
		if m.activeView == viewGEX {
			m.gexTable, _ = m.gexTable.Update(tea.KeyMsg{Type: tea.KeyDown})
		}
	}
}

func (m *Model) navigateUp() {
	switch m.focusPanel {
	case panelLegs:
		if m.selectedLeg > 0 {
			m.selectedLeg--
		}
	case panelStrategy:
		if m.selectedStrategy > 0 {
			m.selectedStrategy--
		}
	case panelMain:
		if m.activeView == viewGEX {
			m.gexTable, _ = m.gexTable.Update(tea.KeyMsg{Type: tea.KeyUp})
		}
	}
}

// Layout dimensions
func (m Model) sidebarWidth() int {
	sw := m.width / 4
	if sw < 24 {
		sw = 24
	}
	if sw > 32 {
		sw = 32
	}
	return sw
}

func (m Model) mainPanelWidth() int {
	return m.width - m.sidebarWidth() - 6 // borders
}

func (m Model) mainPanelHeight() int {
	return m.height - 6 // bottom strip + borders
}

func (m Model) View() string {
	if !m.ready {
		return "Loading Strader Fly TUI..."
	}
	if m.showHelp {
		return m.renderHelp()
	}
	return m.renderLayout()
}

func (m Model) renderLayout() string {
	sw := m.sidebarWidth()
	mw := m.mainPanelWidth()

	sidebarH := m.height - 6
	legsH := sidebarH / 3
	posH := sidebarH / 3
	stratH := sidebarH - legsH - posH

	// Sidebar panels
	legs := m.renderLegsPanel(sw-2, legsH-2)
	pos := m.renderPositionPanel(sw-2, posH-2)
	strat := m.renderStrategyPanel(sw-2, stratH-2)

	legsBox := panelStyle(m.focusPanel == panelLegs, sw-2, legsH-2).Render(legs)
	posBox := panelStyle(m.focusPanel == panelPosition, sw-2, posH-2).Render(pos)
	stratBox := panelStyle(m.focusPanel == panelStrategy, sw-2, stratH-2).Render(strat)

	sidebar := lipgloss.JoinVertical(lipgloss.Left, legsBox, posBox, stratBox)

	// Main panel
	mainContent := m.renderMainPanel(mw-2, m.mainPanelHeight()-2)
	mainBox := panelStyle(m.focusPanel == panelMain, mw-2, m.mainPanelHeight()-2).Render(mainContent)

	// Join sidebar + main
	top := lipgloss.JoinHorizontal(lipgloss.Top, sidebar, mainBox)

	// Bottom strip
	strip := m.renderGreekStrip(m.width - 4)
	stripBox := lipgloss.NewStyle().
		Width(m.width - 4).
		Border(lipgloss.RoundedBorder()).
		BorderForeground(colorOverlay).
		Foreground(colorText).
		Render(strip)

	return lipgloss.JoinVertical(lipgloss.Left, top, stripBox)
}

func (m Model) renderLegsPanel(w, h int) string {
	title := titleStyle().Render("Legs")
	var lines string
	for i, leg := range m.data.Strategy.Legs {
		prefix := "  "
		if i == m.selectedLeg && m.focusPanel == panelLegs {
			prefix = "▶ "
		}
		side := "+"
		if leg.Side == "sell" {
			side = "-"
		}
		qty := leg.Qty
		if leg.Side == "sell" {
			qty = leg.Qty
		}
		strike := fmt.Sprintf("%.0f", leg.Strike)
		typ := "C"
		if leg.Type == "put" {
			typ = "P"
		}
		delta := fmt.Sprintf("Δ%+.2f", leg.Greeks.Delta)
		var deltaStyled string
		if leg.Greeks.Delta >= 0 {
			deltaStyled = greenStyle().Render(delta)
		} else {
			deltaStyled = redStyle().Render(delta)
		}
		line := fmt.Sprintf("%s%s%d %s%s  %s", prefix, side, qty, strike, typ, deltaStyled)
		lines += line + "\n"
	}
	return title + "\n" + lines
}

func (m Model) renderPositionPanel(w, h int) string {
	title := titleStyle().Render("Position")
	agg := m.data.Strategy.Aggregate
	s := m.data.Strategy

	colorVal := func(v float64, label string) string {
		str := fmt.Sprintf("%s: %+.4f", label, v)
		if v > 0 {
			return greenStyle().Render(str)
		} else if v < 0 {
			return redStyle().Render(str)
		}
		return subtextStyle().Render(str)
	}

	lines := fmt.Sprintf("%s\n%s\n%s\n%s\n",
		colorVal(agg.Delta, "Net Δ"),
		colorVal(agg.Gamma, "Net Γ"),
		colorVal(agg.Theta, "Net Θ"),
		colorVal(agg.Vega, "Net V"),
	)
	lines += subtextStyle().Render(fmt.Sprintf("Debit:  %.2f", s.NetDebit)) + "\n"
	lines += greenStyle().Render(fmt.Sprintf("MaxP:   %.2f", s.MaxProfit)) + "\n"
	lines += redStyle().Render(fmt.Sprintf("MaxL:   %.2f", s.MaxLoss)) + "\n"

	return title + "\n" + lines
}

func (m Model) renderStrategyPanel(w, h int) string {
	title := titleStyle().Render("Strategy")
	var lines string
	for i, s := range m.strategies {
		prefix := "  "
		if i == m.selectedStrategy && m.focusPanel == panelStrategy {
			prefix = "▶ "
		} else if i == m.selectedStrategy {
			prefix = "● "
		}
		lines += prefix + s + "\n"
	}
	lines += "\n" + subtextStyle().Render(fmt.Sprintf("DTE: %d  Exp: %s", m.data.Strategy.DTE, m.data.Strategy.Expiration))
	return title + "\n" + lines
}

func (m Model) renderMainPanel(w, h int) string {
	if m.bitmapMode {
		return m.renderBitmap(w, h)
	}
	switch m.activeView {
	case viewPayoff:
		return m.renderPayoffCurve(w, h)
	case viewGEX:
		return m.renderGEXView(w, h)
	case viewGreeks:
		return m.renderGreekProfiles(w, h)
	case viewHeatmap:
		return m.renderHeatmap(w, h)
	default:
		return "Unknown view"
	}
}

func (m Model) renderBitmap(w, h int) string {
	if m.imageCache != "" {
		return m.imageCache
	}
	img, err := graphics.RenderImage("tui/data/tv-screenshot.png", w, h-2)
	if err != nil {
		return fmt.Sprintf("Bitmap: %v\n%s", err, subtextStyle().Render("(install chafa for image support)"))
	}
	return img
}

func (m Model) viewLabel() string {
	switch m.activeView {
	case viewPayoff:
		return "Payoff Curve"
	case viewGEX:
		return "GEX Matrix"
	case viewGreeks:
		return "Greek Profiles"
	case viewHeatmap:
		return "Profit Heatmap"
	}
	return ""
}

func (m Model) renderHelp() string {
	help := titleStyle().Render("Strader Fly TUI — Keyboard Reference") + "\n\n"
	help += "  " + mauveStyle().Render("Tab/Shift+Tab") + "  Cycle panel focus\n"
	help += "  " + mauveStyle().Render("j/k") + "            Navigate within panel\n"
	help += "  " + mauveStyle().Render("1 2 3 4") + "        Switch main view\n"
	help += "                   1=Payoff  2=GEX  3=Greeks  4=Heatmap\n"
	help += "  " + mauveStyle().Render("v") + "              Toggle bitmap mode\n"
	help += "  " + mauveStyle().Render("?") + "              Toggle this help\n"
	help += "  " + mauveStyle().Render("q") + "              Quit\n"
	help += "\n" + subtextStyle().Render("Press any key to close help")
	return lipgloss.NewStyle().
		Padding(2, 4).
		Background(colorBg).
		Foreground(colorText).
		Render(help)
}
