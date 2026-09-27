//! Opt-in Linux Secret Service probe used by the release artifact smoke.
//!
//! This example is never started by the desktop application.  A Linux CI job
//! runs it inside an explicit `dbus-run-session` with a temporary keyring
//! daemon.  The account is process-specific, the value is never printed, and
//! a successful run always deletes the credential before returning.

#[cfg(target_os = "linux")]
mod linux {
    use keyring::Error;
    use std::time::{SystemTime, UNIX_EPOCH};

    const SERVICE_PREFIX: &str = "com.agent-audit.desktop.f055-probe";

    fn run() -> Result<(), &'static str> {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|_| "nonce")?
            .as_nanos();
        let service = format!("{SERVICE_PREFIX}.{}", std::process::id());
        let account = format!("probe-{nonce}");
        let secret = format!("not-for-output-{nonce}");
        let entry = keyring::Entry::new(&service, &account).map_err(|_| "entry")?;

        let mut stored = false;
        let result = (|| {
            entry.set_password(&secret).map_err(|_| "store")?;
            stored = true;

            let value = entry.get_password().map_err(|_| "read")?;
            if value != secret {
                return Err("mismatch");
            }

            entry.delete_credential().map_err(|_| "delete")?;
            stored = false;
            match entry.get_password() {
                Err(Error::NoEntry) => Ok(()),
                _ => Err("missing"),
            }
        })();

        if stored {
            let _ = entry.delete_credential();
        }
        result
    }

    pub fn main() -> i32 {
        match run() {
            Ok(()) => {
                println!("secret_service_probe=passed");
                0
            }
            Err(stage) => {
                eprintln!("secret_service_probe=failed stage={stage}");
                1
            }
        }
    }
}

#[cfg(target_os = "linux")]
fn main() {
    std::process::exit(linux::main());
}

#[cfg(not(target_os = "linux"))]
fn main() {
    eprintln!("secret_service_probe=not_supported");
    std::process::exit(2);
}
