package ui

import "github.com/charmbracelet/lipgloss"

// Catppuccin Mocha-adjacent palette
var (
	colorBg      = lipgloss.Color("#1e1e2e")
	colorSurface = lipgloss.Color("#313244")
	colorOverlay = lipgloss.Color("#45475a")
	colorText    = lipgloss.Color("#cdd6f4")
	colorSubtext = lipgloss.Color("#a6adc8")
	colorGreen   = lipgloss.Color("#a6e3a1")
	colorRed     = lipgloss.Color("#f38ba8")
	colorBlue    = lipgloss.Color("#89b4fa")
	colorYellow  = lipgloss.Color("#f9e2af")
	colorMauve   = lipgloss.Color("#cba6f7")
)

func panelStyle(focused bool, w, h int) lipgloss.Style {
	borderColor := colorOverlay
	if focused {
		borderColor = colorBlue
	}
	return lipgloss.NewStyle().
		Width(w).
		Height(h).
		Background(colorSurface).
		Foreground(colorText).
		Border(lipgloss.RoundedBorder()).
		BorderForeground(borderColor)
}

func titleStyle() lipgloss.Style {
	return lipgloss.NewStyle().
		Bold(true).
		Foreground(colorBlue).
		Background(colorSurface)
}

func greenStyle() lipgloss.Style {
	return lipgloss.NewStyle().Foreground(colorGreen)
}

func redStyle() lipgloss.Style {
	return lipgloss.NewStyle().Foreground(colorRed)
}

func subtextStyle() lipgloss.Style {
	return lipgloss.NewStyle().Foreground(colorSubtext)
}

func mauveStyle() lipgloss.Style {
	return lipgloss.NewStyle().Foreground(colorMauve)
}

func yellowStyle() lipgloss.Style {
	return lipgloss.NewStyle().Foreground(colorYellow)
}
