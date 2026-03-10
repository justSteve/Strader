// Package data provides types and loading for butterfly spread sample data.
package data

import (
	"encoding/json"
	"os"
)

// ButterflyData is the top-level structure of butterfly-sample.json.
type ButterflyData struct {
	Underlying   Underlying   `json:"underlying"`
	Strategy     Strategy     `json:"strategy"`
	PayoffCurve  PayoffCurve  `json:"payoffCurve"`
	PayoffByDTE  PayoffByDTE  `json:"payoffByDTE"`
	GreeksByStrike GreeksByStrike `json:"greeksByStrike"`
	GEXMatrix    GEXMatrix    `json:"gexMatrix"`
}

type Underlying struct {
	Symbol    string  `json:"symbol"`
	Price     float64 `json:"price"`
	Change    float64 `json:"change"`
	ChangePct float64 `json:"changePct"`
	IV30      float64 `json:"iv30"`
	IV60      float64 `json:"iv60"`
}

type Strategy struct {
	Name       string  `json:"name"`
	Type       string  `json:"type"`
	Variant    string  `json:"variant"`
	Expiration string  `json:"expiration"`
	DTE        int     `json:"dte"`
	NetDebit   float64 `json:"netDebit"`
	MaxProfit  float64 `json:"maxProfit"`
	MaxLoss    float64 `json:"maxLoss"`
	Breakevens []float64 `json:"breakevens"`
	Legs       []Leg   `json:"legs"`
	Aggregate  Greeks  `json:"aggregate"`
}

type Leg struct {
	Strike  float64 `json:"strike"`
	Type    string  `json:"type"`
	Side    string  `json:"side"`
	Qty     int     `json:"qty"`
	Premium float64 `json:"premium"`
	IV      float64 `json:"iv"`
	Greeks  Greeks  `json:"greeks"`
}

type Greeks struct {
	Delta float64 `json:"delta"`
	Gamma float64 `json:"gamma"`
	Theta float64 `json:"theta"`
	Vega  float64 `json:"vega"`
}

type PayoffCurve struct {
	Description string        `json:"description"`
	Points      []PayoffPoint `json:"points"`
}

type PayoffPoint struct {
	Price float64 `json:"price"`
	PnL   float64 `json:"pnl"`
}

type PayoffByDTE struct {
	Description string                       `json:"description"`
	Curves      map[string][]PayoffPoint     `json:"curves"`
}

type GreeksByStrike struct {
	Description string    `json:"description"`
	Strikes     []float64 `json:"strikes"`
	Delta       []float64 `json:"delta"`
	Gamma       []float64 `json:"gamma"`
	Theta       []float64 `json:"theta"`
	Vega        []float64 `json:"vega"`
}

type GEXMatrix struct {
	Description string    `json:"description"`
	Strikes     []float64 `json:"strikes"`
	CallGEX     []float64 `json:"callGex"`
	PutGEX      []float64 `json:"putGex"`
	NetGEX      []float64 `json:"netGex"`
}

// Load reads and parses the butterfly sample data from a JSON file.
func Load(path string) (*ButterflyData, error) {
	f, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var d ButterflyData
	if err := json.Unmarshal(f, &d); err != nil {
		return nil, err
	}
	return &d, nil
}
