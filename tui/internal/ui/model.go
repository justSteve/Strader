package ui

import (
	"github.com/gastown/strader-flytui/internal/data"

	tea "github.com/charmbracelet/bubbletea"
	btable "github.com/evertras/bubble-table/table"
)

// ViewMode selects what the main panel displays.
type ViewMode int

const (
	ViewPayoff    ViewMode = iota // 1
	ViewGEX                       // 2
	ViewGreeks                    // 3
	ViewHeatmap                   // 4
	ViewDashboard                 // 5
)

// Panel identifies which panel has keyboard focus.
type Panel int

const (
	PanelLegs     Panel = iota
	PanelPosition
	PanelStrategy
	PanelMain
	panelCount // sentinel for cycling
)

// Model is the top-level Bubble Tea model for the Strader Fly TUI.
type Model struct {
	data   *data.ButterflyData
	width  int
	height int
	ready  bool

	// View state
	activeView ViewMode
	focusPanel Panel
	bitmapMode bool
	showHelp   bool

	// Sidebar navigation
	selectedLeg int
	strategyIdx int
	strategies  []string

	// GEX table (evertras/bubble-table)
	gexTable btable.Model

	// Image path for bitmap toggle
	imagePath string
}

// NewModel creates the initial model from loaded data.
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
		mainW := m.mainPanelWidth()
		if mainW < 20 {
			mainW = 20
		}
		m.gexTable = m.buildGEXTable(mainW)
	}
	return m, nil
}

// handleKey processes all keyboard input — lazygit-style navigation.
func (m Model) handleKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	// Help overlay intercepts all keys
	if m.showHelp {
		m.showHelp = false
		return m, nil
	}

	key := msg.String()

	switch key {
	case "q", "ctrl+c":
		return m, tea.Quit

	// Panel focus cycling
	case "tab":
		m.focusPanel = (m.focusPanel + 1) % panelCount
		return m, nil
	case "shift+tab":
		m.focusPanel = (m.focusPanel - 1 + panelCount) % panelCount
		return m, nil

	// View switching (works regardless of focus)
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

	// Bitmap toggle
	case "v":
		m.bitmapMode = !m.bitmapMode

	// Vertical navigation within focused panel
	case "j", "down":
		m.navigateDown()
	case "k", "up":
		m.navigateUp()

	// Help
	case "?":
		m.showHelp = !m.showHelp

	default:
		// Forward unhandled keys to GEX table when it's active
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

// Layout helpers
const sidebarWidth = 26

func (m Model) mainPanelWidth() int {
	w := m.width - sidebarWidth - 4
	if w < 20 {
		return 20
	}
	return w
}

func (m Model) bodyHeight() int {
	h := m.height - 5 // bottom strip
	if h < 10 {
		return 10
	}
	return h
}
