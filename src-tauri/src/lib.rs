//! Stage Finder Tauri core.
//!
//! Deliberately minimal (see docs/ARCHITECTURE.md): window lifecycle, sidecar
//! spawn + supervision, per-launch session token generation, and the two
//! commands that expose the backend URL and session token to the renderer.
//! No business logic lives here.

use std::io;
use std::net::{TcpListener, TcpStream};
use std::path::Path;
use std::process::{Child, Command};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use rand::distributions::Alphanumeric;
use rand::Rng;
use tauri::{Manager, RunEvent, State};

/// Shared sidecar handle. `child` is `None` once the process has been killed
/// on app exit (the supervisor then stops respawning it).
pub struct SidecarState {
    pub url: String,
    pub token: String,
    child: Arc<Mutex<Option<Child>>>,
}

fn generate_session_token() -> String {
    rand::thread_rng()
        .sample_iter(&Alphanumeric)
        .take(48)
        .map(char::from)
        .collect()
}

fn allocate_port() -> io::Result<u16> {
    let listener = TcpListener::bind(("127.0.0.1", 0))?;
    Ok(listener.local_addr()?.port())
}

/// Project root, i.e. the parent of this crate's manifest directory.
/// Only used for the dev-mode spawn; release builds use the packaged sidecar
/// (feature pkg-016).
fn project_root() -> &'static Path {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("src-tauri must live inside the project root")
}

fn spawn_backend(port: u16, token: &str) -> io::Result<Child> {
    if cfg!(debug_assertions) {
        // Dev: run the sidecar from the checkout via uv.
        let backend_dir = project_root().join("backend");
        Command::new("uv")
            .arg("run")
            .arg("python")
            .arg("-m")
            .arg("app")
            .current_dir(&backend_dir)
            .env("STAGE_FINDER_PORT", port.to_string())
            .env("STAGE_FINDER_SESSION_TOKEN", token)
            .spawn()
    } else {
        // Release: run the bundled PyInstaller sidecar (externalBin),
        // installed next to the main executable without the target triple.
        // Windows requires the explicit .exe suffix: CreateProcess does
        // not append it when the program string contains a path.
        let exe_dir = std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|d| d.to_path_buf()))
            .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "cannot resolve exe dir"))?;
        let sidecar_name = if cfg!(windows) {
            "stage-finder-backend.exe"
        } else {
            "stage-finder-backend"
        };
        Command::new(exe_dir.join(sidecar_name))
            .env("STAGE_FINDER_PORT", port.to_string())
            .env("STAGE_FINDER_SESSION_TOKEN", token)
            .spawn()
    }
}

fn wait_for_backend(port: u16, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    false
}

/// Health-check the sidecar, then restart it if it ever exits unexpectedly.
fn supervise(child_slot: Arc<Mutex<Option<Child>>>, port: u16, token: String) {
    std::thread::spawn(move || {
        if wait_for_backend(port, Duration::from_secs(30)) {
            eprintln!("stage-finder: sidecar healthy on 127.0.0.1:{port}");
        } else {
            eprintln!("stage-finder: sidecar did not become healthy within 30s");
        }
        loop {
            std::thread::sleep(Duration::from_secs(2));
            let mut slot = child_slot.lock().expect("sidecar lock poisoned");
            let exited = match slot.as_mut() {
                Some(child) => matches!(child.try_wait(), Ok(Some(_))),
                None => false,
            };
            if exited {
                eprintln!("stage-finder: sidecar exited; restarting");
                match spawn_backend(port, &token) {
                    Ok(child) => *slot = Some(child),
                    Err(error) => {
                        eprintln!("stage-finder: sidecar restart failed: {error}");
                    }
                }
            }
        }
    });
}

#[tauri::command]
fn get_backend_url(state: State<SidecarState>) -> String {
    state.url.clone()
}

#[tauri::command]
fn get_session_token(state: State<SidecarState>) -> String {
    state.token.clone()
}

pub fn run() {
    let token = generate_session_token();
    let port = allocate_port().expect("failed to allocate a free port");
    let url = format!("http://127.0.0.1:{port}");
    let child = spawn_backend(port, &token).expect("failed to spawn the sidecar backend");
    let child_slot: Arc<Mutex<Option<Child>>> = Arc::new(Mutex::new(Some(child)));

    supervise(Arc::clone(&child_slot), port, token.clone());

    let sidecar = SidecarState {
        url,
        token,
        child: child_slot,
    };

    tauri::Builder::default()
        .manage(sidecar)
        .invoke_handler(tauri::generate_handler![get_backend_url, get_session_token])
        .build(tauri::generate_context!())
        .expect("error while building the tauri application")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                if let Some(mut child) = app.state::<SidecarState>().child.lock().unwrap().take() {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        });
}
