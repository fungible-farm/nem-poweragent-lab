//! The windows-rs adapter (FR-009): narrow typed operations, no process spawn, no caller-supplied
//! executable path. Every entry point re-checks authorisation, so a caller cannot reach a Win32
//! call without a matching ADR-002 decision and a granted path.

use crate::{authorize, Op, Refusal};
use poweragent_policy::Decision;
use windows::core::HSTRING;
use windows::Win32::Storage::FileSystem::{GetFileVersionInfoSizeW, GetFileVersionInfoW, VerQueryValueW, VS_FIXEDFILEINFO};

#[derive(Debug, PartialEq, Eq)]
pub enum NativeError {
    Refused(Refusal),
    NotNativeOp,
    Os(String),
}

/// Run one native operation. Only `Op::NativeFileVersion` is served here.
pub fn execute(decision: &Decision, op: &Op) -> Result<String, NativeError> {
    authorize(decision, op).map_err(NativeError::Refused)?;
    match op {
        Op::NativeFileVersion { path } => file_version(path),
        _ => Err(NativeError::NotNativeOp),
    }
}

/// `major.minor.build.revision` of a file's fixed version resource.
fn file_version(path: &str) -> Result<String, NativeError> {
    let wide = HSTRING::from(path.replace('/', "\\"));
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
        Ok(format!(
            "{}.{}.{}.{}",
            info.dwFileVersionMS >> 16,
            info.dwFileVersionMS & 0xffff,
            info.dwFileVersionLS >> 16,
            info.dwFileVersionLS & 0xffff
        ))
    }
}
