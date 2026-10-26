//! The windows-rs adapter (FR-009): narrow typed operations, no process spawn, no caller-supplied
//! executable path. Every entry point re-checks authorisation, so a caller cannot reach a Win32
//! call without a matching ADR-002 decision and a granted path.

use crate::{authorize, Op, Refusal};
use poweragent_policy::{Capability, Decision};
use std::fs::OpenOptions;
use std::os::windows::fs::OpenOptionsExt;
use std::os::windows::io::AsRawHandle;
use windows::core::HSTRING;
use windows::Win32::Foundation::HANDLE;
use windows::Win32::Storage::FileSystem::{
    GetFileVersionInfoSizeW, GetFileVersionInfoW, GetFinalPathNameByHandleW, VerQueryValueW, FILE_NAME_NORMALIZED, VS_FIXEDFILEINFO,
};

#[derive(Debug, PartialEq, Eq)]
pub enum NativeError {
    Refused(Refusal),
    NotNativeOp,
    Os(String),
}

/// Run one native operation. Only `Op::NativeFileVersion` is served here.
pub fn execute(decision: &Decision, op: &Op) -> Result<String, NativeError> {
    authorize(decision, op).map_err(NativeError::Refused)?; // lexical gate: cheap, but NOT sufficient on its own
    match (op, decision) {
        (Op::NativeFileVersion { path }, Decision::Run { granted, .. }) => file_version(path, granted),
        _ => Err(NativeError::NotNativeOp),
    }
}

/// Strip the `\\?\` / `\\?\UNC\` prefix Windows adds to final paths and normalise for comparison.
fn plain(p: &str) -> String {
    let p = p.strip_prefix(r"\\?\UNC\").map(|r| format!(r"\\{r}")).unwrap_or_else(|| p.strip_prefix(r"\\?\").unwrap_or(p).to_string());
    p.replace('/', "\\").trim_end_matches('\\').to_lowercase()
}

fn within(root: &str, target: &str) -> bool {
    target == root || target.starts_with(&format!("{root}\\"))
}

/// The real, fully resolved location of the file behind an open handle (junctions, symbolic links and every other
/// reparse point already followed).
fn final_path_of(file: &std::fs::File) -> Result<String, NativeError> {
    let h = HANDLE(file.as_raw_handle());
    let mut buf = vec![0u16; 1024];
    // SAFETY: `h` is a valid open handle owned by `file`, which outlives the call; `buf` is a valid writable slice.
    let n = unsafe { GetFinalPathNameByHandleW(h, &mut buf, FILE_NAME_NORMALIZED) } as usize;
    if n == 0 || n > buf.len() {
        return Err(NativeError::Os(format!("cannot resolve the final path: {}", windows::core::Error::from_thread())));
    }
    Ok(String::from_utf16_lossy(&buf[..n]))
}

/// `major.minor.build.revision` of a file's fixed version resource.
///
/// Authorisation is checked against what the OS actually resolves, not the text of the path: the file is opened (so
/// any junction or symbolic link in the path is followed), its final path is read back from the handle, and that is
/// compared with the *canonical* form of each granted root. The version API is then called on that resolved path
/// while the handle stays open with `FILE_SHARE_READ` only, so the file cannot be deleted or renamed, nor its parent
/// directories replaced, between the check and the use.
fn file_version(path: &str, granted: &[Capability]) -> Result<String, NativeError> {
    const FILE_SHARE_READ: u32 = 1;
    let file = OpenOptions::new()
        .read(true)
        .share_mode(FILE_SHARE_READ)
        .open(path.replace('/', "\\"))
        .map_err(|e| NativeError::Os(format!("cannot open {path}: {e}")))?;
    let real = final_path_of(&file)?;
    let real_plain = plain(&real);
    let inside = granted.iter().any(|c| match c {
        Capability::FsRead { path: root } => std::fs::canonicalize(root.replace('/', "\\"))
            .map(|r| within(&plain(&r.to_string_lossy()), &real_plain))
            .unwrap_or(false),
        _ => false,
    });
    if !inside {
        return Err(NativeError::Refused(Refusal::PathNotGranted(format!("{path} resolves to {real}"))));
    }
    let wide = HSTRING::from(real.strip_prefix(r"\\?\").unwrap_or(&real));
    // SAFETY: `wide` outlives the calls; the buffer is sized by the API itself; the VS_FIXEDFILEINFO
    // pointer returned by VerQueryValueW points into `buf` and is only read while `buf` is alive.
    unsafe {
        let size = GetFileVersionInfoSizeW(&wide, None);
        if size == 0 {
            return Err(NativeError::Os(format!("no version resource: {}", windows::core::Error::from_thread())));
        }
        let mut buf = vec![0u8; size as usize];
        GetFileVersionInfoW(&wide, None, size, buf.as_mut_ptr().cast()).map_err(|e| NativeError::Os(e.to_string()))?;
        let mut p: *mut core::ffi::c_void = core::ptr::null_mut();
        let mut len = 0u32;
        let ok = VerQueryValueW(buf.as_ptr().cast(), &HSTRING::from("\\"), &mut p, &mut len);
        if !ok.as_bool() || p.is_null() || (len as usize) < core::mem::size_of::<VS_FIXEDFILEINFO>() {
            return Err(NativeError::Os("no fixed file info".into()));
        }
        let info = &*(p as *const VS_FIXEDFILEINFO);
        drop(file); // released only after the version resource has been read
        Ok(format!(
            "{}.{}.{}.{}",
            info.dwFileVersionMS >> 16,
            info.dwFileVersionMS & 0xffff,
            info.dwFileVersionLS >> 16,
            info.dwFileVersionLS & 0xffff
        ))
    }
}
