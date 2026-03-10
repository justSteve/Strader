package main

import (
	"fmt"
	"os"
	"path/filepath"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gastown/strader-flytui/internal/data"
	"github.com/gastown/strader-flytui/internal/ui"
)

func main() {
	dataDir := findDataDir()

	d, err := data.Load(filepath.Join(dataDir, "butterfly-sample.json"))
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error loading data: %v\n", err)
		os.Exit(1)
	}

	imagePath := filepath.Join(dataDir, "tv-screenshot.png")
	m := ui.NewModel(d, imagePath)

	p := tea.NewProgram(m, tea.WithAltScreen(), tea.WithMouseCellMotion())
	if _, err := p.Run(); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}

func findDataDir() string {
	candidates := []string{
		"tui/data",
		"data",
		"../data",
		"../../data",
	}
	for _, c := range candidates {
		if _, err := os.Stat(filepath.Join(c, "butterfly-sample.json")); err == nil {
			return c
		}
	}
	return "tui/data"
}
