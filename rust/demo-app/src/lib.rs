//! Dioxus (Vue/React-in-Rust) power-simulation app.
//!
//! Loads the real Lab 5 fault transient log from the web server, computes the
//! C37.118 phasors / positive sequence / SCADA via the `phase-model` WASM
//! crate (the simulation runs entirely client-side), and animates the three
//! feeds on a canvas — the "dynamic, framework-based" replacement for static
//! HTML (docs/PSCADOSSE.md). Built with `trunk` (`just rust-web`).
#![allow(non_snake_case)]

use std::sync::Arc;

use dioxus::prelude::*;
use gloo_timers::future::TimeoutFuture;
use phase_model::ThreePhaseWaveform;
use wasm_bindgen::JsCast;
use wasm_bindgen::JsValue;
use web_sys::{CanvasRenderingContext2d, HtmlCanvasElement};

const LOG: &str = "/labs/05-spartan-chaosnet-transient-stream/dpsim_transient_log.json";
const PHASOR_RATE_HZ: u32 = 100;

const COLOR_A: &str = "#2a78d6";
const COLOR_B: &str = "#4e9a63";
const COLOR_C: &str = "#c07a2b";
const COLOR_FAULT: &str = "#e34948";
const COLOR_INK: &str = "#898781";

fn js(v: &str) -> JsValue {
    JsValue::from_str(v)
}

fn set_dash(ctx: &CanvasRenderingContext2d, vals: &[f64]) {
    let arr = js_sys::Array::new();
    for v in vals {
        arr.push(&JsValue::from_f64(*v));
    }
    ctx.set_line_dash(&arr.into()).ok();
}

struct Model {
    times: Vec<f64>,
    va: Vec<f64>,
    vb: Vec<f64>,
    vc: Vec<f64>,
    ft: Vec<f64>,
    ma: Vec<f64>,
    mb: Vec<f64>,
    mc: Vec<f64>,
    v1: Vec<f64>,
    trigger: f64,
    clear: f64,
    rms_kv: f64,
    ymax_kv: f64,
}

impl Model {
    fn from_log_json(text: &str) -> Option<Arc<Self>> {
        let wave = ThreePhaseWaveform::from_log_json(text).ok()?;
        let (ft, ph) = wave.phasor_frames(PHASOR_RATE_HZ);
        let v1 = ThreePhaseWaveform::positive_sequence(&ph);
        let ma: Vec<f64> = ph[0].iter().map(|c| c.abs()).collect();
        let mb: Vec<f64> = ph[1].iter().map(|c| c.abs()).collect();
        let mc: Vec<f64> = ph[2].iter().map(|c| c.abs()).collect();
        let v1m: Vec<f64> = v1.iter().map(|c| c.abs()).collect();
        let rms = (wave.va.iter().map(|v| v * v).sum::<f64>() / wave.va.len() as f64).sqrt();
        let ymax = wave
            .va
            .iter()
            .chain(&wave.vb)
            .chain(&wave.vc)
            .fold(0.0f64, |m, v| m.max(v.abs()))
            / 1000.0;
        Some(Arc::new(Self {
            times: wave.times,
            va: wave.va,
            vb: wave.vb,
            vc: wave.vc,
            ft,
            ma,
            mb,
            mc,
            v1: v1m,
            trigger: 0.2,
            clear: 0.35,
            rms_kv: rms / 1000.0,
            ymax_kv: ymax.max(1.0),
        }))
    }
}

fn canvas() -> Option<(HtmlCanvasElement, CanvasRenderingContext2d)> {
    let doc = web_sys::window()?.document()?;
    let canvas = doc.get_element_by_id("cv")?.dyn_into::<HtmlCanvasElement>().ok()?;
    let ctx = canvas.get_context("2d").ok()??.dyn_into::<CanvasRenderingContext2d>().ok()?;
    Some((canvas, ctx))
}

fn draw(ctx: &CanvasRenderingContext2d, m: &Model, now: f64, scope: bool) {
    let w = 980.0;
    let h = 820.0;
    ctx.set_fill_style(&js("#101418"));
    ctx.fill_rect(0.0, 0.0, w, h);

    let tmax = m.times[m.times.len() - 1];
    let x0 = 40.0;
    let xw = w - 56.0;
    let x_of = |t: f64| x0 + (t / tmax) * xw;

    // panels: (y0, height, title)
    let panels = [
        (0.0, 300.0, "RAW 5 kHz — va / vb / vc"),
        (330.0, 220.0, "C37.118 @ 100 Hz — |Va| |Vb| |Vc| + |V1|"),
        (590.0, 150.0, "SCADA @ 4 s — one RMS value (the event is invisible here)"),
    ];

    for (py, ph, title) in panels {
        ctx.set_stroke_style(&js("#232a33"));
        ctx.set_line_width(1.0);
        ctx.stroke_rect(8.0, py, w - 16.0, ph);
        ctx.set_fill_style(&js("#889"));
        ctx.set_font("11px sans-serif");
        ctx.set_text_align("left");
        ctx.set_text_baseline("top");
        ctx.fill_text(title, 14.0, py + 4.0).ok();
        // fault shading
        ctx.set_fill_style(&js("rgba(227,73,72,0.12)"));
        ctx.fill_rect(x_of(m.trigger), py + 16.0, x_of(m.clear) - x_of(m.trigger), ph - 16.0);
    }

    // Panel 1: raw waveform (full or scope-windowed)
    let (tlo, thi) = if scope {
        ((now - 0.08).max(0.0), now.max(0.001))
    } else {
        (0.0, tmax)
    };
    let xs = |t: f64| x0 + ((t - tlo) / (thi - tlo)) * xw;
    let ys = |v: f64| 150.0 - (v / 1000.0) / m.ymax_kv * 140.0;
    for (series, color) in [(&m.va, COLOR_A), (&m.vb, COLOR_B), (&m.vc, COLOR_C)] {
        ctx.set_stroke_style(&js(color));
        ctx.set_line_width(1.2);
        ctx.begin_path();
        let mut first = true;
        for (i, t) in m.times.iter().enumerate() {
            if *t < tlo || *t > thi {
                continue;
            }
            let (x, y) = (xs(*t), ys(series[i]));
            if first {
                ctx.move_to(x, y);
                first = false;
            } else {
                ctx.line_to(x, y);
            }
        }
        ctx.stroke();
    }

    // Panel 2: phasor magnitudes + positive sequence
    let yf = |v: f64| 330.0 + 110.0 - (v / 1000.0) / m.ymax_kv * 110.0;
    for (series, color) in [(&m.ma, COLOR_A), (&m.mb, COLOR_B), (&m.mc, COLOR_C)] {
        ctx.set_stroke_style(&js(color));
        ctx.set_line_width(1.5);
        ctx.begin_path();
        for (i, t) in m.ft.iter().enumerate() {
            let (x, y) = (x_of(*t), yf(series[i]));
            if i == 0 {
                ctx.move_to(x, y);
            } else {
                ctx.line_to(x, y);
            }
        }
        ctx.stroke();
    }
    ctx.set_stroke_style(&js(COLOR_INK));
    ctx.set_line_width(1.5);
    set_dash(&ctx, &[5.0, 4.0]);
    ctx.begin_path();
    for (i, t) in m.ft.iter().enumerate() {
        let (x, y) = (x_of(*t), yf(m.v1[i]));
        if i == 0 {
            ctx.move_to(x, y);
        } else {
            ctx.line_to(x, y);
        }
    }
    ctx.stroke();
    set_dash(&ctx, &[]);

    // Panel 3: SCADA (flat, single value)
    let yrms = 590.0 + 75.0 - m.rms_kv / m.ymax_kv * 75.0;
    ctx.set_stroke_style(&js(COLOR_FAULT));
    ctx.set_line_width(2.0);
    ctx.begin_path();
    ctx.move_to(x0, yrms);
    ctx.line_to(w - 16.0, yrms);
    ctx.stroke();

    // cursor + status
    let cx = x_of(now);
    ctx.set_stroke_style(&js(COLOR_INK));
    set_dash(&ctx, &[3.0, 3.0]);
    for (y, hh) in [(0.0, 300.0), (330.0, 220.0), (590.0, 150.0)] {
        ctx.begin_path();
        ctx.move_to(cx, y + 16.0);
        ctx.line_to(cx, y + hh);
        ctx.stroke();
    }
    set_dash(&ctx, &[]);
}

pub fn App() -> Element {
    let mut model = use_signal(|| None::<Arc<Model>>);
    let mut now = use_signal(|| 0.0f64);
    let mut playing = use_signal(|| true);
    let mut speed = use_signal(|| 1.0f64);
    let mut scope = use_signal(|| false);

    // fetch the real log once
    use_effect(move || {
        spawn(async move {
            let resp = gloo_net::http::Request::get(LOG).send().await.ok();
            let text = match resp {
                Some(r) => r.text().await.ok(),
                None => None,
            };
            if let Some(t) = text {
                model.set(Model::from_log_json(&t));
            }
        });
    });

    // advance the replay cursor
    use_effect(move || {
        if !playing() {
            return;
        }
        spawn(async move {
            loop {
                TimeoutFuture::new(30).await;
                if !playing() {
                    break;
                }
                let n = now() + 0.002 * speed();
                if n > 0.56 {
                    now.set(0.56);
                    playing.set(false);
                    break;
                }
                now.set(n);
            }
        });
    });

    // redraw whenever data or cursor changes
    use_effect(move || {
        if let Some(m) = model() {
            if let Some((_, ctx)) = canvas() {
                draw(&ctx, &m, now(), scope());
            }
        }
    });

    let play_label = if playing() { "Pause" } else { "Play" };
    let scope_label = if scope() { "Scope: on" } else { "Scope: off" };
    let status = model.with(|m| match m {
        Some(_) => format!("t = {:.3} s — phasor frames computed in-WASM", now()),
        None => "loading the real DPsim log from the web server…".to_string(),
    });

    rsx! {
        div {
            style: "display:flex; gap:18px; flex-wrap:wrap;",
            canvas { id: "cv", width: "980", height: "820" }
            div {
                style: "display:flex; flex-direction:column; gap:10px; min-width:240px;",
                div {
                    button {
                        onclick: move |_| playing.set(!playing()),
                        "{play_label}"
                    }
                    button { onclick: move |_| { now.set(0.0); playing.set(true); }, "Reset" }
                    button {
                        onclick: move |_| scope.set(!scope()),
                        "{scope_label}"
                    }
                }
                div { style: "font-family:ui-monospace,monospace;font-size:12px;color:#898781;", "{status}" }
                div {
                    style: "font-size:12px;color:#898781;line-height:1.7;",
                    "va (blue) · vb (green) · vc (amber) · |V1| pos-seq (dashed). "
                    "Red band = the 0.2–0.35 s line-to-ground fault. The SCADA feed "
                    "never moves (one 4 s interval holds the whole event)."
                }
            }
        }
    }
}

fn main() {
    dioxus::launch(App);
}
