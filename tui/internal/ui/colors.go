package ui

import "github.com/charmbracelet/lipgloss"

// Catppuccin Mocha-adjacent palette
var (
	ColorBg      = lipgloss.Color("#1e1e2e")
	ColorSurface = lipgloss.Color("#313244")
	ColorOverlay = lipgloss.Color("#45475a")
	ColorText    = lipgloss.Color("#cdd6f4")
	ColorSubtext = lipgloss.Color("#a6adc8")
	ColorGreen   = lipgloss.Color("#a6e3a1")
	ColorRed     = lipgloss.Color("#f38ba8")
	ColorBlue    = lipgloss.Color("#89b4fa")
	ColorYellow  = lipgloss.Color("#f9e2af")
	ColorMauve   = lipgloss.Color("#cba6f7")
)

// Panel styles
var (
	ActiveBorderStyle = lipgloss.NewStyle().
				Border(lipgloss.RoundedBorder()).
				BorderForeground(ColorBlue)

	InactiveBorderStyle = lipgloss.NewStyle().
				Border(lipgloss.RoundedBorder()).
				BorderForeground(ColorOverlay)

	TitleStyle = lipgloss.NewStyle().
			Foreground(ColorBlue).
			Bold(true)

	SubtitleStyle = lipgloss.NewStyle().
			Foreground(ColorSubtext)

	PositiveStyle = lipgloss.NewStyle().
			Foreground(ColorGreen)

	NegativeStyle = lipgloss.NewStyle().
			Foreground(ColorRed)

	HighlightStyle = lipgloss.NewStyle().
			Foreground(ColorYellow)

	MauveStyle = lipgloss.NewStyle().
			Foreground(ColorMauve)
)

func ValueStyle(v float64) lipgloss.Style {
	if v > 0 {
		return PositiveStyle
	} else if v < 0 {
		return NegativeStyle
	}
	return lipgloss.NewStyle().Foreground(ColorText)
}
