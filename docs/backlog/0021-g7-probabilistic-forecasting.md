# 0021 — G7: probabilistic forecasting

- **Status:** open. Real-data evaluation is blocked by G5's access decision. [PRD-0010](../prd/0010-powercoder-physics-grounded-engineering-agent.md) G7,
  priority B4. Depends on G2 and G5.
- **Requirements:** PC-REQ-040–044.

## Deliverables
- **Command layer:** the forecasting DSL, compiled into G1's IR.
- **Model registry:** StatsForecast, LightGBM, Chronos and TimesFM, plus physical models. Each
  licence is recorded at adoption (PSCADOSSE; Chronos and TimesFM are Apache-2.0).
- **Forecasting:** weather-conditioned, with leakage-free hindcasting.
- **Evaluation:** probabilistic, using pinball loss, MAE, WAPE, calibration, and skill against
  persistence and authoritative baselines.
- **Physical scenarios:** forecast-driven AC power-flow scenarios.

## Targets
1. Regional demand.
2. Wind and solar.
3. Voltage and constraint risk.

## Exit criteria
- Every forecast carries its model identity, issue time and valid time.
- Injected future-data leakage is rejected.
- Forecasts are calibrated, and skill is measured on unseen periods.
- Aggregated renewables keep their spatial correlation.
- Forecast-driven AC runs are validated, and infeasible scenarios are reported, not dropped.

## Cheapest first step
The hindcast harness and leakage tests on a public demand series, until NEM access is decided. The
harness, not the data, is the asset.
