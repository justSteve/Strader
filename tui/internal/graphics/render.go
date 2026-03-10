// Package graphics provides bitmap rendering for the TUI ↔ image toggle.
// Two renderers: chafa (universal, character-based) and Kitty (high-res, terminal-dependent).
// Use RenderImage() which auto-detects the best available renderer.
package graphics

import (
	"encoding/base64"
	"fmt"
	"os"
	"os/exec"
	"strings"
)

// Renderer selects the image rendering backend.
type Renderer int

const (
	RendererChafa Renderer = iota
	RendererKitty
)

// DetectRenderer checks terminal capabilities and returns the best renderer.
func DetectRenderer() Renderer {
	term := os.Getenv("TERM_PROGRAM")
	switch term {
	case "WezTerm", "kitty", "ghostty":
		return RendererKitty
	}
	if os.Getenv("KITTY_WINDOW_ID") != "" {
		return RendererKitty
	}
	return RendererChafa
}

// RenderImage picks the best available renderer and returns a string
// suitable for embedding directly in a Bubble Tea View().
// cols/rows should match the panel dimensions in character cells.
func RenderImage(imagePath string, cols, rows int) (string, error) {
	switch DetectRenderer() {
	case RendererKitty:
		return renderKitty(imagePath, cols, rows)
	default:
		return renderChafa(imagePath, cols, rows)
	}
}

// ClearImage returns escape sequences to remove a Kitty image.
// For chafa, returns empty string (just re-render TUI content).
func ClearImage() string {
	if DetectRenderer() == RendererKitty {
		return deleteKitty()
	}
	return ""
}

// --- chafa renderer (Tier 1: works everywhere) ---

func renderChafa(imagePath string, cols, rows int) (string, error) {
	args := []string{
		imagePath,
		fmt.Sprintf("--size=%dx%d", cols, rows),
		"--format=symbols",
		"--color-space=din99d",
		"--dither=diffusion",
		"--symbols=block+border+space+extra",
	}
	cmd := exec.Command("chafa", args...)
	out, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("chafa render failed: %w (is chafa installed?)", err)
	}
	return strings.TrimRight(string(out), "\n"), nil
}

// --- Kitty graphics protocol renderer (Tier 2: needs WezTerm/Kitty/Ghostty) ---

func renderKitty(imagePath string, cols, rows int) (string, error) {
	data, err := os.ReadFile(imagePath)
	if err != nil {
		return "", fmt.Errorf("read image: %w", err)
	}
	encoded := base64.StdEncoding.EncodeToString(data)
	inTmux := os.Getenv("TMUX") != ""

	var sb strings.Builder
	chunks := splitString(encoded, 4096)

	for i, chunk := range chunks {
		more := 1
		if i == len(chunks)-1 {
			more = 0
		}

		var payload string
		if i == 0 {
			// First chunk: transmit + display, PNG format, specify cell dimensions
			payload = fmt.Sprintf("\x1b_Gf=100,a=T,c=%d,r=%d,q=2,m=%d;%s\x1b\\",
				cols, rows, more, chunk)
		} else {
			// Continuation chunks
			payload = fmt.Sprintf("\x1b_Gm=%d;%s\x1b\\", more, chunk)
		}

		if inTmux {
			payload = tmuxPassthrough(payload)
		}
		sb.WriteString(payload)
	}
	return sb.String(), nil
}

func deleteKitty() string {
	cmd := "\x1b_Ga=d,q=2;\x1b\\"
	if os.Getenv("TMUX") != "" {
		cmd = tmuxPassthrough(cmd)
	}
	return cmd
}

// tmuxPassthrough wraps escape sequences in DCS passthrough for tmux 3.4+.
// Prerequisite: operator must run `tmux set -g allow-passthrough on`
func tmuxPassthrough(seq string) string {
	escaped := strings.ReplaceAll(seq, "\x1b", "\x1b\x1b")
	return fmt.Sprintf("\x1bPtmux;%s\x1b\\", escaped)
}

func splitString(s string, size int) []string {
	var chunks []string
	for len(s) > 0 {
		end := size
		if end > len(s) {
			end = len(s)
		}
		chunks = append(chunks, s[:end])
		s = s[end:]
	}
	return chunks
}
