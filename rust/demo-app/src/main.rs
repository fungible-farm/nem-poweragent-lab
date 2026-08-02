//! Launch stub: builds the wasm cdylib and launches the Dioxus app.
fn main() {
    dioxus::launch(demo_app::App);
}
