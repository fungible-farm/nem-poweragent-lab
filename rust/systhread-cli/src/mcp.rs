/// Task 5 replaces this body with a real rmcp `ServerHandler` + `stdio()` transport serve loop.
/// Kept as its own async fn (not inlined into main) so main.rs's dispatch stays a one-line call
/// regardless of how much the real server implementation grows.
pub async fn run_stdio() -> Result<(), String> {
    std::future::pending::<()>().await;
    Ok(())
}
