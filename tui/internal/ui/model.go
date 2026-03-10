package ui

import (
	"github.com/gastown/strader-flytui/internal/data"

	tea "github.com/charmbracelet/bubbletea"
	btable "github.com/evertras/bubble-table/table"
)

// View modes for the main panel
type ViewMode int

const (
	ViewPayoff ViewMode = iota
	ViewGEX
	ViewGreeks
	ViewHeatmap
	ViewDashboard
)

// Focus panels
type Panel int

const (
	PanelLegs Panel = iota
	PanelPosition
	PanelStrategy
	PanelMain
	PanelCount // sentinel
)

type Model struct {
	data       *data.ButterflyData
	width      int
	height     int
	ready      bool
	activeView ViewMode
	focusPanel Panel
	bitmapMode bool

	// Sidebar state
	selectedLeg int
	strategyIdx int
	strategies  []string

	// GEX table (bubble-table)
	gexTable btable.Model

	// Help overlay
	showHelp bool

	// Image path for bitmap mode
	imagePath string
}

func NewModel(d *data.ButterflyData, imagePath string) Model {
	m := Model{
		data:       d,
		activeView: ViewPayoff,
		focusPanel: PanelLegs,
		imagePath:  imagePath,
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
		return m.handleKey(msg)
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		m.ready = true
		mainW := m.width - sidebarWidth - 4
		if mainW < 20 {
			mainW = 20
		}
		m.gexTable = m.buildGEXTable(mainW)
	}
	return m, nil
}

func (m Model) handleKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	if m.showHelp {
		m.showHelp = false
		return m, nil
	}

	switch msg.String() {
	case "q", "ctrl+c":
		return m, tea.Quit
	case "tab":
		m.focusPanel = (m.focusPanel + 1) % PanelCount
		return m, nil
	case "shift+tab":
		m.focusPanel = (m.focusPanel - 1 + PanelCount) % PanelCount
		return m, nil
	case "1":
		m.activeView = ViewPayoff
		m.bitmapMode = false
	case "2":
		m.activeView = ViewGEX
		m.bitmapMode = false
	case "3":
		m.activeView = ViewGreeks
		m.bitmapMode = false
	case "4":
		m.activeView = ViewHeatmap
		m.bitmapMode = false
	case "5":
		m.activeView = ViewDashboard
		m.bitmapMode = false
	case "v":
		m.bitmapMode = !m.bitmapMode
	case "j", "down":
		m.navigateDown()
	case "k", "up":
		m.navigateUp()
	case "?":
		m.showHelp = !m.showHelp
	default:
		// Forward to GEX table when it's focused
		if m.focusPanel == PanelMain && m.activeView == ViewGEX && !m.bitmapMode {
			var cmd tea.Cmd
			m.gexTable, cmd = m.gexTable.Update(msg)
			return m, cmd
		}
	}
	return m, nil
}

func (m *Model) navigateDown() {
	switch m.focusPanel {
	case PanelLegs:
		if m.selectedLeg < len(m.data.Strategy.Legs)-1 {
			m.selectedLeg++
		}
	case PanelStrategy:
		if m.strategyIdx < len(m.strategies)-1 {
			m.strategyIdx++
		}
	case PanelMain:
		if m.activeView == ViewGEX {
			m.gexTable, _ = m.gexTable.Update(tea.KeyMsg{Type: tea.KeyDown})
		}
	}
}

func (m *Model) navigateUp() {
	switch m.focusPanel {
	case PanelLegs:
		if m.selectedLeg > 0 {
			m.selectedLeg--
		}
	case PanelStrategy:
		if m.strategyIdx > 0 {
			m.strategyIdx--
		}
	case PanelMain:
		if m.activeView == ViewGEX {
			m.gexTable, _ = m.gexTable.Update(tea.KeyMsg{Type: tea.KeyUp})
		}
	}
}
