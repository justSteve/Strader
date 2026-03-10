package ui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
	btable "github.com/evertras/bubble-table/table"
)

const (
	colStrike  = "strike"
	colCallGEX = "callgex"
	colPutGEX  = "putgex"
	colNetGEX  = "netgex"
	colBar     = "bar"
)

// buildGEXTable creates a sortable, navigable bubble-table for GEX data.
func (m Model) buildGEXTable(width int) btable.Model {
	gex := m.data.GEXMatrix

	// Find max absolute value for bar scaling
	maxAbs := 1.0
	for _, v := range gex.NetGEX {
		if a := v; a < 0 {
			a = -a
		}
		if v > maxAbs {
			maxAbs = v
		}
		if -v > maxAbs {
			maxAbs = -v
		}
	}

	colW := (width - 4) / 5
	if colW < 8 {
		colW = 8
	}
	barW := colW + 4 // bar column wider

	columns := []btable.Column{
		btable.NewColumn(colStrike, "Strike", colW).WithStyle(
			lipgloss.NewStyle().Foreground(ColorText).Bold(true)),
		btable.NewColumn(colCallGEX, "Call GEX", colW),
		btable.NewColumn(colPutGEX, "Put GEX", colW),
		btable.NewColumn(colNetGEX, "Net GEX", colW),
		btable.NewColumn(colBar, "Distribution", barW),
	}

	rows := make([]btable.Row, len(gex.Strikes))
	for i := range gex.Strikes {
		barStr := gexBar(gex.NetGEX[i], maxAbs, barW-4)
		rows[i] = btable.NewRow(btable.RowData{
			colStrike:  fmt.Sprintf("%.0f", gex.Strikes[i]),
			colCallGEX: gexCellStyled(gex.CallGEX[i]),
			colPutGEX:  gexCellStyled(gex.PutGEX[i]),
			colNetGEX:  gexCellStyled(gex.NetGEX[i]),
			colBar:     barStr,
		})
	}

	baseStyle := lipgloss.NewStyle().
		Foreground(ColorText).
		Padding(0, 1)

	headerStyle := lipgloss.NewStyle().
		Foreground(ColorBlue).
		Bold(true).
		Padding(0, 1).
		BorderBottom(true).
		BorderStyle(lipgloss.NormalBorder()).
		BorderForeground(ColorOverlay0)

	highlightStyle := lipgloss.NewStyle().
		Background(ColorSurface1).
		Foreground(ColorText).
		Bold(true)

	t := btable.New(columns).
		WithRows(rows).
		WithBaseStyle(baseStyle).
		HeaderStyle(headerStyle).
		HighlightStyle(highlightStyle).
		Focused(true).
		SortByDesc(colNetGEX).
		WithTargetWidth(width - 2)

	return t
}

// gexCellStyled returns a color-coded GEX value string.
func gexCellStyled(v float64) string {
	s := fmt.Sprintf("%+.0f", v)
	if v > 0 {
		return PositiveStyle.Render(s)
	} else if v < 0 {
		return NegativeStyle.Render(s)
	}
	return s
}

// gexBar renders an inline bar chart for a GEX value.
func gexBar(v, maxAbs float64, maxWidth int) string {
	if maxAbs == 0 || maxWidth < 2 {
		return ""
	}
	pct := v / maxAbs
	barLen := int(pct * float64(maxWidth/2))

	var bar string
	if barLen > 0 {
		// Positive: bar extends right from center
		pad := maxWidth/2
		bar = strings.Repeat(" ", pad) + PositiveStyle.Render(strings.Repeat("█", barLen))
	} else if barLen < 0 {
		// Negative: bar extends left from center
		absLen := -barLen
		pad := maxWidth/2 - absLen
		if pad < 0 {
			pad = 0
		}
		bar = strings.Repeat(" ", pad) + NegativeStyle.Render(strings.Repeat("█", absLen))
	} else {
		bar = strings.Repeat(" ", maxWidth/2) + DimStyle.Render("·")
	}
	return bar
}

// renderGEXMatrix renders the GEX table with a title and summary.
func (m Model) renderGEXMatrix(w, h int) string {
	gex := m.data.GEXMatrix

	// Summary line
	totalNet := 0.0
	maxStrike := 0.0
	maxNet := 0.0
	for i, v := range gex.NetGEX {
		totalNet += v
		if v > maxNet {
			maxNet = v
			maxStrike = gex.Strikes[i]
		}
	}

	summary := fmt.Sprintf("  Peak: %s at %.0f  |  Total Net: %s",
		PositiveStyle.Render(fmt.Sprintf("%.0f", maxNet)),
		maxStrike,
		ValueStyle(totalNet).Render(fmt.Sprintf("%+.0f", totalNet)),
	)

	title := TitleStyle.Render("GEX Matrix \u2014 Gamma Exposure by Strike") + "\n"
	title += SubtitleStyle.Render(summary) + "\n\n"

	return title + m.gexTable.View()
}
