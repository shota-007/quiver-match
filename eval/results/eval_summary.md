| Metric | agent-low | agent-medium | baseline |
|---|---|---|---|
| Runs completed | 11/11 | 11/11 | 11/11 |
| Board type suits skill + waves | 11/11 | 11/11 | 9/11 |
| Volume in reference range | 11/11 | 11/11 | 9/11 |
| Length given in wrong units | 0/11 | 0/11 | 10/11 |
| Dimensions match stated volume (±15%) | 11/11 | 11/11 | 10/11 |
| Uses live forecast | 11/11 | 11/11 | 0/11 |
| Validator found nothing to fix | 11/11 | 11/11 | n/a |
| Warns when spot is above skill | 3/3 | 3/3 | 2/3 |
| Code flags risky trips (go/caution/no-go) | 3/3 | 3/3 | n/a |
| Day-by-day plan complete | 11/11 | 11/11 | n/a |
| Share of reasons citing a number | 0.83 | 0.77 | 0.55 |
| Avg tokens per run | 9953 | 11806 | 409.73 |
| Avg input tokens | 8889.09 | 10133.27 | 149.73 |
| Avg cached input tokens | 3725 | 4648.82 | 0 |
| Avg output tokens | 1063.91 | 1672.73 | 260 |
| Avg latency (s) | 3.46 | 4.32 | 0.23 |

**Repeatability (P6, same input 3 times)**

| Variant | Volumes (L) | Lengths (in) | Volume spread (max-min) |
|---|---|---|---|
| agent-low | [38.7, 38.7, 38.7] | [66.0, 66.0, 66.0] | 0.0 |
| baseline | [37.2, 37.2, 37.2] | [6.4, 6.4, 6.4] | 0.0 |

Note: repeat runs returned identical answers with identical token counts, which suggests the gateway served cached responses for identical requests. Treat this as inconclusive about model variance.

**Per-profile results**

| Profile | Variant | Board | Dims (in) | Volume (L) | Type ok | Volume ok | Dims consistent |
|---|---|---|---|---|---|---|---|
| P1 Beginner, El Porto (spot above level) | agent-low | foam longboard | 96 x 22.5 x 3.25 | 86.3 | True | True | True (implied 86.3) |
| P1 Beginner, El Porto (spot above level) | agent-medium | foam longboard | 96 x 22.5 x 3.25 | 86.3 | True | True | True (implied 86.3) |
| P1 Beginner, El Porto (spot above level) | baseline | Soft-top longboard | 9 x 23 x 3.25 | 78.0 | True | True | True (implied 75.4) |
| P2 Light beginner, Doheny | agent-low | foam longboard | 96 x 21.75 x 3.1875 | 81.8 | True | True | True (implied 81.8) |
| P2 Light beginner, Doheny | agent-medium | foam longboard | 96 x 21.75 x 3.1875 | 81.8 | True | True | True (implied 81.8) |
| P2 Light beginner, Doheny | baseline | Soft-top longboard | 9 x 23 x 3.25 | 78.0 | True | True | True (implied 75.4) |
| P3 Heavy beginner, Waikiki | agent-low | foam longboard | 112 x 24 x 3.75 | 123.9 | True | True | True (implied 123.9) |
| P3 Heavy beginner, Waikiki | agent-medium | foam longboard | 112 x 24 x 3.75 | 123.9 | True | True | True (implied 123.9) |
| P3 Heavy beginner, Waikiki | baseline | foam longboard | 10 x 24 x 3.5 | 99.8 | True | False | False (implied 123.9) |
| P4 Novice, Malibu | agent-low | funboard | 91 x 21.5 x 3.0625 | 58.9 | True | True | True (implied 58.9) |
| P4 Novice, Malibu | agent-medium | funboard | 91 x 21.5 x 3.0625 | 58.9 | True | True | True (implied 58.9) |
| P4 Novice, Malibu | baseline | 8'0" soft-top longboard / mini-malibu | 96 x 23 x 3.25 | 65.2 | True | True | True (implied 67.0) |
| P5 Novice, Biarritz (not in spot DB) | agent-low | funboard | 96 x 22.25 x 3.1875 | 66.9 | True | True | True (implied 66.9) |
| P5 Novice, Biarritz (not in spot DB) | agent-medium | funboard | 96 x 22.25 x 3.1875 | 66.9 | True | True | True (implied 66.9) |
| P5 Novice, Biarritz (not in spot DB) | baseline | Mid-length soft-top | 8 x 22.5 x 3.25 | 72.0 | True | True | True (implied 67.9) |
| P6 Intermediate, El Porto | agent-low | fish | 66 x 21 x 2.75 | 38.7 | True | True | True (implied 38.7) |
| P6 Intermediate, El Porto | agent-medium | fish | 66 x 21 x 2.75 | 38.7 | True | True | True (implied 38.7) |
| P6 Intermediate, El Porto | baseline | performance funboard / everyday hybrid | 6.4 x 20.75 x 2.625 | 37.2 | False | True | True (implied 40.7) |
| P7 Light intermediate, low fitness, Pleasure Point | agent-low | hybrid shortboard | 71 x 19.875 x 2.875 | 36.2 | True | True | True (implied 36.2) |
| P7 Light intermediate, low fitness, Pleasure Point | agent-medium | hybrid shortboard | 71 x 19.875 x 2.875 | 36.2 | True | True | True (implied 36.2) |
| P7 Light intermediate, low fitness, Pleasure Point | baseline | Performance-oriented hybrid shortboard | 6 x 20.5 x 2.625 | 35.5 | True | True | True (implied 34.6) |
| P8 Intermediate, Ocean Beach SF (spot above level) | agent-low | hybrid shortboard | 74 x 19.875 x 2.875 | 37.8 | True | True | True (implied 37.8) |
| P8 Intermediate, Ocean Beach SF (spot above level) | agent-medium | hybrid shortboard | 74 x 19.875 x 2.875 | 37.8 | True | True | True (implied 37.8) |
| P8 Intermediate, Ocean Beach SF (spot above level) | baseline | Versatile performance shortboard (daily driver) | 6.2 x 20.5 x 2.625 | 35.0 | False | True | True (implied 33.9) |
| P9 Advanced, Lower Trestles | agent-low | performance shortboard | 74 x 19.5 x 2.625 | 32.3 | True | True | True (implied 32.3) |
| P9 Advanced, Lower Trestles | agent-medium | performance shortboard | 74 x 19.5 x 2.625 | 32.3 | True | True | True (implied 32.3) |
| P9 Advanced, Lower Trestles | baseline | Performance shortboard (Lower Trestles daily driver) | 5.11 x 18.5 x 2.38 | 27.5 | True | False | True (implied 26.6) |
| P10 Expert, Pipeline | agent-low | step-up | 73 x 18 x 2.3125 | 25.4 | True | True | True (implied 25.4) |
| P10 Expert, Pipeline | agent-medium | step-up | 73 x 18 x 2.3125 | 25.4 | True | True | True (implied 25.4) |
| P10 Expert, Pipeline | baseline | High-performance Pipeline step-up shortboard | 6 x 18.5 x 2.38 | 28.1 | True | True | True (implied 26.5) |
| P11 Beginner, Uluwatu trip (heavy reef) | agent-low | foam longboard | 96 x 22.25 x 3.0625 | 80.4 | True | True | True (implied 80.4) |
| P11 Beginner, Uluwatu trip (heavy reef) | agent-medium | foam longboard | 96 x 22.25 x 3.0625 | 80.4 | True | True | True (implied 80.4) |
| P11 Beginner, Uluwatu trip (heavy reef) | baseline | Soft-top longboard | 9 x 22.5 x 3 | 73.0 | True | True | True (implied 68.1) |
