package ui

import "github.com/charmbracelet/lipgloss"

// Catppuccin Mocha palette — exact spec values
var (
	ColorBase     = lipgloss.Color("#1e1e2e") // darkest background
	ColorMantle   = lipgloss.Color("#181825") // even darker, for contrast
	ColorCrust    = lipgloss.Color("#11111b") // absolute dark
	ColorSurface0 = lipgloss.Color("#313244") // panel backgrounds
	ColorSurface1 = lipgloss.Color("#45475a") // elevated surfaces
	ColorSurface2 = lipgloss.Color("#585b70") // higher elevation
	ColorOverlay0 = lipgloss.Color("#6c7086") // subtle borders
	ColorOverlay1 = lipgloss.Color("#7f849c") // mid borders
	ColorText     = lipgloss.Color("#cdd6f4") // primary text
	ColorSubtext0 = lipgloss.Color("#a6adc8") // secondary text
	ColorSubtext1 = lipgloss.Color("#bac2de") // slightly brighter secondary
	ColorGreen    = lipgloss.Color("#a6e3a1") // profit, positive
	ColorRed      = lipgloss.Color("#f38ba8") // loss, negative
	ColorBlue     = lipgloss.Color("#89b4fa") // accent, active borders
	ColorYellow   = lipgloss.Color("#f9e2af") // warnings, highlights
	ColorMauve    = lipgloss.Color("#cba6f7") // special emphasis
	ColorPeach    = lipgloss.Color("#fab387") // warm accent
	ColorTeal     = lipgloss.Color("#94e2d5") // cool accent
	ColorSky      = lipgloss.Color("#89dceb") // light cool accent
	ColorLavender = lipgloss.Color("#b4befe") // soft accent
	ColorFlamingo = lipgloss.Color("#f2cdcd") // soft warm accent
	ColorRosewater= lipgloss.Color("#f5e0dc") // lightest warm

	// DTE curve colors — dim to bright as expiry approaches
	ColorDTE30 = lipgloss.Color("#585b70") // Surface2 — dimmest
	ColorDTE15 = lipgloss.Color("#7f849c") // Overlay1
	ColorDTE7  = lipgloss.Color("#9399b2") // brighter
	ColorDTE1  = ColorYellow              // brightest
)

// Panel styles with proper padding
var (
	ActiveBorderStyle = lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(ColorBlue).
		Padding(0, 1)

	InactiveBorderStyle = lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(ColorOverlay0).
		Padding(0, 1)

	FocusedBorderStyle = lipgloss.NewStyle().
		Border(lipgloss.ThickBorder()).
		BorderForeground(ColorBlue).
		Padding(0, 1)

	TitleStyle = lipgloss.NewStyle().
		Foreground(ColorBlue).
		Bold(true)

	SubtitleStyle = lipgloss.NewStyle().
		Foreground(ColorSubtext0)

	PositiveStyle = lipgloss.NewStyle().
		Foreground(ColorGreen)

	NegativeStyle = lipgloss.NewStyle().
		Foreground(ColorRed)

	HighlightStyle = lipgloss.NewStyle().
		Foreground(ColorYellow).
		Bold(true)

	MauveStyle = lipgloss.NewStyle().
		Foreground(ColorMauve).
		Bold(true)

	DimStyle = lipgloss.NewStyle().
		Foreground(ColorOverlay0)
)

// ValueStyle returns green for positive, red for negative, neutral for zero.
func ValueStyle(v float64) lipgloss.Style {
	if v > 0 {
		return PositiveStyle
	} else if v < 0 {
		return NegativeStyle
	}
	return lipgloss.NewStyle().Foreground(ColorText)
}

// ValueColor returns just the color for a value (useful in tables/grids).
func ValueColor(v float64) lipgloss.Color {
	if v > 0 {
		return ColorGreen
	} else if v < 0 {
		return ColorRed
	}
	return ColorText
}
