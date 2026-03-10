package ui

import (
	"fmt"

	"github.com/charmbracelet/lipgloss"
	btable "github.com/evertras/bubble-table/table"
)

const (
	colStrike  = "strike"
	colCallGEX = "callgex"
	colPutGEX  = "putgex"
	colNetGEX  = "netgex"
)

func (m Model) buildGEXTable(width int) btable.Model {
	gex := m.data.GEXMatrix
	colW := (width - 4) / 4
	if colW < 10 {
		colW = 10
	}

	columns := []btable.Column{
		btable.NewColumn(colStrike, "Strike", colW),
		btable.NewColumn(colCallGEX, "Call GEX", colW),
		btable.NewColumn(colPutGEX, "Put GEX", colW),
		btable.NewColumn(colNetGEX, "Net GEX", colW),
	}

	rows := make([]btable.Row, len(gex.Strikes))
	for i := range gex.Strikes {
		rows[i] = btable.NewRow(btable.RowData{
			colStrike:  fmt.Sprintf("%.0f", gex.Strikes[i]),
			colCallGEX: gexCell(gex.CallGEX[i]),
			colPutGEX:  gexCell(gex.PutGEX[i]),
			colNetGEX:  gexCell(gex.NetGEX[i]),
		})
	}

	baseStyle := lipgloss.NewStyle().
		Foreground(ColorText).
		Padding(0, 1)

	headerStyle := lipgloss.NewStyle().
		Foreground(ColorBlue).
		Bold(true).
		Padding(0, 1)

	t := btable.New(columns).
		WithRows(rows).
		WithBaseStyle(baseStyle).
		HeaderStyle(headerStyle).
		Focused(true).
		SortByDesc(colNetGEX).
		WithTargetWidth(width - 2)

	return t
}

func gexCell(v float64) string {
	s := fmt.Sprintf("%+.0f", v)
	if v > 0 {
		return PositiveStyle.Render(s)
	} else if v < 0 {
		return NegativeStyle.Render(s)
	}
	return s
}

func (m Model) renderGEXMatrix(w, h int) string {
	title := TitleStyle.Render("GEX Matrix \u2014 Gamma Exposure by Strike") + "\n\n"
	return title + m.gexTable.View()
}
