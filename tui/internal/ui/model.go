package ui

import (
	"github.com/gastown/strader-flytui/internal/data"

	tea "github.com/charmbracelet/bubbletea"
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

	// Sidebar scroll state
	strategyIdx int

	// Help overlay
	showHelp bool

	// Image path for bitmap mode
	imagePath string
}

func NewModel(d *data.ButterflyData, imagePath string) Model {
	return Model{
		data:       d,
		activeView: ViewPayoff,
		focusPanel: PanelLegs,
		imagePath:  imagePath,
	}
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
	case "shift+tab":
		m.focusPanel = (m.focusPanel - 1 + PanelCount) % PanelCount
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
		m.scrollDown()
	case "k", "up":
		m.scrollUp()
	case "?":
		m.showHelp = !m.showHelp
	}
	return m, nil
}

func (m *Model) scrollDown() {
	if m.focusPanel == PanelStrategy {
		variants := []string{"Standard Fly", "Iron Fly", "Broken Wing"}
		if m.strategyIdx < len(variants)-1 {
			m.strategyIdx++
		}
	}
}

func (m *Model) scrollUp() {
	if m.focusPanel == PanelStrategy {
		if m.strategyIdx > 0 {
			m.strategyIdx--
		}
	}
}
