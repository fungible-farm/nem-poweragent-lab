#[derive(Clone, Copy, Debug, clap::ValueEnum, serde::Deserialize, schemars::JsonSchema)]
#[serde(rename_all = "kebab-case")]
pub enum Track {
    DigitalThread,
    Grid,
    Pipeline,
}

impl Track {
    /// The kebab-case slug used both for artifact filenames (render.rs) and in
    /// user-facing messages (check.rs's empty-instances error).
    pub fn slug(self) -> &'static str {
        match self {
            Track::DigitalThread => "digital-thread",
            Track::Grid => "grid",
            Track::Pipeline => "pipeline",
        }
    }
}
